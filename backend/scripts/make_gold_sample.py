#!/usr/bin/env python
"""Sorteia 210 passos (semente fixa) p/ rotulação manual → results/gold/gold_steps.csv.

70 por dataset (SWE-rebench, SWE-smith, CodeTraceBench; no CTB proporcional ao nº de passos de cada agente);
exclui `harness_protocol` e passos `message` (trivialmente `think`). A coluna `gold_category` fica VAZIA para preenchimento manual (Fase 6).
O rótulo previsto vem só das regras (sem LLM), para que a avaliação seja reproduzível.
"""
from __future__ import annotations

import csv
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
            rows.append({
                "id": f"{t.id[:48]}#{s.idx}", "dataset": ds, "agent": t.agent, "traj_id": t.id, "idx": s.idx,
                "tool": s.action.tool_native or s.action.tool, "thought": short(s.thought, 200),
                "action": short(s.action.raw or s.action.command, 350), "observation": short(s.observation.content if s.observation else "", 250),
                "pred_category": s.category, "pred_subcategory": s.subcategory or "", "label_source": s.label_source,
                "confidence": s.confidence, "gold_category": ""})
    out = ROOT / "results" / "gold" / "gold_steps.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} passos → {out}")
    print(Counter((r["dataset"], r["agent"]) for r in rows))
    print(Counter(r["pred_category"] for r in rows))


if __name__ == "__main__":
    main()
