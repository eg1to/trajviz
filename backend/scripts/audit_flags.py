#!/usr/bin/env python
"""Auditoria leve de `error`, `repeated`, `loop` e `test_fail` (SWE-rebench + SWE-smith, amostras novas e independentes).

    uv run python scripts/audit_flags.py            # sorteia 20 passos por flag (≤ 2 por trajetória) e imprime os casos
    uv run python scripts/audit_flags.py --render   # lê scripts/audit_flags_verdicts.json e escreve results/audit_flags.md
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


def collect() -> dict[str, list[dict]]:
    pool = defaultdict(list)
    paths = sorted((SAMPLES / "swe-rebench").glob("chat*.json")) + sorted(p for sp in ("tool", "xml", "ticks") for p in (SAMPLES / "swe-smith" / sp).glob("*.json"))
    for p in paths:
        traj, _, _ = run_pipeline(p)
        ds = "swe-rebench" if "swe-rebench" in str(p) else "swe-smith"
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
                                    "loop": {"range": loop["range"], "pattern": loop.get("pattern"), "kind": loop["kind"],
                                             "steps": [f"#{x.idx} {x.category}: {cut(act(x), 70)}" for x in traj.steps[loop["range"][0]:min(loop["range"][1] + 1, loop["range"][0] + 8)]]} if loop else None})
    return pool


def sample(pool) -> list[dict]:
    rng = random.Random(SEED + 1)  # semente própria: independente da auditoria do no_new_info
    out = []
    for f in FLAGS:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    pool = collect()
    cases = sample(pool)
    sizes = {f: len(pool[f]) for f in FLAGS}
    if not args.render:
        print("pool:", sizes)
        for c in cases:
            print(f"\n## {c['n']} [{c['dataset']}] {c['traj'][:40]} #{c['idx']} cat={c['category']} exit={c['exit_code']}\nAÇÃO: {c['action'][:200]}\nMOTIVO: {c['reason']}")
            if c["prev_action"]:
                print(f"AÇÃO ANTERIOR: {c['prev_action']}")
            if c["loop"]:
                print(f"LOOP {c['loop']['range']} {c['loop']['kind']}: " + " | ".join(c["loop"]["steps"][:6]))
            print(f"OBS: {c['obs'][:200]!r}")
            if c["ctx"]:
                print(f"CTX(match): {c['ctx']!r}")
            if c["tail"] and c["flag"] in ("test_fail", "error"):
                print(f"FIM: {c['tail'][-200:]!r}")
        return
    v = json.loads(VERDICTS.read_text())
    L = ["# Auditoria leve dos detectores `error`, `repeated`, `loop` e `test_fail`", "",
         f"`backend/scripts/audit_flags.py` · semente {SEED + 1} (independente da auditoria do `no_new_info`) · SWE-rebench + SWE-smith (amostras de `data/samples/`, 110 trajetórias) · "
         f"até {N} passos por flag, no máximo {PER_TRAJ} por trajetória.", "",
         "> **Pré-avaliação do assistente — revisar.** Os vereditos abaixo são uma primeira leitura minha (correto / falso positivo / duvidoso) com base na ação e na observação cortadas; "
         "não foram revisados por humano. A auditoria serve para **medir** os detectores; nenhuma regra foi ajustada por causa dela.", "",
         f"Passos marcados no pool (110 trajetórias): {sizes}.", "", "## Contagem por flag (pré-avaliação)", "",
         "| flag | amostrados | correto | duvidoso | falso positivo | precisão (correto ÷ amostrados) | precisão incl. duvidosos como meio-acerto |", "|---|---:|---:|---:|---:|---:|---:|"]
    summary = {}
    for f in FLAGS:
        cs = [c for c in cases if c["flag"] == f]
        t = Counter(v.get(c["n"], {}).get("verdict", "?") for c in cs)
        n = len(cs)
        summary[f] = (n, t)
        L.append(f"| `{f}` | {n} | {t['correto']} | {t['duvidoso']} | {t['falso_positivo']} | {100 * t['correto'] / n:.0f}% | {100 * (t['correto'] + t['duvidoso'] / 2) / n:.0f}% |")
    L += ["", "Com 20 casos por flag o IC 95% da precisão é largo (± ~20 p.p. perto de 50%, ± ~10 p.p. perto de 90%): isto é um sinal, não uma medida.", ""]
    notes = VERDICTS.with_suffix(".note.md")
    if notes.exists():
        L += [notes.read_text().strip(), ""]
    for f in FLAGS:
        L += [f"## `{f}`", ""]
        for c in (x for x in cases if x["flag"] == f):
            vd = v.get(c["n"], {"verdict": "?", "why": ""})
            L += [f"### {c['n']} · {c['dataset']} · `{c['traj'][:48]}` #{c['idx']} — **{vd['verdict'].replace('_', ' ')}** _(pré-avaliação do assistente — revisar)_", "",
                  f"- categoria: {c['category']} · exit code: {c['exit_code']} · motivo do detector: {c['reason']}", f"- ação: `{c['action'][:200]}`"]
            if c["ctx"]:
                L.append(f"- trecho onde o padrão casou: `{c['ctx'][:260].replace(chr(96), chr(39))}`")
            if c["prev_action"]:
                L.append(f"- ação anterior equivalente: `{c['prev_action']}`")
            if c["loop"]:
                L += [f"- loop {c['loop']['range']} ({c['loop']['kind']}): " + " → ".join(c["loop"]["steps"][:6])]
            L += [f"- por quê: {vd['why']}", "", "```text", c["obs"], "```", ""]
    (RESULTS / "audit_flags.md").write_text("\n".join(L))
    print({f: dict(t) for f, (n, t) in summary.items()})


if __name__ == "__main__":
    main()
