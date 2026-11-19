# Plano do MVP — trajviz

Versão para o Claude Code. Plano completo (com justificativas) no documento do TCC.

## 1. Objetivo e diferenciais
App web que recebe um log bruto de agente de código e vai direto para a visualização.
1. **Zero rotulação manual** — classificador de regras + fallback em LLM rotula cada ação no upload.
2. **Dashboard** de métricas da trajetória (ferramentas, fases, erros, loops, arquivos, desfecho).
3. **Multiformato** — esquema canônico único + adaptadores com detecção automática.

Fora do MVP (TCC II): relações semânticas entre passos (Thought→Action etc.), estudo com usuários.

## 2. Datasets e papéis
| Dataset | Papel | Agente / modelo | Volume |
| --- | --- | --- | --- |
| nebius/SWE-rebench-openhands-trajectories | Base (sucesso × falha) | OpenHands v0.54 · Qwen3-Coder-480B | 67.074 trajetórias, ~2 GB |
| SWE-bench/SWE-smith-trajectories | Segundo formato | SWE-agent · Claude 3.7 (72%) / 3.5 (26%) / GPT-4o (2%) | 76.002 linhas (24.100 / 26.076 / 25.826), splits `tool`/`xml`/`ticks`, ~3,1 GB (sem `train-*`) |
| NJU-LINK/CodeTraceBench | Gabarito | OpenHands, mini-SWE-agent, Terminus2, SWE-agent | 3.316 únicas (`verified` 1.000 ⊂ `full`; o "4.316" do README conta o verified em dobro) |

O que se sabe pelos cards (**confirmado na Fase 1 — detalhes e correções em `docs/formats.md`**; ex.: o split `tool` do SWE-smith mistura formato nativo e xml, `patch` do SWE-smith não alinha com a trajetória, e `step_id` do CodeTraceBench tem semântica diferente por agente):
- **SWE-rebench**: uma linha por trajetória; `trajectory` = lista de mensagens `system`/`user`/`assistant`/`tool`;
  `assistant.tool_calls[].function.arguments` é string JSON; `tool` tem `name` e `tool_call_id`.
  Campos: `trajectory_id`, `instance_id`, `repo`, `model_patch`, `exit_status`, `resolved`,
  `gen_tests_correct`, `pred_passes_gen_tests`.
- **SWE-smith**: `messages` é uma **string** com a lista serializada; mensagens têm `role`, `content`,
  `agent`, `message_type`; conteúdo de `user` pode ser lista de partes `{"type":"text","text":...}`.
  Campos: `instance_id`, `resolved`, `model`, `traj_id`, `patch`. Os 3 splits provavelmente diferem
  na forma de representar a ação.
- **CodeTraceBench**: metadados em Parquet/JSONL; trajetórias em `bench_artifacts/full/<traj_id>.tar.zst`;
  `stages` (string JSON) com `incorrect_step_ids`, `unuseful_step_ids` e rationale por estágio;
  `incorrect_stages`, contagens de passos e estágios, `solved`, `agent`, `model`, `difficulty`, `category`.

## 3. Estrutura do repositório
```
trajviz/
  CLAUDE.md  README.md  docker-compose.yml  .gitignore
  docs/            PLAN.md  formats.md  decisions.md
  prompts/         prompts por fase para o Claude Code
  data/raw/        datasets baixados (fora do git)
  data/samples/    amostras pequenas (~50 por formato)
  backend/
    pyproject.toml
    app/
      main.py  schema.py
      adapters/   detect.py  openhands.py  sweagent.py  codetracebench.py  generic_chat.py
      labeling/   taxonomy.py  rules.py  bash_parser.py  llm.py
      analysis/   detectors.py  metrics.py
      datasets/   loaders.py
    tests/  fixtures/
    scripts/  explore_dataset.py  evaluate.py  batch_stats.py
  frontend/
    src/  api/  pages/  components/
  results/   tabelas e gráficos da avaliação
```

