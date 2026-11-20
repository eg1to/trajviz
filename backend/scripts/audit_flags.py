#!/usr/bin/env python
"""Auditoria leve de `error`, `repeated`, `loop` e `test_fail` (SWE-rebench + SWE-smith, amostras novas e independentes).

    uv run python scripts/audit_flags.py            # sorteia 20 passos por flag (≤ 2 por trajetória) e imprime os casos
    uv run python scripts/audit_flags.py --render   # lê scripts/audit_flags_verdicts.json e escreve results/audit_flags.md (rodada 1)
    uv run python scripts/audit_flags.py --round2   # rodada 2 (regras corrigidas de test_fail e loop; 300+300 trajetórias NOVAS, semente SEED+2, sem reaproveitar casos)
    uv run python scripts/audit_flags.py --round2 --render   # results/audit_flags.md = antes × depois + rodadas 1 e 2
Os vereditos são uma PRÉ-AVALIAÇÃO DO ASSISTENTE (primeira leitura): revisar. Esta auditoria mede; não é para ajustar regras.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RESULTS, ROOT, SEED, run_pipeline  # noqa: E402

FLAGS = ["error", "repeated", "loop", "test_fail"]
N, PER_TRAJ = 20, 2
VERDICTS = ROOT / "backend" / "scripts" / "audit_flags_verdicts.json"
SAMPLES = ROOT / "data" / "samples"


def cut(s, n):
    s = (s or "").replace("\r\n", "\n").strip()
    return s if len(s) <= n else s[:n] + f"… [+{len(s) - n}]"


def act(step):
    a = step.action
    if a.tool == "editor":
        return f"editor {a.command} {a.args.get('path', '')}" + (f" view_range={a.args.get('view_range')}" if a.args.get("view_range") else "")
    return (a.command or a.raw or a.tool).strip()


def fresh_sources(seed: int):
    """Trajetórias NOVAS (fora de data/samples/): 300 do SWE-rebench e 300 do SWE-smith (100 por split), sorteadas no arquivo inteiro."""
    import numpy as np
    import pyarrow.parquet as pq
    rng = np.random.default_rng(seed)
    used = {json.loads(p.read_text()).get("trajectory_id") or json.loads(p.read_text()).get("traj_id") for p in
            list((SAMPLES / "swe-rebench").glob("chat*.json")) + [q for sp in ("tool", "xml", "ticks") for q in (SAMPLES / "swe-smith" / sp).glob("*.json")]}
    base = ROOT / "data" / "raw"
    pf = pq.ParquetFile(base / "swe-rebench" / "trajectories.parquet")
    want = set(rng.choice(pf.metadata.num_rows, 700, replace=False).tolist())
    cols = ["trajectory_id", "instance_id", "repo", "trajectory", "model_patch", "exit_status", "resolved"]
    pos = 0
    for batch in pf.iter_batches(batch_size=32, columns=cols):
        for j, row in enumerate(batch.to_pylist()):
            if pos + j in want and row["trajectory_id"] not in used:
                yield "swe-rebench", row
        pos += batch.num_rows
    for split in ("tool", "xml", "ticks"):
        files = sorted((base / "swe-smith" / "data").glob(f"{split}-*.parquet"))
        for f in files:
            pf = pq.ParquetFile(f)
            want = set(rng.choice(pf.metadata.num_rows, 150 // len(files) + 1, replace=False).tolist())
            pos = 0
            for batch in pf.iter_batches(batch_size=16):
                for j, row in enumerate(batch.to_pylist()):
                    if pos + j in want and row["traj_id"] not in used:
                        yield "swe-smith", row
                pos += batch.num_rows


def collect(round2: bool = False) -> dict[str, list[dict]]:
    pool = defaultdict(list)
    if round2:
        sources = ((ds, row) for ds, row in fresh_sources(SEED + 2))
    else:
        paths = sorted((SAMPLES / "swe-rebench").glob("chat*.json")) + sorted(p for sp in ("tool", "xml", "ticks") for p in (SAMPLES / "swe-smith" / sp).glob("*.json"))
        sources = (("swe-rebench" if "swe-rebench" in str(p) else "swe-smith", p) for p in paths)
    for ds, p in sources:
        traj, _, _ = run_pipeline(p)
        for s in traj.steps:
            if s.subcategory in ("keys", "harness_protocol"):
                continue
            for f in FLAGS:
                if f in s.flags:
                    ref = (s.flag_refs or {}).get(f)
                    prev = traj.steps[ref] if ref is not None else None
                    loop = next((lp for lp in traj.meta.get("loops", []) if lp["range"][0] <= s.idx <= lp["range"][1]), None) if f == "loop" else None
                    full = s.observation.content if s.observation else ""
                    key = str(s.flag_details.get(f, "")).replace("padrão: ", "")
                    pos = full.find(key) if key and key in full else (full.find("Traceback") if "Traceback" in key else -1)
                    ctx = cut(full[max(0, pos - 80):pos + 240], 330) if pos >= 0 else None
                    pool[f].append({"flag": f, "ctx": ctx, "tail": cut(full[-260:], 260) if len(full) > 330 else None, "dataset": ds, "traj": traj.id, "idx": s.idx, "category": s.category, "action": cut(act(s), 220),
                                    "reason": s.flag_details.get(f), "obs": cut(s.observation.content if s.observation else "", 320),
                                    "exit_code": s.observation.exit_code if s.observation else None,
                                    "prev_action": cut(act(prev), 160) if prev else None,
                                    "loop": {"range": loop["range"], "pattern": loop.get("pattern"), "kind": loop["kind"], "signature": loop.get("signature"), "file": loop.get("file"),
                                             "steps": [f"#{x.idx} {x.category}: {cut(act(x), 70)}" for x in traj.steps[loop["range"][0]:min(loop["range"][1] + 1, loop["range"][0] + 8)]]} if loop else None})
    return pool


def sample(pool, round2: bool = False) -> list[dict]:
    rng = random.Random(SEED + 2 if round2 else SEED + 1)  # sementes próprias: independentes entre si e da auditoria do no_new_info
    out = []
    for f in (["test_fail", "loop"] if round2 else FLAGS):
        cands = pool[f][:]
        rng.shuffle(cands)
        per, chosen = Counter(), []
        for c in cands:
            if per[c["traj"]] < PER_TRAJ:
                per[c["traj"]] += 1
                chosen.append(c)
            if len(chosen) == N:
                break
        for i, c in enumerate(chosen, 1):
            c["n"] = f"{f}-{i}"
        out += chosen
    return out


R1_SUMMARY = {"error": (20, 18, 1, 1), "repeated": (20, 15, 5, 0), "loop": (20, 5, 8, 7), "test_fail": (20, 10, 10, 0)}  # (n, correto, duvidoso, FP) — rodada 1 congelada
CASES2 = ROOT / "backend" / "scripts" / "audit_flags_round2_cases.json"
V2 = ROOT / "backend" / "scripts" / "audit_flags_round2_verdicts.json"


def show(cases: list[dict]) -> None:
    for c in cases:
        print(f"\n## {c['n']} [{c['dataset']}] {c['traj'][:40]} #{c['idx']} cat={c['category']} exit={c['exit_code']}\nAÇÃO: {c['action'][:200]}\nMOTIVO: {c['reason']}")
        if c["loop"]:
            print(f"LOOP {c['loop']['range']} {c['loop']['kind']}: " + " | ".join(c["loop"]["steps"][:6]))
        print(f"OBS: {c['obs'][:200]!r}")
        if c["ctx"]:
            print(f"CTX(match): {c['ctx']!r}")
        if c["tail"]:
            print(f"FIM: {c['tail'][-200:]!r}")


def render_combined(cases: list[dict], sizes: dict) -> str:
    v = json.loads(V2.read_text())
    r1 = (ROOT / "backend" / "scripts" / "audit_flags_round1.md").read_text()
    L = ["# Auditoria leve dos detectores — antes × depois da correção de `test_fail` e `loop`", "",
         "> **Pré-avaliação do assistente — revisar.** Os vereditos (correto / falso positivo / duvidoso) são uma primeira leitura minha com base na ação e na observação cortadas; "
         "não foram revisados por humano. A rodada 1 mediu os detectores; a rodada 2 mede **só** as duas regras corrigidas (`test_fail` e `loop`) numa amostra **nova** "
         f"(semente {SEED + 2}; ~700 trajetórias do SWE-rebench + ~450 do SWE-smith fora de `data/samples/`; nenhum caso da rodada 1 reaproveitado; ≤ {PER_TRAJ} por trajetória).", "",
         "## Antes × depois (lado a lado)", "",
         "Antes = regras originais, 110 trajetórias de `data/samples/` (rodada 1). Depois = regras corrigidas, ~1.150 trajetórias novas (rodada 2). Amostras diferentes: compare as proporções com a largura do IC em mente (20 casos ⇒ ± ~20 p.p.).", "",
         "| flag | rodada | amostrados | correto | duvidoso | falso positivo | % correto | % correto + ½ duvidoso | passos marcados no pool |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    summ = {}
    for f in ("test_fail", "loop"):
        n1, c1, d1, f1 = R1_SUMMARY[f]
        cs = [c for c in cases if c["flag"] == f]
        t = Counter(v.get(c["n"], {}).get("verdict", "?") for c in cs)
        n2 = len(cs)
        summ[f] = (n2, t)
        L.append(f"| `{f}` | 1 — antes | {n1} | {c1} | {d1} | {f1} | {100 * c1 / n1:.0f}% | {100 * (c1 + d1 / 2) / n1:.0f}% | 100 (de 110 traj.) / 276 loop") if False else None
        L.append(f"| `{f}` | **1 — antes** | {n1} | {c1} | {d1} | {f1} | {100 * c1 / n1:.0f}% | {100 * (c1 + d1 / 2) / n1:.0f}% | {'100' if f == 'test_fail' else '276'} |")
        L.append(f"| `{f}` | **2 — depois** | {n2} | {t['correto']} | {t['duvidoso']} | {t['falso_positivo']} | {100 * t['correto'] / max(n2, 1):.0f}% | {100 * (t['correto'] + t['duvidoso'] / 2) / max(n2, 1):.0f}% | {sizes[f]} |")
    L += ["", "(`error` e `repeated` não mudaram e não foram reauditados: ver rodada 1 abaixo.)", ""]
    note = V2.with_suffix(".note.md")
    if note.exists():
        L += [note.read_text().strip(), ""]
    L += ["---", "", "# Rodada 2 — regras corrigidas, amostra nova (`test_fail` e `loop`)", ""]
    for f in ("test_fail", "loop"):
        L += [f"## `{f}`", ""]
        for c in (x for x in cases if x["flag"] == f):
            vd = v.get(c["n"], {"verdict": "?", "why": ""})
            L += [f"### {c['n']} · {c['dataset']} · `{c['traj'][:48]}` #{c['idx']} — **{vd['verdict'].replace('_', ' ')}** _(pré-avaliação do assistente — revisar)_", "",
                  f"- categoria: {c['category']} · exit code: {c['exit_code']} · motivo do detector: {c['reason']}", f"- ação: `{c['action'][:200]}`"]
            if c["ctx"]:
                L.append(f"- trecho onde o padrão casou: `{c['ctx'][:260].replace(chr(96), chr(39))}`")
            if c["loop"]:
                L.append(f"- loop {c['loop']['range']} ({c['loop']['kind']}): " + " → ".join(c["loop"]["steps"][:6]))
            L += [f"- por quê: {vd['why']}", "", "```text", c["obs"], "```", ""]
    L += ["---", "", "# Rodada 1 — regras originais (congelada)", "", "_Texto da auditoria original, preservado sem alterações (amostra: 110 trajetórias de `data/samples/`, semente " + str(SEED + 1) + ")._", ""]
    body = r1.split("## Contagem por flag (pré-avaliação)", 1)[1]
    L += ["## Contagem por flag (pré-avaliação)" + body]
    (RESULTS / "audit_flags.md").write_text("\n".join(L))
    return summ


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round2", action="store_true")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    if not args.round2:
        sys.exit("A rodada 1 está congelada em scripts/audit_flags_round1.md; use --round2.")
    if not args.render:
        pool = collect(round2=True)
        cases = sample(pool, round2=True)
        sizes = {f: len(pool[f]) for f in ("test_fail", "loop")}
        CASES2.write_text(json.dumps({"sizes": sizes, "cases": cases}, ensure_ascii=False, indent=1))
        print("pool:", sizes, "casos:", Counter(c["flag"] for c in cases))
        show(cases)
        return
    d = json.loads(CASES2.read_text())
    summ = render_combined(d["cases"], d["sizes"])
    print({f: dict(t) for f, (n, t) in summ.items()})


if __name__ == "__main__":
    main()
