# Detectores × gabarito do CodeTraceBench (`verified`)

`backend/scripts/eval_detectors.py` · só regras (sem LLM) · semente 20251119 · bootstrap B=2000 **sobre trajetórias** · linha de base aleatória = 100 sorteios com a mesma nº de flags por trajetória.

- Trajetórias avaliadas: **976** de 1000 (descartadas: {'sem_artefato': 8, 'unsupported': 16}); por agente: {'OpenHands': 512, 'SWE-agent': 108, 'Terminus2': 220, 'mini-SWE-agent': 136}.
- Só **392** delas têm ao menos um passo incorreto/inútil anotado; as demais entram como "anotadas sem problemas" (negativos).
- 34% dos passos anotados foram alinhados por **hipótese** (cauda do `step_id`; docs/formats.md §4.5) — ver a linha "só alinhamento confirmado".

P/R/F1 são agregados (somando contagens de todas as trajetórias do recorte). **lift** = F1 do detector ÷ F1 do marcador aleatório; IC 95% por bootstrap.

## Antes × depois da correção de `test_fail` e `loop`

Antes = regras da 1ª avaliação (`eval_detectors_before.json`, `eval_detectors_before.md`); depois = esta execução. Mesmas 976 trajetórias, mesma semente. `test_fail`: pytest passou a seguir seus códigos de saída (1 = falha; 2/3/4 = `error`; 5 = sem flag). `loop`: só repetição da mesma ação normalizada (arquivo + intervalo/trecho) ou ciclo edit → test_fail com o mesmo erro.

| tarefa (recorte: todos) | marcados antes → depois | precisão antes → depois | revocação antes → depois | F1 antes → depois | lift F1 antes → depois [IC95 depois] |
|---|---|---|---|---|---|
| unuseful × repeated ∪ no_new_info | 2009 → 2009 | 0.004 → 0.004 | 0.038 → 0.038 | 0.007 → 0.007 | 0.80× → 0.80× [0.12; 1.67] |
| incorrect × error ∪ test_fail | 4398 → 4382 | 0.075 → 0.075 | 0.220 → 0.220 | 0.112 → 0.112 | 1.62× → 1.62× [1.44; 1.80] |
| incorrect × loop | 1899 → 48 | 0.071 → 0.125 | 0.090 → 0.004 | 0.080 → 0.008 | 1.47× → 2.43× [0.00; 3.33] |
| estágio incorreto × ≥ 1 flag | 3221 → 3065 | 0.069 → 0.069 | 0.418 → 0.401 | 0.118 → 0.118 | 0.84× → 0.84× [0.77; 0.93] |
| estágio incorreto × error ∪ test_fail ∪ loop | 2670 → 2462 | 0.074 → 0.076 | 0.373 → 0.350 | 0.124 → 0.124 | 0.92× → 0.95× [0.86; 1.03] |

## Interpretação (5 linhas)

