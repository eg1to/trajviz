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

## Estado atual
- [ ] Fase 1 — exploração dos datasets (`docs/formats.md`, `data/samples/`)
- [ ] Fase 2 — schema + adaptadores + detecção de formato
- [ ] Fase 3 — rotulação (regras + fallback Haiku)
- [ ] Fase 4 — detectores, métricas, API
- [ ] Fase 5 — frontend: upload, faixa de fases, inspetor, grafo (pôster: seg 23/11)
- [ ] Fase 6 — dashboard, filtros, avaliação (`scripts/evaluate.py`, `results/`)
- [ ] Fase 7 — docker compose, polimento, demo (MVP: qua 25/11)
