#!/usr/bin/env python
"""Detectores × gabarito do CodeTraceBench (verified, só regras). Escreve results/eval_detectors.{md,json}.

Passo: unuseful × (repeated ∪ no_new_info); incorrect × (error ∪ test_fail) e × loop. Estágio: incorreto × ≥ 1 flag.
Precisão/revocação/F1 agregados (pooled) com IC 95% por bootstrap sobre TRAJETÓRIAS (B=2000) e linha de base aleatória com a mesma
taxa de flags por trajetória (média de 100 sorteios; lift = F1 do detector / F1 do aleatório).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RESULTS, SEED, artifact, ci95, fmt, fmt_ci, prf, run_pipeline, verified_ids  # noqa: E402

from app.adapters import codetracebench as ctb  # noqa: E402
from app.adapters.base import UnsupportedArtifact  # noqa: E402

B, DRAWS = 2000, 100
FLAG_SETS = {"unuseful": {"repeated", "no_new_info"}, "incorrect_err": {"error", "test_fail"}, "incorrect_loop": {"loop"}}
STAGE_ANY = {"error", "test_fail", "repeated", "no_new_info", "loop"}


@dataclass
class TrajData:
    tid: str
    agent: str
    origin: str
    kind: str
    n: int
    flags: dict[str, set[int]]  # nome do detector (grupo) → idx marcados
    harness: set[int]
    gold: dict[str, dict[int, str]]  # 'unuseful'/'incorrect' → {idx: via}
    stages: list[dict] = field(default_factory=list)  # {pos, flagged_any, flagged_err, idxs, confirmed}


def extract(tid: str) -> TrajData | str:
    try:
        traj, _, _ = run_pipeline(artifact(tid))
    except UnsupportedArtifact:
        return "unsupported"
    except FileNotFoundError:
        return "sem_artefato"
    except Exception as e:  # noqa: BLE001
        return f"erro:{type(e).__name__}"
    gt = traj.ground_truth
    if gt is None:
        return "sem_gabarito"
    steps = traj.steps
    flags = {k: {s.idx for s in steps if set(s.flags) & fs and s.subcategory not in ("keys", "harness_protocol")} for k, fs in FLAG_SETS.items()}
    gold: dict[str, dict[int, str]] = {"unuseful": {}, "incorrect": {}}
    for a in gt.annotations:
        for s in a.steps:
            if s.resolved_idx is None:
                continue
            via = s.resolved_via or "none"
            if "unuseful" in s.labels:
                gold["unuseful"][s.resolved_idx] = via
            if "incorrect" in s.labels:
                gold["incorrect"][s.resolved_idx] = via
    inc_stages = {a.stage_id for a in gt.annotations if a.incorrect_step_ids}
    stages = []
    for st in gt.stages:
        idxs, confirmed = set(), True
        for sid in range(st.start_step_id, st.end_step_id + 1):
            i, via = ctb.resolve_idx(traj, gt.step_ref_kind, sid, None)
            if i is not None:
                idxs.add(i)
            if via != "rule" and via != "action_ref":
                confirmed = False
        live = [steps[i] for i in idxs if steps[i].subcategory not in ("keys", "harness_protocol")]
        stages.append({"pos": st.stage_id in inc_stages, "any": any(set(s.flags) & STAGE_ANY for s in live),
                       "err_loop": any(set(s.flags) & {"error", "test_fail", "loop"} for s in live), "n": len(idxs), "confirmed": confirmed})
    origin = traj.meta.get("origin", "?")
    return TrajData(tid, traj.agent or "?", origin, gt.step_ref_kind, len(steps), flags,
                    {s.idx for s in steps if s.subcategory == "harness_protocol"}, gold, stages)


# ----------------------------------------------------------------------------- contagens por trajetória
def step_counts(td: TrajData, pred_key: str, gold_key: str, *, harness: bool, confirmed_only: bool) -> tuple[int, int, int, int] | None:
    """→ (n_universo, positivos, predições, TP) para uma trajetória."""
    universe = set(range(td.n))
    pos = set(td.gold[gold_key])
    pred = set(td.flags[pred_key])
    if not harness:  # sem passos harness_protocol: saem do universo e do gabarito
        universe -= td.harness
        pos -= td.harness
    if confirmed_only:  # só alinhamento confirmado: passos alinhados por hipótese saem de tudo
        hyp = {i for i, v in td.gold[gold_key].items() if v == "hypothesis"} | {i for g in td.gold.values() for i, v in g.items() if v == "hypothesis"}
        universe -= hyp
        pos -= hyp
    pred &= universe
    pos &= universe
    return len(universe), len(pos), len(pred), len(pred & pos)


def stage_counts(td: TrajData, key: str, *, confirmed_only: bool, harness: bool) -> tuple[int, int, int, int] | None:
    sts = [s for s in td.stages if s["confirmed"]] if confirmed_only else td.stages
    n = len(sts)
    pos = sum(1 for s in sts if s["pos"])
    pred = sum(1 for s in sts if s[key])
    tp = sum(1 for s in sts if s["pos"] and s[key])
    return n, pos, pred, tp


def evaluate(rows: list[tuple[int, int, int, int]], rng: np.random.Generator) -> dict:
    a = np.array(rows, dtype=float)  # (n, pos, pred, tp) por trajetória
    n, pos, pred, tp = a.T
    P, R, F = prf(tp.sum(), pred.sum(), pos.sum())
    # linha de base: mesma taxa de flags por trajetória, posições sorteadas (média de DRAWS sorteios) + esperança analítica
    with np.errstate(divide="ignore", invalid="ignore"):
        e_tp = np.where(n > 0, pred * pos / n, 0.0)
    draws = []
    for _ in range(DRAWS):
        t = 0
        for ni, pi, ki in zip(n.astype(int), pos.astype(int), pred.astype(int)):
            if ni > 0 and ki > 0 and pi > 0:
                t += rng.hypergeometric(pi, ni - pi, min(ki, ni))
        draws.append(t)
    bP, bR, bF = prf(float(np.mean(draws)), pred.sum(), pos.sum())
    boot = {"P": [], "R": [], "F": [], "lift": [], "bF": []}
    for _ in range(B):
        ix = rng.integers(0, len(a), len(a))
        s = a[ix]
        p_, r_, f_ = prf(s[:, 3].sum(), s[:, 2].sum(), s[:, 1].sum())
        _, _, bf_ = prf(float(e_tp[ix].sum()), s[:, 2].sum(), s[:, 1].sum())
        boot["P"].append(p_); boot["R"].append(r_); boot["F"].append(f_); boot["bF"].append(bf_)
        boot["lift"].append(f_ / bf_ if bf_ and bf_ == bf_ and f_ == f_ else float("nan"))
    return {"n_traj": int(len(a)), "n_universe": int(n.sum()), "n_pos": int(pos.sum()), "n_pred": int(pred.sum()), "tp": int(tp.sum()),
            "precision": P, "recall": R, "f1": F, "precision_ci": ci95(boot["P"]), "recall_ci": ci95(boot["R"]), "f1_ci": ci95(boot["F"]),
            "base_precision": bP, "base_recall": bR, "base_f1": bF, "base_f1_ci": ci95(boot["bF"]),
            "lift_f1": F / bF if bF and bF == bF and F == F else float("nan"), "lift_ci": ci95(boot["lift"]),
            "flag_rate": float(pred.sum() / n.sum()) if n.sum() else float("nan"), "pos_rate": float(pos.sum() / n.sum()) if n.sum() else float("nan")}


def main() -> None:
    ids = verified_ids()
    data: list[TrajData] = []
    skipped: dict[str, int] = defaultdict(int)
    for k, tid in enumerate(ids):
        r = extract(tid)
        if isinstance(r, str):
            skipped[r] += 1
        else:
            data.append(r)
        if (k + 1) % 200 == 0:
            print(f"{k + 1}/{len(ids)}", file=sys.stderr)
    print(f"{len(data)} trajetórias avaliadas; descartadas: {dict(skipped)}", file=sys.stderr)
    rng = np.random.default_rng(SEED)

    slices: list[tuple[str, callable, dict]] = [("todos", lambda t: True, {"harness": True, "confirmed_only": False})]
    for ag in sorted({t.agent for t in data}):
        slices.append((f"agente = {ag}", lambda t, ag=ag: t.agent == ag, {"harness": True, "confirmed_only": False}))
    for og in sorted({t.origin for t in data}):
        slices.append((f"origem = {og}", lambda t, og=og: t.origin == og, {"harness": True, "confirmed_only": False}))
    slices += [("com harness_protocol (padrão)", lambda t: True, {"harness": True, "confirmed_only": False}),
               ("sem harness_protocol", lambda t: True, {"harness": False, "confirmed_only": False}),
               ("só alinhamento confirmado", lambda t: True, {"harness": True, "confirmed_only": True})]
    tasks = [("unuseful × repeated ∪ no_new_info", "step", "unuseful", "unuseful"), ("incorrect × error ∪ test_fail", "step", "incorrect_err", "incorrect"),
             ("incorrect × loop", "step", "incorrect_loop", "incorrect"), ("estágio incorreto × ≥ 1 flag", "stage", "any", None),
             ("estágio incorreto × error ∪ test_fail ∪ loop", "stage", "err_loop", None)]
    results = []
    for tname, level, pk, gk in tasks:
        for sname, sel, opt in slices:
            tds = [t for t in data if sel(t)]
            rows = [step_counts(t, pk, gk, **opt) if level == "step" else stage_counts(t, pk, **opt) for t in tds]
            if not rows:
                continue
            ev = evaluate(rows, rng)
            results.append({"task": tname, "level": level, "slice": sname, **ev})
    out = {"seed": SEED, "bootstrap": B, "baseline_draws": DRAWS, "n_verified": len(ids), "n_evaluated": len(data), "skipped": dict(skipped),
           "by_agent_traj": {a: sum(1 for t in data if t.agent == a) for a in sorted({t.agent for t in data})},
           "n_traj_with_any_annotation": sum(1 for t in data if t.gold["incorrect"] or t.gold["unuseful"]),
           "gold_hypothesis_share": float(np.mean([v == "hypothesis" for t in data for g in t.gold.values() for v in g.values()] or [0])),
           "results": results}
    (RESULTS / "eval_detectors.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    (RESULTS / "eval_detectors.md").write_text(render(out))
    print((RESULTS / "eval_detectors.md").read_text())


def render(o: dict) -> str:
    L = ["# Detectores × gabarito do CodeTraceBench (`verified`)", "",
         f"`backend/scripts/eval_detectors.py` · só regras (sem LLM) · semente {o['seed']} · bootstrap B={o['bootstrap']} **sobre trajetórias** · "
         f"linha de base aleatória = {o['baseline_draws']} sorteios com a mesma nº de flags por trajetória.", "",
         f"- Trajetórias avaliadas: **{o['n_evaluated']}** de {o['n_verified']} (descartadas: {o['skipped'] or 'nenhuma'}); por agente: {o['by_agent_traj']}.",
         f"- Só **{o['n_traj_with_any_annotation']}** delas têm ao menos um passo incorreto/inútil anotado; as demais entram como \"anotadas sem problemas\" (negativos).",
         f"- {100 * o['gold_hypothesis_share']:.0f}% dos passos anotados foram alinhados por **hipótese** (cauda do `step_id`; docs/formats.md §4.5) — ver a linha \"só alinhamento confirmado\".", "",
         "P/R/F1 são agregados (somando contagens de todas as trajetórias do recorte). **lift** = F1 do detector ÷ F1 do marcador aleatório; IC 95% por bootstrap.", ""]
    L += interpretation(o)
    for tname in dict.fromkeys(r["task"] for r in o["results"]):
        L += [f"## {tname}", "", "| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |",
              "|---|---:|---:|---:|---:|---|---|---|---:|---|"]
        for r in (x for x in o["results"] if x["task"] == tname):
            L.append(f"| {r['slice']} | {r['n_traj']} | {r['n_universe']} | {r['n_pos']} | {r['n_pred']} | {fmt_ci(r['precision'], r['precision_ci'])} | "
                     f"{fmt_ci(r['recall'], r['recall_ci'])} | {fmt_ci(r['f1'], r['f1_ci'])} | {fmt(r['base_f1'])} | {fmt_ci(r['lift_f1'], r['lift_ci'], 2)}× |")
        L.append("")
    return "\n".join(L) + "\n"


def interpretation(o: dict) -> list[str]:
    g = lambda task, sl="todos": next(r for r in o["results"] if r["task"] == task and r["slice"] == sl)  # noqa: E731
    u, e, lp = g("unuseful × repeated ∪ no_new_info"), g("incorrect × error ∪ test_fail"), g("incorrect × loop")
    st, st2 = g("estágio incorreto × ≥ 1 flag"), g("estágio incorreto × error ∪ test_fail ∪ loop")
    ec = g("incorrect × error ∪ test_fail", "só alinhamento confirmado")
    mini = g("incorrect × error ∪ test_fail", "agente = mini-SWE-agent")
    pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731
    return ["## Interpretação (5 linhas)", "",
            f"1. **`repeated ∪ no_new_info` não reproduz os passos \"inúteis\" do gabarito**: precisão {pct(u['precision'])}, revocação {pct(u['recall'])}, lift {u['lift_f1']:.2f}× (IC {u['lift_ci'][0]:.2f}–{u['lift_ci'][1]:.2f}, contém 1) — indistinguível de sorteio. O gabarito define \"inútil\" por julgamento do anotador; leitura idêntica a uma anterior capta, no máximo, uma fração mínima disso (hipótese não testada: não auditei os passos anotados).",
            f"2. **`error ∪ test_fail` é fraco, mas acima do acaso** para os passos incorretos: precisão {pct(e['precision'])}, revocação {pct(e['recall'])}, F1 {e['f1']:.3f}, lift {e['lift_f1']:.2f}× (IC {e['lift_ci'][0]:.2f}–{e['lift_ci'][1]:.2f}); no mini-SWE-agent chega a F1 {mini['f1']:.3f} (lift {mini['lift_f1']:.2f}×). Hipótese (não testada): \"incorreto\" no gabarito é ação que muda o estado de forma errada, o que difere de comando que falha.",
            f"3. **`loop`** tem lift {lp['lift_f1']:.2f}× (IC {lp['lift_ci'][0]:.2f}–{lp['lift_ci'][1]:.2f}) com precisão de {pct(lp['precision'])} e IC largo em vários recortes: sinal marginal.",
            f"4. **No nível de estágio a revocação parece boa ({pct(st['recall'])}), mas é efeito da taxa de flags**: {st['n_pred']} de {st['n_universe']} estágios têm ≥ 1 flag, a precisão é {pct(st['precision'])} e o lift é {st['lift_f1']:.2f}× (< 1). Com só `error ∪ test_fail ∪ loop` o lift é {st2['lift_f1']:.2f}×. A linha de base sorteia estágios sem considerar o tamanho do estágio (limitação: estágios longos têm mais chance de ter flag).",
            f"5. **Limitações**: {pct(o['gold_hypothesis_share'])} dos passos anotados foram alinhados por hipótese (cauda do `step_id`); restringir ao alinhamento confirmado muda o lift de `error ∪ test_fail` para {ec['lift_f1']:.2f}× e derruba os positivos de `unuseful` para {g('unuseful × repeated ∪ no_new_info', 'só alinhamento confirmado')['n_pos']}; excluir `harness_protocol` quase não muda nada; {o['n_traj_with_any_annotation']} de {o['n_evaluated']} trajetórias têm alguma anotação (o resto vale como \"sem problemas\", o que pode não ser verdade)."]


if __name__ == "__main__":
    main()
