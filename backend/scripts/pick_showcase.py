#!/usr/bin/env python
"""Escolhe amostras com padrões interessantes (loops, ciclos edit→test, gabarito, trace do Ark) para as capturas do front.
Escreve frontend/e2e/showcase.json e imprime a justificativa de cada escolha."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import library, pipeline  # noqa: E402


def main() -> None:
    rows = []
    for it, path in library.index(refresh=True):
        try:
            pt = pipeline.process(path, path.name, use_llm=False, sample_id=it.id)
        except pipeline.PipelineError:
            continue
        m = pt.metrics
        rows.append({"id": it.id, "dataset": it.dataset, "agent": pt.trajectory.agent, "resolved": pt.trajectory.resolved, "n": m.outcome.n_steps,
                     "loops": len(m.problems.loop_ranges), "cycles": m.dynamics.edit_test_cycles, "passed": m.dynamics.cycles_passed,
                     "failed": m.dynamics.cycles_failed, "errors": m.problems.error.count, "repeated": m.problems.repeated.count + m.problems.no_new_info.count,
                     "gt": (m.ground_truth.n_incorrect + m.ground_truth.n_unuseful) if m.ground_truth else 0,
                     "gt_inc": m.ground_truth.n_incorrect if m.ground_truth else 0, "task": pt.trajectory.task_id})

    def best(cands, key):
        return max(cands, key=key) if cands else None

    def rb(res):
        return [r for r in rows if r["dataset"] == "swe-rebench" and r["resolved"] is res and 40 <= r["n"] <= 110]
    picks = {
        "swe_rebench_resolved": best(rb(True), lambda r: (r["cycles"] >= 2, r["passed"], r["cycles"], r["errors"] + r["repeated"], -abs(r["n"] - 80))),
        "swe_rebench_unresolved": best(rb(False), lambda r: (r["loops"] > 0, r["cycles"], r["failed"], r["errors"] + r["repeated"], -abs(r["n"] - 80))),
        "swe_smith": best([r for r in rows if r["dataset"] == "swe-smith" and 25 <= r["n"] <= 90], lambda r: (r["loops"] > 0, r["cycles"], r["errors"] + r["repeated"])),
        "ctb_gt": best([r for r in rows if r["dataset"] == "codetracebench" and r["gt_inc"] > 0 and r["n"] >= 30 and r["loops"] > 0],
                            lambda r: (r["gt"], r["loops"], r["errors"])) or best([r for r in rows if r["dataset"] == "codetracebench" and r["gt_inc"] > 0],
                                                                             lambda r: (r["loops"], r["gt"], r["n"])),
        "ark": best([r for r in rows if r["dataset"] == "ark"], lambda r: (r["failed"] > 0, r["errors"] > 0, r["cycles"], r["n"])),  # trace real do Ark
    }
    out = {k: v for k, v in picks.items() if v}
    (ROOT / "frontend" / "e2e" / "showcase.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    for k, v in out.items():
        print(f"{k}: {v['id']}  n={v['n']} resolved={v['resolved']} loops={v['loops']} ciclos={v['cycles']} (pass {v['passed']}/fail {v['failed']}) erros={v['errors']} rep/nni={v['repeated']} gt={v['gt']}")


if __name__ == "__main__":
    main()
