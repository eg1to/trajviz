# Relatório de parse (Fase 2)

Gerado por `backend/scripts/parse_samples.py` — detect + parse de `data/samples/` (CodeTraceBench: os 60 artefatos `.tar.zst` do `--sample 60`, com ground truth do manifest `verified`).

## Resumo por grupo

| grupo | arquivos | sucesso | falhas | não suportado¹ | média de passos | % passos c/ observação | % passos c/ exit_code² | último = submit | passos c/ pensamento |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SWE-rebench | 50 | 50 (100.0%) | 0 | 0 | 63.7 | 98.4% | 99.3% | 88.0% | 74.0% |
| SWE-smith/tool | 20 | 20 (100.0%) | 0 | 0 | 24.1 | 95.9% | 0.0% | 100.0% | 92.5% |
| SWE-smith/xml | 20 | 20 (100.0%) | 0 | 0 | 32.2 | 96.9% | 0.0% | 100.0% | 89.3% |
| SWE-smith/ticks | 20 | 20 (100.0%) | 0 | 0 | 35.6 | 97.2% | 0.0% | 90.0% | 88.2% |
| CodeTraceBench | 60 | 58 (96.7%) | 0 | 2 | 46.5 | 81.3% | 64.4% | 91.4% | 68.1% |

¹ `UnsupportedArtifact`: artefato só com logs/asciinema (sem trajetória estruturada); erro claro e esperado, contado como não-sucesso.
² % dos passos de ferramenta bash/keys com `exit_code` extraído (SWE-rebench e CTB-OpenHands/mini-SWE trazem exit code; SWE-smith/SWE-agent/Terminus2 não).

## CodeTraceBench por adaptador

| adaptador | trajetórias | `step_count` do manifest = passos extraídos | idem, sem contar passos `message` | = na unidade do benchmark (exato / ±1)³ | anotações | alinhadas (`resolved_idx`) | confirmadas (action_ref/regra) | hipótese |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ctb_miniswe | 7 | 6/7 (85.7%) | 7/7 | 6/7 / 7/7 | 14 | 14 (100.0%) | 14 | 0 |
| ctb_openhands_events | 12 | 10/12 (83.3%) | 11/12 | 11/12 / 11/12 | 36 | 36 (100.0%) | 27 | 9 |
| ctb_openhands_swe | 19 | 0/19 (0.0%) | 0/19 | 19/19 / 19/19 | 16 | 16 (100.0%) | 0 | 16 |
| ctb_sweagent | 7 | 7/7 (100.0%) | 2/7 | 7/7 / 7/7 | 35 | 35 (100.0%) | 35 | 0 |
| ctb_terminus2 | 13 | 1/13 (7.7%) | 1/13 | 10/13 / 13/13 | 48 | 48 (100.0%) | 34 | 14 |
| **total** | 58 | 24/58 (41.4%) | 21/58 | 53/58 / 57/58 | 149 | 149 (100.0%) | 110 (73.8%) | 39 |

³ Unidade do benchmark (hipótese por agente): SWE-agent/mini-SWE = passos; OpenHands-TB = ações ≠ `message`; Terminus2 = nº de comandos (`keystrokes`) somando os episódios; OpenHands-SWE = tool_calls − 1 (a última, `finish`, não entra).

Alinhamento do `step_id`: **confirmado** = `action_ref` (id nativo do evento/episódio) ou regra do `step_ref_kind` validada; **hipótese** = cauda de OpenHands-TB/Terminus2 (unidades que o benchmark numera depois das primárias) e OpenHands-SWE (n-ésima tool_call) — ver docs/formats.md §4.5 e decisions.md.

## Critério de pronto

| critério | resultado | ok? |
|---|---|---|
| SWE-rebench ≥ 100% | 50/50 (100.0%) | ✅ |
| SWE-smith/tool ≥ 100% | 20/20 (100.0%) | ✅ |
| SWE-smith/xml ≥ 100% | 20/20 (100.0%) | ✅ |
| SWE-smith/ticks ≥ 100% | 20/20 (100.0%) | ✅ |
| CodeTraceBench ≥ 90% | 58/60 (96.7%) | ✅ |

## Formatos detectados

- **SWE-rebench**: {'openhands_chat': 50.0}
- **SWE-smith/tool**: {'sweagent_smith': 20.0}
- **SWE-smith/xml**: {'sweagent_smith': 20.0}
- **SWE-smith/ticks**: {'sweagent_smith': 20.0}
- **CodeTraceBench**: {'ctb_openhands_swe': 19.0, 'ctb_openhands_events': 12.0, 'ctb_sweagent': 7.0, 'ctb_terminus2': 13.0, 'ctb_miniswe': 7.0}

## Falhas e artefatos não suportados

- **CodeTraceBench**: `miniswe-Anthropic__Claude-Sonnet-4-20250514-Thinking-mlflow-` — UnsupportedArtifact: miniswe-Anthropic__Claude-Sonnet-4-20250514-Thinking-mlflow-register-60a717c0.tar.zst: artefato só com logs/asciinema (sem trajetória estruturada)
- **CodeTraceBench**: `miniswe-Anthropic__Claude-Sonnet-4-20250514-Thinking-large-s` — UnsupportedArtifact: miniswe-Anthropic__Claude-Sonnet-4-20250514-Thinking-large-scale-text-editing-e70ac842.tar.zst: artefato só com logs/asciinema (sem trajetória estruturada)
