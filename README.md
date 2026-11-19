# trajviz

Visualizador de trajetórias de agentes de código. Envie o log bruto de um agente (OpenHands, SWE-agent,
CodeTraceBench ou chat genérico) e veja na hora o grafo da trajetória, a faixa de fases, o inspetor de
cada passo e um dashboard de métricas, sem nenhuma rotulação manual.

TCC I — DCC/UFMG · Pedro Henrique Egito Aguiar · Orientador: Marco Túlio Valente

## Como rodar

```bash
# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs

# frontend
cd frontend
npm install
npm run dev                               # http://localhost:5173
```

Ou tudo junto: `docker compose up`.

Para o fallback de rotulação por LLM (opcional):

```bash
export ANTHROPIC_API_KEY=...
export LABEL_LLM_ENABLED=1
export LLM_MODEL=claude-haiku-5-5
```

## Dados

Coloque os datasets em `data/raw/` (fora do git):

- `data/raw/swe-rebench/` — nebius/SWE-rebench-openhands-trajectories
- `data/raw/swe-smith/` — SWE-bench/SWE-smith-trajectories
- `data/raw/codetracebench/` — NJU-LINK/CodeTraceBench

Os formatos estão documentados em `docs/formats.md`.

## Documentação

- `docs/PLAN.md` — plano do MVP
- `docs/formats.md` — formatos dos datasets
- `docs/decisions.md` — registro de decisões
