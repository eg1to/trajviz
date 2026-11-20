# Índice de resultados (Fase 6)

Tudo é reprodutível com semente fixa (20251119) a partir de `backend/scripts/`. **Leia as ressalvas de cada avaliação**: o gold manual ainda não foi preenchido e as auditorias são pré-avaliações do assistente.

| arquivo | o que é | script |
|---|---|---|
| `warm_cache_report.md` / `warm_cache_cold_report.md` | % de passos com cada flag por dataset e tempo do pipeline nas amostras da biblioteca | `warm_cache.py [--cold]` |
| `eval_detectors.md` / `.json` | detectores × gabarito do CodeTraceBench (verified, 976 trajetórias) | `eval_detectors.py` |
| `audit_no_new_info.md` | auditoria do `no_new_info` no SWE-smith (1ª rodada: 80% de falsos positivos; 2ª: 0/20) | `audit_no_new_info.py` |
| `audit_flags.md` | auditoria leve de `error`, `repeated`, `loop`, `test_fail` (pré-avaliação do assistente) | `audit_flags.py` |
| `eval_classifier.md` / `.json` | classificador de categorias: concordância regra × LLM; acurácia × gold (**gold vazio**) | `evaluate.py` |
| `batch_stats.md` / `.json` / `.parquet` | resolvidas × não resolvidas em 3.576 trajetórias; tempo do pipeline | `batch_stats.py` |
| `figures/` | 6 figuras do pôster (PNG 300 dpi + SVG) e `palette.json` | `figures.py`, `export_palette.py` |
| `poster/` | `numeros.md`, `achados_metodologicos.md`, figuras e 3 capturas | `poster_pack.py` |
| `labeling_report.md`, `parse_report.md` | cobertura da rotulação e do parse (fases 2–3) | `label_report.py`, `parse_samples.py` |
| `gold/gold_steps_cego.csv` | 210 passos para você rotular — **só contexto + `gold_category` vazio** (sem rótulo da regra, do LLM, confiança nem label_source) | `make_gold_sample.py` |
| `gold/gold_steps_previsoes.csv`, `eval_classifier_llm_labels.csv` | previsões da regra e do LLM, **para não abrir antes de rotular**; `evaluate.py` junta tudo pelo `id` | `make_gold_sample.py`, `evaluate.py` |
| `eval_detectors_before.{md,json}`, `batch_stats_before.json` | resultados ANTES da correção de `test_fail` e `loop` (para a comparação lado a lado) | — |
| `screenshots/` | capturas da interface (Fase 5) | `npm run screenshots` |

## Parágrafo por avaliação

**Detectores × gabarito.** Nas 976 trajetórias avaliadas do `verified` (re-executado depois da correção de `test_fail` e `loop`; antes × depois lado a lado em `eval_detectors.md`): `error ∪ test_fail` continua acima de um marcador aleatório com a mesma taxa de flags para os passos *incorretos* (precisão 7,5%, revocação 22,0%, F1 0,112, lift 1,62×, IC 95% 1,44–1,80) — a correção do `test_fail` mexeu pouco aqui porque o que saiu de `test_fail` (pytest exit 2/4) entrou em `error`, e a união é a mesma; `repeated ∪ no_new_info` é indistinguível de sorteio para os passos *inúteis* (lift 0,80×, IC 0,12–1,67). **`loop` mudou muito:** de 1.899 passos marcados para 48 (precisão 7,1% → 12,5%, revocação 9,0% → 0,4%); o lift de 2,43× tem IC 0,00–3,33, ou seja, **inconclusivo**. No nível de estágio o lift segue < 1. 34% dos passos anotados foram alinhados por hipótese. Os conceitos do benchmark ("incorreto", "inútil") não são os mesmos que "comando falhou" e "leitura repetida".

**Auditorias manuais** (vereditos meus, "pré-avaliação do assistente — revisar"). `no_new_info`: a 1ª regra tinha 80% de falsos positivos no SWE-smith; corrigida (12,6% → 2,8% dos passos; 0/20 na nova amostra). Rodada 1 dos demais detectores (20 casos por flag): `error` 90% corretos, `repeated` 75% (25% duvidosos), `test_fail` 50% (50% duvidosos, quase todos exit 2/4/5 do pytest) e `loop` 25% (35% falsos positivos). **Rodada 2, depois da correção, em ~1.150 trajetórias novas (semente diferente, nenhum caso reaproveitado):** `test_fail` **80%** corretos (3 duvidosos e 1 falso positivo — o exit do `grep` no fim de um pipe) e `loop` **100%** (20/20, de apenas 11 trajetórias; os laços são genuínos, mas o detector perdeu revocação). A auditoria expôs duas lacunas da minha própria implementação de `loop`, corrigidas antes da amostra final (ver `audit_flags.md`).

**Classificador.** Sem gold preenchido (0 de 210 linhas) **não há acurácia nem matriz de confusão**. Foi medida a concordância regra × LLM (Haiku 5.5 em todos os 210 passos, ignorando as regras): ~89,5%, kappa ~0,88, com custo total de US$ 0,0209 (limite: US$ 0,05; ver `eval_classifier.md`). Concordância não é acerto. **O CSV que você preenche agora é cego** (`gold/gold_steps_cego.csv`: sem rótulos da regra nem do LLM); as previsões ficam em arquivos separados que o `evaluate.py` junta pelo `id`.

**Resolvidas × não resolvidas.** 2.000 trajetórias do SWE-rebench (1.000 + 1.000), 976 do CodeTraceBench e 600 do SWE-smith (resolved não validado). No SWE-rebench, as resolvidas são menores (mediana 56 × 68 passos, δ de Cliff −0,34), têm mais passos de teste (12,8% × 10,7%, δ = 0,26) e menos `no_new_info` (δ = −0,16), todos com p corrigido por Holm < 0,001. Efeitos pequenos a médios e **associativos**: o tamanho da tarefa, o limite de iterações e o agente confundem. Tempo do pipeline: mediana 31 ms, p95 92 ms por trajetória. (A taxa de `loop` deixou de diferir entre os grupos depois da correção: δ = −0,005, p(Holm) = 0,67.)

**Figuras e pôster.** `figures/` reúne as figuras (mesma paleta do front) e `poster/` os 14 números-chave com fonte, os achados metodológicos e as capturas escolhidas.
