#!/usr/bin/env python
"""Cobertura da rotulação só com regras (data/samples/) + estimativa de custo do LLM (dry-run) → results/labeling_report.md.

    uv run python scripts/label_report.py                 # só regras + dry-run
    uv run python scripts/label_report.py --llm           # + UMA execução com LLM só em data/samples/swe-rebench/ (--budget 0.20)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.base import UnsupportedArtifact  # noqa: E402
from app.adapters.detect import parse_any  # noqa: E402
from app.config import LLMConfig  # noqa: E402
from app.labeling import RULE_MIN_CONF, label_trajectory  # noqa: E402
from app.labeling.llm import LLMLabeler  # noqa: E402
from app.labeling.rules import label_step_rules  # noqa: E402
from app.labeling.bash_parser import Ctx  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
CTB = ROOT / "data" / "raw" / "codetracebench"
CATS = ["explore", "search", "read", "edit", "reproduce", "test", "setup", "vcs", "think", "submit", "other"]


def sample_paths():
    for p in sorted((SAMPLES / "swe-rebench").glob("chat*.json")):
        yield "SWE-rebench", "OpenHands", p
    for sp in ("tool", "xml", "ticks"):
        for p in sorted((SAMPLES / "swe-smith" / sp).glob("*.json")):
            yield "SWE-smith", "SWE-agent", p
    for tid in json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text()):
        yield "CodeTraceBench", None, CTB / "bench_artifacts" / "full" / f"{tid}.tar.zst"


def verified_present():
    ids = {json.loads(line)["traj_id"] for line in (CTB / "bench_manifest.verified.jsonl").read_text().splitlines()}
    present = sorted(p for p in (CTB / "bench_artifacts" / "full").glob("*.tar.zst") if p.name[:-8] in ids)
    return present, len(ids)


def cmd_key(step) -> str:
    a = step.action
    if a.tool in ("bash", "keys", "ipython"):
        return (step.subcategory or (a.command or "").split("\n")[0][:30] or a.tool).split("|")[0][:40]
    return f"[{a.tool_native or a.tool}] {a.command or ''}".strip()[:40]


def pc(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="roda UMA vez o LLM só em data/samples/swe-rebench/")
    ap.add_argument("--budget", type=float, default=0.20)
    args = ap.parse_args()

    groups = defaultdict(lambda: {"traj": 0, "steps": 0, "src": Counter(), "cat": Counter(), "other_nokeys": 0, "keys": 0})
    amb = defaultdict(Counter)  # dataset → chave → n (passos other ou conf < 0.6)
    cand: dict[str, list] = defaultdict(list)  # dataset → [(traj, [passos candidatos])]
    parsed: dict[str, list] = defaultdict(list)
    for ds, agent, p in sample_paths():
        try:
            t = parse_any(p, manifest_dir=CTB)
        except UnsupportedArtifact:
            continue
        label_trajectory(t)
        ag = agent or t.agent
        parsed[ds].append(t)
        for key in (ds, f"{ds} · {ag}"):
            g = groups[key]
            g["traj"] += 1
            g["steps"] += len(t.steps)
            for s in t.steps:
                g["src"][s.label_source] += 1
                g["cat"][s.category] += 1
                if s.subcategory == "keys":
                    g["keys"] += 1
                elif s.category == "other":
                    g["other_nokeys"] += 1
        pend = [s for s in t.steps if s.label_source == "fallback"]
        for s in t.steps:
            if s.category == "other" and s.subcategory != "keys" or s.confidence < RULE_MIN_CONF:
                amb[ds][cmd_key(s)] += 1
        if pend:
            cand[ds].append((t, pend))
    L = ["# Relatório de rotulação (Fase 3) — só regras", "",
         "Gerado por `backend/scripts/label_report.py` sobre `data/samples/` (CodeTraceBench: os 58 artefatos estruturados do `--sample 60`).", "",
         "`label_source`: **rule** = ferramenta exata ou comando com confiança ≥ 0,6; **fallback** = melhor palpite da regra com confiança < 0,6 "
         "(candidato ao LLM). `other` não conta as teclas de controle (`subcategory=keys`, rótulo correto).", "",
         "## Cobertura por dataset e agente", "",
         "| grupo | traj. | passos | rule | fallback | other (sem keys) | keys | " + " | ".join(CATS) + " |",
         "|---|---:|---:|---:|---:|---:|---:|" + "---:|" * len(CATS)]
    for k in sorted(groups, key=lambda x: (x.split(" ·")[0], " ·" in x, x)):
        g = groups[k]
        n = g["steps"]
        L.append(f"| {'**' + k + '**' if ' ·' not in k else '&nbsp;&nbsp;' + k.split(' · ')[1]} | {g['traj']} | {n} | {pc(g['src']['rule'], n)} | "
                 f"{pc(g['src']['fallback'], n)} | {pc(g['other_nokeys'], n)} | {pc(g['keys'], n)} | "
                 + " | ".join(pc(g['cat'][c], n) for c in CATS) + " |")
    L += ["", "## Critério: `other` (sem keys) < 15% por dataset", ""]
    for ds in ("SWE-rebench", "SWE-smith", "CodeTraceBench"):
        g = groups[ds]
        r = g["other_nokeys"] / g["steps"]
        L.append(f"- {ds}: {pc(g['other_nokeys'], g['steps'])} {'✅' if r < 0.15 else '❌'}")
    L += ["", "## Top 30 comandos/executáveis que ficaram `other` ou com confiança < 0,6 (o que o LLM recebe)", ""]
    allamb = Counter()
    for c in amb.values():
        allamb.update(c)
    L += ["| # | comando/executável | passos | datasets |", "|---|---|---:|---|"]
    for i, (k, n) in enumerate(allamb.most_common(30), 1):
        L.append(f"| {i} | `{k}` | {n} | {', '.join(d for d in amb if amb[d][k]) } |")
    # ---- dry-run
    lab = LLMLabeler(LLMConfig.from_env())
    L += ["", "## Estimativa de custo do LLM (dry-run, sem rede)", "",
          f"Modelo `{lab.cfg.model}` · preços US$ 0,10 / 0,50 por MTok (cache hit 0,01) · 1 requisição por trajetória · "
          "tokens ≈ caracteres/3,2 (conservador).", "",
          "| conjunto | trajetórias | passos p/ LLM | requisições | tokens de entrada | tokens de saída | custo sem cache | custo c/ cache do system |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for ds in ("SWE-rebench", "SWE-smith", "CodeTraceBench"):
        e = lab.estimate(cand[ds])
        L.append(f"| amostras {ds} | {len(parsed[ds])} | {e['steps']} | {e['requests']} | {e['input_tokens']:,} | {e['output_tokens']:,} | US$ {e['cost_usd_no_cache']:.4f} | US$ {e['cost_usd_with_cache']:.4f} |")
    present, total = verified_present()
    vc = []
    for p in present:
        try:
            t = parse_any(p, manifest_dir=CTB)
        except UnsupportedArtifact:
            continue
        except Exception as e:  # noqa: BLE001
            print("ERRO", p.name, type(e).__name__, file=sys.stderr)
            continue
        label_trajectory(t)
        pend = [s for s in t.steps if s.label_source == "fallback"]
        if pend:
            vc.append((t, pend))
    ntraj = len(present)
    e = lab.estimate(vc)
    scale = total / ntraj if ntraj else 0
    L.append(f"| CTB `verified` — {ntraj} artefatos presentes de {total} | {ntraj} | {e['steps']} | {e['requests']} | {e['input_tokens']:,} | {e['output_tokens']:,} | US$ {e['cost_usd_no_cache']:.4f} | US$ {e['cost_usd_with_cache']:.4f} |")
    L.append(f"| CTB `verified` — extrapolado p/ {total} (×{scale:.2f}) | {total} | {int(e['steps'] * scale)} | {int(e['requests'] * scale)} | {int(e['input_tokens'] * scale):,} | {int(e['output_tokens'] * scale):,} | US$ {e['cost_usd_no_cache'] * scale:.4f} | US$ {e['cost_usd_with_cache'] * scale:.4f} |")
    L += ["", f"O `--all` do download tinha {ntraj}/{total} artefatos do `verified` no disco na hora do relatório (a extrapolação é linear)."]
    # ---- execução real com LLM (uma vez, só SWE-rebench)
    if args.llm:
        cfg = LLMConfig.from_env()
        cfg.enabled, cfg.budget_usd = True, args.budget
        if not cfg.api_key:
            L += ["", "## Execução com LLM", "", "`ANTHROPIC_API_KEY` ausente — execução pulada."]
        else:
            llm = LLMLabeler(cfg)
            before = llm.total.cost_usd
            dist, moved = Counter(), Counter()
            n_llm = n_trajs = 0
            for t in parsed["SWE-rebench"]:
                snap = {s.idx: s.category for s in t.steps}
                label_trajectory(t, llm)
                n_trajs += 1
                for s in t.steps:
                    if s.label_source == "llm":
                        n_llm += 1
                        dist[s.category] += 1
                        moved[(snap[s.idx], s.category)] += 1
                if llm.budget_exhausted:
                    break
            r = llm.run
            L += ["", "## Execução com LLM (uma vez, só `data/samples/swe-rebench/`)", "",
                  f"- Modelo `{cfg.model}` · orçamento US$ {args.budget:.2f} · trajetórias processadas: {n_trajs}/{len(parsed['SWE-rebench'])}"
                  f"{' · **orçamento atingido**' if llm.budget_exhausted else ''}",
                  f"- Requisições: {r.requests} · passos rotulados pelo LLM: {n_llm} · passos vindos do cache: {llm.total.cache_hits_steps}",
                  f"- Tokens: entrada {r.input_tokens:,} · saída {r.output_tokens:,} · cache leitura {r.cache_read_tokens:,} · cache escrita {r.cache_write_tokens:,}",
                  f"- **Custo real desta execução: US$ {r.cost_usd:.4f}** (acumulado em `.cache/llm_usage.json`: US$ {llm.total.cost_usd:.4f}; antes: US$ {before:.4f})",
                  f"- Erros: {llm.errors or 'nenhum'}", "",
                  "Distribuição dos rótulos dados pelo LLM: " + ", ".join(f"{k} {v}" for k, v in dist.most_common()), "",
                  "Maiores mudanças (palpite da regra → LLM): " + ", ".join(f"{a}→{b}: {n}" for (a, b), n in moved.most_common(8))]
            # cobertura depois do LLM
            tot = sum(len(t.steps) for t in parsed["SWE-rebench"])
            oth = sum(1 for t in parsed["SWE-rebench"] for s in t.steps if s.category == "other" and s.subcategory != "keys")
            L.append(f"\n`other` (sem keys) em SWE-rebench depois do LLM: {pc(oth, tot)}.")
    out = ROOT / "results" / "labeling_report.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
