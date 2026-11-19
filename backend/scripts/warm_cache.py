#!/usr/bin/env python
"""Processa todo data/samples/ (só regras, sem LLM) e enche o cache da biblioteca.

    uv run python scripts/warm_cache.py [--cold]   # --cold: mede o tempo sem cache (cache temporário, descartado)
Escreve results/warm_cache_report.md (tempo por trajetória e % de passos com cada flag por dataset).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import config, library, pipeline  # noqa: E402

FLAGS = ["error", "test_fail", "test_pass", "repeated", "no_new_info", "loop", "truncated"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cold", action="store_true")
    args = ap.parse_args()
    tmp = None
    if args.cold:
        tmp = tempfile.TemporaryDirectory(prefix="trajviz-cold-")
        config.CACHE_DIR = Path(tmp.name)
    rows, fails = [], []
    stats = defaultdict(lambda: {"traj": 0, "steps": 0, "flags": Counter(), "sec": 0.0, "steps100": 0.0, "unsupp": 0})
    for it, path in library.index(refresh=True):
        t0 = time.perf_counter()
        try:
            pt = pipeline.process(path, path.name, use_llm=False, sample_id=it.id)
        except pipeline.PipelineError as e:
            if e.code == "unsupported_artifact":
                stats[it.dataset]["unsupp"] += 1
            else:
                fails.append((it.id, e.code, e.message[:120]))
            continue
        dt = time.perf_counter() - t0
        n = len(pt.trajectory.steps)
        st = stats[it.dataset]
        st["traj"] += 1; st["steps"] += n; st["sec"] += dt; st["steps100"] += n / 100
        analyz = [s for s in pt.trajectory.steps if s.subcategory not in ("keys", "harness_protocol")]
        st.setdefault("analyz", 0); st["analyz"] += len(analyz)
        for s in analyz:
            st["flags"].update(s.flags)
        rows.append((it.id, n, dt))
    L = ["# Cache da biblioteca e flags (Fase 4)", "",
         f"`scripts/warm_cache.py{' --cold' if args.cold else ''}` — só regras (sem LLM). Tempo {'SEM cache (frio)' if args.cold else 'com o cache existente (quente)'}.", "",
         "## Tempo do pipeline", "", "| dataset | traj. | passos médios | s / trajetória | s / 100 passos |", "|---|---:|---:|---:|---:|"]
    tot_s = tot_n = tot_t = 0
    for ds, st in sorted(stats.items()):
        if not st["traj"]:
            continue
        L.append(f"| {ds} | {st['traj']} | {st['steps'] / st['traj']:.1f} | {st['sec'] / st['traj']:.3f} | {st['sec'] / st['steps100']:.3f} |")
        tot_s += st["sec"]; tot_n += st["steps100"]; tot_t += st["traj"]
    L.append(f"| **total** | {tot_t} | — | {tot_s / tot_t:.3f} | {tot_s / tot_n:.3f} |")
    worst = max(rows, key=lambda r: r[2])
    L += ["", f"Meta: < 2 s por trajetória de 100 passos → {'✅' if tot_s / tot_n < 2 else '❌'}. Mais lenta: `{worst[0]}` ({worst[1]} passos, {worst[2]:.2f} s).", "",
          "## % de passos com cada flag (por dataset; sem passos keys/harness)", "",
          "| dataset | passos | " + " | ".join(FLAGS) + " |", "|---|---:|" + "---:|" * len(FLAGS)]
    for ds, st in sorted(stats.items()):
        if st["traj"]:
            L.append(f"| {ds} | {st['analyz']} | " + " | ".join(f"{100 * st['flags'][f] / st['analyz']:.1f}%" for f in FLAGS) + " |")
    if any(st["unsupp"] for st in stats.values()):
        L += ["", "Artefatos não suportados (só logs): " + ", ".join(f"{d}: {s['unsupp']}" for d, s in stats.items() if s["unsupp"])]
    if fails:
        L += ["", "## Falhas", ""] + [f"- `{i}`: {c} — {m}" for i, c, m in fails]
    else:
        L += ["", "Nenhuma falha de processamento."]
    out = ROOT / "results" / ("warm_cache_cold_report.md" if args.cold else "warm_cache_report.md")
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    if tmp:
        tmp.cleanup()


if __name__ == "__main__":
    main()
