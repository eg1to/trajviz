#!/usr/bin/env python
"""Resolvidas × não resolvidas em escala (só regras). Escreve results/batch_stats.{md,parquet}.

SWE-rebench: 2.000 trajetórias (1.000 resolvidas + 1.000 não; semente fixa, espalhadas pelos row groups; leitura em lotes, uma de cada vez).
CTB verified: todas as 992 artefatos (por agente). SWE-smith: 600 (200 por split) — `resolved` NÃO VALIDADO (marcado em toda tabela/figura).
Por métrica: mediana dos dois grupos, Mann-Whitney U (p com correção de Holm dentro de cada estrato) e delta de Cliff (resolvida − não resolvida).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CTB_DIR, RESULTS, ROOT, SEED, artifact, cliffs_delta, fmt, holm, mann_whitney, run_pipeline, verified_ids  # noqa: E402

from app.adapters.base import UnsupportedArtifact  # noqa: E402

PHASES = ["Entendimento", "Modificação", "Verificação", "Controle"]
METRICS = [("n_steps", "nº de passos"), ("pct_Entendimento", "% Entendimento"), ("pct_Modificação", "% Modificação"), ("pct_Verificação", "% Verificação"),
           ("pct_Controle", "% Controle"), ("pct_test", "% passos test"), ("first_edit_rel", "posição relativa da 1ª edição"), ("error_rate", "taxa de error"),
           ("repeated_rate", "taxa de repeated"), ("nni_rate", "taxa de no_new_info"), ("loop_rate", "taxa de loop"), ("cycles", "ciclos edit→test"),
           ("pct_cycles_passed", "% ciclos terminando em test_pass")]
N_REBENCH, N_SMITH_PER_SPLIT = 1000, 200
BASE = ROOT / "data" / "raw"
REB_COLS = ["trajectory_id", "instance_id", "repo", "trajectory", "model_patch", "exit_status", "resolved", "gen_tests_correct", "pred_passes_gen_tests"]


def record(ds: str, group: str, agent: str, traj, m, secs: float, resolved, extra: dict | None = None) -> dict:
    e = m.effort
    n = len(traj.steps)
    an = max(sum(1 for s in traj.steps if s.subcategory not in ("keys", "harness_protocol")), 1)
    r = {"dataset": ds, "group": group, "agent": agent, "id": traj.id, "resolved": None if resolved is None else bool(resolved), "format": traj.source_format,
         "n_steps": n, "n_core": e.n_core_steps, "time_s": secs,
         "pct_test": e.by_category["test"].pct_core / 100, "first_edit_rel": (m.dynamics.first_edit_idx / n) if m.dynamics.first_edit_idx is not None and n else np.nan,
         "error_rate": m.problems.error.count / an, "repeated_rate": m.problems.repeated.count / an, "nni_rate": m.problems.no_new_info.count / an,
         "loop_rate": m.problems.loop.count / an, "cycles": m.dynamics.edit_test_cycles, "cycles_passed": m.dynamics.cycles_passed,
         "pct_cycles_passed": (m.dynamics.cycles_passed / m.dynamics.edit_test_cycles) if m.dynamics.edit_test_cycles else np.nan,
         "origin": traj.meta.get("origin"), "action_formats": json.dumps(traj.meta.get("action_formats")) if traj.meta.get("action_formats") else None}
    for p in PHASES:
        ph = next((x for x in e.by_phase if x.phase == p), None)
        r[f"pct_{p}"] = (ph.pct_core / 100) if ph else np.nan
    for t in m.dynamics.dominant_phase_by_third:  # fração de cada fase em cada terço (figura de fases por terço)
        for p in PHASES:
            r[f"t{t.third}_{p}"] = (t.counts.get(p, 0) / t.n_steps) if t.n_steps else np.nan
    if extra:
        r.update(extra)
    return r


# ----------------------------------------------------------------------------- leitura em lotes
def rebench_rows(rng):
    pf = pq.ParquetFile(BASE / "swe-rebench" / "trajectories.parquet")
    flags = pf.read(columns=["resolved"]).column("resolved").to_numpy()  # 67k inteiros: barato
    res_idx = rng.choice(np.flatnonzero(flags == 1), N_REBENCH, replace=False)
    non_idx = rng.choice(np.flatnonzero(flags == 0), N_REBENCH, replace=False)
    want = set(res_idx.tolist()) | set(non_idx.tolist())
    base, spread = 0, []
    for g in range(pf.metadata.num_row_groups):
        n = pf.metadata.row_group(g).num_rows
        picked = sorted(i - base for i in want if base <= i < base + n)
        spread.append(len(picked))
        if picked:
            pos, targets = 0, set(picked)
            for batch in pf.iter_batches(batch_size=32, row_groups=[g], columns=REB_COLS):
                for k, row in enumerate(batch.to_pylist()):
                    if pos + k in targets:
                        yield row
                pos += batch.num_rows
        base += n
    print(f"rebench: amostradas por row group = {spread}", file=sys.stderr)


def smith_rows(rng):
    for split in ("tool", "xml", "ticks"):
        files = sorted((BASE / "swe-smith" / "data").glob(f"{split}-*.parquet"))
        per_file = [N_SMITH_PER_SPLIT // len(files)] * len(files)
        for i in range(N_SMITH_PER_SPLIT - sum(per_file)):
            per_file[i] += 1
        for f, k in zip(files, per_file):
            pf = pq.ParquetFile(f)
            targets = set(rng.choice(pf.metadata.num_rows, k, replace=False).tolist())
            pos = 0
            for batch in pf.iter_batches(batch_size=16):
                for j, row in enumerate(batch.to_pylist()):
                    if pos + j in targets:
                        yield split, row
                pos += batch.num_rows


def main() -> None:
    rng = np.random.default_rng(SEED)
    t_all = time.perf_counter()
    rows, skipped = [], {"ctb_unsupported": 0, "ctb_sem_artefato": 0, "erros": 0}
    t0 = time.perf_counter()
    for k, row in enumerate(rebench_rows(rng)):
        try:
            traj, m, secs = run_pipeline(row)
        except Exception:  # noqa: BLE001
            skipped["erros"] += 1
            continue
        rows.append(record("SWE-rebench", "swe-rebench", "OpenHands", traj, m, secs, row["resolved"]))
        if (k + 1) % 500 == 0:
            print(f"rebench {k + 1}/{2 * N_REBENCH}", file=sys.stderr)
    t_reb = time.perf_counter() - t0
    for k, tid in enumerate(verified_ids()):
        try:
            traj, m, secs = run_pipeline(artifact(tid))
        except UnsupportedArtifact:
            skipped["ctb_unsupported"] += 1
            continue
        except FileNotFoundError:
            skipped["ctb_sem_artefato"] += 1
            continue
        except Exception:  # noqa: BLE001
            skipped["erros"] += 1
            continue
        rows.append(record("CodeTraceBench", f"ctb:{traj.agent}", traj.agent or "?", traj, m, secs, traj.resolved))
    print("ctb ok", file=sys.stderr)
    for split, row in smith_rows(rng):
        try:
            traj, m, secs = run_pipeline(row)
        except Exception:  # noqa: BLE001
            skipped["erros"] += 1
            continue
        fm = traj.meta.get("action_formats") or {}
        rows.append(record("SWE-smith", f"smith:{split}", "SWE-agent", traj, m, secs, row["resolved"], {"split": split, "main_format": max(fm, key=fm.get) if fm else None}))
    total = time.perf_counter() - t_all
    df = pd.DataFrame(rows)
    df.to_parquet(RESULTS / "batch_stats.parquet", index=False)
    (RESULTS / "batch_stats.md").write_text(render(df, total, skipped))
    print((RESULTS / "batch_stats.md").read_text()[:3000])


def compare(sub: pd.DataFrame) -> list[dict]:
    a, b = sub[sub.resolved == True], sub[sub.resolved == False]  # noqa: E712
    out = []
    for col, label in METRICS:
        x, y = a[col].to_numpy(float), b[col].to_numpy(float)
        u, p = mann_whitney(x, y)
        out.append({"metric": col, "label": label, "n_res": int((~np.isnan(x)).sum()), "n_non": int((~np.isnan(y)).sum()), "med_res": float(np.nanmedian(x)) if (~np.isnan(x)).any() else np.nan,
                    "med_non": float(np.nanmedian(y)) if (~np.isnan(y)).any() else np.nan, "p": p, "delta": cliffs_delta(x, y)})
    for r, ph in zip(out, holm([r["p"] for r in out])):
        r["p_holm"] = ph
    return out


def strata(df: pd.DataFrame):
    yield "SWE-rebench (2.000: 1.000 resolvidas + 1.000 não)", df[df.dataset == "SWE-rebench"], False
    c = df[(df.dataset == "CodeTraceBench") & df.resolved.notna()]
    yield "CodeTraceBench verified — todos (solved conhecido)", c, False
    for ag in sorted(c.agent.unique()):
        yield f"CodeTraceBench verified — {ag}", c[c.agent == ag], False
    s = df[df.dataset == "SWE-smith"]
    yield "SWE-smith (600) — ⚠ resolved NÃO VALIDADO", s, True
    for sp in ("tool", "xml", "ticks"):
        yield f"SWE-smith/{sp} (200) — ⚠ resolved NÃO VALIDADO", s[s.split == sp], True


def stars(p):
    return "" if p != p else ("***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "")


def render(df: pd.DataFrame, total: float, skipped: dict) -> str:
    t = df.time_s
    L = ["# Resolvidas × não resolvidas — estatísticas em lote (só regras)", "",
         f"`backend/scripts/batch_stats.py` · semente {SEED} · {len(df)} trajetórias processadas · tabela por trajetória em `results/batch_stats.parquet`.", "",
         "Convenção: **Δ de Cliff > 0 = a métrica é MAIOR nas resolvidas**. p = Mann-Whitney bilateral; **p(Holm)** corrige pelas 13 métricas de cada estrato (`*` p<0,05, `**` <0,01, `***` <0,001, sobre o p corrigido). "
         "|Δ| < 0,147 desprezível · < 0,33 pequeno · < 0,474 médio · ≥ 0,474 grande (Romano et al.).", "",
         "> ⚠️ **SWE-smith: `resolved` não validado** (o patch não bate com a trajetória em ~83% das linhas; ver docs/formats.md §0). Os números do SWE-smith descrevem a coluna `resolved` como está e **não** podem ser lidos como sucesso real da tarefa. "
         "No CodeTraceBench, agentes/origens (SWE-bench × TerminalBench) e limites de iteração confundem as comparações; no SWE-rebench o agente e o modelo são fixos mas o tamanho da tarefa não é controlado. **Associação, não causalidade.**", "",
         "## Tempo do pipeline (detect → parse → rótulos → detectores → métricas, por trajetória, sem cache, sem I/O do Parquet)", "",
         f"- Total desta execução (incluindo leitura dos dados): **{total:.0f} s** para {len(df)} trajetórias · só pipeline: {t.sum():.0f} s", "",
         "| dataset | traj. | mediana (s) | p95 (s) | máx (s) | passos medianos |", "|---|---:|---:|---:|---:|---:|"]
    for ds, g in df.groupby("dataset"):
        L.append(f"| {ds} | {len(g)} | {g.time_s.median():.3f} | {g.time_s.quantile(0.95):.3f} | {g.time_s.max():.3f} | {g.n_steps.median():.0f} |")
    L.append(f"| **todos** | {len(df)} | {t.median():.3f} | {t.quantile(0.95):.3f} | {t.max():.3f} | {df.n_steps.median():.0f} |")
    L += ["", f"Descartadas: {skipped}.", ""]
    all_rows = {}
    for name, sub, unval in strata(df):
        res = compare(sub)
        all_rows[name] = res
        nr, nn = int((sub.resolved == True).sum()), int((sub.resolved == False).sum())  # noqa: E712
        L += [f"## {name}", "", f"resolvidas n = {nr} · não resolvidas n = {nn}", "",
              "| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |", "|---|---:|---:|---:|---:|---:|"]
        for r in res:
            L.append(f"| {r['label']} | {fmt(r['med_res'], 3)} | {fmt(r['med_non'], 3)} | {fmt(r['delta'], 3)} | {fmt(r['p'], 4)} | {fmt(r['p_holm'], 4)}{stars(r['p_holm'])} |")
        L.append("")
    (RESULTS / "batch_stats.json").write_text(json.dumps({"total_s": total, "n": len(df), "skipped": skipped, "pipeline_median_s": float(t.median()), "pipeline_p95_s": float(t.quantile(0.95)),
                                                         "strata": all_rows}, indent=1, ensure_ascii=False, default=float))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
