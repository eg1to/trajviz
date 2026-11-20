# Detectores × gabarito do CodeTraceBench (`verified`)

`backend/scripts/eval_detectors.py` · só regras (sem LLM) · semente 20251119 · bootstrap B=2000 **sobre trajetórias** · linha de base aleatória = 100 sorteios com a mesma nº de flags por trajetória.

- Trajetórias avaliadas: **976** de 1000 (descartadas: {'sem_artefato': 8, 'unsupported': 16}); por agente: {'OpenHands': 512, 'SWE-agent': 108, 'Terminus2': 220, 'mini-SWE-agent': 136}.
- Só **392** delas têm ao menos um passo incorreto/inútil anotado; as demais entram como "anotadas sem problemas" (negativos).
- 34% dos passos anotados foram alinhados por **hipótese** (cauda do `step_id`; docs/formats.md §4.5) — ver a linha "só alinhamento confirmado".

P/R/F1 são agregados (somando contagens de todas as trajetórias do recorte). **lift** = F1 do detector ÷ F1 do marcador aleatório; IC 95% por bootstrap.

## Interpretação (5 linhas)

1. **`repeated ∪ no_new_info` não reproduz os passos "inúteis" do gabarito**: precisão 0.4%, revocação 3.8%, lift 0.80× (IC 0.12–1.67, contém 1) — indistinguível de sorteio. O gabarito define "inútil" por julgamento do anotador; leitura idêntica a uma anterior capta, no máximo, uma fração mínima disso (hipótese não testada: não auditei os passos anotados).
2. **`error ∪ test_fail` é fraco, mas acima do acaso** para os passos incorretos: precisão 7.5%, revocação 22.0%, F1 0.112, lift 1.62× (IC 1.44–1.81); no mini-SWE-agent chega a F1 0.275 (lift 1.94×). Hipótese (não testada): "incorreto" no gabarito é ação que muda o estado de forma errada, o que difere de comando que falha.
3. **`loop`** tem lift 1.47× (IC 1.10–1.81) com precisão de 7.1% e IC largo em vários recortes: sinal marginal.
4. **No nível de estágio a revocação parece boa (41.8%), mas é efeito da taxa de flags**: 3221 de 6561 estágios têm ≥ 1 flag, a precisão é 6.9% e o lift é 0.84× (< 1). Com só `error ∪ test_fail ∪ loop` o lift é 0.92×. A linha de base sorteia estágios sem considerar o tamanho do estágio (limitação: estágios longos têm mais chance de ter flag).
5. **Limitações**: 33.7% dos passos anotados foram alinhados por hipótese (cauda do `step_id`); restringir ao alinhamento confirmado muda o lift de `error ∪ test_fail` para 1.73× e derruba os positivos de `unuseful` para 126; excluir `harness_protocol` quase não muda nada; 392 de 976 trajetórias têm alguma anotação (o resto vale como "sem problemas", o que pode não ser verdade).
## unuseful × repeated ∪ no_new_info

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 39857 | 208 | 2009 | 0.004 [0.000; 0.009] | 0.038 [0.005; 0.078] | 0.007 [0.001; 0.017] | 0.009 | 0.80 [0.12; 1.67]× |
| agente = OpenHands | 512 | 22617 | 52 | 749 | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.004 | 0.00 [0.00; 0.00]× |
| agente = SWE-agent | 108 | 4512 | 47 | 374 | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.005 | 0.00 [0.00; 0.00]× |
| agente = Terminus2 | 220 | 8719 | 84 | 566 | 0.012 [0.000; 0.036] | 0.083 [0.000; 0.164] | 0.022 [0.000; 0.057] | 0.017 | 1.25 [0.00; 2.52]× |
| agente = mini-SWE-agent | 136 | 4009 | 25 | 320 | 0.003 [0.000; 0.010] | 0.040 [0.000; 0.133] | 0.006 [0.000; 0.019] | 0.008 | 0.70 [0.00; 2.10]× |
| origem = SWE-bench | 489 | 18116 | 69 | 861 | 0.001 [0.000; 0.004] | 0.014 [0.000; 0.049] | 0.002 [0.000; 0.007] | 0.003 | 0.64 [0.00; 1.79]× |
| origem = TerminalBench | 487 | 21741 | 139 | 1148 | 0.006 [0.000; 0.015] | 0.050 [0.000; 0.105] | 0.011 [0.000; 0.027] | 0.012 | 0.89 [0.00; 1.83]× |
| com harness_protocol (padrão) | 976 | 39857 | 208 | 2009 | 0.004 [0.000; 0.009] | 0.038 [0.005; 0.079] | 0.007 [0.001; 0.017] | 0.009 | 0.82 [0.11; 1.67]× |
| sem harness_protocol | 976 | 39619 | 202 | 2009 | 0.004 [0.000; 0.009] | 0.040 [0.005; 0.083] | 0.007 [0.001; 0.017] | 0.009 | 0.83 [0.12; 1.70]× |
| só alinhamento confirmado | 976 | 39315 | 126 | 1982 | 0.001 [0.000; 0.003] | 0.016 [0.000; 0.042] | 0.002 [0.000; 0.005] | 0.006 | 0.30 [0.00; 0.77]× |

