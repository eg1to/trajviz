#!/usr/bin/env python
"""Acurácia do classificador de categorias: regras × LLM × gold manual. Escreve results/eval_classifier.md (+ .json).

Uso: uv run python scripts/evaluate.py [--gold CAMINHO.csv] [--no-llm]
O gold padrão é results/gold/gold_steps_cego_pedro.csv (se existir; senão gold_steps_cego.csv). O CSV cego traz contexto + `gold_category`
(+ opcionais `duvida`, `notas`); as previsões da regra ficam em gold_steps_previsoes.csv e são juntadas pelo `id`.
A comparação em três vias roda o Haiku em TODOS os passos do gold, ignorando as regras (orçamento máx. US$ 0,05; respostas já pagas vêm do cache).
IC 95%: bootstrap percentil por TRAJETÓRIA (B = 2.000): os passos de uma mesma trajetória não são independentes (ver docs/decisions.md).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CTB_DIR, RESULTS, ROOT, SEED, artifact, fmt, run_pipeline  # noqa: E402

from app.config import LLMConfig  # noqa: E402
from app.labeling.llm import LLMLabeler  # noqa: E402
from app.labeling.taxonomy import Category  # noqa: E402

CATS = [c.value for c in Category]
K = len(CATS)
IX = {c: i for i, c in enumerate(CATS)}
GOLD_DIR = RESULTS / "gold"
DEFAULT_GOLD = [GOLD_DIR / "gold_steps_cego_pedro.csv", GOLD_DIR / "gold_steps_cego.csv"]
BUDGET = 0.05
B = 2000
SAMPLES = ROOT / "data" / "samples"
MIN_ROWS = 70


def is_doubt(v: str) -> bool:
    try:
        return float(v) == 1.0
    except (TypeError, ValueError):
        return (v or "").strip().lower() in ("x", "sim", "s", "true")


def load_gold(path: Path, pred_path: Path | None = None) -> list[dict]:
    """Junta o CSV cego preenchido com as previsões (gold_steps_previsoes.csv, que o rotulador NÃO deve abrir), pelo `id`."""
    blind = {r["id"]: r for r in csv.DictReader(path.open())}
    rows = list(csv.DictReader((pred_path or GOLD_DIR / "gold_steps_previsoes.csv").open()))
    for r in rows:
        b = blind.get(r["id"], {})
        r["idx"] = int(r["idx"])
        r["gold"] = (b.get("gold_category") or "").strip().lower()
        r["doubt"] = is_doubt(b.get("duvida", ""))
        r["nota"] = (b.get("notas") or "").strip()
        r["tool"], r["action"] = b.get("tool", ""), b.get("action", "")
    return rows


def index_trajectories(ids: set[str]) -> dict:
    """traj_id → Trajectory (processado só com regras) para as amostras de data/samples/."""
    out = {}
    paths = list((SAMPLES / "swe-rebench").glob("chat*.json")) + [p for sp in ("tool", "xml", "ticks") for p in (SAMPLES / "swe-smith" / sp).glob("*.json")]
    paths += [artifact(t) for t in json.loads((SAMPLES / "codetracebench" / "_sample_ids.json").read_text())]
    # gold held-out: SWE-rebench/SWE-smith salvos em data/holdout/ por make_gold_sample.py --holdout; CTB direto do arquivo bruto
    paths += list((ROOT / "data" / "holdout").glob("*.json"))
    paths += [artifact(t) for t in sorted(ids) if (CTB_DIR / "bench_artifacts" / "full" / f"{t}.tar.zst").exists()]
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

# ----------------------------------------------------------------------------- métricas (vetorizadas sobre matrizes de confusão)
def stats_from_cms(cm: np.ndarray) -> dict[str, np.ndarray]:
    """cm: (..., K, K), linhas = 1º rótulo (gold ou 1º método), colunas = 2º. Acurácia, F1 por classe, F1 macro (classes presentes em
    qualquer dos lados) e kappa de Cohen."""
    cm = cm.astype(float)
    n = cm.sum((-1, -2))
    tp = np.diagonal(cm, axis1=-2, axis2=-1)
    row, col = cm.sum(-1), cm.sum(-2)
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where(row + col > 0, 2 * tp / (row + col), np.nan)
        prec = np.where(col > 0, tp / col, np.nan)
        rec = np.where(row > 0, tp / row, np.nan)
        acc = tp.sum(-1) / n
        pe = (row * col).sum(-1) / n**2
        kap = np.where(pe < 1, (acc - pe) / (1 - pe), np.nan)
    return {"acc": acc, "f1": f1, "prec": prec, "rec": rec, "macro_f1": np.nanmean(f1, axis=-1), "kappa": kap}


class Boot:
    """Bootstrap por trajetória: sorteia trajetórias com reposição e soma as matrizes de confusão de cada uma."""

    def __init__(self, rows: list[dict], rng: np.random.Generator, b: int = B):
        self.rows = rows
        self.tids = sorted({r["traj_id"] for r in rows})
        pos = {t: i for i, t in enumerate(self.tids)}
        self.pos = np.array([pos[r["traj_id"]] for r in rows])
        T = len(self.tids)
        idx = rng.integers(0, T, (b, T))
        self.W = np.stack([np.bincount(i, minlength=T) for i in idx]).astype(float)  # (B, T)

    def cm(self, ka: str, kb: str):
        a = np.array([IX[r[ka]] for r in self.rows]); c = np.array([IX[r[kb]] for r in self.rows])
        per = np.zeros((len(self.tids), K * K))
        np.add.at(per, (self.pos, a * K + c), 1)
        return per.sum(0).reshape(K, K), (self.W @ per).reshape(-1, K, K)

    def stats(self, ka: str, kb: str) -> dict:
        """Estimativa pontual + bootstrap de cada métrica: {nome: (ponto, (lo, hi), amostras)}."""
        pt_cm, bt_cm = self.cm(ka, kb)
        p, s = stats_from_cms(pt_cm), stats_from_cms(bt_cm)
        out = {}
        for k in p:
            lo, hi = np.nanpercentile(s[k], [2.5, 97.5], axis=0)
            out[k] = (p[k], (lo, hi), s[k])
        out["cm"] = pt_cm
        return out


def fci(t, d: int = 3, i=None) -> str:
    x, (lo, hi) = (t[0], t[1]) if i is None else (t[0][i], (t[1][0][i], t[1][1][i]))
    return f"{fmt(float(x), d)} [{fmt(float(lo), d)}; {fmt(float(hi), d)}]"


def slice_table(rows, rng, key, title_first="recorte"):
    """Linhas: todos · dataset · label_source · agente (só o que tem ≥ 1 linha)."""
    slices = [("todos", rows)]
    slices += [(f"dataset = {v}", [r for r in rows if r["dataset"] == v]) for v in sorted({r["dataset"] for r in rows})]
    slices += [(f"label_source = {v}", [r for r in rows if r["label_source"] == v]) for v in sorted({r["label_source"] for r in rows})]
    L = [f"| {title_first} | n | traj. | acurácia [IC95] | F1 macro [IC95] |", "|---|---:|---:|---|---|"]
    out = {}
    for name, sub in slices:
        if not sub:
            continue
        st = Boot(sub, rng).stats("gold", key)
        L.append(f"| {name} | {len(sub)} | {len(st_tids(sub))} | {fci(st['acc'])} | {fci(st['macro_f1'])} |")
        out[name] = {"n": len(sub), "acc": float(st["acc"][0]), "acc_ci": [float(x) for x in st["acc"][1]], "macro_f1": float(st["macro_f1"][0]), "macro_f1_ci": [float(x) for x in st["macro_f1"][1]]}
    return L, out


def st_tids(sub):
    return {r["traj_id"] for r in sub}


def short_action(r: dict, n: int = 110) -> str:
    a = r.get("action", "")
    try:
        j = json.loads(a)
        if isinstance(j, dict):
            a = j.get("command") or j.get("cmd") or json.dumps(j, ensure_ascii=False)
            if j.get("path") and j.get("command") and j["command"] in ("view", "create", "str_replace", "insert", "undo_edit"):
                a = f"{j['command']} {j['path']}"
    except (ValueError, TypeError):
        pass
    a = " ".join(str(a).split()).replace("|", "\\|")
    return (a[:n] + "…") if len(a) > n else a


def top_confusions(rows, key, k=10):
    cnt = Counter((r["gold"], r[key]) for r in rows if r["gold"] != r[key])
    out = []
    for (g, p), n in cnt.most_common(k):
        cand = [r for r in rows if r["gold"] == g and r[key] == p]
        ex = next((r for r in cand if r["nota"]), cand[0])
        out.append({"gold": g, "pred": p, "n": n, "n_doubt": sum(r["doubt"] for r in cand), "id": ex["id"], "tool": ex["tool"], "action": short_action(ex),
                    "nota": ex["nota"], "ex_doubt": ex["doubt"], "dataset": ex["dataset"], "idx": ex["idx"], "pred_sub": ex.get("pred_subcategory", "")})
    return out


def cm_md(cm, title):
    L = [f"{title}", "", "| gold \\ previsto | " + " | ".join(CATS) + " | total |", "|---|" + "---:|" * (K + 1)]
    for i, c in enumerate(CATS):
        L.append(f"| **{c}** | " + " | ".join((f"**{int(cm[i, j])}**" if i == j and cm[i, j] else str(int(cm[i, j])) if cm[i, j] else "·") for j in range(K)) + f" | {int(cm[i].sum())} |")
    return L


def per_class_table(rows, rng, methods: dict[str, str]):
    """F1 por categoria [IC95] para cada método (n gold, n previsto da regra)."""
    boots = Boot(rows, rng)
    sts = {m: boots.stats("gold", k) for m, k in methods.items()}
    L = ["| categoria | n gold | " + " | ".join(f"F1 {m} [IC95]" for m in methods) + " | precisão regras | revocação regras |", "|---|---:|" + "---|" * len(methods) + "---:|---:|"]
    first = next(iter(sts.values()))
    for i, c in enumerate(CATS):
        ng = sum(1 for r in rows if r["gold"] == c)
        L.append(f"| {c} | {ng} | " + " | ".join(fci(st["f1"], 2, i) for st in sts.values()) + f" | {fmt(float(first['prec'][0][i]), 2)} | {fmt(float(first['rec'][0][i]), 2)} |")
    return L, sts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=None, help="CSV do gold (padrão: gold_steps_cego_pedro.csv se existir, senão gold_steps_cego.csv)")
    ap.add_argument("--tag", default="", help="sufixo dos resultados (ex.: holdout → eval_classifier_holdout.md; previsões em results/gold_<tag>_previsoes.csv)")
    ap.add_argument("--no-llm", action="store_true", help="não chama o LLM (usa só o cache já pago se houver; sem chave, pula a comparação)")
    args = ap.parse_args()
    tag = f"_{args.tag}" if args.tag else ""
    path = args.gold or next(p for p in DEFAULT_GOLD if p.exists())
    pred_path = RESULTS / f"gold_{args.tag}_previsoes.csv" if args.tag else None
    rows = load_gold(path, pred_path)
    filled = [r for r in rows if r["gold"] in CATS]
    invalid = [r for r in rows if r["gold"] and r["gold"] not in CATS]
    rng = np.random.default_rng(SEED)
    llm_map, info = ({}, {"enabled": False, "model": "—", "budget_usd": BUDGET, "cost_usd": 0.0, "requests": 0, "labeled": 0, "from_cache": 0, "errors": ["--no-llm"]}) if args.no_llm else run_llm(rows)
    for r in rows:
        r["llm"] = llm_map.get((r["traj_id"], r["idx"]), "")
        # produção (regras + LLM): o LLM só decide os passos em que a regra ficou abaixo de 0,6 (label_source = fallback)
        r["hybrid"] = r["llm"] if (r["label_source"] == "fallback" and r["llm"]) else r["pred_category"]
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    L = ["# Acurácia do classificador de categorias", "",
         f"`backend/scripts/evaluate.py` · gold: `{rel}` (CSV cego: sem rótulos de regra/LLM; as previsões ficam em `{pred_path.name if pred_path else 'gold_steps_previsoes.csv'}`) · semente {SEED} · "
         f"IC 95% por bootstrap percentil **sobre trajetórias** (B={B}; os passos de uma trajetória não são independentes).", ""]
    if len(filled) < MIN_ROWS:
        L += [f"> ⚠️ **AMOSTRA PEQUENA / SEM GOLD**: apenas **{len(filled)}** de {len(rows)} linhas têm `gold_category` preenchida (mínimo recomendado: {MIN_ROWS}). "
              + ("Acurácia, F1 e matriz **não puderam ser calculados**; o relatório traz só a concordância regra × LLM. " if not filled else "Os ICs são muito largos: indicativo, não medida. "), ""]
    if invalid:
        L += [f"> {len(invalid)} linhas têm `gold_category` inválida (ignoradas): {sorted({r['gold'] for r in invalid})}", ""]
    doubt = [r for r in filled if r["doubt"]]
    L += [f"- Linhas no CSV: {len(rows)} · com gold válido: **{len(filled)}** (de **{len(st_tids(filled))}** trajetórias) · marcadas `duvida=1`: **{len(doubt)}** · com nota do anotador: {sum(1 for r in filled if r['nota'])} · categorias: {', '.join(CATS)}.",
          "- Métricas: **F1 macro** = média do F1 das categorias que aparecem no gold ou na previsão (cada categoria pesa igual; `submit`, `vcs`, `explore`, `other` têm poucos exemplos); **kappa** de Cohen entre dois rótulos.",
          "- **Regras + LLM** = o que o app faz em produção: o LLM só decide os passos com `label_source = fallback` (confiança < 0,6); nos demais vale a regra. **LLM** = Haiku 5.5 em *todos* os passos, ignorando as regras.", ""]
    # ---- LLM
    usage = json.loads((ROOT / "backend" / ".cache" / "llm_usage.json").read_text())["cost_usd"]
    L += ["## Execução do LLM em todos os passos do gold (ignorando as regras)", "",
          f"Modelo `{info['model']}` · orçamento máximo US$ {BUDGET:.2f} · passos rotulados: {info['labeled']}/{len(rows)} (do cache: {info['from_cache']}) · requisições: {info['requests']} · "
          f"**custo desta execução: US$ {info['cost_usd']:.4f}** (acumulado do projeto em `.cache/llm_usage.json`: US$ {usage:.4f}; a 1ª execução pagou US$ 0,0199 e as seguintes reaproveitam o cache)"
          + (f" · tokens {info.get('tokens')}" if info.get("tokens") else "") + (f" · avisos: {info['errors']}" if info["errors"] else ""), ""]
    both = [r for r in rows if r["llm"]]
    summary: dict = {"gold_path": str(rel), "gold_rows": len(rows), "gold_filled": len(filled), "gold_doubt": len(doubt), "gold_trajectories": len(st_tids(filled)), "llm": info, "rule_vs_llm": {}}
    if both:
        st = Boot(both, rng).stats("pred_category", "llm")
        summary["rule_vs_llm"] = {"n": len(both), "agreement": float(st["acc"][0]), "agreement_ci": [float(x) for x in st["acc"][1]], "kappa": float(st["kappa"][0]), "kappa_ci": [float(x) for x in st["kappa"][1]]}
        L += ["## Concordância regra × LLM (não depende do gold)", "",
              f"- n = {len(both)} passos · concordância **{fci(st['acc'])}** · kappa de Cohen **{fci(st['kappa'])}**", ""]
        by_src = defaultdict(lambda: [[], []])
        for r in both:
            by_src[r["label_source"]][0].append(r["pred_category"]); by_src[r["label_source"]][1].append(r["llm"])
        L += ["| origem do rótulo da regra | n | concordância com o LLM |", "|---|---:|---:|"]
        for k, (x, y) in by_src.items():
            L.append(f"| {k} | {len(x)} | {fmt(float(np.mean([a == b for a, b in zip(x, y)])))} |")
        dis = Counter((r["pred_category"], r["llm"]) for r in both if r["pred_category"] != r["llm"])
        L += ["", "Maiores divergências (regra → LLM): " + ", ".join(f"{a}→{b}: {n}" for (a, b), n in dis.most_common(8)), ""]
    if not filled:
        L += ["## Regras × gold", "", "Sem linhas com `gold_category` preenchida: nada a calcular.", ""]
    else:
        # ---- regras × gold
        L += ["## Regras × gold", "", "### Por recorte", ""]
        t, summary["rules_slices"] = slice_table(filled, rng, "pred_category")
        L += t
        base = Counter(r["gold"] for r in filled).most_common(1)[0]
        L += ["", f"Linha de base trivial (sempre `{base[0]}`): acurácia {base[1] / len(filled):.3f}.", ""]
        if both:
            ly = [r for r in filled if r["llm"]]
            L += ["### LLM × gold por recorte", ""]
            t, summary["llm_slices"] = slice_table(ly, rng, "llm")
            L += t + [""]
        methods = {"regras": "pred_category"} | ({"LLM": "llm", "regras+LLM": "hybrid"} if both else {})
        sub = [r for r in filled if r["llm"]] if both else filled
        L += ["### F1 por categoria", ""]
        t, sts = per_class_table(sub, rng, methods)
        L += t + [""]
        summary["f1_per_class"] = {m: {c: float(st["f1"][0][i]) for i, c in enumerate(CATS)} for m, st in sts.items()}
        summary["confusion"] = {"labels": CATS, "rules": sts["regras"]["cm"].astype(int).tolist()} | ({"llm": sts["LLM"]["cm"].astype(int).tolist()} if "LLM" in sts else {})
        L += cm_md(sts["regras"]["cm"], "### Matriz de confusão — regras (linhas = gold, colunas = previsto; `·` = 0)") + [""]
        if "LLM" in sts:
            L += cm_md(sts["LLM"]["cm"], "### Matriz de confusão — LLM (todos os passos)") + [""]
        # ---- três vias
        if both:
            bt = Boot(sub, rng)
            S = {m: bt.stats("gold", k) for m, k in methods.items()}
            rl = bt.stats("pred_category", "llm")
            L += ["## Três vias: regras × LLM × gold (nos mesmos passos)", "",
                  "| método | n | acurácia [IC95] | F1 macro [IC95] | kappa com o gold [IC95] |", "|---|---:|---|---|---|"]
            for m in methods:
                L.append(f"| {m} | {len(sub)} | {fci(S[m]['acc'])} | {fci(S[m]['macro_f1'])} | {fci(S[m]['kappa'])} |")
            d_acc = S["LLM"]["acc"][2] - S["regras"]["acc"][2]
            d_f1 = S["LLM"]["macro_f1"][2] - S["regras"]["macro_f1"][2]
            dh = S["regras+LLM"]["acc"][2] - S["regras"]["acc"][2]
            pt = lambda m, k: float(S[m][k][0])  # noqa: E731
            L += ["", f"- kappa regras × LLM: {fci(rl['kappa'])} (concordância {fci(rl['acc'])}).",
                  f"- Diferença LLM − regras (pareada, bootstrap por trajetória): acurácia **{pt('LLM', 'acc') - pt('regras', 'acc'):+.3f}** [{np.percentile(d_acc, 2.5):+.3f}; {np.percentile(d_acc, 97.5):+.3f}] · "
                  f"F1 macro **{pt('LLM', 'macro_f1') - pt('regras', 'macro_f1'):+.3f}** [{np.percentile(d_f1, 2.5):+.3f}; {np.percentile(d_f1, 97.5):+.3f}].",
                  f"- Diferença regras+LLM − regras: acurácia **{pt('regras+LLM', 'acc') - pt('regras', 'acc'):+.3f}** [{np.percentile(dh, 2.5):+.3f}; {np.percentile(dh, 97.5):+.3f}] "
                  f"({sum(1 for r in sub if r['label_source'] == 'fallback')} passos em `fallback` no gold: o LLM só entra neles).", ""]
            both_ok = Counter(((r["pred_category"] == r["gold"]), (r["llm"] == r["gold"])) for r in sub)
            L += [f"- Acertos: ambos {both_ok[(True, True)]} · só regras {both_ok[(True, False)]} · só LLM {both_ok[(False, True)]} · nenhum {both_ok[(False, False)]}.", ""]
            summary["three_way"] = {"n": len(sub), **{m: {"acc": pt(m, "acc"), "acc_ci": [float(x) for x in S[m]["acc"][1]], "macro_f1": pt(m, "macro_f1"), "macro_f1_ci": [float(x) for x in S[m]["macro_f1"][1]],
                                                          "kappa": pt(m, "kappa"), "kappa_ci": [float(x) for x in S[m]["kappa"][1]]} for m in methods},
                                    "kappa_rule_llm": float(rl["kappa"][0]), "kappa_rule_llm_ci": [float(x) for x in rl["kappa"][1]],
                                    "llm_minus_rules_acc": [pt("LLM", "acc") - pt("regras", "acc"), float(np.percentile(d_acc, 2.5)), float(np.percentile(d_acc, 97.5))]}
        # ---- maiores confusões
        tc = top_confusions(filled, "pred_category")
        summary["top_confusions_rules"] = tc
        L += ["## As 10 maiores confusões (regras: gold → previsto)", "",
              "| # | gold → previsto | n (com dúvida) | exemplo (passo) | tool · ação | nota do anotador |", "|---:|---|---:|---|---|---|"]
        for i, c in enumerate(tc, 1):
            L.append(f"| {i} | {c['gold']} → {c['pred']} | {c['n']} ({c['n_doubt']}) | {c['dataset']} #{c['idx']}{' ⚠' if c['ex_doubt'] else ''} | `{c['tool']}` · {c['action']} | {c['nota'].replace('|', chr(92) + '|') or '—'} |")
        L += ["", "⚠ = o exemplo é uma linha marcada `duvida=1`. O exemplo é, quando há, uma linha com nota do anotador. Previsto = rótulo da regra (`pred_category`).", ""]
        if both:
            tl = top_confusions([r for r in filled if r["llm"]], "llm", 5)
            summary["top_confusions_llm"] = tl
            L += ["Para comparação, as 5 maiores confusões do **LLM** (gold → LLM): " + "; ".join(f"{c['gold']} → {c['pred']}: {c['n']}" for c in tl), ""]
        # ---- sensibilidade
        firm = [r for r in filled if not r["doubt"]]
        L += [f"## Sensibilidade: excluindo as {len(doubt)} linhas com `duvida=1` (n = {len(firm)})", ""]
        if doubt and firm:
            ms = {"regras": "pred_category"} | ({"LLM": "llm", "regras+LLM": "hybrid"} if both else {})
            sub2 = [r for r in firm if r["llm"]] if both else firm
            B2, B1 = Boot(sub2, rng), Boot(sub, rng) if both else Boot(filled, rng)
            L += ["| método | n | acurácia [IC95] | F1 macro [IC95] | kappa [IC95] | Δ acurácia vs. todos | Δ F1 macro vs. todos |", "|---|---:|---|---|---|---:|---:|"]
            sens = {}
            for m, k in ms.items():
                a, b = B2.stats("gold", k), B1.stats("gold", k)
                L.append(f"| {m} | {len(sub2)} | {fci(a['acc'])} | {fci(a['macro_f1'])} | {fci(a['kappa'])} | {float(a['acc'][0] - b['acc'][0]):+.3f} | {float(a['macro_f1'][0] - b['macro_f1'][0]):+.3f} |")
                sens[m] = {"n": len(sub2), "acc": float(a["acc"][0]), "acc_ci": [float(x) for x in a["acc"][1]], "macro_f1": float(a["macro_f1"][0]), "macro_f1_ci": [float(x) for x in a["macro_f1"][1]],
                           "kappa": float(a["kappa"][0]), "d_acc": float(a["acc"][0] - b["acc"][0]), "d_macro_f1": float(a["macro_f1"][0] - b["macro_f1"][0])}
            dsub = [r for r in doubt if r["llm"]] if both else doubt
            L += ["", "Acurácia **só nas linhas duvidosas** (n = " + str(len(dsub)) + "; IC por trajetória, muito largo): " + ", ".join(
                f"{m} {fci(Boot(dsub, rng).stats('gold', k)['acc'])}" for m, k in ms.items()), ""]
            t, _ = per_class_table(sub2, rng, {"regras": "pred_category"})
            L += ["F1 por categoria das regras sem as linhas duvidosas:", ""] + t + [""]
            tcs = top_confusions(firm, "pred_category", 10)
            same = [(c["gold"], c["pred"]) for c in tc] == [(c["gold"], c["pred"]) for c in tcs]
            L += ["Maiores confusões das regras sem as duvidosas: " + "; ".join(f"{c['gold']} → {c['pred']}: {c['n']}" for c in tcs[:10]) + f". Ranking idêntico ao completo? **{'sim' if same else 'não'}**.", ""]
            summary["sensitivity"] = {"n": len(firm), "methods": sens, "top_confusions_rules": tcs}
        else:
            L += ["Sem linhas com dúvida (ou todas duvidosas): nada a comparar.", ""]
    # distribuição de rótulos
    L += [f"## Distribuição dos rótulos nos {len(rows)} passos do gold", "", "| categoria | gold | regras | LLM |", "|---|---:|---:|---:|"]
    cg, cr, cl = Counter(r["gold"] for r in rows if r["gold"]), Counter(r["pred_category"] for r in rows), Counter(r["llm"] for r in rows if r["llm"])
    L += [f"| {c} | {cg[c]} | {cr[c]} | {cl[c]} |" for c in CATS]
    (RESULTS / f"eval_classifier{tag}.md").write_text("\n".join(L) + "\n")
    (RESULTS / f"eval_classifier{tag}.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=float))
    with (RESULTS / f"eval_classifier{tag}_llm_labels.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["id", "llm_category"]); [w.writerow([r["id"], r["llm"]]) for r in rows if r["llm"]]
    if args.tag and filled:
        dev_vs_holdout(summary, args.tag)
    print("\n".join(L))


def dev_vs_holdout(held: dict, tag: str) -> None:
    """Escreve/atualiza em results/RESULTS.md a tabela desenvolvimento × held-out (entre marcadores), a partir dos dois JSON."""
    dev_p = RESULTS / "eval_classifier.json"
    if not dev_p.exists():
        return
    dev = json.loads(dev_p.read_text())

    def cell(sl: dict | None) -> str:
        if not sl:
            return "—"
        f = lambda x: f"{x:.3f}".replace(".", ",")  # noqa: E731
        return f"{f(sl['acc'])} [{f(sl['acc_ci'][0])}; {f(sl['acc_ci'][1])}] · F1 {f(sl['macro_f1'])} (n={sl['n']})"

    names = ["todos"] + [f"dataset = {d}" for d in ("SWE-rebench", "SWE-smith", "CodeTraceBench")]
    L = [f"<!-- dev-holdout:{tag} -->", f"## Desenvolvimento × held-out ({tag})", "",
         "Regras × gold manual (acurácia [IC95 por trajetória] · F1 macro). *Desenvolvimento* = `data/samples/` (usado para escrever as regras); *held-out* = trajetórias de `data/raw/` fora dessa amostra, rotuladas às cegas depois. "
         "Se a coluna held-out for menor, os números de desenvolvimento eram otimistas.", "",
         "| recorte | desenvolvimento | held-out |", "|---|---|---|"]
    for n in names:
        L.append(f"| {n.replace('dataset = ', '')} | {cell(dev.get('rules_slices', {}).get(n))} | {cell(held.get('rules_slices', {}).get(n))} |")
    L += ["", f"Detalhes: `eval_classifier.md` (desenvolvimento) e `eval_classifier_{tag}.md` (held-out).", f"<!-- /dev-holdout:{tag} -->"]
    md = (RESULTS / "RESULTS.md").read_text()
    a, b = f"<!-- dev-holdout:{tag} -->", f"<!-- /dev-holdout:{tag} -->"
    block = "\n".join(L)
    if a in md:
        md = md[:md.index(a)] + block + md[md.index(b) + len(b):]
    else:
        md = md.rstrip("\n") + "\n\n" + block + "\n"
    (RESULTS / "RESULTS.md").write_text(md)


if __name__ == "__main__":
    main()
