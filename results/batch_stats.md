# Resolvidas × não resolvidas — estatísticas em lote (só regras)

`backend/scripts/batch_stats.py` · semente 20251119 · 3576 trajetórias processadas · tabela por trajetória em `results/batch_stats.parquet`.

Convenção: **Δ de Cliff > 0 = a métrica é MAIOR nas resolvidas**. p = Mann-Whitney bilateral; **p(Holm)** corrige pelas 13 métricas de cada estrato (`*` p<0,05, `**` <0,01, `***` <0,001, sobre o p corrigido). |Δ| < 0,147 desprezível · < 0,33 pequeno · < 0,474 médio · ≥ 0,474 grande (Romano et al.).

> ⚠️ **SWE-smith: `resolved` não validado** (o patch não bate com a trajetória em ~83% das linhas; ver docs/formats.md §0). Os números do SWE-smith descrevem a coluna `resolved` como está e **não** podem ser lidos como sucesso real da tarefa. No CodeTraceBench, agentes/origens (SWE-bench × TerminalBench) e limites de iteração confundem as comparações; no SWE-rebench o agente e o modelo são fixos mas o tamanho da tarefa não é controlado. **Associação, não causalidade.**

## Tempo do pipeline (detect → parse → rótulos → detectores → métricas, por trajetória, sem cache, sem I/O do Parquet)

- Total desta execução (incluindo leitura dos dados): **195 s** para 3576 trajetórias · só pipeline: 139 s

| dataset | traj. | mediana (s) | p95 (s) | máx (s) | passos medianos |
|---|---:|---:|---:|---:|---:|
| CodeTraceBench | 976 | 0.052 | 0.151 | 1.206 | 35 |
| SWE-rebench | 2000 | 0.031 | 0.059 | 0.121 | 62 |
| SWE-smith | 600 | 0.010 | 0.028 | 0.059 | 24 |
| **todos** | 3576 | 0.031 | 0.092 | 1.206 | 50 |

Descartadas: {'ctb_unsupported': 16, 'ctb_sem_artefato': 8, 'erros': 0}.

## SWE-rebench (2.000: 1.000 resolvidas + 1.000 não)

resolvidas n = 1000 · não resolvidas n = 1000

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 56.000 | 68.000 | -0.340 | 0.0000 | 0.0000*** |
| % Entendimento | 0.404 | 0.414 | -0.070 | 0.0065 | 0.0326* |
| % Modificação | 0.152 | 0.161 | -0.094 | 0.0003 | 0.0018** |
| % Verificação | 0.333 | 0.312 | 0.150 | 0.0000 | 0.0000*** |
| % Controle | 0.092 | 0.082 | 0.103 | 0.0001 | 0.0005*** |
| % passos test | 0.128 | 0.107 | 0.261 | 0.0000 | 0.0000*** |
| posição relativa da 1ª edição | 0.405 | 0.383 | 0.104 | 0.0001 | 0.0005*** |
| taxa de error | 0.042 | 0.048 | -0.084 | 0.0011 | 0.0067** |
| taxa de repeated | 0.000 | 0.000 | -0.011 | 0.5906 | 1.0000 |
| taxa de no_new_info | 0.020 | 0.029 | -0.161 | 0.0000 | 0.0000*** |
| taxa de loop | 0.000 | 0.000 | -0.005 | 0.2239 | 0.6716 |
| ciclos edit→test | 2.000 | 2.000 | 0.014 | 0.5656 | 1.0000 |
| % ciclos terminando em test_pass | 1.000 | 1.000 | 0.054 | 0.0229 | 0.0916 |

## CodeTraceBench verified — todos (solved conhecido)