1. **`repeated ∪ no_new_info` não reproduz os passos "inúteis" do gabarito**: precisão 0.4%, revocação 3.8%, lift 0.80× (IC 0.12–1.67, contém 1) — indistinguível de sorteio. O gabarito define "inútil" por julgamento do anotador; leitura idêntica a uma anterior capta, no máximo, uma fração mínima disso (hipótese não testada: não auditei os passos anotados).
2. **`error ∪ test_fail` é fraco, mas acima do acaso** para os passos incorretos: precisão 7.5%, revocação 22.0%, F1 0.112, lift 1.62× (IC 1.44–1.80); no mini-SWE-agent chega a F1 0.275 (lift 1.93×). Hipótese (não testada): "incorreto" no gabarito é ação que muda o estado de forma errada, o que difere de comando que falha.
3. **`loop` ficou muito mais conservador depois da correção**: 48 passos marcados (antes 1899), precisão 12.5%, revocação 0.4%, lift 2.43× com IC 0.00–3.33 (contém 1): com tão poucos acertos o resultado é **inconclusivo** — a correção removeu falsos positivos (ver `audit_flags.md`), mas o detector quase não encontra os passos incorretos do gabarito.
4. **No nível de estágio a revocação parece boa (40.1%), mas é efeito da taxa de flags**: 3065 de 6561 estágios têm ≥ 1 flag, a precisão é 6.9% e o lift é 0.84× (< 1). Com só `error ∪ test_fail ∪ loop` o lift é 0.95×. A linha de base sorteia estágios sem considerar o tamanho do estágio (limitação: estágios longos têm mais chance de ter flag).
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
| todos | 976 | 39857 | 1497 | 4382 | 0.075 [0.060; 0.092] | 0.220 [0.185; 0.256] | 0.112 [0.091; 0.134] | 0.069 | 1.62 [1.44; 1.80]× |
| agente = OpenHands | 512 | 22617 | 608 | 2877 | 0.050 [0.035; 0.067] | 0.235 [0.182; 0.293] | 0.082 [0.059; 0.107] | 0.054 | 1.53 [1.24; 1.80]× |
| agente = SWE-agent | 108 | 4512 | 200 | 403 | 0.060 [0.014; 0.117] | 0.120 [0.030; 0.213] | 0.080 [0.020; 0.149] | 0.064 | 1.23 [0.44; 1.75]× |
| agente = Terminus2 | 220 | 8719 | 311 | 586 | 0.067 [0.037; 0.100] | 0.125 [0.071; 0.193] | 0.087 [0.049; 0.128] | 0.058 | 1.49 [0.93; 2.34]× |
| agente = mini-SWE-agent | 136 | 4009 | 378 | 516 | 0.238 [0.171; 0.312] | 0.325 [0.246; 0.403] | 0.275 [0.206; 0.347] | 0.143 | 1.93 [1.69; 2.19]× |
| origem = SWE-bench | 489 | 18116 | 638 | 1892 | 0.089 [0.063; 0.119] | 0.265 [0.203; 0.325] | 0.134 [0.097; 0.173] | 0.069 | 1.94 [1.66; 2.16]× |
| origem = TerminalBench | 487 | 21741 | 859 | 2490 | 0.064 [0.047; 0.084] | 0.186 [0.147; 0.231] | 0.096 [0.072; 0.121] | 0.069 | 1.39 [1.16; 1.62]× |
| com harness_protocol (padrão) | 976 | 39857 | 1497 | 4382 | 0.075 [0.060; 0.092] | 0.220 [0.186; 0.257] | 0.112 [0.092; 0.134] | 0.069 | 1.61 [1.44; 1.80]× |
| sem harness_protocol | 976 | 39619 | 1432 | 4382 | 0.075 [0.060; 0.092] | 0.230 [0.193; 0.266] | 0.113 [0.092; 0.136] | 0.070 | 1.62 [1.46; 1.83]× |
| só alinhamento confirmado | 976 | 39315 | 1004 | 4294 | 0.058 [0.043; 0.073] | 0.247 [0.198; 0.293] | 0.094 [0.072; 0.116] | 0.054 | 1.73 [1.52; 1.94]× |

## incorrect × loop

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 39857 | 1497 | 48 | 0.125 [0.000; 0.341] | 0.004 [0.000; 0.012] | 0.008 [0.000; 0.023] | 0.003 | 2.43 [0.00; 3.33]× |
| agente = OpenHands | 512 | 22617 | 608 | 17 | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 | — [—; —]× |
| agente = SWE-agent | 108 | 4512 | 200 | 25 | 0.240 [0.000; 0.556] | 0.030 [0.000; 0.091] | 0.053 [0.000; 0.147] | 0.021 | 2.54 [0.00; 3.33]× |
| agente = Terminus2 | 220 | 8719 | 311 | 0 | — [—; —] | 0.000 [0.000; 0.000] | — [—; —] | — | — [—; —]× |
| agente = mini-SWE-agent | 136 | 4009 | 378 | 6 | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.001 | 0.00 [0.00; 0.00]× |
| origem = SWE-bench | 489 | 18116 | 638 | 35 | 0.171 [0.000; 0.487] | 0.009 [0.000; 0.027] | 0.018 [0.000; 0.051] | 0.007 | 2.62 [0.00; 3.33]× |
| origem = TerminalBench | 487 | 21741 | 859 | 13 | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 [0.000; 0.000] | 0.000 | 0.00 [0.00; 0.00]× |
| com harness_protocol (padrão) | 976 | 39857 | 1497 | 48 | 0.125 [0.000; 0.355] | 0.004 [0.000; 0.012] | 0.008 [0.000; 0.023] | 0.003 | 2.25 [0.00; 3.33]× |
| sem harness_protocol | 976 | 39619 | 1432 | 48 | 0.125 [0.000; 0.357] | 0.004 [0.000; 0.012] | 0.008 [0.000; 0.023] | 0.003 | 2.51 [0.00; 3.19]× |
| só alinhamento confirmado | 976 | 39315 | 1004 | 48 | 0.125 [0.000; 0.333] | 0.006 [0.000; 0.017] | 0.011 [0.000; 0.032] | 0.004 | 2.59 [0.00; 3.33]× |