## 4. Endpoints
- `POST /api/trajectories` — upload (`.json`, `.jsonl`, `.traj`, `.parquet` 1 linha, `.tar.zst`) → `{id, format_detected, confidence}`
- `GET /api/trajectories/{id}` — trajetória canônica completa
- `GET /api/trajectories/{id}/metrics` — métricas do dashboard
- `GET /api/library`, `POST /api/library/sample` — amostras pré-carregadas
- `PATCH /api/trajectories/{id}/steps/{idx}` — correção opcional de rótulo (gera dados de avaliação)

## 5. Rotulação
Taxonomia e regras: ver `CLAUDE.md`. Exemplos de sinal por categoria:
| Categoria | Sinais |
| --- | --- |
| explore | `ls`, `find` (sem `-name`), `tree`, `view` em diretório |
| search | `grep`, `rg`, `ag`, `git grep`, `find -name` |
| read | `cat`, `head`, `tail`, `sed -n`, `nl`, `view` em arquivo |
| edit | `str_replace`, `create`, `insert`, `sed -i`, `patch`, redirecionamento `>`/`>>`, heredoc |
| reproduce | `python reproduce*.py`, `python -c`, executar script criado pelo agente |
| test | `pytest`, `tox`, `unittest`, `npm test`, `make test` |
| setup | `pip install`, `conda`, `export`, `cd` sozinho |
| vcs | `git diff`, `git status`, `git log`, `git checkout`, `git stash` |
| think | ferramenta `think`, mensagem sem tool call |
| submit | `finish`, `submit`, `exit` |

## 6. Detectores
- `error`: exit_code ≠ 0, ou `Traceback`, `Error:`, `command not found`, `No such file` na observação.
- `repeated`: mesma ação normalizada já vista.
- `loop`: ciclo de n-gramas de (categoria, alvo) repetido ≥ 3 vezes.
- `no_new_info`: leitura/busca com observação igual a uma anterior (equivalente a `unuseful_step_ids`).

## 7. Métricas do dashboard
KPIs (resolved, exit_status, nº de passos, arquivos/linhas do patch) · contagem e % por categoria ·
ranking de ferramentas e executáveis bash · passo da 1ª edição e % antes de editar · ciclos edit→test ·
taxa de erro, repeated, loop, no_new_info, maior sequência de erros · arquivos lidos × editados ·
tamanho das observações por passo.

## 8. Telas
1. Upload / Biblioteca. 2. Trajetória › Grafo (faixa de fases + grafo React Flow + filtros + inspetor).
3. Trajetória › Dashboard (clicar num item leva ao passo). 4. Comparar (stretch).
Cores das categorias fixas e seguras para daltonismo.

## 9. Avaliação
1. Acurácia do classificador: ~200 passos rotulados à mão (estratificado por dataset/agente) → acurácia,
   F1 por categoria, matriz de confusão; "só regras" vs "regras + LLM".
2. Cobertura: % regra / LLM / other por dataset e agente; custo gasto no LLM.
3. Detectores vs CodeTraceBench verified: `repeated` + `no_new_info` vs `unuseful_step_ids`
   (precisão/revocação); estágios com `error` vs estágios incorretos.

## 10. Cronograma
| Dia | Data | Backend | Frontend | Avaliação / entregas |
| --- | --- | --- | --- | --- |
| 1 | qui 19/11 | Explorar datasets, formats.md, schema.py | — | Amostras, decisions.md |
| 2 | sex 20/11 | Adaptadores + detect.py | — | — |
| 3 | sáb 21/11 | Rotulação: regras, bash parser, fallback Haiku | Scaffold + tipos do OpenAPI | Relatório de cobertura |
| 4 | dom 22/11 | Detectores, métricas, API, cache, biblioteca | Upload, faixa de fases, inspetor, grafo | Capturas + rascunho do pôster |
| 5 | seg 23/11 | — | Dashboard | **Entrega do pôster** |
| 6 | ter 24/11 | — | Filtros, modo compacto, navegação | 200 passos rotulados, evaluate.py |
| 7 | qua 25/11 | docker compose, README | Polimento, Comparar (stretch) | batch_stats, capturas, demo |

Prioridade se o tempo apertar: pipeline + avaliação > grafo + inspetor > dashboard > biblioteca > comparar.