resolvidas n = 498 · não resolvidas n = 450

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 33.000 | 38.000 | -0.221 | 0.0000 | 0.0000*** |
| % Entendimento | 0.434 | 0.372 | 0.191 | 0.0000 | 0.0000*** |
| % Modificação | 0.110 | 0.156 | -0.188 | 0.0000 | 0.0000*** |
| % Verificação | 0.208 | 0.190 | -0.000 | 0.9989 | 1.0000 |
| % Controle | 0.179 | 0.168 | -0.008 | 0.8387 | 1.0000 |
| % passos test | 0.026 | 0.000 | 0.189 | 0.0000 | 0.0000*** |
| posição relativa da 1ª edição | 0.400 | 0.319 | 0.179 | 0.0000 | 0.0000*** |
| taxa de error | 0.075 | 0.089 | -0.112 | 0.0028 | 0.0194* |
| taxa de repeated | 0.000 | 0.000 | 0.024 | 0.4539 | 1.0000 |
| taxa de no_new_info | 0.000 | 0.000 | -0.025 | 0.4478 | 1.0000 |
| taxa de loop | 0.000 | 0.000 | -0.013 | 0.0098 | 0.0588 |
| ciclos edit→test | 0.000 | 0.000 | 0.129 | 0.0001 | 0.0006*** |
| % ciclos terminando em test_pass | 0.000 | 0.000 | -0.060 | 0.2475 | 1.0000 |

## CodeTraceBench verified — OpenHands

resolvidas n = 287 · não resolvidas n = 225

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 35.000 | 42.000 | -0.306 | 0.0000 | 0.0000*** |
| % Entendimento | 0.421 | 0.389 | 0.109 | 0.0344 | 0.2063 |
| % Modificação | 0.073 | 0.114 | -0.216 | 0.0000 | 0.0003*** |
| % Verificação | 0.238 | 0.231 | 0.005 | 0.9183 | 1.0000 |
| % Controle | 0.231 | 0.200 | 0.113 | 0.0274 | 0.1920 |
| % passos test | 0.043 | 0.020 | 0.239 | 0.0000 | 0.0000*** |
| posição relativa da 1ª edição | 0.411 | 0.342 | 0.147 | 0.0048 | 0.0406* |
| taxa de error | 0.077 | 0.100 | -0.172 | 0.0008 | 0.0081** |
| taxa de repeated | 0.000 | 0.000 | 0.017 | 0.6893 | 1.0000 |
| taxa de no_new_info | 0.000 | 0.000 | -0.046 | 0.3026 | 0.9623 |
| taxa de loop | 0.000 | 0.000 | -0.009 | 0.1105 | 0.5524 |
| ciclos edit→test | 1.000 | 0.000 | 0.132 | 0.0045 | 0.0406* |
| % ciclos terminando em test_pass | 0.000 | 0.000 | -0.073 | 0.2406 | 0.9623 |

## CodeTraceBench verified — SWE-agent

resolvidas n = 80 · não resolvidas n = 28

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 34.000 | 43.500 | -0.256 | 0.0449 | 0.3590 |
| % Entendimento | 0.623 | 0.600 | 0.038 | 0.7684 | 1.0000 |
| % Modificação | 0.150 | 0.167 | -0.033 | 0.7953 | 1.0000 |
| % Verificação | 0.109 | 0.160 | -0.273 | 0.0324 | 0.2919 |
| % Controle | 0.058 | 0.035 | 0.244 | 0.0555 | 0.3888 |
| % passos test | 0.000 | 0.052 | -0.368 | 0.0017 | 0.0204* |
| posição relativa da 1ª edição | 0.419 | 0.447 | -0.016 | 0.9059 | 1.0000 |
| taxa de error | 0.051 | 0.068 | -0.137 | 0.2795 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | 0.308 | 0.0034 | 0.0358* |
| taxa de no_new_info | 0.017 | 0.020 | 0.087 | 0.4728 | 1.0000 |
| taxa de loop | 0.000 | 0.000 | -0.107 | 0.0033 | 0.0358* |
| ciclos edit→test | 0.000 | 1.000 | -0.366 | 0.0011 | 0.0147* |
| % ciclos terminando em test_pass | 0.000 | 0.250 | -0.229 | 0.1355 | 0.8131 |

## CodeTraceBench verified — Terminus2

