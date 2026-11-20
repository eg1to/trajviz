# Cache da biblioteca e flags (Fase 4)

`scripts/warm_cache.py --cold` — só regras (sem LLM). Tempo SEM cache (frio).

## Tempo do pipeline

| dataset | traj. | passos médios | s / trajetória | s / 100 passos |
|---|---:|---:|---:|---:|
| codetracebench | 58 | 46.5 | 0.061 | 0.131 |
| swe-rebench | 50 | 63.7 | 0.032 | 0.050 |
| swe-smith | 60 | 30.7 | 0.012 | 0.038 |
| **total** | 168 | — | 0.035 | 0.075 |

Meta: < 2 s por trajetória de 100 passos → ✅. Mais lenta: `codetracebench/openhands-Anthropic__Claude-Sonnet-4-20250514-Thinking-build-pov-ray-aa2667f5` (500 passos, 0.46 s).

## % de passos com cada flag (por dataset; sem passos keys/harness)

| dataset | passos | error | test_fail | test_pass | repeated | no_new_info | loop | truncated |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| codetracebench | 2596 | 9.1% | 1.2% | 1.0% | 1.9% | 2.3% | 0.0% | 1.0% |
| swe-rebench | 3181 | 5.7% | 1.4% | 6.9% | 0.6% | 3.4% | 0.3% | 0.6% |
| swe-smith | 1838 | 8.1% | 0.4% | 0.7% | 1.0% | 2.8% | 0.0% | 3.3% |

Artefatos não suportados (só logs): codetracebench: 2

Nenhuma falha de processamento.