## incorrect × error ∪ test_fail

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 39857 | 1497 | 4398 | 0.075 [0.059; 0.092] | 0.220 [0.185; 0.256] | 0.112 [0.090; 0.134] | 0.069 | 1.62 [1.44; 1.81]× |
| agente = OpenHands | 512 | 22617 | 608 | 2886 | 0.050 [0.035; 0.066] | 0.235 [0.182; 0.293] | 0.082 [0.059; 0.107] | 0.054 | 1.53 [1.24; 1.80]× |
| agente = SWE-agent | 108 | 4512 | 200 | 409 | 0.059 [0.013; 0.117] | 0.120 [0.029; 0.214] | 0.079 [0.018; 0.147] | 0.064 | 1.23 [0.41; 1.75]× |
| agente = Terminus2 | 220 | 8719 | 311 | 587 | 0.066 [0.037; 0.099] | 0.125 [0.074; 0.192] | 0.087 [0.050; 0.127] | 0.058 | 1.49 [0.92; 2.35]× |
| agente = mini-SWE-agent | 136 | 4009 | 378 | 516 | 0.238 [0.169; 0.311] | 0.325 [0.246; 0.399] | 0.275 [0.203; 0.344] | 0.142 | 1.94 [1.70; 2.20]× |
| origem = SWE-bench | 489 | 18116 | 638 | 1906 | 0.089 [0.063; 0.116] | 0.265 [0.201; 0.323] | 0.133 [0.097; 0.169] | 0.068 | 1.95 [1.66; 2.16]× |
| origem = TerminalBench | 487 | 21741 | 859 | 2492 | 0.064 [0.047; 0.084] | 0.186 [0.147; 0.229] | 0.095 [0.072; 0.121] | 0.069 | 1.39 [1.16; 1.63]× |
| com harness_protocol (padrão) | 976 | 39857 | 1497 | 4398 | 0.075 [0.060; 0.092] | 0.220 [0.183; 0.259] | 0.112 [0.091; 0.135] | 0.070 | 1.60 [1.43; 1.80]× |
| sem harness_protocol | 976 | 39619 | 1432 | 4398 | 0.075 [0.059; 0.092] | 0.230 [0.194; 0.266] | 0.113 [0.091; 0.135] | 0.069 | 1.63 [1.45; 1.82]× |
| só alinhamento confirmado | 976 | 39315 | 1004 | 4310 | 0.058 [0.044; 0.072] | 0.247 [0.202; 0.293] | 0.093 [0.073; 0.115] | 0.054 | 1.73 [1.51; 1.94]× |

## incorrect × loop

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 39857 | 1497 | 1899 | 0.071 [0.042; 0.104] | 0.090 [0.052; 0.131] | 0.080 [0.047; 0.114] | 0.054 | 1.47 [1.10; 1.81]× |
| agente = OpenHands | 512 | 22617 | 608 | 952 | 0.034 [0.005; 0.065] | 0.053 [0.007; 0.113] | 0.041 [0.006; 0.080] | 0.037 | 1.12 [0.38; 1.54]× |
| agente = SWE-agent | 108 | 4512 | 200 | 231 | 0.108 [0.014; 0.239] | 0.125 [0.016; 0.248] | 0.116 [0.015; 0.234] | 0.067 | 1.72 [0.41; 2.42]× |
| agente = Terminus2 | 220 | 8719 | 311 | 540 | 0.081 [0.032; 0.138] | 0.141 [0.053; 0.242] | 0.103 [0.041; 0.167] | 0.061 | 1.70 [1.00; 2.66]× |
| agente = mini-SWE-agent | 136 | 4009 | 378 | 176 | 0.193 [0.042; 0.390] | 0.090 [0.018; 0.170] | 0.123 [0.025; 0.227] | 0.086 | 1.42 [0.50; 2.09]× |
| origem = SWE-bench | 489 | 18116 | 638 | 517 | 0.095 [0.032; 0.173] | 0.077 [0.027; 0.138] | 0.085 [0.030; 0.151] | 0.053 | 1.59 [0.86; 2.07]× |
| origem = TerminalBench | 487 | 21741 | 859 | 1382 | 0.062 [0.030; 0.098] | 0.100 [0.048; 0.156] | 0.077 [0.037; 0.116] | 0.053 | 1.45 [0.94; 1.87]× |
| com harness_protocol (padrão) | 976 | 39857 | 1497 | 1899 | 0.071 [0.042; 0.104] | 0.090 [0.054; 0.131] | 0.080 [0.047; 0.113] | 0.054 | 1.46 [1.13; 1.80]× |
| sem harness_protocol | 976 | 39619 | 1432 | 1899 | 0.071 [0.042; 0.104] | 0.094 [0.054; 0.136] | 0.081 [0.047; 0.114] | 0.053 | 1.53 [1.14; 1.84]× |
| só alinhamento confirmado | 976 | 39315 | 1004 | 1878 | 0.061 [0.035; 0.092] | 0.114 [0.068; 0.162] | 0.079 [0.047; 0.114] | 0.051 | 1.57 [1.15; 1.95]× |

