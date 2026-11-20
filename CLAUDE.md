# trajviz — visualizador de trajetórias de agentes de código

TCC I (Projeto Orientado em Computação I, DCC/UFMG). Aluno: Pedro Henrique Egito Aguiar. Orientador: Marco Túlio Valente.

## Objetivo
Enviar um log bruto de agente de código (OpenHands, SWE-agent, CodeTraceBench, chat genérico) e ver
imediatamente: grafo da trajetória + faixa de fases + inspetor de passos + dashboard de métricas.
**Nenhuma rotulação manual.** Referência principal: TraceView (SOAR-Lab), que exige rotular cada ação
e cada relação à mão antes de visualizar e não tem dashboard.

Plano completo: `docs/PLAN.md`. Formatos dos dados: `docs/formats.md` (gerado na fase 1).
Decisões: `docs/decisions.md` — acrescente uma linha sempre que tomar uma decisão de design.

## Arquitetura
- `backend/` — Python 3.12, `uv`, FastAPI, Pydantic v2.
  Pipeline: `adapters/` → `schema.py` (modelo canônico TAR) → `labeling/` → `analysis/` → JSON.
- `frontend/` — Vite + React + TypeScript, Tailwind, shadcn/ui, `@xyflow/react` (grafo) + dagre,
  Recharts, TanStack Query, Zustand.
- O front **só consome o JSON canônico**. Nenhuma lógica de parsing ou de rotulação no front.
- Sem banco de dados no MVP: cache em disco (`backend/.cache/`, chave = hash do arquivo).

## Modelo de dados (resumo — o contrato é `backend/app/schema.py`)
- `Trajectory`: id, source_format, agent, model, task_id, repo, problem_statement, resolved,
  exit_status, patch, steps[], ground_truth (anotações do CodeTraceBench, se houver).
- `Step` (um passo Thought → Action → Result): idx, thought, action, observation, category,
  subcategory, label_source (`rule` | `llm` | `fallback` | `user`), confidence, flags[], files[].
- `Action`: tool (normalizado), command, args, raw. `Observation`: content, exit_code, is_error, chars.

## Taxonomia de ações (fixa)
`explore`, `search`, `read`, `edit`, `reproduce`, `test`, `setup`, `vcs`, `think`, `submit`, `other`.
Fases: Entendimento (explore, search, read) · Modificação (edit) · Verificação (reproduce, test, vcs)
· Controle (setup, think, submit).
Flags automáticas: `error`, `repeated`, `loop`, `no_new_info`, `truncated`.

## Achados da Fase 1 (detalhes em `docs/formats.md`)
- SWE-smith: o split `tool` mistura formato nativo e xml → detectar por mensagem; `patch` não é confiável.
- CodeTraceBench: 5 formatos brutos (OpenHands log de LLM, OpenHands eventos, SWE-agent `.traj`, mini-SWE `.traj.json`, Terminus2 episódios);
  `step_id` tem semântica diferente por agente; `verified` ⊂ `full` (3.316 únicas).
- Amostras em `data/samples/{swe-rebench(50),swe-smith/{tool,xml,ticks}(20 cada),codetracebench(60)}/` (fora do git).

## Adaptadores (Fase 2) — `backend/app/adapters/`
`detect.parse_any(path|obj, row=0)` detecta e converte. Cada módulo: `NAME`, `can_parse(obj)->float`, `parse(source)->Trajectory`.
`openhands_chat` (SWE-rebench) · `sweagent_smith` (SWE-smith; ação decidida por mensagem) · `generic_chat` (OpenAI/Anthropic) ·
`ctb_openhands_swe`, `ctb_sweagent`, `ctb_miniswe`, `ctb_terminus2`, `ctb_openhands_events` + `codetracebench.py` · `claude_code_session` (Fase 7; `.jsonl` de sessão inteira = 1 trajetória) (`.tar.zst`/dir,
manifest → `ground_truth` com `resolved_idx`/`resolved_via`). Testes: `cd backend && uv run pytest` (fixtures reais em `tests/fixtures/`,
regeneráveis com `scripts/make_fixtures.py`); lote: `uv run python scripts/parse_samples.py`.
Ficou de fora/limitações: nada do plano foi pulado; `files` só vem do `path` do editor (bash fica p/ a Fase 3); mini-SWE TB sem JSON
(2/60) → `UnsupportedArtifact`; alinhamento da cauda de OpenHands-TB/Terminus2 e do OpenHands-SWE é hipótese; `generic_chat` só testado com mensagens sintéticas.

