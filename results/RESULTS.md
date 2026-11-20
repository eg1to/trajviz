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
| `gold/gold_steps.csv` | 210 passos para você rotular (`gold_category` vazio); `llm_labels.csv` = rótulos do LLM para comparar | `make_gold_sample.py`, `evaluate.py` |
| `screenshots/` | capturas da interface (Fase 5) | `npm run screenshots` |

## Parágrafo por avaliação

**Detectores × gabarito.** Nas 976 trajetórias avaliadas do `verified`, só `error ∪ test_fail` fica claramente acima de um marcador aleatório com a mesma taxa de flags para os passos *incorretos* (precisão 7,5%, revocação 22,0%, F1 0,112, lift 1,62×, IC 95% 1,44–1,81); `loop` tem lift 1,47× (IC 1,10–1,81) e `repeated ∪ no_new_info` é indistinguível de sorteio para os passos *inúteis* (lift 0,80×, IC 0,12–1,67). No nível de estágio o lift é < 1. 34% dos passos anotados foram alinhados por hipótese (unidades diferentes do `step_id` por agente). Interpretação cautelosa: os conceitos do benchmark ("incorreto", "inútil") não são os mesmos que "comando falhou" e "leitura repetida".

**Auditorias manuais.** `no_new_info`: a 1ª regra tinha 80% de falsos positivos no SWE-smith; corrigida (12,6% → 2,8% dos passos; 0/20 na nova amostra). Os demais detectores, em amostra independente de 20 casos por flag (pré-avaliação do assistente): `error` 90% corretos, `repeated` 75% (25% duvidosos), `test_fail` 50% (50% duvidosos, quase todos exit 2/4/5 do pytest) e `loop` 25% (35% falsos positivos). Nada foi ajustado por causa dessa auditoria.

**Classificador.** Sem gold preenchido (0 de 210 linhas) **não há acurácia nem matriz de confusão**. Foi medida a concordância regra × LLM (Haiku 5.5 em todos os 210 passos, ignorando as regras): 89,5% [85,2; 93,3], kappa 0,874 [0,823; 0,920], com custo de US$ 0,0199 (limite: US$ 0,05). Concordância não é acerto: ela só diz que regras e LLM erram de formas parecidas ou acertam juntos.

**Resolvidas × não resolvidas.** 2.000 trajetórias do SWE-rebench (1.000 + 1.000), 976 do CodeTraceBench e 600 do SWE-smith (resolved não validado). No SWE-rebench, as resolvidas são menores (mediana 56 × 68 passos, δ de Cliff −0,34), têm mais passos de teste (12,8% × 10,7%, δ = 0,26) e menos `no_new_info` (δ = −0,16), todos com p corrigido por Holm < 0,001. Efeitos pequenos a médios e **associativos**: o tamanho da tarefa, o limite de iterações e o agente confundem. Tempo do pipeline: mediana 28 ms, p95 73 ms por trajetória.

**Figuras e pôster.** `figures/` reúne as figuras (mesma paleta do front) e `poster/` os 14 números-chave com fonte, os achados metodológicos e as capturas escolhidas.
