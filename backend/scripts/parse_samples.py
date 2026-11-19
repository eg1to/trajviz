#!/usr/bin/env python
"""Roda detect + parse em todo data/samples/ e gera results/parse_report.md.

- SWE-rebench / SWE-smith: os JSON de data/samples/<dataset>/.
- CodeTraceBench: as 60 trajetórias de data/samples/codetracebench/_sample_ids.json, lidas do artefato
  .tar.zst original (data/raw/codetracebench/bench_artifacts/full/), com ground truth do manifest.
Critério de pronto: 100% em SWE-rebench/SWE-smith, ≥ 90% no CTB.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.base import UnsupportedArtifact  # noqa: E402
from app.adapters.detect import detect, parse_any  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
CTB = ROOT / "data" / "raw" / "codetracebench"


def unit_count(t, kind: str) -> int:
    """Nº de passos na UNIDADE que o benchmark usa para numerar `step_id` (hipótese por agente, formats.md §4.5)."""
    if kind == "episode":  # 1 passo do benchmark = 1 comando (keystrokes) de um episódio
        return sum(len(s.action.args.get("commands", [])) for s in t.steps)
    nomsg = sum(1 for s in t.steps if s.action.tool != "message")
    if kind == "run_rank":
        return nomsg
    if kind == "tool_call_rank":
        return nomsg - 1  # a última tool_call (finish) não entra
    return len(t.steps)


def targets():
    for p in sorted((SAMPLES / "swe-rebench").glob("chat*.json")):
        yield "SWE-rebench", p, "openhands_chat"
    for sp in ("tool", "xml", "ticks"):
        for p in sorted((SAMPLES / "swe-smith" / sp).glob("*.json")):
            yield f"SWE-smith/{sp}", p, "sweagent_smith"
    ids = json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text())
    for tid in ids:
        yield "CodeTraceBench", CTB / "bench_artifacts" / "full" / f"{tid}.tar.zst", None


def main() -> None:
    G: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    errs: dict[str, list[str]] = defaultdict(list)
    wrong_detect: list[str] = []
    for group, path, want in targets():
        g = G[group]
        g["files"] += 1
        try:
            name, conf = detect(path)
            if want and name != want:
                wrong_detect.append(f"{path.name}: {name} (esperado {want})")
            t = parse_any(path, manifest_dir=CTB)
        except UnsupportedArtifact as e:
            g["unsupported"] += 1
            errs[group].append(f"`{path.name[:60]}` — UnsupportedArtifact: {e}")
            continue
        except Exception as e:  # noqa: BLE001
            g["failed"] += 1
            errs[group].append(f"`{path.name[:60]}` — {type(e).__name__}: {str(e)[:160]}")
            continue
        g["ok"] += 1
        key = f"{group}|{t.source_format}"
        n = len(t.steps)
        g["steps"] += n
        g["with_obs"] += sum(1 for s in t.steps if s.observation is not None)
        g["with_exit"] += sum(1 for s in t.steps if s.observation is not None and s.observation.exit_code is not None)
        g["bash_steps"] += sum(1 for s in t.steps if s.action.tool in ("bash", "keys"))
        g["bash_exit"] += sum(1 for s in t.steps if s.observation is not None and s.observation.exit_code is not None
                              and s.action.tool in ("bash", "keys"))
        g["last_submit"] += bool(t.steps and t.steps[-1].action.tool == "submit")
        g["thought"] += sum(1 for s in t.steps if s.thought)
        g["all_fallback"] += all(s.category == "other" and s.label_source == "fallback" for s in t.steps)
        g.setdefault("formats", set()) if False else None
        G[group + "#fmt"][t.source_format] += 1
        if t.ground_truth is not None:
            gt = t.ground_truth
            sub = G[f"CodeTraceBench/{t.source_format}"]
            sub["n"] += 1
            sub["steps"] += n
            sub["sc_strict"] += n == gt.manifest_step_count
            sub["sc_unit"] += unit_count(t, gt.step_ref_kind) == gt.manifest_step_count
            sub["sc_unit_pm1"] += abs(unit_count(t, gt.step_ref_kind) - gt.manifest_step_count) <= 1
            sub["sc_nomsg"] += sum(1 for s in t.steps if s.action.tool != "message") == gt.manifest_step_count
            anns = [s for a in gt.annotations for s in a.steps]
            sub["ann"] += len(anns)
            sub["ann_ok"] += sum(1 for s in anns if s.resolved_idx is not None)
            sub["ann_confirmed"] += sum(1 for s in anns if s.resolved_via in ("action_ref", "rule"))
            sub["ann_hyp"] += sum(1 for s in anns if s.resolved_via == "hypothesis")
            sub["ann_ref"] += sum(1 for s in anns if s.resolved_via == "action_ref")
            g["ann"] += len(anns)
            g["ann_ok"] += sum(1 for s in anns if s.resolved_idx is not None)
            g["ann_confirmed"] += sum(1 for s in anns if s.resolved_via in ("action_ref", "rule"))
            g["sc_strict"] += n == gt.manifest_step_count
            g["with_gt"] += 1
        else:
            g["no_gt"] += 1
    pc = lambda a, b: f"{100 * a / b:.1f}%" if b else "—"  # noqa: E731
    L = ["# Relatório de parse (Fase 2)", "",
         "Gerado por `backend/scripts/parse_samples.py` — detect + parse de `data/samples/` "
         "(CodeTraceBench: os 60 artefatos `.tar.zst` do `--sample 60`, com ground truth do manifest `verified`).", "",
         "## Resumo por grupo", "",
         "| grupo | arquivos | sucesso | falhas | não suportado¹ | média de passos | % passos c/ observação | % passos c/ exit_code² | último = submit | passos c/ pensamento |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    order = ["SWE-rebench", "SWE-smith/tool", "SWE-smith/xml", "SWE-smith/ticks", "CodeTraceBench"]
    for k in order:
        g = G[k]
        if not g["files"]:
            continue
        ok = int(g["ok"])
        L.append(f"| {k} | {int(g['files'])} | {ok} ({pc(ok, g['files'])}) | {int(g['failed'])} | {int(g['unsupported'])} | "
                 f"{g['steps'] / ok:.1f} | {pc(g['with_obs'], g['steps'])} | {pc(g['bash_exit'], g['bash_steps'])} | "
                 f"{pc(g['last_submit'], ok)} | {pc(g['thought'], g['steps'])} |")
    L += ["", "¹ `UnsupportedArtifact`: artefato só com logs/asciinema (sem trajetória estruturada); erro claro e esperado, contado como não-sucesso.",
          "² % dos passos de ferramenta bash/keys com `exit_code` extraído (SWE-rebench e CTB-OpenHands/mini-SWE trazem exit code; SWE-smith/SWE-agent/Terminus2 não).", ""]
    ctb = {k: v for k, v in G.items() if k.startswith("CodeTraceBench/")}
    L += ["## CodeTraceBench por adaptador", "",
          "| adaptador | trajetórias | `step_count` do manifest = passos extraídos | idem, sem contar passos `message` | = na unidade do benchmark (exato / ±1)³ | anotações | alinhadas (`resolved_idx`) | confirmadas (action_ref/regra) | hipótese |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tot = defaultdict(float)
    for k in sorted(ctb):
        v = ctb[k]
        for f in ("n", "sc_strict", "sc_nomsg", "sc_unit", "sc_unit_pm1", "ann", "ann_ok", "ann_confirmed", "ann_hyp"):
            tot[f] += v[f]
        L.append(f"| {k.split('/')[1]} | {int(v['n'])} | {int(v['sc_strict'])}/{int(v['n'])} ({pc(v['sc_strict'], v['n'])}) | "
                 f"{int(v['sc_nomsg'])}/{int(v['n'])} | {int(v['sc_unit'])}/{int(v['n'])} / {int(v['sc_unit_pm1'])}/{int(v['n'])} | {int(v['ann'])} | {int(v['ann_ok'])} ({pc(v['ann_ok'], v['ann'])}) | "
                 f"{int(v['ann_confirmed'])} | {int(v['ann_hyp'])} |")
    L.append(f"| **total** | {int(tot['n'])} | {int(tot['sc_strict'])}/{int(tot['n'])} ({pc(tot['sc_strict'], tot['n'])}) | "
             f"{int(tot['sc_nomsg'])}/{int(tot['n'])} | {int(tot['sc_unit'])}/{int(tot['n'])} / {int(tot['sc_unit_pm1'])}/{int(tot['n'])} | {int(tot['ann'])} | {int(tot['ann_ok'])} ({pc(tot['ann_ok'], tot['ann'])}) | "
             f"{int(tot['ann_confirmed'])} ({pc(tot['ann_confirmed'], tot['ann'])}) | {int(tot['ann_hyp'])} |")
    L += ["", "³ Unidade do benchmark (hipótese por agente): SWE-agent/mini-SWE = passos; OpenHands-TB = ações ≠ `message`; "
          "Terminus2 = nº de comandos (`keystrokes`) somando os episódios; OpenHands-SWE = tool_calls − 1 (a última, `finish`, não entra).", "",
          "Alinhamento do `step_id`: **confirmado** = `action_ref` (id nativo do evento/episódio) ou regra do `step_ref_kind` validada; "
          "**hipótese** = cauda de OpenHands-TB/Terminus2 (unidades que o benchmark numera depois das primárias) e OpenHands-SWE "
          "(n-ésima tool_call) — ver docs/formats.md §4.5 e decisions.md.", ""]
    L += ["## Critério de pronto", "", "| critério | resultado | ok? |", "|---|---|---|"]
    for k, need in (("SWE-rebench", 1.0), ("SWE-smith/tool", 1.0), ("SWE-smith/xml", 1.0), ("SWE-smith/ticks", 1.0), ("CodeTraceBench", 0.9)):
        g = G[k]
        r = g["ok"] / g["files"] if g["files"] else 0
        L.append(f"| {k} ≥ {int(need * 100)}% | {int(g['ok'])}/{int(g['files'])} ({pc(g['ok'], g['files'])}) | {'✅' if r >= need else '❌'} |")
    L += ["", "## Formatos detectados", ""]
    for k in order:
        L.append(f"- **{k}**: {dict(G[k + '#fmt'])}")
    if wrong_detect:
        L += ["", "### Detecções divergentes do esperado", ""] + [f"- {w}" for w in wrong_detect]
    L += ["", "## Falhas e artefatos não suportados", ""]
    any_err = False
    for k in order:
        for e in errs.get(k, []):
            any_err = True
            L.append(f"- **{k}**: {e}")
    if not any_err:
        L.append("Nenhuma.")
    out = ROOT / "results" / "parse_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
