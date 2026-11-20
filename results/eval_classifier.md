# Acurácia do classificador de categorias

`backend/scripts/evaluate.py` · gold: `results/gold/gold_steps_cego_pedro.csv` (CSV cego: sem rótulos de regra/LLM; as previsões ficam em `gold_steps_previsoes.csv`) · semente 20251119 · IC 95% por bootstrap percentil **sobre trajetórias** (B=2000; os passos de uma trajetória não são independentes).

- Linhas no CSV: 210 · com gold válido: **210** (de **112** trajetórias) · marcadas `duvida=1`: **21** · com nota do anotador: 22 · categorias: explore, search, read, edit, reproduce, test, setup, vcs, think, submit, other.
- Métricas: **F1 macro** = média do F1 das categorias que aparecem no gold ou na previsão (cada categoria pesa igual; `submit`, `vcs`, `explore`, `other` têm poucos exemplos); **kappa** de Cohen entre dois rótulos.
- **Regras + LLM** = o que o app faz em produção: o LLM só decide os passos com `label_source = fallback` (confiança < 0,6); nos demais vale a regra. **LLM** = Haiku 5.5 em *todos* os passos, ignorando as regras.

## Execução do LLM em todos os passos do gold (ignorando as regras)

Modelo `claude-haiku-5-5` · orçamento máximo US$ 0.05 · passos rotulados: 210/210 (do cache: 210) · requisições: 0 · **custo desta execução: US$ 0.0000** (acumulado do projeto em `.cache/llm_usage.json`: US$ 0.0209; a 1ª execução pagou US$ 0,0199 e as seguintes reaproveitam o cache) · tokens {'in': 0, 'out': 0, 'cache_read': 0, 'cache_write': 0}

## Concordância regra × LLM (não depende do gold)

- n = 210 passos · concordância **0.895 [0.846; 0.935]** · kappa de Cohen **0.875 [0.817; 0.922]**

| origem do rótulo da regra | n | concordância com o LLM |
|---|---:|---:|
| rule | 206 | 0.898 |
| fallback | 4 | 0.750 |

Maiores divergências (regra → LLM): edit→reproduce: 4, explore→search: 3, search→explore: 2, explore→setup: 2, read→reproduce: 2, explore→think: 1, reproduce→test: 1, other→setup: 1

## Regras × gold

### Por recorte

| recorte | n | traj. | acurácia [IC95] | F1 macro [IC95] |
|---|---:|---:|---|---|
| todos | 210 | 112 | 0.943 [0.904; 0.976] | 0.915 [0.861; 0.961] |
| dataset = CodeTraceBench | 70 | 36 | 0.829 [0.740; 0.912] | 0.829 [0.696; 0.907] |
| dataset = SWE-rebench | 70 | 38 | 1.000 [1.000; 1.000] | 1.000 [1.000; 1.000] |
| dataset = SWE-smith | 70 | 38 | 1.000 [1.000; 1.000] | 1.000 [1.000; 1.000] |
| label_source = fallback | 4 | 3 | 0.250 [0.000; 1.000] | 0.333 [0.000; 1.000] |
| label_source = rule | 206 | 111 | 0.956 [0.923; 0.985] | 0.928 [0.868; 0.972] |

Linha de base trivial (sempre `read`): acurácia 0.224.

### LLM × gold por recorte

| recorte | n | traj. | acurácia [IC95] | F1 macro [IC95] |
|---|---:|---:|---|---|
| todos | 210 | 112 | 0.914 [0.876; 0.952] | 0.872 [0.793; 0.925] |
| dataset = CodeTraceBench | 70 | 36 | 0.843 [0.762; 0.926] | 0.821 [0.683; 0.898] |
| dataset = SWE-rebench | 70 | 38 | 0.957 [0.905; 1.000] | 0.944 [0.825; 1.000] |
| dataset = SWE-smith | 70 | 38 | 0.943 [0.894; 0.986] | 0.716 [0.634; 0.991] |
| label_source = fallback | 4 | 3 | 0.500 [0.000; 1.000] | 0.500 [0.000; 1.000] |
| label_source = rule | 206 | 111 | 0.922 [0.883; 0.955] | 0.879 [0.787; 0.932] |

### F1 por categoria

