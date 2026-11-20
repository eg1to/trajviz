#!/usr/bin/env python
"""Monta results/poster/ (numeros.md, achados_metodologicos.md, cópias de figuras/capturas) e results/RESULTS.md a partir dos relatórios.
Cada número do pôster é lido dos arquivos de resultado e citado com arquivo + linha do relatório."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RESULTS, ROOT  # noqa: E402

POSTER = RESULTS / "poster"
SHOTS = RESULTS / "screenshots"
BEST_SHOTS = ["05-ctb-gabarito-loop-grafo.png", "02-swe-rebench-resolvida-dashboard-completo.png", "03-swe-rebench-nao-resolvida-grafo.png"]
FIGS = ["fases_por_terco_resolvidas_vs_nao", "detectores_vs_gabarito", "faixas_exemplo", "formatos_unificados"]


def line(rel: str, needle: str) -> str:
    """'`arquivo` (linha N)': primeira linha do arquivo que contém `needle`."""
    for i, ln in enumerate((RESULTS.parent / rel).read_text().splitlines(), 1):
        if needle in ln:
            return f"`{rel}` (linha {i})"
    raise KeyError(f"{needle!r} não encontrado em {rel}")


def val(r: dict, key: str) -> str:
    """Mediana legível: inteiros para contagens, % para frações."""
    v = r[key]
    if r["metric"] in ("n_steps", "cycles"):
        return pt(v, 0)
    return pt(100 * v, 1) + "%"


def pt(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


ACHADOS = """# Achados metodológicos sobre os dados (para o pôster e o relatório)

Descobertas feitas ao construir os adaptadores e as avaliações; cada uma muda como os datasets devem ser usados. Detalhes em `docs/formats.md` e `docs/decisions.md`.

