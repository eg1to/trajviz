#!/usr/bin/env python
"""Auditoria do detector `no_new_info` no SWE-smith: sorteia 20 passos marcados (semente fixa) e gera results/audit_no_new_info.md.

    uv run python scripts/audit_no_new_info.py            # gera o rascunho (sem vereditos) e imprime os casos
    uv run python scripts/audit_no_new_info.py --render   # lê scripts/audit_no_new_info_verdicts.json e escreve o relatório final
Os vereditos (correto | falso_positivo | duvidoso) são um julgamento humano/do revisor sobre cada par de passos.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import library, pipeline  # noqa: E402

SEED, N = 20251119, 20
VERDICTS = ROOT / "backend" / "scripts" / "audit_no_new_info_verdicts.json"


def cut(s: str | None, n: int = 300) -> str:
    s = (s or "").replace("\r\n", "\n").strip()
    return s if len(s) <= n else s[:n] + f"… [+{len(s) - n} chars]"


def act(step) -> str:
    a = step.action
    if a.tool == "editor":
        return f"editor {a.command} {a.args.get('path', '')}" + (f" view_range={a.args.get('view_range')}" if a.args.get("view_range") else "")
    return (a.command or a.raw or a.tool).strip().split("\n")[0][:200]


def collect() -> tuple[list[dict], dict]:
    cases, per_kind, totals = [], Counter(), Counter()
    for it, path in library.index():
        if it.dataset != "swe-smith":
            continue
        pt = pipeline.process(path, path.name, use_llm=False, sample_id=it.id)
        steps = pt.trajectory.steps
        for s in steps:
            if s.subcategory in ("keys", "harness_protocol"):
                continue
            totals["analisados"] += 1
            if "no_new_info" in s.flags:
                ref = (s.flag_refs or {}).get("no_new_info")
                kind = "releitura" if "releitura" in str(s.flag_details.get("no_new_info")) else "observação idêntica"
                per_kind[kind] += 1
                prev = steps[ref] if ref is not None and 0 <= ref < len(steps) else None
                cases.append({"sample": it.id, "split": it.split, "idx": s.idx, "ref": ref, "kind": kind, "reason": s.flag_details.get("no_new_info"),
                              "category": s.category, "action": act(s), "prev_action": act(prev) if prev else None,
                              "obs": cut(s.observation.content if s.observation else ""), "prev_obs": cut(prev.observation.content if prev and prev.observation else ""),
                              "edited_between": any(x.category == "edit" for x in steps[(ref or 0) + 1:s.idx]) if ref is not None else None,
                              "edits_between": [f"#{x.idx} {', '.join(fr.path for fr in x.files if fr.mode == 'edit') or '(arquivo não identificado)'}"
                                                for x in steps[(ref or 0) + 1:s.idx] if x.category == "edit"] if ref is not None else []})
    return cases, {"flagged": len(cases), "analisados": totals["analisados"], "por_tipo": dict(per_kind)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    cases, stats = collect()
    sample = random.Random(SEED).sample(cases, min(N, len(cases)))
    for i, c in enumerate(sample, 1):
        c["n"] = i
    if not args.render:
        print(json.dumps(stats, ensure_ascii=False))
        for c in sample:
            print(f"\n### {c['n']}. {c['sample']} #{c['idx']} ({c['kind']}; edições entre: {c['edits_between']})\nREASON: {c['reason']}\nAÇÃO #{c['idx']}: {c['action']}\n"
                  f"AÇÃO #{c['ref']}: {c['prev_action']}\nOBS atual: {c['obs'][:300]!r}\nOBS prev : {c['prev_obs'][:300]!r}")
        return
    verdicts = json.loads(VERDICTS.read_text())
    tally = Counter(v["verdict"] for v in verdicts.values())
    L = ["# Auditoria do detector `no_new_info` — SWE-smith", "",
         f"Gerado por `backend/scripts/audit_no_new_info.py` (semente {SEED}). Base: as 60 trajetórias de `data/samples/swe-smith/` — "
         f"{stats['flagged']} passos marcados de {stats['analisados']} analisados ({100 * stats['flagged'] / stats['analisados']:.1f}%); "
         f"por tipo: {stats['por_tipo']}. Abaixo, {len(sample)} casos sorteados; cada um mostra a ação, a ação anterior equivalente (`flag_refs`) e as duas observações (cortadas em 300 chars).", "",
         "## Resultado", "", "| veredito | casos | % |", "|---|---:|---:|"]
    for k, label in (("correto", "correto"), ("duvidoso", "duvidoso"), ("falso_positivo", "falso positivo")):
        L.append(f"| {label} | {tally[k]} | {100 * tally[k] / len(sample):.0f}% |")
    fp = tally["falso_positivo"] / len(sample)
    L += ["", f"Critério: ajustar a regra se > 25% forem falsos positivos → **{'AJUSTAR' if fp > 0.25 else 'manter a regra'}** ({100 * fp:.0f}% falsos positivos).", ""]
    note = VERDICTS.with_suffix(".note.md")
    if note.exists():
        L += [note.read_text().strip(), ""]
    L += ["## Casos", ""]
    for c in sample:
        v = verdicts.get(str(c["n"]), {"verdict": "?", "why": ""})
        L += [f"### {c['n']}. `{c['sample'].split('/', 1)[1][:60]}` #{c['idx']} — **{v['verdict'].replace('_', ' ')}**", "",
              f"- tipo: {c['kind']} · {c['reason']}", f"- ação #{c['idx']}: `{c['action']}`", f"- ação anterior #{c['ref']}: `{c['prev_action']}`",
              f"- edições entre os dois: {'; '.join(c['edits_between']) if c['edits_between'] else 'nenhuma'}", f"- motivo do veredito: {v['why']}", "",
              "```text", "# observação atual", c["obs"], "", "# observação anterior", c["prev_obs"], "```", ""]
    (ROOT / "results" / "audit_no_new_info.md").write_text("\n".join(L))
    print(f"results/audit_no_new_info.md — {dict(tally)}")


if __name__ == "__main__":
    main()