| categoria | n gold | F1 regras [IC95] | F1 LLM [IC95] | F1 regras+LLM [IC95] | precisão regras | revocação regras |
|---|---:|---|---|---|---:|---:|
| explore | 6 | 0.75 [0.40; 1.00] | 0.67 [0.18; 0.93] | 0.75 [0.40; 1.00] | 0.60 | 1.00 |
| search | 29 | 1.00 [1.00; 1.00] | 0.92 [0.83; 0.98] | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| read | 47 | 0.98 [0.94; 1.00] | 0.97 [0.92; 1.00] | 0.98 [0.94; 1.00] | 0.98 | 0.98 |
| edit | 37 | 0.95 [0.89; 1.00] | 0.93 [0.86; 0.99] | 0.96 [0.90; 1.00] | 0.90 | 1.00 |
| reproduce | 47 | 0.96 [0.91; 0.99] | 0.94 [0.89; 0.98] | 0.96 [0.91; 0.99] | 0.96 | 0.96 |
| test | 8 | 1.00 [1.00; 1.00] | 0.89 [0.67; 1.00] | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| setup | 14 | 0.53 [0.15; 0.78] | 0.75 [0.48; 0.93] | 0.60 [0.25; 0.84] | 1.00 | 0.36 |
| vcs | 5 | 0.91 [0.67; 1.00] | 0.91 [0.67; 1.00] | 0.91 [0.67; 1.00] | 0.83 | 1.00 |
| think | 7 | 1.00 [1.00; 1.00] | 0.88 [0.60; 1.00] | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| submit | 5 | 1.00 [1.00; 1.00] | 1.00 [1.00; 1.00] | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| other | 5 | 1.00 [1.00; 1.00] | 0.75 [0.00; 1.00] | 1.00 [1.00; 1.00] | 1.00 | 1.00 |

### Matriz de confusão — regras (linhas = gold, colunas = previsto; `·` = 0)

| gold \ previsto | explore | search | read | edit | reproduce | test | setup | vcs | think | submit | other | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **explore** | **6** | · | · | · | · | · | · | · | · | · | · | 6 |
| **search** | · | **29** | · | · | · | · | · | · | · | · | · | 29 |
| **read** | · | · | **46** | · | 1 | · | · | · | · | · | · | 47 |
| **edit** | · | · | · | **37** | · | · | · | · | · | · | · | 37 |
| **reproduce** | · | · | 1 | 1 | **45** | · | · | · | · | · | · | 47 |
| **test** | · | · | · | · | · | **8** | · | · | · | · | · | 8 |
| **setup** | 4 | · | · | 3 | 1 | · | **5** | 1 | · | · | · | 14 |
| **vcs** | · | · | · | · | · | · | · | **5** | · | · | · | 5 |
| **think** | · | · | · | · | · | · | · | · | **7** | · | · | 7 |
| **submit** | · | · | · | · | · | · | · | · | · | **5** | · | 5 |
| **other** | · | · | · | · | · | · | · | · | · | · | **5** | 5 |

### Matriz de confusão — LLM (todos os passos)

| gold \ previsto | explore | search | read | edit | reproduce | test | setup | vcs | think | submit | other | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **explore** | **4** | 1 | · | · | · | · | · | · | 1 | · | · | 6 |
| **search** | 2 | **27** | · | · | · | · | · | · | · | · | · | 29 |
| **read** | · | · | **44** | · | 1 | · | · | 1 | 1 | · | · | 47 |
| **edit** | · | · | · | **34** | 3 | · | · | · | · | · | · | 37 |
| **reproduce** | · | · | · | · | **46** | 1 | · | · | · | · | · | 47 |
| **test** | · | · | · | · | · | **8** | · | · | · | · | · | 8 |
| **setup** | · | 2 | · | 2 | 1 | · | **9** | · | · | · | · | 14 |
| **vcs** | · | · | · | · | · | · | · | **5** | · | · | · | 5 |
| **think** | · | · | · | · | · | · | · | · | **7** | · | · | 7 |
| **submit** | · | · | · | · | · | · | · | · | · | **5** | · | 5 |
| **other** | · | · | · | · | · | 1 | 1 | · | · | · | **3** | 5 |

## Três vias: regras × LLM × gold (nos mesmos passos)

| método | n | acurácia [IC95] | F1 macro [IC95] | kappa com o gold [IC95] |
|---|---:|---|---|---|
| regras | 210 | 0.943 [0.905; 0.974] | 0.915 [0.860; 0.959] | 0.932 [0.887; 0.969] |
| LLM | 210 | 0.914 [0.874; 0.952] | 0.872 [0.794; 0.926] | 0.898 [0.850; 0.942] |
| regras+LLM | 210 | 0.948 [0.911; 0.980] | 0.923 [0.863; 0.970] | 0.938 [0.895; 0.976] |

- kappa regras × LLM: 0.875 [0.821; 0.928] (concordância 0.895 [0.849; 0.941]).
- Diferença LLM − regras (pareada, bootstrap por trajetória): acurácia **-0.029** [-0.067; +0.010] · F1 macro **-0.043** [-0.128; +0.027].
- Diferença regras+LLM − regras: acurácia **+0.005** [+0.000; +0.015] (4 passos em `fallback` no gold: o LLM só entra neles).

- Acertos: ambos 185 · só regras 13 · só LLM 7 · nenhum 5.

## As 10 maiores confusões (regras: gold → previsto)

