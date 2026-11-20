#!/usr/bin/env python
"""Sorteia 210 passos (semente fixa) p/ rotulação manual → results/gold/gold_steps_cego.csv (+ gold_steps_previsoes.csv, que NÃO deve ser aberto).

70 por dataset (SWE-rebench, SWE-smith, CodeTraceBench; no CTB proporcional ao nº de passos de cada agente);
exclui `harness_protocol` e passos `message` (trivialmente `think`). A coluna `gold_category` do CSV cego fica VAZIA para preenchimento manual; o cego não traz rótulo previsto, label_source, confiança nem rótulo do LLM.
O rótulo previsto vem só das regras (sem LLM), para que a avaliação seja reproduzível.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
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


def main() -> None:
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
