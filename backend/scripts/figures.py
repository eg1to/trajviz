#!/usr/bin/env python
"""Figuras do pôster (matplotlib; paleta do front; fundo branco; PNG 300 dpi + SVG) em results/figures/.
Depende de: results/batch_stats.{parquet,json}, results/eval_detectors.json (e results/eval_classifier.json para a matriz de confusão)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CTB_DIR, RESULTS, ROOT, SEED, run_pipeline  # noqa: E402
from export_palette import export  # noqa: E402

FIG = RESULTS / "figures"
PAL = export()
K = PAL["kinds"]
PH = PAL["phase_color"]
PHASES = ["Entendimento", "Modificação", "Verificação", "Controle"]
GOOD, BAD = "#009E73", "#D55E00"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Arial"], "figure.facecolor": "white", "axes.facecolor": "white",
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e5e5e5", "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold"})


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("figura:", name)


# ----------------------------------------------------------------------------- 1. fases por terço
def fig_phases(df: pd.DataFrame) -> None:
    d = df[df.dataset == "SWE-rebench"]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    w = 0.38
    for ti in range(3):
        for gi, (flag, label) in enumerate([(True, "resolvidas"), (False, "não resolvidas")]):
            g = d[d.resolved == flag]
            bottom = 0.0
            x = ti + (gi - 0.5) * (w + 0.04)
            for p in PHASES:
                v = float(g[f"t{ti + 1}_{p}"].mean() * 100)
                ax.bar(x, v, w, bottom=bottom, color=PH[p], edgecolor="white", linewidth=0.6, hatch="" if gi == 0 else "//")
                if v > 6:
                    ax.text(x, bottom + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white" if p in ("Entendimento", "Verificação", "Controle") else "black")
                bottom += v
            ax.text(x, -4, "R" if gi == 0 else "N", ha="center", va="top", fontsize=8, fontweight="bold")
    ax.set_xticks(range(3)); ax.set_xticklabels(["1º terço", "2º terço", "3º terço"], fontsize=9)
    ax.tick_params(axis="x", pad=14)
    ax.set_ylabel("% dos passos do terço (média por trajetória)"); ax.set_ylim(0, 100)
    ax.legend(handles=[Patch(color=PH[p], label=p) for p in PHASES] + [Patch(facecolor="white", edgecolor="black", label="R = resolvidas"), Patch(facecolor="white", edgecolor="black", hatch="//", label="N = não resolvidas")],
              loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False, fontsize=8)
    ax.set_title(f"Fases ao longo da trajetória — SWE-rebench (n = {int((d.resolved == True).sum())} + {int((d.resolved == False).sum())})", loc="left")  # noqa: E712
    ax.grid(axis="x", visible=False)
    save(fig, "fases_por_terco_resolvidas_vs_nao")


# ----------------------------------------------------------------------------- 2. métricas
def fig_metrics(df: pd.DataFrame, stats: dict) -> None:
    key = next(k for k in stats["strata"] if k.startswith("SWE-rebench"))
    rows = [r for r in stats["strata"][key] if r["delta"] == r["delta"]]
    top = sorted(rows, key=lambda r: -abs(r["delta"]))[:6]
    d = df[df.dataset == "SWE-rebench"]
    fig, axes = plt.subplots(2, 3, figsize=(9.5, 6.0))
    for ax, r in zip(axes.flat, top):
        col = r["metric"]
        data = [d[(d.resolved == True)][col].dropna().to_numpy(), d[(d.resolved == False)][col].dropna().to_numpy()]  # noqa: E712
        parts = ax.violinplot(data, showextrema=False, widths=0.8)
        for pc, c in zip(parts["bodies"], (GOOD, BAD)):
            pc.set_facecolor(c); pc.set_alpha(0.35); pc.set_edgecolor(c)
        bp = ax.boxplot(data, widths=0.22, showfliers=False, patch_artist=True, medianprops={"color": "black", "linewidth": 1.4})
        for b, c in zip(bp["boxes"], (GOOD, BAD)):
            b.set_facecolor(c); b.set_alpha(0.8)
        ax.set_xticks([1, 2]); ax.set_xticklabels(["resolvidas", "não resolvidas"], fontsize=8)
        p = r["p_holm"]
        ax.set_title(f"{r['label']}\nδ de Cliff = {r['delta']:+.2f} · p(Holm) {'< 0,001' if p < 0.001 else f'= {p:.3f}'.replace('.', ',')}", fontsize=8.5, loc="left")
        ax.grid(axis="x", visible=False)
    fig.suptitle("Resolvidas × não resolvidas (SWE-rebench; as 6 métricas com maior efeito) — δ > 0: maior nas resolvidas", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, "metricas_resolvidas_vs_nao")


# ----------------------------------------------------------------------------- 3. detectores × gabarito
def fig_detectors() -> None:
    o = json.loads((RESULTS / "eval_detectors.json").read_text())
    tasks = ["unuseful × repeated ∪ no_new_info", "incorrect × error ∪ test_fail", "incorrect × loop", "estágio incorreto × ≥ 1 flag"]
    names = ["inútil × repeated ∪\nno_new_info (passo)", "incorreto × error ∪\ntest_fail (passo)", "incorreto × loop\n(passo)", "estágio incorreto ×\n≥ 1 flag (estágio)"]
    rs = [next(r for r in o["results"] if r["task"] == t and r["slice"] == "todos") for t in tasks]
    bj = json.loads((RESULTS / "eval_detectors_before.json").read_text())  # antes da correção de test_fail/loop
    bs_ = [next(r for r in bj["results"] if r["task"] == t and r["slice"] == "todos") for t in tasks]
    fig, ax = plt.subplots(figsize=(9.4, 4.4))
    x = np.arange(len(rs))
    w = 0.34
    for off, key, label, color in ((-w / 2 - 0.02, "precision", "precisão", "#0072B2"), (w / 2 + 0.02, "recall", "revocação", "#E69F00")):
        v = np.array([r[key] for r in rs])
        lo = v - np.array([r[f"{key}_ci"][0] for r in rs]); hi = np.array([r[f"{key}_ci"][1] for r in rs]) - v
        ax.bar(x + off, v * 100, w, color=color, label=label, yerr=[lo * 100, hi * 100], capsize=3, error_kw={"lw": 1})
        base = np.array([r["base_precision"] if key == "precision" else r["base_recall"] for r in rs])
        for xi, b in zip(x + off, base):
            ax.plot([xi - w / 2, xi + w / 2], [b * 100] * 2, color="black", lw=2, solid_capstyle="butt")
        for xi, vi in zip(x + off, v):
            ax.text(xi, vi * 100 + 1.5, f"{vi * 100:.1f}", ha="center", fontsize=7)
    ax.plot([], [], color="black", lw=2, label="linha de base aleatória (mesma nº de flags)")
    for xi, r, b in zip(x, rs, bs_):
        ax.text(xi, 62, f"lift F1 = {r['lift_f1']:.2f}× (antes {b['lift_f1']:.2f}×)\nIC [{r['lift_ci'][0]:.2f}; {r['lift_ci'][1]:.2f}] · {r['n_pred']} marcados (antes {b['n_pred']})", ha="center", va="top", fontsize=7, fontweight="bold",
                color="#009E73" if r["lift_ci"][0] > 1 else "#D55E00" if r["lift_ci"][1] < 1 else "#555")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("%"); ax.set_ylim(0, 65)
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.set_title(f"Detectores × gabarito do CodeTraceBench, depois da correção de test_fail e loop (n = {o['n_evaluated']}; IC 95% bootstrap)", loc="left", fontsize=9)
    ax.grid(axis="x", visible=False)
    save(fig, "detectores_vs_gabarito")


# ----------------------------------------------------------------------------- 4. faixas de exemplo
def strip_data():
    res, non = [], []
    for p in sorted((ROOT / "data" / "samples" / "swe-rebench").glob("chat*.json")):
        j = json.loads(p.read_text())
        traj, m, _ = run_pipeline(p)
        if 50 <= len(traj.steps) <= 95:
            (res if j["resolved"] == 1 else non).append((traj, m))
    rng = np.random.default_rng(SEED)

    def pick(group):  # 3 trajetórias de tamanho próximo à mediana, com pelo menos um ciclo edit→test e distintas entre si
        med = np.median([len(t.steps) for t, _ in group])
        cand = [g for g in group if g[1].dynamics.edit_test_cycles >= 1] or group
        cand = sorted(cand, key=lambda g: abs(len(g[0].steps) - med))[:8]
        idx = rng.choice(len(cand), 3, replace=False)
        return sorted((cand[i] for i in idx), key=lambda g: len(g[0].steps))
    return pick(res), pick(non)


def draw_strip(ax, traj, m, y, h=0.55):
    from matplotlib.patches import Rectangle
    n = len(traj.steps)
    w = 1.0 / n
    for s in traj.steps:
        kind = "harness_protocol" if s.subcategory == "harness_protocol" else "keys" if s.subcategory == "keys" else "message" if s.action.tool == "message" else s.category
        k = K[kind]
        r = Rectangle((s.idx * w, y), w * 0.94, h, facecolor=("#E4E4E7" if k["special"] else k["color"]), hatch="////" if k["special"] else None, edgecolor="#9ca3af" if k["special"] else "none", linewidth=0.3)
        ax.add_patch(r)
        if "error" in s.flags:
            ax.add_patch(Rectangle((s.idx * w, y - 0.09), w * 0.94, 0.06, facecolor=PAL["error_color"], edgecolor="none"))
        if "test_fail" in s.flags:
            ax.text(s.idx * w + w / 2, y + h / 2, "✕", ha="center", va="center", fontsize=6, color="white", fontweight="bold")
        if "test_pass" in s.flags:
            ax.text(s.idx * w + w / 2, y + h / 2, "✓", ha="center", va="center", fontsize=6, color="white", fontweight="bold")
    for lp in traj.meta.get("loops", []):
        ax.add_patch(Rectangle((lp["range"][0] * w, y + h + 0.05), (lp["range"][1] - lp["range"][0] + 1) * w, 0.07, facecolor=PAL["error_color"], edgecolor="none"))


def fig_strips() -> None:
    res, non = strip_data()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    y = 0.0
    labels = []
    for tag, group, color in (("RESOLVIDA", res, GOOD), ("NÃO RESOLVIDA", non, BAD)):
        for traj, m in group:
            draw_strip(ax, traj, m, y)
            name = (traj.task_id or traj.id)[:38]
            ax.text(-0.012, y + 0.27, f"{tag}", ha="right", va="center", fontsize=7.5, fontweight="bold", color=color)
            ax.text(-0.012, y + 0.08, f"{len(traj.steps)} passos", ha="right", va="center", fontsize=7, color="#444")
            ax.text(1.008, y + 0.27, name, ha="left", va="center", fontsize=6.5, color="#444")
            y += 0.95
        y += 0.35
    ax.set_xlim(0, 1); ax.set_ylim(-0.3, y)
    ax.invert_yaxis(); ax.axis("off")
    handles = [Patch(color=PH[p], label=p) for p in PHASES]
    cats = [("explore", "Explorar"), ("search", "Buscar"), ("read", "Ler"), ("edit", "Editar"), ("reproduce", "Reproduzir"), ("test", "Testar"), ("vcs", "Versionar"), ("setup", "Preparar"), ("think", "Pensar"), ("submit", "Entregar")]
    handles = [Patch(facecolor=K[c]["color"], label=l) for c, l in cats] + [Patch(facecolor="#E4E4E7", hatch="////", edgecolor="#9ca3af", label="message/keys/outro"),
                                                                              Patch(facecolor=PAL["error_color"], label="erro (barra) / loop (faixa)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=5, frameon=False, fontsize=7.5)
    ax.set_title("Faixas de fases de 6 trajetórias reais (SWE-rebench; tempo normalizado: início → fim)", loc="left", fontsize=10, fontweight="bold")
    save(fig, "faixas_exemplo")


# ----------------------------------------------------------------------------- 6. formatos
def fig_formats(df: pd.DataFrame) -> None:
    man = [json.loads(line) for line in (CTB_DIR / "bench_manifest.full.jsonl").read_text().splitlines()]
    ctb = Counter()
    for r in man:
        a = r["agent"]
        origin_swe = (r.get("source_relpath") or "").startswith("swe_raw/")
        ctb["CTB · " + {"SWE-agent": "SWE-agent .traj", "mini-SWE-agent": "mini-SWE .traj.json", "Terminus2": "Terminus2 (episódios)"}.get(a, "OpenHands (log de LLM)" if origin_swe else "OpenHands (eventos)")] += 1
    s = df[(df.dataset == "SWE-smith") & (df.split == "tool")]
    frac_native = float((s.main_format == "native").mean()) if len(s) else 0.38
    tool_n = 24100
    xml_tool = round(tool_n * (1 - frac_native))
    rows = [("SWE-rebench · OpenHands (chat)", 67074, False), ("SWE-smith · ticks", 25826, False),
            ("SWE-smith · xml (26.076 do split xml + ~62% do split tool*)", 26076 + xml_tool, True), ("SWE-smith · ação nativa (~38% do split tool*)", round(tool_n * frac_native), True)]
    rows += [(k, v, False) for k, v in sorted(ctb.items(), key=lambda kv: -kv[1])]
    rows = sorted(rows, key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    colors = ["#0072B2" if r[0].startswith("SWE-rebench") else "#E69F00" if r[0].startswith("SWE-smith") else "#009E73" for r in rows]
    bars = ax.barh([r[0] for r in rows], [r[1] for r in rows], color=colors)
    for b, r in zip(bars, rows):
        if r[2]:
            b.set_hatch("///"); b.set_edgecolor("white")
        ax.text(r[1] * 1.08, b.get_y() + b.get_height() / 2, f"{r[1]:,}".replace(",", "."), va="center", fontsize=8)
    ax.set_xscale("log"); ax.set_xlim(60, 400000); ax.set_xlabel("nº de trajetórias (escala log)")
    ax.set_title("9 formatos brutos → 1 modelo canônico (Trajectory/Step)", loc="left")
    ax.grid(axis="y", visible=False)
    ax.text(0.99, 0.02, "listrado = inclui estimativa: o split `tool` mistura os dois formatos (proporção medida em 200 linhas)", transform=ax.transAxes, ha="right", fontsize=7, color="#555")
    save(fig, "formatos_unificados")
    print("formatos:", len(rows), "barras · fração nativa no split tool (amostra):", round(frac_native, 3), "· CTB:", dict(ctb))


def main() -> None:
    df = pd.read_parquet(RESULTS / "batch_stats.parquet")
    stats = json.loads((RESULTS / "batch_stats.json").read_text())
    fig_phases(df); fig_metrics(df, stats); fig_detectors(); fig_strips(); fig_formats(df)
    if (FIG / "matriz_confusao.png").exists():
        print("matriz_confusao.png já gerada por evaluate.py")
    else:
        print("matriz_confusao.png NÃO gerada: gold sem linhas preenchidas")


if __name__ == "__main__":
    main()
