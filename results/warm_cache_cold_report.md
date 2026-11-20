# Cache da biblioteca e flags (Fase 4)

`scripts/warm_cache.py --cold` — só regras (sem LLM). Tempo SEM cache (frio).

## Tempo do pipeline

| dataset | traj. | passos médios | s / trajetória | s / 100 passos |
|---|---:|---:|---:|---:|
| codetracebench | 58 | 46.5 | 0.056 | 0.122 |
| swe-rebench | 50 | 63.7 | 0.031 | 0.048 |
| swe-smith | 60 | 30.7 | 0.011 | 0.035 |
| **total** | 168 | — | 0.032 | 0.071 |

Meta: < 2 s por trajetória de 100 passos → ✅. Mais lenta: `codetracebench/openhands-Anthropic__Claude-Sonnet-4-20250514-Thinking-build-pov-ray-aa2667f5` (500 passos, 0.48 s).

## % de passos com cada flag (por dataset; sem passos keys/harness)

| dataset | passos | error | test_fail | test_pass | repeated | no_new_info | loop | truncated |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| codetracebench | 2596 | 9.0% | 1.6% | 1.0% | 1.9% | 2.3% | 3.8% | 1.0% |
| swe-rebench | 3181 | 4.6% | 2.9% | 6.9% | 0.6% | 3.4% | 3.6% | 0.6% |
| swe-smith | 1838 | 8.1% | 0.5% | 0.7% | 1.0% | 2.8% | 8.8% | 3.3% |

Artefatos não suportados (só logs): codetracebench: 2

Nenhuma falha de processamento.