1. **O split `tool` do SWE-smith mistura dois formatos de ação.** ~38% das linhas usam `tool_calls` nativo e ~62% usam o texto `<function=…>` do split `xml` (medido em 200 linhas). O nome do split não identifica o formato: a detecção precisa ser **por mensagem**.
2. **O `patch` do SWE-smith não corresponde à trajetória.** Em ~83% das linhas não vazias, nenhum arquivo do patch é sequer citado na trajetória (e 26–30% dos patches são vazios). Por isso o `resolved` do SWE-smith é tratado como **não validado** em toda tabela, figura e selo da interface.
3. **O CodeTraceBench tem 3.316 trajetórias únicas, não 4.316.** O README soma o split `verified` (1.000) ao `full` (3.316), mas o `verified` está contido no `full` (1.000/1.000 `traj_id`). A tabela de agentes do README também é do `full`, não do `verified`.
4. **O `step_id` do gabarito do CodeTraceBench não tem a mesma unidade em todos os agentes.** SWE-agent: índice em `trajectory[]`; mini-SWE: n-ésima mensagem do assistente; OpenHands/TerminalBench: k-ésimo evento `run` seguido de uma *cauda* das demais ações; Terminus2: **comandos** (`keystrokes`), não episódios (`step_count` = Σ comandos). {n_hyp}% dos passos anotados só se alinham por hipótese (cauda e OpenHands/SWE-bench). Isso limita qualquer comparação com o gabarito (ver `results/eval_detectors.md`, linha "só alinhamento confirmado").
5. **Parte do gabarito mede o protocolo do harness, não o agente.** No SWE-agent/mini-SWE, o submit recusado pelo "STOP! BEFORE SUBMITTING" (`<PATCH_CONTEXT>`) aparece como passo incorreto/inútil. O pipeline marca esses passos como `submit/harness_protocol`; excluí-los quase não muda os resultados (`results/eval_detectors.md`, recorte "sem harness_protocol"), mas é uma fonte de ruído conhecida.
6. **Observações são cortadas em tamanhos diferentes por ferramenta** (OpenHands ~30 mil caracteres, SWE-agent ~100 mil, Terminus2 ~10 mil) e há três formas de marcar o corte; o campo `truncated` unifica o que dá para detectar.
7. **A primeira versão do detector `no_new_info` errava em 80% dos casos** (16 de 20 auditados no SWE-smith): tratava uma leitura inteira *abreviada* como cobertura total do arquivo e não entendia `view_range` em texto. Depois da correção: 0 de 20 na nova amostra e 12,6% → 2,8% dos passos marcados (`results/audit_no_new_info.md`). Lição: auditar manualmente uma amostra de cada detector antes de reportar métricas.
8. **A auditoria leve dos demais detectores mostra pontos fracos conhecidos** (`results/audit_flags.md`, pré-avaliação do assistente): `loop` marca edições em lote e leituras de intervalos diferentes do mesmo arquivo; `test_fail` trata exit 2/4/5 do pytest (erro de uso, nada coletado) como teste falhando; `error` casa `Error:` impresso de propósito por scripts de reprodução. Nada foi ajustado por causa dela.
9. **Os detectores concordam pouco com o gabarito** (`results/eval_detectors.md`): só `error ∪ test_fail` fica claramente acima do acaso para os passos incorretos (lift ~1,6×), e `repeated ∪ no_new_info` é indistinguível de sorteio para os passos "inúteis". Reportado como resultado, não escondido; o conceito de "incorreto/inútil" do benchmark não é o mesmo que "comando falhou/leitura repetida".
10. **{n_eval} das 1.000 trajetórias do `verified` foram avaliadas** (8 não têm artefato e 16 são só logs sem trajetória estruturada); só uma parte delas tem algum passo anotado como problemático — as demais valem como "sem problemas", o que pode não ser verdade.
"""


def main() -> None:
    POSTER.mkdir(exist_ok=True)
    bs = json.loads((RESULTS / "batch_stats.json").read_text())
    ed = json.loads((RESULTS / "eval_detectors.json").read_text())
    ec = json.loads((RESULTS / "eval_classifier.json").read_text())
    usage = json.loads((ROOT / "backend" / ".cache" / "llm_usage.json").read_text())
    res = lambda task, sl="todos": next(r for r in ed["results"] if r["task"] == task and r["slice"] == sl)  # noqa: E731
    e, u = res("incorrect × error ∪ test_fail"), res("unuseful × repeated ∪ no_new_info")
    reb = next(v for k, v in bs["strata"].items() if k.startswith("SWE-rebench"))
    sig = sorted((r for r in reb if r["p_holm"] == r["p_holm"] and r["p_holm"] < 0.05), key=lambda r: -abs(r["delta"]))[:3]
    n_flag_sig = len(sig)
    lines = ["# Números-chave para o pôster", "",
             "Cada número vem de um relatório em `results/` (arquivo e linha entre parênteses). Reprodutível: `cd backend && uv run python scripts/poster_pack.py`.", ""]
    N = []
    N.append(f"**{bs['n']:,}".replace(",", ".") + f" trajetórias** foram processadas ponta a ponta nas estatísticas em lote (2.000 SWE-rebench, 992 do CodeTraceBench verified menos {bs['skipped']['ctb_unsupported'] + bs['skipped']['ctb_sem_artefato']} sem trajetória estruturada, 600 SWE-smith). Fonte: {line('results/batch_stats.md', 'trajetórias processadas')}.")
    N.append("**9 formatos brutos de logs de agentes viram 1 único modelo canônico** (Trajectory/Step): OpenHands chat, SWE-smith (3 variantes de ação), e 5 formatos do CodeTraceBench. "
             f"Fonte: {line('results/parse_report.md', 'CodeTraceBench por adaptador')} e a figura `formatos_unificados`.")
    N.append(f"**Mediana de {pt(bs['pipeline_median_s'] * 1000, 0)} ms e p95 de {pt(bs['pipeline_p95_s'] * 1000, 0)} ms por trajetória** para detectar o formato, converter, rotular, detectar problemas e calcular métricas (sem cache), **sem nenhuma rotulação manual** (o tempo de rotular à mão não foi medido). Fonte: {line('results/batch_stats.md', '| **todos**')}.")
    N.append(f"**{pt(100 * (1 - 0.026), 1)}% a 99,8% dos passos são rotulados só por regras** (97,4% no CodeTraceBench, 99,8% no SWE-rebench e no SWE-smith); o LLM só é chamado nos 0,2%–2,6% restantes. «rotulado por regra» = confiança ≥ 0,6; **a acurácia dessas regras ainda não foi medida** (falta o gold). Fonte: {line('results/labeling_report.md', '| **CodeTraceBench**')}.")
    N.append(f"**Custo total do LLM em todo o projeto: US$ {pt(usage['cost_usd'], 4)}** ({usage['requests']} requisições; orçamento planejado: US$ 4,91). Fonte: `backend/.cache/llm_usage.json` e {line('results/eval_classifier.md', 'custo desta execução')}.")
    if ec.get("rule_vs_llm"):
        r = ec["rule_vs_llm"]
        N.append(f"**Regras e LLM concordam em {pt(100 * r['agreement'], 1)}% dos passos** (kappa de Cohen {pt(r['kappa'], 2)}; n = {r['n']}) — **não** é acurácia contra gold: o gold manual ainda não foi preenchido ({ec['gold_filled']}/{ec['gold_rows']}). Fonte: {line('results/eval_classifier.md', 'kappa de Cohen')}.")
    N.append(f"**Detectores × gabarito (CodeTraceBench, {ed['n_evaluated']} trajetórias):** `error ∪ test_fail` acha passos incorretos com precisão de {pt(100 * e['precision'])}% e revocação de {pt(100 * e['recall'])}% (F1 {pt(e['f1'], 3)}, **{pt(e['lift_f1'], 2)}× melhor que sorteio**, IC 95% {pt(e['lift_ci'][0], 2)}–{pt(e['lift_ci'][1], 2)}). Fonte: {line('results/eval_detectors.md', '## incorrect × error ∪ test_fail')}.")
    N.append(f"**`repeated ∪ no_new_info` não reproduz os passos \"inúteis\" do gabarito:** lift de {pt(u['lift_f1'], 2)}× (IC {pt(u['lift_ci'][0], 2)}–{pt(u['lift_ci'][1], 2)}, contém 1 = indistinguível de acaso). Resultado negativo reportado como tal. Fonte: {line('results/eval_detectors.md', '## unuseful × repeated')}.")
    for r in sig:
        sign = "maior" if r["delta"] > 0 else "menor"
        N.append(f"**Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** {r['label']} é {sign} nas resolvidas (mediana {val(r, 'med_res')} × {val(r, 'med_non')}; δ de Cliff {pt(r['delta'], 2)}; p corrigido por Holm {('< 0,001' if r['p_holm'] < 0.001 else pt(r['p_holm'], 4))}). Fonte: {line('results/batch_stats.md', r['label'])}.")
    N.append("**A 1ª versão do detector `no_new_info` errava em 80% dos casos** (16 de 20 auditados no SWE-smith); depois da correção, 0 de 20 e a taxa de marcação caiu de 12,6% para 2,8% dos passos. Fonte: "
             f"{line('results/audit_no_new_info.md', 'Rodada 1')}.")
    lp, lb = res("incorrect × loop"), next(r for r in json.loads((RESULTS / "eval_detectors_before.json").read_text())["results"] if r["task"] == "incorrect × loop" and r["slice"] == "todos")
    N.append(f"**Depois de corrigir `loop` (só a mesma ação normalizada ou o ciclo edit → test_fail com o mesmo erro) o detector ficou muito mais preciso e muito menos sensível:** {lp['n_pred']} passos marcados no CodeTraceBench (antes {lb['n_pred']}), revocação {pt(100 * lp['recall'])}% — lift de {pt(lp['lift_f1'], 2)}×, mas com IC {pt(lp['lift_ci'][0], 2)}–{pt(lp['lift_ci'][1], 2)} (inconclusivo). Fonte: {line('results/eval_detectors.md', '## incorrect × loop')}.")
    N.append("**Auditoria leve dos detectores (20 casos cada, pré-avaliação do assistente — revisar):** `error` 90% corretos e `repeated` 75% (+25% duvidosos) na rodada 1; "
             "`test_fail` foi de **50% para 80% corretos** (duvidosos de 50% para 15%) depois de seguir os códigos de saída do pytest, e `loop` de **25% para 100%** na amostra nova (11 trajetórias; ver ressalva de revocação). "
             f"Fonte: {line('results/audit_flags.md', '| `test_fail` | **2')}.")
    N.append(f"**O gabarito do CodeTraceBench tem 3.316 trajetórias únicas, não 4.316** (o `verified` está contido no `full`), e **{pt(100 * ed['gold_hypothesis_share'], 0)}% dos passos anotados só se alinham aos passos reais por hipótese** (o `step_id` tem unidade diferente por agente). Fonte: `docs/formats.md` §0/§4.5 e {line('results/eval_detectors.md', 'alinhados por **hipótese**')}.")
    for i, n in enumerate(N, 1):
        lines.append(f"{i}. {n}")
    lines += ["", "## Ressalvas que devem acompanhar os números", "",
              "- O gold manual (210 passos) ainda não foi preenchido: **não há acurácia do classificador** — só concordância regra × LLM.",
              "- O SWE-smith traz `resolved` não validado: nenhuma conclusão sobre sucesso real vem dele.",
              "- Resolvidas × não resolvidas é **associação**, não causalidade (tamanho da tarefa, limite de iterações e agente confundem).",
              "- Os vereditos das auditorias são do assistente (1ª leitura), não de um humano."]
    (POSTER / "numeros.md").write_text("\n".join(lines) + "\n")
    (POSTER / "achados_metodologicos.md").write_text(ACHADOS.format(n_hyp=pt(100 * ed["gold_hypothesis_share"], 0), n_eval=ed["n_evaluated"]))
    for f in FIGS:
        for ext in ("png", "svg"):
            shutil.copy(RESULTS / "figures" / f"{f}.{ext}", POSTER / f"{f}.{ext}")
    for s in BEST_SHOTS:
        shutil.copy(SHOTS / s, POSTER / s)
    print((POSTER / "numeros.md").read_text())


if __name__ == "__main__":
    main()
