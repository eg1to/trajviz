# Números-chave para o pôster

Cada número vem de um relatório em `results/` (arquivo e linha entre parênteses). Reprodutível: `cd backend && uv run python scripts/poster_pack.py`.

1. **3.576 trajetórias** foram processadas ponta a ponta nas estatísticas em lote (2.000 SWE-rebench, 992 do CodeTraceBench verified menos 24 sem trajetória estruturada, 600 SWE-smith). Fonte: `results/batch_stats.md` (linha 3).
2. **9 formatos brutos de logs de agentes viram 1 único modelo canônico** (Trajectory/Step): OpenHands chat, SWE-smith (3 variantes de ação), e 5 formatos do CodeTraceBench. Fonte: `results/parse_report.md` (linha 18) e a figura `formatos_unificados`.
3. **Mediana de 34 ms e p95 de 89 ms por trajetória** para detectar o formato, converter, rotular, detectar problemas e calcular métricas (sem cache), **sem nenhuma rotulação manual** (o tempo de rotular à mão não foi medido). Fonte: `results/batch_stats.md` (linha 18).
4. **97,4% a 99,8% dos passos são rotulados só por regras** (97,4% no CodeTraceBench, 99,8% no SWE-rebench e no SWE-smith); o LLM só é chamado nos 0,2%–2,6% restantes. «rotulado por regra» = confiança ≥ 0,6; a acurácia dessas regras contra o gold manual está no número seguinte. Fonte: `results/labeling_report.md` (linha 11).
5. **Custo total do LLM em todo o projeto: US$ 0,0209** (118 requisições; orçamento planejado: US$ 4,91). Fonte: `backend/.cache/llm_usage.json` e `results/eval_classifier.md` (linha 11).
6. **O classificador de regras acerta 94,3% dos passos contra um gold manual cego** (210 passos de 112 trajetórias, 1 anotador; IC 95% 90,5–97,4%; F1 macro 0,92, kappa 0,93), contra 91,4% do Haiku 5.5 rotulando todos os passos (diferença LLM − regras -2,9 p.p., IC -6,7 a 1,0: indistinguível) e 94,8% das regras + LLM só nos passos incertos (o que o app faz). Os acertos não são uniformes: 100% no SWE-rebench e no SWE-smith, 82,9% no CodeTraceBench; a categoria mais fraca é `setup` (F1 0,53). Fonte: `results/eval_classifier.md` (linha 98).
7. **Sensibilidade ao anotador:** sem as 21 linhas que o anotador marcou como duvidosas, a acurácia das regras vai a 97,9% (IC 95% 95,3–100,0%); nas duvidosas é de ~62% (n = 21). As confusões restantes são `setup` → `edit` (`cp`) e `setup` → `explore` (`which`). Fonte: `results/eval_classifier.md` (linha 128).
8. **Regras e LLM concordam em 89,5% dos passos** (kappa 0,88; n = 210), mas concordância não é acerto: contra o gold, os dois erram em lugares diferentes (só regras acertam 13 passos, só LLM 7, nenhum 5). Fonte: `results/eval_classifier.md` (linha 15).
9. **Detectores × gabarito (CodeTraceBench, 976 trajetórias):** `error ∪ test_fail` acha passos incorretos com precisão de 7,5% e revocação de 22,0% (F1 0,112, **1,62× melhor que sorteio**, IC 95% 1,44–1,80). Fonte: `results/eval_detectors.md` (linha 45).
10. **`repeated ∪ no_new_info` não reproduz os passos "inúteis" do gabarito:** lift de 0,80× (IC 0,12–1,67, contém 1 = indistinguível de acaso). Resultado negativo reportado como tal. Fonte: `results/eval_detectors.md` (linha 30).
11. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** nº de passos é menor nas resolvidas (mediana 56 × 68; δ de Cliff -0,34; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 28).
12. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** % passos test é maior nas resolvidas (mediana 12,8% × 10,7%; δ de Cliff 0,26; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 33).
13. **Resolvidas × não resolvidas (SWE-rebench, 2.000 trajetórias):** taxa de no_new_info é menor nas resolvidas (mediana 2,0% × 2,9%; δ de Cliff -0,16; p corrigido por Holm < 0,001). Fonte: `results/batch_stats.md` (linha 37).
14. **A 1ª versão do detector `no_new_info` errava em 80% dos casos** (16 de 20 auditados no SWE-smith); depois da correção, 0 de 20 e a taxa de marcação caiu de 12,6% para 2,8% dos passos. Fonte: `results/audit_no_new_info.md` (linha 15).
15. **Depois de corrigir `loop` (só a mesma ação normalizada ou o ciclo edit → test_fail com o mesmo erro) o detector ficou muito mais preciso e muito menos sensível:** 48 passos marcados no CodeTraceBench (antes 1899), revocação 0,4% — lift de 2,43×, mas com IC 0,00–3,33 (inconclusivo). Fonte: `results/eval_detectors.md` (linha 60).
16. **Auditoria leve dos detectores (20 casos cada, pré-avaliação do assistente — revisar):** `error` 90% corretos e `repeated` 75% (+25% duvidosos) na rodada 1; `test_fail` foi de **50% para 80% corretos** (duvidosos de 50% para 15%) depois de seguir os códigos de saída do pytest, e `loop` de **25% para 100%** na amostra nova (11 trajetórias; ver ressalva de revocação). Fonte: `results/audit_flags.md` (linha 12).
17. **O gabarito do CodeTraceBench tem 3.316 trajetórias únicas, não 4.316** (o `verified` está contido no `full`), e **34% dos passos anotados só se alinham aos passos reais por hipótese** (o `step_id` tem unidade diferente por agente). Fonte: `docs/formats.md` §0/§4.5 e `results/eval_detectors.md` (linha 7).

## Ressalvas que devem acompanhar os números

- **O gold tem 1 anotador** (o autor do projeto, que conhece a taxonomia): não há concordância entre anotadores; 21 dos 210 passos foram marcados como duvidosos.
- **As amostras do gold são as mesmas de `data/samples/`, usadas na Fase 3 para medir a cobertura das regras**: a acurácia de 100% no SWE-rebench/SWE-smith pode ser otimista; o CodeTraceBench (formatos mais variados) é o recorte mais informativo.
- Categorias raras (`explore` 6, `vcs` 5, `submit` 5, `other` 5, `think` 7 passos) têm F1 com IC muito largo; o F1 macro pesa todas igualmente.
- O SWE-smith traz `resolved` não validado: nenhuma conclusão sobre sucesso real vem dele.
- Resolvidas × não resolvidas é **associação**, não causalidade (tamanho da tarefa, limite de iterações e agente confundem).
- Os vereditos das auditorias são do assistente (1ª leitura), não de um humano.
