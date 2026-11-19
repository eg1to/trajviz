# Relatório de rotulação (Fase 3) — só regras

Gerado por `backend/scripts/label_report.py` sobre `data/samples/` (CodeTraceBench: os 58 artefatos estruturados do `--sample 60`).

`label_source`: **rule** = ferramenta exata ou comando com confiança ≥ 0,6; **fallback** = melhor palpite da regra com confiança < 0,6 (candidato ao LLM). `other` não conta as teclas de controle (`subcategory=keys`, rótulo correto).

## Cobertura por dataset e agente

| grupo | traj. | passos | rule | fallback | other (sem keys) | keys | explore | search | read | edit | reproduce | test | setup | vcs | think | submit | other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **CodeTraceBench** | 58 | 2696 | 97.4% | 2.6% | 1.6% | 3.2% | 7.4% | 12.4% | 15.5% | 14.8% | 9.6% | 3.0% | 5.1% | 2.0% | 22.6% | 2.9% | 4.7% |
| &nbsp;&nbsp;OpenHands | 31 | 1729 | 97.7% | 2.3% | 1.0% | 1.9% | 7.1% | 11.2% | 12.4% | 8.1% | 9.2% | 3.9% | 5.8% | 2.9% | 34.9% | 1.6% | 2.9% |
| &nbsp;&nbsp;SWE-agent | 7 | 254 | 100.0% | 0.0% | 0.0% | 0.0% | 5.5% | 11.4% | 34.6% | 28.7% | 5.5% | 2.0% | 0.4% | 0.8% | 2.4% | 8.7% | 0.0% |
| &nbsp;&nbsp;Terminus2 | 13 | 505 | 94.9% | 5.1% | 4.6% | 10.3% | 10.3% | 13.3% | 7.3% | 27.7% | 15.4% | 1.6% | 6.3% | 0.0% | 0.0% | 3.2% | 14.9% |
| &nbsp;&nbsp;mini-SWE-agent | 7 | 208 | 98.6% | 1.4% | 1.4% | 0.0% | 5.3% | 21.2% | 38.5% | 22.6% | 3.4% | 0.0% | 1.4% | 0.5% | 0.0% | 5.8% | 1.4% |
| **SWE-rebench** | 50 | 3184 | 99.8% | 0.2% | 0.0% | 0.1% | 3.6% | 15.3% | 21.7% | 17.1% | 22.7% | 9.7% | 1.8% | 1.8% | 4.9% | 1.4% | 0.1% |
| &nbsp;&nbsp;OpenHands | 50 | 3184 | 99.8% | 0.2% | 0.0% | 0.1% | 3.6% | 15.3% | 21.7% | 17.1% | 22.7% | 9.7% | 1.8% | 1.8% | 4.9% | 1.4% | 0.1% |
| **SWE-smith** | 60 | 1840 | 99.8% | 0.2% | 0.0% | 0.1% | 0.8% | 9.1% | 24.6% | 30.5% | 24.6% | 1.2% | 3.3% | 0.0% | 0.0% | 5.8% | 0.1% |
| &nbsp;&nbsp;SWE-agent | 60 | 1840 | 99.8% | 0.2% | 0.0% | 0.1% | 0.8% | 9.1% | 24.6% | 30.5% | 24.6% | 1.2% | 3.3% | 0.0% | 0.0% | 5.8% | 0.1% |

## Critério: `other` (sem keys) < 15% por dataset

- SWE-rebench: 0.0% ✅
- SWE-smith: 0.0% ✅
- CodeTraceBench: 1.6% ✅

## Top 30 comandos/executáveis que ficaram `other` ou com confiança < 0,6 (o que o LLM recebe)

| # | comando/executável | passos | datasets |
|---|---|---:|---|
| 1 | `cp` | 19 | CodeTraceBench |
| 2 | `rm` | 15 | SWE-rebench, SWE-smith, CodeTraceBench |
| 3 | `echo` | 10 | SWE-rebench, CodeTraceBench |
| 4 | `jobs` | 9 | CodeTraceBench |
| 5 | `kill` | 7 | CodeTraceBench |
| 6 | `mips-linux-gnu-gcc` | 5 | CodeTraceBench |
| 7 | `curl` | 3 | CodeTraceBench |
| 8 | `nginx` | 3 | CodeTraceBench |
| 9 | `node vm.js` | 3 | CodeTraceBench |
| 10 | `7z` | 3 | CodeTraceBench |
| 11 | `pkill` | 2 | CodeTraceBench |
| 12 | `povray` | 2 | CodeTraceBench |
| 13 | `configure` | 2 | CodeTraceBench |
| 14 | `mv` | 2 | CodeTraceBench |
| 15 | `setup.py` | 1 | CodeTraceBench |
| 16 | `node useAutocomplete.js');` | 1 | CodeTraceBench |
| 17 | `yarn -v` | 1 | CodeTraceBench |
| 18 | `node node` | 1 | CodeTraceBench |
| 19 | `apt-cache` | 1 | CodeTraceBench |
| 20 | `javac` | 1 | CodeTraceBench |
| 21 | `-1` | 1 | CodeTraceBench |
| 22 | `read_xp_key_from_cdrom_box` | 1 | CodeTraceBench |
| 23 | `qemu-img` | 1 | CodeTraceBench |
| 24 | `mips-linux-gnu-nm` | 1 | CodeTraceBench |
| 25 | `node vm.js');` | 1 | CodeTraceBench |
| 26 | `mkdir` | 1 | CodeTraceBench |
| 27 | `wget` | 1 | CodeTraceBench |
| 28 | `grep` | 1 | CodeTraceBench |
| 29 | `gen_primitives.sh` | 1 | CodeTraceBench |
| 30 | `dmesg` | 1 | CodeTraceBench |

## Estimativa de custo do LLM (dry-run, sem rede)

Modelo `claude-haiku-5-5` · preços US$ 0,10 / 0,50 por MTok (cache hit 0,01) · 1 requisição por trajetória · tokens ≈ caracteres/3,2 (conservador).

| conjunto | trajetórias | passos p/ LLM | requisições | tokens de entrada | tokens de saída | custo sem cache | custo c/ cache do system |
|---|---:|---:|---:|---:|---:|---:|---:|
| amostras SWE-rebench | 50 | 5 | 5 | 5,992 | 225 | US$ 0.0007 | US$ 0.0004 |
| amostras SWE-smith | 60 | 4 | 4 | 4,873 | 180 | US$ 0.0006 | US$ 0.0003 |
| amostras CodeTraceBench | 58 | 69 | 21 | 35,742 | 3,105 | US$ 0.0051 | US$ 0.0034 |
| CTB `verified` — 992 artefatos presentes de 1000 | 992 | 2322 | 365 | 793,842 | 104,490 | US$ 0.1316 | US$ 0.0991 |
| CTB `verified` — extrapolado p/ 1000 (×1.01) | 1000 | 2340 | 367 | 800,243 | 105,332 | US$ 0.1327 | US$ 0.0999 |

O `--all` do download tinha 992/1000 artefatos do `verified` no disco na hora do relatório (a extrapolação é linear).