## estágio incorreto × ≥ 1 flag

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 6561 | 531 | 3065 | 0.069 [0.060; 0.079] | 0.401 [0.357; 0.447] | 0.118 [0.103; 0.134] | 0.140 | 0.84 [0.77; 0.93]× |
| agente = OpenHands | 512 | 3351 | 216 | 1581 | 0.058 [0.046; 0.070] | 0.421 [0.347; 0.495] | 0.101 [0.081; 0.121] | 0.114 | 0.89 [0.77; 1.02]× |
| agente = SWE-agent | 108 | 613 | 71 | 294 | 0.054 [0.027; 0.085] | 0.225 [0.123; 0.333] | 0.088 [0.045; 0.133] | 0.158 | 0.55 [0.31; 0.78]× |
| agente = Terminus2 | 220 | 1859 | 95 | 818 | 0.050 [0.035; 0.067] | 0.432 [0.324; 0.539] | 0.090 [0.064; 0.118] | 0.093 | 0.96 [0.77; 1.16]× |
| agente = mini-SWE-agent | 136 | 738 | 149 | 372 | 0.175 [0.137; 0.215] | 0.436 [0.358; 0.510] | 0.250 [0.199; 0.298] | 0.305 | 0.82 [0.69; 0.95]× |
| origem = SWE-bench | 489 | 2789 | 260 | 1226 | 0.072 [0.055; 0.089] | 0.338 [0.277; 0.398] | 0.118 [0.093; 0.144] | 0.162 | 0.73 [0.62; 0.83]× |
| origem = TerminalBench | 487 | 3772 | 271 | 1839 | 0.068 [0.057; 0.081] | 0.461 [0.399; 0.527] | 0.118 [0.100; 0.139] | 0.124 | 0.96 [0.85; 1.06]× |
| com harness_protocol (padrão) | 976 | 6561 | 531 | 3065 | 0.069 [0.060; 0.079] | 0.401 [0.357; 0.444] | 0.118 [0.103; 0.134] | 0.140 | 0.84 [0.77; 0.92]× |
| sem harness_protocol | 976 | 6561 | 531 | 3065 | 0.069 [0.060; 0.079] | 0.401 [0.359; 0.444] | 0.118 [0.104; 0.134] | 0.141 | 0.84 [0.77; 0.92]× |
| só alinhamento confirmado | 976 | 3130 | 323 | 1668 | 0.082 [0.069; 0.096] | 0.424 [0.370; 0.480] | 0.138 [0.117; 0.160] | 0.165 | 0.83 [0.75; 0.93]× |

## estágio incorreto × error ∪ test_fail ∪ loop

| recorte | traj. | passos/estágios | positivos | marcados | precisão [IC95] | revocação [IC95] | F1 [IC95] | F1 aleatório | lift [IC95] |
|---|---:|---:|---:|---:|---|---|---|---:|---|
| todos | 976 | 6561 | 531 | 2462 | 0.076 [0.065; 0.086] | 0.350 [0.309; 0.392] | 0.124 [0.107; 0.140] | 0.131 | 0.95 [0.86; 1.03]× |
| agente = OpenHands | 512 | 3351 | 216 | 1373 | 0.060 [0.047; 0.073] | 0.380 [0.314; 0.447] | 0.103 [0.083; 0.124] | 0.111 | 0.93 [0.79; 1.06]× |
| agente = SWE-agent | 108 | 613 | 71 | 217 | 0.060 [0.030; 0.092] | 0.183 [0.100; 0.275] | 0.090 [0.047; 0.135] | 0.149 | 0.61 [0.35; 0.84]× |
| agente = Terminus2 | 220 | 1859 | 95 | 596 | 0.050 [0.033; 0.068] | 0.316 [0.209; 0.427] | 0.087 [0.057; 0.116] | 0.079 | 1.10 [0.82; 1.36]× |
| agente = mini-SWE-agent | 136 | 738 | 149 | 276 | 0.221 [0.173; 0.272] | 0.409 [0.333; 0.484] | 0.287 [0.230; 0.344] | 0.279 | 1.03 [0.87; 1.19]× |
| origem = SWE-bench | 489 | 2789 | 260 | 1008 | 0.083 [0.066; 0.103] | 0.323 [0.264; 0.381] | 0.132 [0.106; 0.161] | 0.149 | 0.89 [0.74; 1.01]× |
| origem = TerminalBench | 487 | 3772 | 271 | 1454 | 0.070 [0.056; 0.083] | 0.376 [0.314; 0.440] | 0.118 [0.096; 0.139] | 0.117 | 1.01 [0.88; 1.14]× |
| com harness_protocol (padrão) | 976 | 6561 | 531 | 2462 | 0.076 [0.064; 0.087] | 0.350 [0.307; 0.393] | 0.124 [0.107; 0.142] | 0.130 | 0.95 [0.85; 1.04]× |
| sem harness_protocol | 976 | 6561 | 531 | 2462 | 0.076 [0.065; 0.087] | 0.350 [0.307; 0.393] | 0.124 [0.107; 0.142] | 0.133 | 0.93 [0.85; 1.04]× |
| só alinhamento confirmado | 976 | 3130 | 323 | 1258 | 0.100 [0.084; 0.117] | 0.390 [0.334; 0.440] | 0.159 [0.135; 0.184] | 0.156 | 1.02 [0.91; 1.12]× |

