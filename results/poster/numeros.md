# Números-chave para o pôster

Cada número vem de um relatório em `results/` (arquivo e linha entre parênteses). Reprodutível: `cd backend && uv run python scripts/poster_pack.py`.

1. **3.576 trajetórias** foram processadas ponta a ponta nas estatísticas em lote (2.000 SWE-rebench, 992 do CodeTraceBench verified menos 24 sem trajetória estruturada, 600 SWE-smith). Fonte: `results/batch_stats.md` (linha 3).
2. **9 formatos brutos de logs de agentes viram 1 único modelo canônico** (Trajectory/Step): OpenHands chat, SWE-smith (3 variantes de ação), e 5 formatos do CodeTraceBench. Fonte: `results/parse_report.md` (linha 18) e a figura `formatos_unificados`.
3. **Mediana de 28 ms e p95 de 73 ms por trajetória** para detectar o formato, converter, rotular, detectar problemas e calcular métricas (sem cache), **sem nenhuma rotulação manual** (o tempo de rotular à mão não foi medido). Fonte: `results/batch_stats.md` (linha 18).
4. **97,4% a 99,8% dos passos são rotulados só por regras** (97,4% no CodeTraceBench, 99,8% no SWE-rebench e no SWE-smith); o LLM só é chamado nos 0,2%–2,6% restantes. «rotulado por regra» = confiança ≥ 0,6; **a acurácia dessas regras ainda não foi medida** (falta o gold). Fonte: `results/labeling_report.md` (linha 11).
5. **Custo total do LLM em todo o projeto: US$ 0,0206** (117 requisições; orçamento planejado: US$ 4,91). Fonte: `backend/.cache/llm_usage.json` e `results/eval_classifier.md` (linha 11).
6. **Regras e LLM concordam em 89,5% dos passos** (kappa de Cohen 0,87; n = 209) — **não** é acurácia contra gold: o gold manual ainda não foi preenchido (0/210). Fonte: `results/eval_classifier.md` (linha 15).
7. **Detectores × gabarito (CodeTraceBench, 976 trajetórias):** `error ∪ test_fail` acha passos incorretos com precisão de 7,5% e revocação de 22,0% (F1 0,112, **1,62× melhor que sorteio**, IC 95% 1,44–1,81). Fonte: `results/eval_detectors.md` (linha 33).
8. **`repeated ∪ no_new_info` não reproduz os passos "inúteis" do gabarito:** lift de 0,80× (IC 0,12–1,67, contém 1 = indistinguível de acaso). Resultado negativo reportado como tal. Fonte: `results/eval_detectors.md` (linha 18).
9. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** nº de passos é menor nas resolvidas (mediana 56 × 68; δ de Cliff -0,34; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 28).
10. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** % passos test é maior nas resolvidas (mediana 12,8% × 10,7%; δ de Cliff 0,26; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 33).
11. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** taxa de no_new_info é menor nas resolvidas (mediana 2,0% × 2,9%; δ de Cliff -0,16; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 37).
12. **A 1ª versão do detector `no_new_info` errava em 80% dos casos** (16 de 20 auditados no SWE-smith); depois da correção, 0 de 20 e a taxa de marcação caiu de 12,6% para 2,8% dos passos. Fonte: `results/audit_no_new_info.md` (linha 15).
13. **Auditoria leve dos outros detectores (20 casos cada, pré-avaliação do assistente — revisar):** `error` 90% corretos, `repeated` 75% (+25% duvidosos), `test_fail` 50% (+50% duvidosos, quase todos códigos de saída do pytest que não significam falha), `loop` só 25%. Fonte: `results/audit_flags.md` (linha 13).
14. **O gabarito do CodeTraceBench tem 3.316 trajetórias únicas, não 4.316** (o `verified` está contido no `full`), e **34% dos passos anotados só se alinham aos passos reais por hipótese** (o `step_id` tem unidade diferente por agente). Fonte: `docs/formats.md` §0/§4.5 e `results/eval_detectors.md` (linha 7).

## Ressalvas que devem acompanhar os números

- O gold manual (210 passos) ainda não foi preenchido: **não há acurácia do classificador** — só concordância regra × LLM.
- O SWE-smith traz `resolved` não validado: nenhuma conclusão sobre sucesso real vem dele.
- Resolvidas × não resolvidas é **associação**, não causalidade (tamanho da tarefa, limite de iterações e agente confundem).
- Os vereditos das auditorias são do assistente (1ª leitura), não de um humano.