| # | gold → previsto | n (com dúvida) | exemplo (passo) | tool · ação | nota do anotador |
|---:|---|---:|---|---|---|
| 1 | setup → explore | 4 (3) | CodeTraceBench #4 ⚠ | `keystrokes` · which tesseract | Verifica ferramenta disponível no ambiente do sistema com which (setup vs explore). |
| 2 | setup → edit | 3 (0) | CodeTraceBench #68 | `run` · cp /app/doom.wad /app/doomgeneric_mips.wad 2>/dev/null \|\| true | — |
| 3 | setup → reproduce | 1 (1) | CodeTraceBench #19 ⚠ | `run` · python -c "import pandas, sklearn, pyarrow, numpy; from rdkit import Chem; print('All packages working!')" | Usa python -c (forma comum de reproduce), mas o objetivo é apenas verificar se os pacotes instalados no ambiente funcionam (setup). |
| 4 | read → reproduce | 1 (1) | CodeTraceBench #16 ⚠ | `keystrokes` · python3 -c "import pandas as pd; df = pd.read_parquet('mapk14_1M.parquet'); print('Training data shape:', df.s… | Usa python3 -c para ler e inspecionar esquema/linhas de um arquivo .parquet (funcionalmente read, embora use python -c típico de reproduce). |
| 5 | reproduce → read | 1 (1) | CodeTraceBench #19 ⚠ | `bash` · sqlite3 /app/oewn.sqlite "SELECT * FROM (SELECT w.wordid AS word_id, w.word AS word, COUNT(DISTINCT s.synsetid… | Executa consulta via sqlite3 para testar a lógica da query desenvolvida (fronteira entre reproduce e read). |
| 6 | reproduce → edit | 1 (1) | CodeTraceBench #66 ⚠ | `bash` · cd ocaml && make runtime > simple_build.log 2>&1 && echo "Compilation successful" \|\| echo "Compilation faile… | Executa make runtime para testar se o projeto compila após ajuste; fronteira entre reproduce (checar erro de build) e setup (compilação do ambiente). |
| 7 | setup → vcs | 1 (1) | CodeTraceBench #28 ⚠ | `run` · cd /app && git clone --depth 1 --branch v1.0.0 https://github.com/Anurag461/lm-evaluation-harness.git | Usa git clone para baixar e instalar repositório no ambiente (setup), não para inspecionar histórico/status (vcs). |

⚠ = o exemplo é uma linha marcada `duvida=1`. O exemplo é, quando há, uma linha com nota do anotador. Previsto = rótulo da regra (`pred_category`).

Para comparação, as 5 maiores confusões do **LLM** (gold → LLM): edit → reproduce: 3; search → explore: 2; setup → search: 2; setup → edit: 2; explore → think: 1

## Sensibilidade: excluindo as 21 linhas com `duvida=1` (n = 189)

| método | n | acurácia [IC95] | F1 macro [IC95] | kappa [IC95] | Δ acurácia vs. todos | Δ F1 macro vs. todos |
|---|---:|---|---|---|---:|---:|
| regras | 189 | 0.979 [0.953; 1.000] | 0.962 [0.905; 1.000] | 0.974 [0.943; 1.000] | +0.036 | +0.047 |
| LLM | 189 | 0.963 [0.933; 0.989] | 0.957 [0.893; 0.992] | 0.955 [0.919; 0.987] | +0.049 | +0.085 |
| regras+LLM | 189 | 0.984 [0.961; 1.000] | 0.971 [0.919; 1.000] | 0.981 [0.953; 1.000] | +0.037 | +0.048 |

Acurácia **só nas linhas duvidosas** (n = 21; IC por trajetória, muito largo): regras 0.619 [0.421; 0.800], LLM 0.476 [0.261; 0.700], regras+LLM 0.619 [0.421; 0.800]

F1 por categoria das regras sem as linhas duvidosas:

| categoria | n gold | F1 regras [IC95] | precisão regras | revocação regras |
|---|---:|---|---:|---:|
| explore | 5 | 0.91 [0.60; 1.00] | 0.83 | 1.00 |
| search | 27 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| read | 43 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| edit | 37 | 0.96 [0.90; 1.00] | 0.93 | 1.00 |
| reproduce | 43 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| test | 8 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| setup | 9 | 0.71 [0.28; 1.00] | 1.00 | 0.56 |
| vcs | 4 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| think | 7 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| submit | 5 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |
| other | 1 | 1.00 [1.00; 1.00] | 1.00 | 1.00 |

Maiores confusões das regras sem as duvidosas: setup → edit: 3; setup → explore: 1. Ranking idêntico ao completo? **não**.

## Distribuição dos rótulos nos 210 passos do gold

| categoria | gold | regras | LLM |
|---|---:|---:|---:|
| explore | 6 | 10 | 6 |
| search | 29 | 29 | 30 |
| read | 47 | 47 | 44 |
| edit | 37 | 41 | 36 |
| reproduce | 47 | 47 | 51 |
| test | 8 | 8 | 10 |
| setup | 14 | 5 | 10 |
| vcs | 5 | 6 | 6 |
| think | 7 | 7 | 9 |
| submit | 5 | 5 | 5 |
| other | 5 | 5 | 3 |
