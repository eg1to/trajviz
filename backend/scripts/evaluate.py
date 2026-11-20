#!/usr/bin/env python
"""Acurácia do classificador de categorias: regras × LLM × gold manual. Escreve results/eval_classifier.md (+ figuras).

Lê results/gold/gold_steps_pedro.csv (ou gold_steps.csv) e usa só as linhas com `gold_category` preenchida.
A comparação em três vias roda o Haiku em TODOS os passos do gold, ignorando as regras (orçamento máx. US$ 0,05).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RESULTS, ROOT, SEED, artifact, ci95, fmt, fmt_ci, run_pipeline  # noqa: E402

from app.config import LLMConfig  # noqa: E402
from app.labeling.llm import LLMLabeler  # noqa: E402
from app.labeling.taxonomy import Category  # noqa: E402

CATS = [c.value for c in Category]
GOLD_DIR = RESULTS / "gold"
BUDGET = 0.05
B = 2000
SAMPLES = ROOT / "data" / "samples"
MIN_ROWS = 70


def load_gold() -> tuple[list[dict], Path]:
    """Junta o CSV CEGO preenchido (results/gold/gold_steps_cego.csv: contexto + gold_category) com as previsões
    (gold_steps_previsoes.csv, que o rotulador NÃO deve abrir), pelo `id`. O cego nunca contém rótulos da regra nem do LLM."""
    blind = GOLD_DIR / "gold_steps_cego.csv"
    gold = {r["id"]: (r.get("gold_category") or "").strip().lower() for r in csv.DictReader(blind.open())}
    rows = list(csv.DictReader((GOLD_DIR / "gold_steps_previsoes.csv").open()))
    for r in rows:
        r["idx"] = int(r["idx"])
        r["gold"] = gold.get(r["id"], "")
    return rows, blind


def index_trajectories(ids: set[str]) -> dict:
    """traj_id → Trajectory (processado só com regras) para as amostras de data/samples/."""
    out = {}
    paths = list((SAMPLES / "swe-rebench").glob("chat*.json")) + [p for sp in ("tool", "xml", "ticks") for p in (SAMPLES / "swe-smith" / sp).glob("*.json")]
    paths += [artifact(t) for t in json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text())]
    for p in paths:
        try:
            traj, _, _ = run_pipeline(p)
        except Exception:  # noqa: BLE001
            continue
        if traj.id in ids:
            out[traj.id] = traj
    return out


def run_llm(rows: list[dict]) -> tuple[dict[tuple[str, int], str], dict]:
    cfg = LLMConfig.from_env()
    cfg.enabled, cfg.budget_usd = True, BUDGET
    info = {"enabled": bool(cfg.api_key), "model": cfg.model, "budget_usd": BUDGET, "cost_usd": 0.0, "requests": 0, "labeled": 0, "from_cache": 0, "errors": []}
    if not cfg.api_key:
        info["errors"].append("ANTHROPIC_API_KEY ausente")
        return {}, info
    trajs = index_trajectories({r["traj_id"] for r in rows})
    lab = LLMLabeler(cfg)
    out: dict[tuple[str, int], str] = {}
    by_traj = defaultdict(list)
    for r in rows:
        by_traj[r["traj_id"]].append(r["idx"])
    cached_before = lab.total.cache_hits_steps
    for tid, idxs in by_traj.items():
        t = trajs.get(tid)
        if t is None:
            info["errors"].append(f"trajetória {tid[:30]} não encontrada")
            continue
        steps = [t.steps[i] for i in idxs if i < len(t.steps)]
        res = lab.label_steps(t, steps)  # força o LLM: não consulta as regras
        for i, lab_ in res.items():
            out[(tid, i)] = lab_.category
        if lab.budget_exhausted:
            info["errors"].append("orçamento atingido")
            break
    info.update(cost_usd=lab.run.cost_usd, requests=lab.run.requests, labeled=len(out), from_cache=lab.total.cache_hits_steps - cached_before,
                tokens={"in": lab.run.input_tokens, "out": lab.run.output_tokens, "cache_read": lab.run.cache_read_tokens, "cache_write": lab.run.cache_write_tokens})
    info["errors"] += sorted(set(lab.errors))
    return out, info


# ----------------------------------------------------------------------------- métricas
def conf_matrix(y, p, labels=CATS):
    ix = {c: i for i, c in enumerate(labels)}
    m = np.zeros((len(labels), len(labels)), int)
    for a, b in zip(y, p):
        if a in ix and b in ix:
            m[ix[a], ix[b]] += 1
    return m


def accuracy(y, p):
    return float(np.mean([a == b for a, b in zip(y, p)])) if len(y) else float("nan")


def f1_per_class(y, p, labels=CATS):
    out = {}
    for c in labels:
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        out[c] = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else float("nan")
    return out


def macro_f1(y, p, labels=CATS):
    present = [c for c in labels if c in set(y) | set(p)]
    f = f1_per_class(y, p, present)
    v = [x for x in f.values() if x == x]
    return float(np.mean(v)) if v else float("nan")


def kappa(a, b, labels=CATS):
    n = len(a)
    if not n:
        return float("nan")
    po = np.mean([x == y for x, y in zip(a, b)])
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] / n * cb[c] / n for c in labels)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def boot(y, p, fn, rng, b=B):
    y, p = np.array(y), np.array(p)
    vals = []
    for _ in range(b):
        ix = rng.integers(0, len(y), len(y))
        vals.append(fn(list(y[ix]), list(p[ix])))
    return ci95(vals)


def block(name, y, p, rng):
    if not y:
        return f"| {name} | 0 | — | — |"
    return f"| {name} | {len(y)} | {fmt_ci(accuracy(y, p), boot(y, p, accuracy, rng), 3)} | {fmt_ci(macro_f1(y, p), boot(y, p, macro_f1, rng), 3)} |"


def plot_confusion(y, p, title, path_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    m = conf_matrix(y, p)
    norm = m / np.maximum(m.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=300)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(CATS))); ax.set_yticks(range(len(CATS)))
    ax.set_xticklabels(CATS, rotation=45, ha="right", fontsize=8); ax.set_yticklabels(CATS, fontsize=8)
    for i in range(len(CATS)):
        for j in range(len(CATS)):
            if m[i, j]:
                ax.text(j, i, str(m[i, j]), ha="center", va="center", fontsize=7, color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xlabel("previsto"); ax.set_ylabel("gold (manual)"); ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path_png, facecolor="white"); fig.savefig(path_png.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


def main() -> None:
    rows, path = load_gold()
    filled = [r for r in rows if r["gold"]]
    invalid = [r for r in filled if r["gold"] not in CATS]
    filled = [r for r in filled if r["gold"] in CATS]
    rng = np.random.default_rng(SEED)
    llm_map, info = run_llm(rows)
    for r in rows:
        r["llm"] = llm_map.get((r["traj_id"], r["idx"]), "")
    L = ["# Acurácia do classificador de categorias", "",
         f"`backend/scripts/evaluate.py` · gold: `{path.relative_to(ROOT)}` (CSV cego, sem rótulos de regra/LLM; as previsões ficam em `gold_steps_previsoes.csv`) · semente {SEED} · IC 95% por bootstrap sobre passos (B={B}).", ""]
    if len(filled) < MIN_ROWS:
        L += [f"> ⚠️ **AMOSTRA PEQUENA / SEM GOLD**: apenas **{len(filled)}** de {len(rows)} linhas têm `gold_category` preenchida (mínimo recomendado: {MIN_ROWS}). "
              + ("Acurácia, F1 e matriz de confusão **não puderam ser calculados**; o relatório abaixo traz só a comparação regra × LLM (que não depende do gold). " if not filled else
                 "Os intervalos de confiança são muito largos: leia como indicativo, não como medida. "), ""]
    if invalid:
        L += [f"> {len(invalid)} linhas têm `gold_category` inválida (ignoradas): {sorted({r['gold'] for r in invalid})}", ""]
    L += [f"- Linhas no CSV: {len(rows)} · com gold válido: **{len(filled)}** · valores aceitos: {', '.join(CATS)}.", ""]
    # ---- LLM
    L += ["## Execução do LLM em todos os passos do gold (ignorando as regras)", "",
          f"Modelo `{info['model']}` · orçamento máximo US$ {BUDGET:.2f} · passos rotulados: {info['labeled']}/{len(rows)} (do cache: {info['from_cache']}) · requisições: {info['requests']} · "
          f"**custo desta execução: US$ {info['cost_usd']:.4f}** (acumulado do projeto em `.cache/llm_usage.json`: US$ {json.loads((ROOT / 'backend' / '.cache' / 'llm_usage.json').read_text())['cost_usd']:.4f}; a 1ª execução pagou US$ 0,0199 e as seguintes reaproveitam o cache)" + (f" · tokens {info.get('tokens')}" if info.get("tokens") else "") + (f" · avisos: {info['errors']}" if info["errors"] else ""), ""]
    both = [r for r in rows if r["llm"]]
    rule_vs_llm = {}
    if both:
        a, b = [r["pred_category"] for r in both], [r["llm"] for r in both]
        rule_vs_llm = {"n": len(both), "agreement": accuracy(a, b), "kappa": kappa(a, b),
                       "agreement_ci": ci95([accuracy(list(np.array(a)[ix]), list(np.array(b)[ix])) for ix in (rng.integers(0, len(a), len(a)) for _ in range(B))]),
                       "kappa_ci": ci95([kappa(list(np.array(a)[ix]), list(np.array(b)[ix])) for ix in (rng.integers(0, len(a), len(a)) for _ in range(B))])}
        L += ["## Concordância regra × LLM (não depende do gold)", "",
              f"- n = {len(both)} passos · concordância **{fmt_ci(rule_vs_llm['agreement'], rule_vs_llm['agreement_ci'])}** · kappa de Cohen **{fmt_ci(rule_vs_llm['kappa'], rule_vs_llm['kappa_ci'])}**", ""]
        by_src = defaultdict(lambda: [[], []])
        for r in both:
            by_src[r["label_source"]][0].append(r["pred_category"]); by_src[r["label_source"]][1].append(r["llm"])
        L += ["| origem do rótulo da regra | n | concordância com o LLM |", "|---|---:|---:|"]
        for k, (x, y) in by_src.items():
            L.append(f"| {k} | {len(x)} | {fmt(accuracy(x, y))} |")
        dis = Counter((r["pred_category"], r["llm"]) for r in both if r["pred_category"] != r["llm"])
        L += ["", "Maiores divergências (regra → LLM): " + ", ".join(f"{a}→{b}: {n}" for (a, b), n in dis.most_common(8)), ""]
    # ---- gold
    figs = []
    summary = {"gold_rows": len(rows), "gold_filled": len(filled), "llm": info, "rule_vs_llm": rule_vs_llm}
    if filled:
        y = [r["gold"] for r in filled]
        pr = [r["pred_category"] for r in filled]
        L += ["## Regras × gold", "", "| recorte | n | acurácia [IC95] | F1 macro [IC95] |", "|---|---:|---|---|", block("todos", y, pr, rng)]
        for ds in sorted({r["dataset"] for r in filled}):
            sub = [r for r in filled if r["dataset"] == ds]
            L.append(block(f"dataset = {ds}", [r["gold"] for r in sub], [r["pred_category"] for r in sub], rng))
        for src in sorted({r["label_source"] for r in filled}):
            sub = [r for r in filled if r["label_source"] == src]
            L.append(block(f"label_source = {src}", [r["gold"] for r in sub], [r["pred_category"] for r in sub], rng))
        f1c = f1_per_class(y, pr)
        L += ["", "### F1 por categoria", "", "| categoria | n gold | F1 |", "|---|---:|---:|"] + [f"| {c} | {sum(1 for v in y if v == c)} | {fmt(f1c[c])} |" for c in CATS]
        m = conf_matrix(y, pr)
        L += ["", "### Matriz de confusão (linhas = gold, colunas = regra)", "", "| gold \\ previsto | " + " | ".join(CATS) + " |", "|---|" + "---:|" * len(CATS)]
        L += [f"| **{c}** | " + " | ".join(str(m[i, j]) for j in range(len(CATS))) + " |" for i, c in enumerate(CATS)]
        plot_confusion(y, pr, f"Regras × gold (n={len(y)})", RESULTS / "figures" / "matriz_confusao.png")
        figs.append("results/figures/matriz_confusao.png")
        base = Counter(y).most_common(1)[0]
        L += ["", f"Linha de base trivial (sempre `{base[0]}`): acurácia {base[1] / len(y):.3f}.", ""]
        ly = [r for r in filled if r["llm"]]
        if ly:
            yg = [r["gold"] for r in ly]
            L += ["## Três vias: regra × LLM × gold (nos mesmos passos)", "", "| método | n | acurácia [IC95] | F1 macro [IC95] |", "|---|---:|---|---|",
                  block("regras", yg, [r["pred_category"] for r in ly], rng), block("LLM (Haiku 5.5, todos os passos)", yg, [r["llm"] for r in ly], rng), ""]
            L += [f"Kappa regra×gold {fmt(kappa([r['pred_category'] for r in ly], yg))} · LLM×gold {fmt(kappa([r['llm'] for r in ly], yg))} · regra×LLM {fmt(kappa([r['pred_category'] for r in ly], [r['llm'] for r in ly]))}", ""]
            summary["three_way"] = {"n": len(ly), "rule_acc": accuracy(yg, [r["pred_category"] for r in ly]), "llm_acc": accuracy(yg, [r["llm"] for r in ly])}
        summary["rule_acc"] = accuracy(y, pr)
        summary["rule_macro_f1"] = macro_f1(y, pr)
    else:
        L += ["## Regras × gold", "", "Sem linhas com `gold_category` preenchida: nada a calcular. Preencha a coluna no CSV (11 categorias: " + ", ".join(CATS) + ") e rode `uv run python scripts/evaluate.py` de novo.", ""]
    # distribuição de rótulos previstos no gold (informativa)
    L += ["## Distribuição dos rótulos previstos nos 210 passos do gold", "", "| categoria | regras | LLM |", "|---|---:|---:|"]
    cr, cl = Counter(r["pred_category"] for r in rows), Counter(r["llm"] for r in rows if r["llm"])
    L += [f"| {c} | {cr[c]} | {cl[c]} |" for c in CATS]
    (RESULTS / "eval_classifier.md").write_text("\n".join(L) + "\n")
    (RESULTS / "eval_classifier.json").write_text(json.dumps({**summary, "figures": figs}, indent=1, ensure_ascii=False, default=float))
    with (RESULTS / "eval_classifier_llm_labels.csv").open("w", newline="") as f:  # fora de results/gold/: o rotulador não deve vê-los antes de terminar
        w = csv.writer(f); w.writerow(["id", "llm_category"]); [w.writerow([r["id"], r["llm"]]) for r in rows if r["llm"]]
    print("\n".join(L))


if __name__ == "__main__":
    main()