## Rotulação (Fase 3) — `backend/app/labeling/`
`label_trajectory(traj, llm=None)`: `rules.py` (ferramenta) → `bash_parser.py` (bashlex, fallback shlex/regex; regras de `python` em `classify_python`) → `llm.py` (só confiança < 0,6).
`Step.files` agora é `[{path, mode: read|edit|run}]`. Config por `backend/.env` (ver `.env.example`; a chave nunca é impressa). Testes: `uv run pytest` (249).
Relatórios: `scripts/label_report.py [--llm --budget 0.20]`, `scripts/make_gold_sample.py`. Limitação conhecida: o critério `other < 15%` mede cobertura, não acerto — o acerto foi medido na Fase 6 (gold manual).

## Detectores, métricas e API (Fase 4)
`analysis/detectors.py`: `error`, `test_fail`, `test_pass`, `repeated`, `no_new_info`, `loop`, `truncated` (+ `flag_details`); `analysis/metrics.py`: `compute_metrics`;
`pipeline.process(...)` = detect → parse → label → detectores → métricas, com cache em `backend/.cache/trajectories/`. Pré-aquecer: `uv run python scripts/warm_cache.py`.
Endpoints (OpenAPI em `docs/openapi.json`; tipos TS: `npm run gen:api`):
`POST /api/trajectories` (multipart: file, format?, row?, use_llm?) · `GET /api/trajectories/{id}` (obs. cortadas em 2.000 chars) ·
`GET /api/trajectories/{id}/steps/{idx}` · `GET /api/trajectories/{id}/metrics` · `PATCH /api/trajectories/{id}/steps/{idx}` ({category}) ·
`GET /api/library?dataset=&agent=&resolved=&q=` · `POST /api/library/{sample_id}/open` · `GET /api/taxonomy` · `GET /api/health`. CORS: http://localhost:5173.
O front só consome a API; erros são 422 `{detail:{code,message,top_keys?}}` (413 p/ > 200 MB, 404 p/ id/passo inexistente).

## Frontend (Fase 5) — `frontend/`
Vite + React + TS strict, Tailwind v4, componentes no estilo shadcn (Radix), React Router, TanStack Query (dados do servidor), Zustand (passo/filtros/aba, espelhados na URL),
`@xyflow/react` (grafo), Recharts (dashboard), prism-react-renderer, html-to-image. Tipos: `npm run gen:api` (de `docs/openapi.json`). Cliente: `src/api/client.ts` (VITE_API_URL, padrão :8000).
Telas: `/` biblioteca + upload; `/t/:id` cabeçalho + faixa de fases + abas Grafo/Dashboard + inspetor. Paleta fixa em `src/theme/categories.ts`.
Testes: `npm test` (vitest), `npm run test:e2e` (Playwright, API em :8011 com cache isolado), `npm run screenshots`. O front não tem lógica de domínio.

## Regras
- `schema.py` é o contrato. Mudou o schema → regenerar os tipos TS (`npm run gen:api`).
- Todo adaptador e toda regra de rotulação tem teste em `backend/tests/` com fixture real
  (trajetórias pequenas em `backend/tests/fixtures/`).
- Classificador em camadas: (1) nome da ferramenta, (2) comando bash (`bash_parser.py`, shlex/bashlex,
  prioridade entre partes de pipeline: edit > test > reproduce > search > read > explore),
  (3) LLM só para `other` ou confiança < 0.6.