resolvidas n = 69 · não resolvidas n = 123

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 22.000 | 35.000 | -0.448 | 0.0000 | 0.0000*** |
| % Entendimento | 0.286 | 0.259 | -0.015 | 0.8625 | 1.0000 |
| % Modificação | 0.231 | 0.289 | -0.058 | 0.5072 | 1.0000 |
| % Verificação | 0.190 | 0.143 | 0.148 | 0.0897 | 0.6395 |
| % Controle | 0.231 | 0.167 | 0.207 | 0.0174 | 0.1740 |
| % passos test | 0.000 | 0.000 | 0.104 | 0.0799 | 0.6395 |
| posição relativa da 1ª edição | 0.250 | 0.163 | 0.082 | 0.3610 | 1.0000 |
| taxa de error | 0.081 | 0.067 | 0.046 | 0.5949 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | -0.045 | 0.5437 | 1.0000 |
| taxa de no_new_info | 0.000 | 0.000 | -0.230 | 0.0008 | 0.0087** |
| taxa de loop | 0.000 | 0.000 | 0.000 | — | — |
| ciclos edit→test | 0.000 | 0.000 | 0.104 | 0.0615 | 0.5535 |
| % ciclos terminando em test_pass | 0.000 | 0.000 | 0.058 | 0.6166 | 1.0000 |

## CodeTraceBench verified — mini-SWE-agent

resolvidas n = 62 · não resolvidas n = 74

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 25.000 | 26.000 | -0.086 | 0.3884 | 1.0000 |
| % Entendimento | 0.645 | 0.436 | 0.397 | 0.0001 | 0.0009*** |
| % Modificação | 0.179 | 0.193 | -0.120 | 0.2303 | 1.0000 |
| % Verificação | 0.066 | 0.119 | -0.238 | 0.0165 | 0.1810 |
| % Controle | 0.050 | 0.095 | -0.308 | 0.0020 | 0.0241* |
| % passos test | 0.000 | 0.000 | 0.127 | 0.0689 | 0.6200 |
| posição relativa da 1ª edição | 0.432 | 0.346 | 0.201 | 0.0442 | 0.4418 |
| taxa de error | 0.086 | 0.113 | -0.144 | 0.1496 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | 0.032 | 0.7184 | 1.0000 |
| taxa de no_new_info | 0.043 | 0.020 | 0.124 | 0.1927 | 1.0000 |
| taxa de loop | 0.000 | 0.000 | -0.014 | 0.3678 | 1.0000 |
| ciclos edit→test | 0.000 | 0.000 | 0.104 | 0.1214 | 0.9716 |
| % ciclos terminando em test_pass | 0.333 | 0.250 | 0.013 | 0.9763 | 1.0000 |

## SWE-smith (600) — ⚠ resolved NÃO VALIDADO

resolvidas n = 255 · não resolvidas n = 345

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 21.000 | 28.000 | -0.266 | 0.0000 | 0.0000*** |
| % Entendimento | 0.346 | 0.348 | -0.013 | 0.7889 | 1.0000 |
| % Modificação | 0.254 | 0.284 | -0.178 | 0.0002 | 0.0018** |
| % Verificação | 0.250 | 0.250 | 0.025 | 0.6008 | 1.0000 |
| % Controle | 0.125 | 0.091 | 0.331 | 0.0000 | 0.0000*** |
| % passos test | 0.000 | 0.000 | 0.112 | 0.0001 | 0.0010** |
| posição relativa da 1ª edição | 0.280 | 0.250 | 0.115 | 0.0162 | 0.0971 |
| taxa de error | 0.067 | 0.062 | -0.002 | 0.9678 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | -0.069 | 0.0375 | 0.1829 |
| taxa de no_new_info | 0.000 | 0.000 | -0.131 | 0.0011 | 0.0080** |
| taxa de loop | 0.000 | 0.000 | -0.022 | 0.0366 | 0.1829 |
| ciclos edit→test | 0.000 | 0.000 | 0.110 | 0.0001 | 0.0010** |
| % ciclos terminando em test_pass | 0.667 | 0.167 | 0.473 | 0.0003 | 0.0022** |

## SWE-smith/tool (200) — ⚠ resolved NÃO VALIDADO