## estágio incorreto × ≥ 1 flag

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 6561 | 531 | 3221 | 0.069 [0.060; 0.079] | 0.418 [0.374; 0.464] | 0.118 [0.104; 0.134] | 0.141 | 0.84 [0.77; 0.91]× |
| agente = OpenHands | 512 | 3351 | 216 | 1657 | 0.057 [0.046; 0.070] | 0.440 [0.366; 0.514] | 0.101 [0.082; 0.123] | 0.116 | 0.87 [0.77; 1.00]× |
| agente = SWE-agent | 108 | 613 | 71 | 306 | 0.052 [0.027; 0.082] | 0.225 [0.125; 0.324] | 0.085 [0.045; 0.129] | 0.161 | 0.53 [0.30; 0.76]× |
| agente = Terminus2 | 220 | 1859 | 95 | 879 | 0.052 [0.038; 0.068] | 0.484 [0.376; 0.593] | 0.094 [0.070; 0.121] | 0.097 | 0.97 [0.81; 1.12]× |
| agente = mini-SWE-agent | 136 | 738 | 149 | 379 | 0.172 [0.135; 0.211] | 0.436 [0.358; 0.513] | 0.246 [0.198; 0.296] | 0.304 | 0.81 [0.69; 0.94]× |
| origem = SWE-bench | 489 | 2789 | 260 | 1250 | 0.070 [0.054; 0.087] | 0.338 [0.273; 0.398] | 0.117 [0.091; 0.142] | 0.164 | 0.71 [0.60; 0.83]× |
| origem = TerminalBench | 487 | 3772 | 271 | 1971 | 0.068 [0.057; 0.080] | 0.494 [0.431; 0.563] | 0.120 [0.101; 0.139] | 0.127 | 0.94 [0.85; 1.04]× |
| com harness_protocol (padrão) | 976 | 6561 | 531 | 3221 | 0.069 [0.060; 0.078] | 0.418 [0.373; 0.463] | 0.118 [0.103; 0.133] | 0.142 | 0.84 [0.76; 0.91]× |
| sem harness_protocol | 976 | 6561 | 531 | 3221 | 0.069 [0.060; 0.079] | 0.418 [0.376; 0.463] | 0.118 [0.104; 0.134] | 0.141 | 0.84 [0.77; 0.91]× |
| só alinhamento confirmado | 976 | 3130 | 323 | 1757 | 0.081 [0.069; 0.095] | 0.443 [0.389; 0.497] | 0.138 [0.117; 0.159] | 0.165 | 0.83 [0.75; 0.92]× |

## estágio incorreto × error ∪ test_fail ∪ loop

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 6561 | 531 | 2670 | 0.074 [0.064; 0.085] | 0.373 [0.329; 0.416] | 0.124 [0.107; 0.140] | 0.135 | 0.92 [0.83; 1.00]× |
| agente = OpenHands | 512 | 3351 | 216 | 1459 | 0.059 [0.047; 0.071] | 0.398 [0.329; 0.468] | 0.103 [0.082; 0.123] | 0.114 | 0.90 [0.78; 1.01]× |
| agente = SWE-agent | 108 | 613 | 71 | 238 | 0.055 [0.027; 0.085] | 0.183 [0.097; 0.267] | 0.084 [0.042; 0.129] | 0.150 | 0.56 [0.32; 0.80]× |
| agente = Terminus2 | 220 | 1859 | 95 | 682 | 0.054 [0.038; 0.072] | 0.389 [0.286; 0.510] | 0.095 [0.067; 0.125] | 0.091 | 1.05 [0.83; 1.26]× |
| agente = mini-SWE-agent | 136 | 738 | 149 | 291 | 0.213 [0.167; 0.264] | 0.416 [0.342; 0.494] | 0.282 [0.225; 0.340] | 0.286 | 0.98 [0.84; 1.16]× |
| origem = SWE-bench | 489 | 2789 | 260 | 1045 | 0.080 [0.063; 0.099] | 0.323 [0.268; 0.381] | 0.129 [0.102; 0.156] | 0.152 | 0.85 [0.73; 0.98]× |
| origem = TerminalBench | 487 | 3772 | 271 | 1625 | 0.070 [0.058; 0.083] | 0.421 [0.353; 0.490] | 0.120 [0.099; 0.140] | 0.125 | 0.96 [0.85; 1.08]× |
| com harness_protocol (padrão) | 976 | 6561 | 531 | 2670 | 0.074 [0.064; 0.085] | 0.373 [0.330; 0.417] | 0.124 [0.107; 0.140] | 0.135 | 0.92 [0.83; 1.00]× |
| sem harness_protocol | 976 | 6561 | 531 | 2670 | 0.074 [0.064; 0.085] | 0.373 [0.330; 0.416] | 0.124 [0.108; 0.141] | 0.134 | 0.92 [0.83; 1.00]× |
| só alinhamento confirmado | 976 | 3130 | 323 | 1391 | 0.097 [0.081; 0.113] | 0.418 [0.363; 0.472] | 0.158 [0.134; 0.181] | 0.161 | 0.98 [0.87; 1.08]× |