- LLM só em `labeling/llm.py`, atrás de `LABEL_LLM_ENABLED`. SDK da Anthropic, modelo
  `claude-haiku-5-5` (env `ANTHROPIC_API_KEY`, `LLM_MODEL`). Orçamento total: ~US$ 4,91.
  - cada requisição < 100K tokens (acima disso o preço do Haiku 5.5 sobe 5x);
  - taxonomia no system prompt com prompt caching;
  - cache local por hash do passo (nunca pagar duas vezes);
  - contador de tokens/custo gravado em `backend/.cache/llm_usage.json`;
  - o app tem que funcionar sem chave (passo fica `other`, `label_source="fallback"`).
- Nunca carregar um dataset inteiro na memória. Ler Parquet com `pyarrow` em lotes
  (`iter_batches`) e salvar amostras em `data/samples/`.
- `data/raw/` e `data/samples/` grandes não vão para o git (ver `.gitignore`).
- Commits pequenos, um por fase/tarefa, mensagem descritiva em português.

## Comandos
- `cd backend && uv run pytest`
- `cd backend && uv run uvicorn app.main:app --reload`
- `cd frontend && npm run dev`
- `cd frontend && npm run gen:api` (gera tipos a partir de `http://localhost:8000/openapi.json`)
- `docker compose up --build` (web :5173 e API :8010; `WEB_PORT`/`API_PORT`; `backend/.env` opcional)

## Estado atual
- [x] Fase 1 — exploração dos datasets (`docs/formats.md`, `data/samples/`, `backend/scripts/explore_dataset.py`)
- [x] Fase 2 — schema + adaptadores + detecção de formato (`backend/app/schema.py`, `backend/app/adapters/`, `results/parse_report.md`)
- [x] Fase 3 — rotulação (regras + fallback Haiku) (`backend/app/labeling/`, `results/labeling_report.md`, `results/gold/gold_steps_cego.csv`)
- [x] Fase 4 — detectores, métricas, API (`backend/app/analysis/`, `pipeline.py`, `main.py`, `library.py`, `docs/openapi.json`)
- [x] Fase 5 — frontend: biblioteca, faixa de fases, grafo, inspetor, dashboard (`frontend/`; capturas em `results/screenshots/`)
- [x] Fase 6 — avaliação e pacote de resultados (`results/RESULTS.md`; gold manual `results/gold/gold_steps_cego_pedro.csv`, 210 passos, 1 anotador): regras 94,3% de acurácia, F1 macro 0,92; LLM 91,4%; `setup` é a categoria fraca (sugestões em `results/eval_classifier_sugestoes.md`, não aplicadas). Reproduzir: `cd backend && uv run python scripts/evaluate.py [--gold CSV] && uv run python scripts/figures.py && uv run python scripts/poster_pack.py`
- [x] Fase 7 — entrega do MVP (`v0.1-mvp`): gold held-out cego (`results/gold/gold_holdout_cego.csv`, `make_gold_sample.py --holdout`; `evaluate.py --gold … --tag holdout` gera `eval_classifier_holdout.md` e a tabela desenvolvimento × held-out no `RESULTS.md`), comparação com o TraceView (`docs/comparacao_traceview.md`, capturas em `results/screenshots/comparacao/`, `frontend/e2e/comparacao.mjs`), mapeamento de taxonomias (`docs/taxonomia_mapeamento.md`), Docker (`docker-compose.yml`: `api` + `web`/nginx; `WEB_PORT`/`API_PORT`), README + `docs/demo.gif`, roteiro da demo (`docs/roteiro_demo.md`, URLs validadas por `frontend/e2e/demo-urls.mjs`) e o adaptador stretch `claude_code_session` (`.jsonl` de `~/.claude/projects/`).
  **Pendências:** (1) Pedro rotular o gold held-out e rodar o `evaluate.py --tag holdout` (sem isso não há número held-out); (2) completar a seção ASE'25 de `docs/taxonomia_mapeamento.md` (TODO); (3) decidir se uma sessão real do Claude Code entra na biblioteca como demo (nenhum log real foi incluído no repositório); (4) a tela "Comparar" não foi implementada.
