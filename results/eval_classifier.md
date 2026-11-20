# Acurácia do classificador de categorias

`backend/scripts/evaluate.py` · gold: `results/gold/gold_steps.csv` · semente 20251119 · IC 95% por bootstrap sobre passos (B=2000).

> ⚠️ **AMOSTRA PEQUENA / SEM GOLD**: apenas **0** de 210 linhas têm `gold_category` preenchida (mínimo recomendado: 70). Acurácia, F1 e matriz de confusão **não puderam ser calculados**; o relatório abaixo traz só a comparação regra × LLM (que não depende do gold). 

- Linhas no CSV: 210 · com gold válido: **0** · valores aceitos: explore, search, read, edit, reproduce, test, setup, vcs, think, submit, other.

## Execução do LLM em todos os passos do gold (ignorando as regras)

Modelo `claude-haiku-5-5` · orçamento máximo US$ 0.05 · passos rotulados: 209/210 (do cache: 0) · requisições: 112 · **custo desta execução: US$ 0.0199** · tokens {'in': 95740, 'out': 16836, 'cache_read': 168720, 'cache_write': 1520}

## Concordância regra × LLM (não depende do gold)

- n = 209 passos · concordância **0.895 [0.852; 0.933]** · kappa de Cohen **0.874 [0.823; 0.920]**

| origem do rótulo da regra | n | concordância com o LLM |
|---|---:|---:|
| rule | 205 | 0.898 |
| fallback | 4 | 0.750 |

Maiores divergências (regra → LLM): edit→reproduce: 4, explore→search: 3, search→explore: 2, explore→setup: 2, read→reproduce: 2, explore→think: 1, reproduce→test: 1, other→setup: 1

## Regras × gold

Sem linhas com `gold_category` preenchida: nada a calcular. Preencha a coluna no CSV (11 categorias: explore, search, read, edit, reproduce, test, setup, vcs, think, submit, other) e rode `uv run python scripts/evaluate.py` de novo.

## Distribuição dos rótulos previstos nos 210 passos do gold

| categoria | regras | LLM |
|---|---:|---:|
| explore | 10 | 6 |
| search | 29 | 30 |
| read | 47 | 44 |
| edit | 41 | 35 |
| reproduce | 47 | 51 |
| test | 8 | 10 |
| setup | 5 | 10 |
| vcs | 6 | 6 |
| think | 7 | 9 |
| submit | 5 | 5 |
| other | 5 | 3 |