resolvidas n = 79 · não resolvidas n = 121

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 22.000 | 27.000 | -0.284 | 0.0007 | 0.0092** |
| % Entendimento | 0.333 | 0.333 | -0.003 | 0.9691 | 1.0000 |
| % Modificação | 0.267 | 0.286 | -0.206 | 0.0139 | 0.1529 |
| % Verificação | 0.261 | 0.250 | 0.053 | 0.5246 | 1.0000 |
| % Controle | 0.115 | 0.094 | 0.272 | 0.0011 | 0.0137* |
| % passos test | 0.000 | 0.000 | 0.076 | 0.0886 | 0.7090 |
| posição relativa da 1ª edição | 0.278 | 0.242 | 0.120 | 0.1517 | 1.0000 |
| taxa de error | 0.067 | 0.057 | -0.033 | 0.6953 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | -0.019 | 0.7434 | 1.0000 |
| taxa de no_new_info | 0.000 | 0.000 | -0.080 | 0.2465 | 1.0000 |
| taxa de loop | 0.000 | 0.000 | -0.017 | 0.2550 | 1.0000 |
| ciclos edit→test | 0.000 | 0.000 | 0.079 | 0.0590 | 0.5391 |
| % ciclos terminando em test_pass | 1.000 | 0.200 | 0.545 | 0.0539 | 0.5391 |

## SWE-smith/xml (200) — ⚠ resolved NÃO VALIDADO

resolvidas n = 88 · não resolvidas n = 112

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 21.000 | 28.000 | -0.187 | 0.0233 | 0.2327 |
| % Entendimento | 0.371 | 0.376 | -0.026 | 0.7565 | 1.0000 |
| % Modificação | 0.239 | 0.273 | -0.146 | 0.0769 | 0.6923 |
| % Verificação | 0.240 | 0.238 | 0.025 | 0.7602 | 1.0000 |
| % Controle | 0.130 | 0.092 | 0.344 | 0.0000 | 0.0004*** |
| % passos test | 0.000 | 0.000 | 0.137 | 0.0046 | 0.0547 |
| posição relativa da 1ª edição | 0.274 | 0.270 | 0.019 | 0.8206 | 1.0000 |
| taxa de error | 0.067 | 0.054 | 0.064 | 0.4366 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | -0.048 | 0.3617 | 1.0000 |
| taxa de no_new_info | 0.000 | 0.000 | -0.110 | 0.1250 | 0.9788 |
| taxa de loop | 0.000 | 0.000 | -0.009 | 0.3808 | 1.0000 |
| ciclos edit→test | 0.000 | 0.000 | 0.134 | 0.0054 | 0.0595 |
| % ciclos terminando em test_pass | 0.500 | 0.125 | 0.375 | 0.1224 | 0.9788 |

## SWE-smith/ticks (200) — ⚠ resolved NÃO VALIDADO

resolvidas n = 88 · não resolvidas n = 112

| métrica | mediana resolvidas | mediana não resolvidas | Δ de Cliff | p | p (Holm) |
|---|---:|---:|---:|---:|---:|
| nº de passos | 21.000 | 30.500 | -0.325 | 0.0001 | 0.0009*** |
| % Entendimento | 0.312 | 0.333 | -0.020 | 0.8075 | 1.0000 |
| % Modificação | 0.265 | 0.290 | -0.176 | 0.0328 | 0.2297 |
| % Verificação | 0.260 | 0.250 | 0.010 | 0.9088 | 1.0000 |
| % Controle | 0.125 | 0.086 | 0.369 | 0.0000 | 0.0001*** |
| % passos test | 0.000 | 0.000 | 0.115 | 0.0372 | 0.2297 |
| posição relativa da 1ª edição | 0.288 | 0.244 | 0.194 | 0.0184 | 0.1658 |
| taxa de error | 0.070 | 0.077 | -0.037 | 0.6519 | 1.0000 |
| taxa de repeated | 0.000 | 0.000 | -0.135 | 0.0255 | 0.2041 |
| taxa de no_new_info | 0.000 | 0.000 | -0.208 | 0.0025 | 0.0277* |
| taxa de loop | 0.000 | 0.000 | -0.042 | 0.1104 | 0.4417 |
| ciclos edit→test | 0.000 | 0.000 | 0.106 | 0.0545 | 0.2726 |
| % ciclos terminando em test_pass | 0.833 | 0.083 | 0.497 | 0.0101 | 0.1015 |

