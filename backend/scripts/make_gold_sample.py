#!/usr/bin/env python
"""Sorteia 210 passos (semente fixa) p/ rotulação manual → results/gold/gold_steps_cego.csv (+ gold_steps_previsoes.csv, que NÃO deve ser aberto).

70 por dataset (SWE-rebench, SWE-smith, CodeTraceBench; no CTB proporcional ao nº de passos de cada agente);
exclui `harness_protocol` e passos `message` (trivialmente `think`). A coluna `gold_category` do CSV cego fica VAZIA para preenchimento manual; o cego não traz rótulo previsto, label_source, confiança nem rótulo do LLM.
O rótulo previsto vem só das regras (sem LLM), para que a avaliação seja reproduzível.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.base import UnsupportedArtifact  # noqa: E402
from app.adapters.detect import parse_any  # noqa: E402
from app.labeling import label_trajectory  # noqa: E402

SEED, PER_DATASET = 20251119, 70
SAMPLES, CTB = ROOT / "data" / "samples", ROOT / "data" / "raw" / "codetracebench"
FOOTER = re.compile(r"\n?\[(?:The command completed[^\]]*|Current working directory:[^\]]*|Python interpreter:[^\]]*|Command finished[^\]]*)\]")


def short(s: str | None, n: int) -> str:
    s = re.sub(r"\s+", " ", FOOTER.sub("", s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def trajectories():
    for p in sorted((SAMPLES / "swe-rebench").glob("chat*.json")):
        yield "SWE-rebench", p
    for sp in ("tool", "xml", "ticks"):
        for p in sorted((SAMPLES / "swe-smith" / sp).glob("*.json")):
            yield "SWE-smith", p
    for tid in json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text()):
        yield "CodeTraceBench", CTB / "bench_artifacts" / "full" / f"{tid}.tar.zst"


def _eligible(t, s) -> bool:
    return not (s.subcategory == "harness_protocol" or s.action.tool == "message")


def holdout(n: int, seed: int) -> None:
    """Gold held-out: n/3 passos por dataset, de trajetórias FORA de data/samples/ (sorteadas direto de data/raw/), ≤ 2 passos por trajetória,
    sem harness_protocol/message. Escreve results/gold/gold_holdout_cego.csv (cego, com duvida/notas vazias) e results/gold_holdout_previsoes.csv
    (fora de gold/). As trajetórias escolhidas (SWE-rebench/SWE-smith) são salvas em data/holdout/ (fora do git) para o evaluate.py poder rodar o LLM."""
    import numpy as np
    import pyarrow.parquet as pq

    per, rng, nrng = n // 3, random.Random(seed), np.random.default_rng(seed)
    used = set()
    for p in list((SAMPLES / "swe-rebench").glob("chat*.json")) + [q for sp in ("tool", "xml", "ticks") for q in (SAMPLES / "swe-smith" / sp).glob("*.json")]:
        o = json.loads(p.read_text())
        used.add(o.get("trajectory_id") or o.get("traj_id"))
    raw = ROOT / "data" / "raw"
    cand: dict[str, list[tuple[str, object]]] = {"SWE-rebench": [], "SWE-smith": [], "CodeTraceBench": []}
    # SWE-rebench: 200 linhas sorteadas no arquivo inteiro, lidas em lotes
    pf = pq.ParquetFile(raw / "swe-rebench" / "trajectories.parquet")
    want = set(nrng.choice(pf.metadata.num_rows, 200, replace=False).tolist())
    cols = ["trajectory_id", "instance_id", "repo", "trajectory", "model_patch", "exit_status", "resolved"]
    pos = 0
    for batch in pf.iter_batches(batch_size=32, columns=cols):
        for j, row in enumerate(batch.to_pylist()):
            if pos + j in want and row["trajectory_id"] not in used:
                cand["SWE-rebench"].append((row["trajectory_id"], row))
        pos += batch.num_rows
    # SWE-smith: ~70 por split
    for split in ("tool", "xml", "ticks"):
        files = sorted((raw / "swe-smith" / "data").glob(f"{split}-*.parquet"))
        for f in files:
            pf = pq.ParquetFile(f)
            want = set(nrng.choice(pf.metadata.num_rows, 70 // len(files) + 1, replace=False).tolist())
            pos = 0
            for batch in pf.iter_batches(batch_size=16):
                for j, row in enumerate(batch.to_pylist()):
                    if pos + j in want and row["traj_id"] not in used:
                        cand["SWE-smith"].append((row["traj_id"], row))
                pos += batch.num_rows
    # CTB: 992 artefatos menos os 60 da amostra
    sample_ids = set(json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text()))
    ids = sorted(p.name.removesuffix(".tar.zst") for p in (CTB / "bench_artifacts" / "full").glob("*.tar.zst") if p.name.removesuffix(".tar.zst") not in sample_ids)
    for tid in rng.sample(ids, 150):
        cand["CodeTraceBench"].append((tid, CTB / "bench_artifacts" / "full" / f"{tid}.tar.zst"))
    hold_dir = ROOT / "data" / "holdout"
    hold_dir.mkdir(parents=True, exist_ok=True)
    rows, ntraj = [], {}
    for ds in ("SWE-rebench", "SWE-smith", "CodeTraceBench"):
        pool = []
        for tid, src in cand[ds]:
            try:
                t = parse_any(src, manifest_dir=CTB) if isinstance(src, Path) else parse_any(src)
            except (UnsupportedArtifact, Exception):  # noqa: BLE001  (artefato ilegível não entra no sorteio)
                continue
            label_trajectory(t)
            ntraj[ds] = ntraj.get(ds, 0) + 1
            for s in t.steps:
                if _eligible(t, s):
                    pool.append((t, s, src))
        rng.shuffle(pool)
        cnt, chosen = Counter(), []
        for t, s, src in pool:
            if len(chosen) == per:
                break
            if cnt[t.id] < 2:
                cnt[t.id] += 1
                chosen.append((t, s, src))
        for t, s, src in chosen:
            if not isinstance(src, Path):
                (hold_dir / f"{t.id}.json").write_text(json.dumps(src, ensure_ascii=False, default=str))
            rows.append(_row(ds, t, s))
    rng.shuffle(rows)
    gold_dir = ROOT / "results" / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    blind_cols = ["id", "dataset", "agent", "traj_id", "idx", "tool", "thought", "action", "observation", "gold_category", "duvida", "notas"]
    with (gold_dir / "gold_holdout_cego.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=blind_cols)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in blind_cols} for r in rows)
    pred_cols = ["id", "dataset", "agent", "traj_id", "idx", "pred_category", "pred_subcategory", "label_source", "confidence"]
    with (ROOT / "results" / "gold_holdout_previsoes.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pred_cols)
        w.writeheader()
        w.writerows({k: r[k] for k in pred_cols} for r in rows)
    print(f"{len(rows)} passos → results/gold/gold_holdout_cego.csv (preencher; salvar como gold_holdout_cego_pedro.csv) e results/gold_holdout_previsoes.csv (não abrir)")
    print("trajetórias parseadas por dataset:", ntraj)
    print(Counter((r["dataset"], r["agent"]) for r in rows))
    print("trajetórias distintas:", len({r["traj_id"] for r in rows}), "| máx. passos/traj:", max(Counter(r["traj_id"] for r in rows).values()))


def _row(ds, t, s) -> dict:
    return {"id": f"{t.id[:36]}~{hashlib.sha1(t.id.encode()).hexdigest()[:6]}#{s.idx}", "dataset": ds, "agent": t.agent, "traj_id": t.id, "idx": s.idx,
            "tool": s.action.tool_native or s.action.tool, "thought": short(s.thought, 200),
            "action": short(s.action.raw or s.action.command, 350), "observation": short(s.observation.content if s.observation else "", 250),
            "pred_category": s.category, "pred_subcategory": s.subcategory or "", "label_source": s.label_source,
            "confidence": s.confidence, "gold_category": ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true", help="gold held-out (trajetórias fora de data/samples/)")
    ap.add_argument("--n", type=int, default=90)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    if a.holdout:
        return holdout(a.n, a.seed)
    pool: dict[str, list[tuple]] = defaultdict(list)
    for ds, p in trajectories():
        try:
            t = parse_any(p, manifest_dir=CTB)
        except UnsupportedArtifact:
            continue
        label_trajectory(t)
        for s in t.steps:
            if s.subcategory == "harness_protocol" or s.action.tool == "message":  # message = think trivial (e.g. 445 numa trajetória)
                continue
            pool[ds].append((t, s))
    rng = random.Random(SEED)
    rows = []
    for ds in ("SWE-rebench", "SWE-smith", "CodeTraceBench"):
        items = pool[ds]
        if ds == "CodeTraceBench":  # proporcional aos agentes (por nº de passos)
            by_ag = defaultdict(list)
            for it in items:
                by_ag[it[0].agent].append(it)
            tot = sum(len(v) for v in by_ag.values())
            quota = {a: max(1, round(PER_DATASET * len(v) / tot)) for a, v in by_ag.items()}
            while sum(quota.values()) > PER_DATASET:
                quota[max(quota, key=quota.get)] -= 1
            while sum(quota.values()) < PER_DATASET:
                quota[max(by_ag, key=lambda a: len(by_ag[a]) / quota[a])] += 1
            chosen = [it for a, v in sorted(by_ag.items()) for it in rng.sample(v, quota[a])]
        else:
            chosen = rng.sample(items, PER_DATASET)
        rng.shuffle(chosen)
        for t, s in chosen:
            rows.append({  # id único: os prefixos de traj_id do CTB colidem

                "id": f"{t.id[:36]}~{hashlib.sha1(t.id.encode()).hexdigest()[:6]}#{s.idx}", "dataset": ds, "agent": t.agent, "traj_id": t.id, "idx": s.idx,
                "tool": s.action.tool_native or s.action.tool, "thought": short(s.thought, 200),
                "action": short(s.action.raw or s.action.command, 350), "observation": short(s.observation.content if s.observation else "", 250),
                "pred_category": s.category, "pred_subcategory": s.subcategory or "", "label_source": s.label_source,
                "confidence": s.confidence, "gold_category": ""})
    gold_dir = ROOT / "results" / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    # CSV CEGO (o que você preenche): só contexto + gold_category vazio — sem rótulo da regra, do LLM, confiança nem label_source
    blind_cols = ["id", "dataset", "agent", "traj_id", "idx", "tool", "thought", "action", "observation", "gold_category"]
    with (gold_dir / "gold_steps_cego.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=blind_cols)
        w.writeheader()
        w.writerows({k: r[k] for k in blind_cols} for r in rows)
    # previsões (NÃO abrir antes de rotular): usadas só por scripts/evaluate.py, juntando pelo `id`
    pred_cols = ["id", "dataset", "agent", "traj_id", "idx", "pred_category", "pred_subcategory", "label_source", "confidence"]
    with (gold_dir / "gold_steps_previsoes.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pred_cols)
        w.writeheader()
        w.writerows({k: r[k] for k in pred_cols} for r in rows)
    from collections import Counter
    print(f"{len(rows)} passos → {gold_dir}/gold_steps_cego.csv (preencher) e gold_steps_previsoes.csv (não abrir)")
    print(Counter((r["dataset"], r["agent"]) for r in rows))


if __name__ == "__main__":
    main()
