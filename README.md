# trajviz

Visualizador de trajetórias de agentes de código, **sem rotulação manual**. Você envia o log bruto de um agente
(OpenHands, SWE-agent, mini-SWE, Terminus2, CodeTraceBench ou chat genérico) e vê na hora o grafo da trajetória,
a faixa de fases, o inspetor de cada passo e um dashboard de métricas com detectores de erro, repetição e loop.
Um classificador de regras (com fallback opcional em LLM) rotula cada ação no upload; a referência, o TraceView, exige rotular tudo à mão.

TCC I — DCC/UFMG · Pedro Henrique Egito Aguiar · Orientador: Marco Túlio Valente

![Grafo de uma trajetória do CodeTraceBench com gabarito](results/screenshots/05-ctb-gabarito-grafo.png)

*Faixa de fases (topo), grafo em serpentina com modo compacto, arcos de loop, marcadores do gabarito do CodeTraceBench e inspetor do passo à direita.*

![Demo: biblioteca → upload → grafo → inspetor → dashboard](docs/demo.gif)

*Do upload ao dashboard (gravado com Playwright; `frontend/e2e/demo-gif.mjs`).*

## Como rodar

### Docker (recomendado)

```bash
mkdir -p backend/.cache data/samples data/raw/codetracebench   # pastas montadas como volume
docker compose up --build
# web: http://localhost:5173   ·   API (Swagger): http://localhost:8010/docs
```

- Portas: `WEB_PORT` (padrão 5173) e `API_PORT` (padrão 8010), por exemplo `API_PORT=8020 WEB_PORT=8080 docker compose up --build`.
  O nginx do `web` repassa `/api` para a API, então o front funciona em qualquer porta (sem CORS).
- Volumes: `data/samples/` (biblioteca), `data/raw/codetracebench/` (opcional; manifest e artefatos do CodeTraceBench, para o gabarito) e `backend/.cache/` (cache em disco e contador de custo do LLM).
  Sem amostras em `data/samples/` a biblioteca fica vazia, mas o **upload funciona**.
- `backend/.env` é opcional. Sem ele (ou sem `ANTHROPIC_API_KEY`) o fallback em LLM fica desligado e o app usa só as regras.
  Para ligá-lo: `cp backend/.env.example backend/.env` e preencha `ANTHROPIC_API_KEY`, `LABEL_LLM_ENABLED=1`, `LLM_MODEL`, `LLM_BUDGET_USD`.
  A chave nunca é impressa nem versionada; a API só usa o LLM quando o upload pede (`use_llm=true`).
- Os containers rodam como root por padrão (arquivos criados em `backend/.cache/` ficam de root). Para usar seu usuário: `LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build` com as pastas já criadas.

### Modo desenvolvimento

```bash
# backend  → http://localhost:8000/docs
cd backend
uv sync
uv run uvicorn app.main:app --reload

# frontend → http://localhost:5173
cd frontend
npm install
npm run dev
```

Se a porta 8000 estiver ocupada, suba a API em outra (`--port 8010`) e aponte o front para ela com
`frontend/.env.local`: `VITE_API_URL=http://localhost:8010` (o padrão é `http://localhost:8000`).
O CORS da API só libera `http://localhost:5173`.
O front **só consome a API** (`docs/openapi.json`); depois de mudar o schema: `cd frontend && npm run gen:api`.
Abra uma amostra direto num passo: `http://localhost:5173/t/<id>?step=42&view=graph&filter=error`
(`view=graph|dashboard`, `filter=error,loop,nospecial,cat:edit`, `range=10-30`, `compact=0|1`, `gt=0`).
Atalhos: `j`/`k` ou ← → navegam entre passos, `Esc` limpa a seleção.

## Formatos suportados

Detecção automática (`backend/app/adapters/detect.py`); todos viram o esquema canônico (`backend/app/schema.py`). Upload aceita `.json`, `.jsonl`, `.traj`, `.parquet` (1 linha), `.tar.zst` e `.zip` (até 200 MB).

| formato | origem | adaptador | observações |
|---|---|---|---|
| OpenHands (log de chat) | SWE-rebench | `openhands_chat` | `resolved` e `exit_status` da fonte |
| SWE-agent (nativo, xml e ticks) | SWE-smith | `sweagent_smith` | ação decidida por mensagem (o split `tool` mistura formatos); `resolved` **não validado** |
| Chat genérico OpenAI/Anthropic | qualquer | `generic_chat` | só testado com mensagens sintéticas; agente = "desconhecido" |
| SWE-agent `.traj` | CodeTraceBench, TraceView | `ctb_sweagent` | abre também os `.traj` avulsos do `evaluation_samples/` do TraceView |
| mini-SWE `.traj.json` | CodeTraceBench | `ctb_miniswe` | 2 de 60 artefatos sem JSON → erro claro (`UnsupportedArtifact`) |
| Terminus2 (episódios) | CodeTraceBench | `ctb_terminus2` | 1 passo por episódio |
| OpenHands (log de LLM e eventos) | CodeTraceBench | `ctb_openhands_swe`, `ctb_openhands_events` | alinhamento da cauda é hipótese |

Artefatos do CodeTraceBench (`.tar.zst`/diretório) trazem o gabarito (`ground_truth`: passos incorretos/inúteis) a partir do manifest em `data/raw/codetracebench/`.

## Resultados principais

Detalhes, ressalvas e scripts em [`results/RESULTS.md`](results/RESULTS.md).

- **Classificador de ações** (gold manual cego, 210 passos, 1 anotador): regras com acurácia **94,3%** [IC95 90,5–97,4] e F1 macro **0,92**; LLM (Haiku 5.5 em todos os passos) 91,4%; `setup` é a categoria fraca. O gold de desenvolvimento saiu das mesmas amostras usadas para escrever as regras, então pode ser otimista: há um gold **held-out** (90 passos de trajetórias fora de `data/samples/`) pronto para ser rotulado (`results/gold/gold_holdout_cego.csv`); ainda sem resultado.
- **Detectores × CodeTraceBench** (976 trajetórias): `error ∪ test_fail` acima do acaso para passos incorretos (lift 1,62×); `repeated ∪ no_new_info` indistinguível do acaso para passos inúteis; `loop` inconclusivo depois da correção.
- **Resolvidas × não resolvidas** (SWE-rebench, 2.000 trajetórias): as resolvidas são menores (mediana 56 × 68 passos), com mais passos de teste (12,8% × 10,7%) e menos `no_new_info`; efeitos pequenos a médios e **associativos** (confundidos por tarefa, limite de iterações e agente).
- **Velocidade**: o pipeline leva mediana de 31 ms por trajetória (p95 92 ms); do upload ao grafo na tela, ~0,9 s.
- **Comparação com o TraceView** ([`docs/comparacao_traceview.md`](docs/comparacao_traceview.md)): 0 rótulos manuais no trajviz × 44 (8 passos) a 158 (27 passos) no TraceView para a mesma visualização completa; o TraceView tem relações entre passos, que o trajviz **não** tem.

## Limitações

- **Sem relações entre passos** (Thought→Action, Result→Thought…): o grafo mostra categoria, ordem cronológica e loops. Fica para o TCC II.
- Rótulos **automáticos**: acurácia medida só em 210 passos com 1 anotador; categorias raras têm IC largo; o gold held-out ainda não foi rotulado.
- O `resolved` do SWE-smith não é validado; o `step_id` do CodeTraceBench tem semântica diferente por agente e o alinhamento da cauda do OpenHands/Terminus2 é hipótese.
- `generic_chat` só foi testado com mensagens sintéticas; logs genéricos aparecem como agente "desconhecido".
- Sem tela de comparação entre execuções, sem estudo com usuários, sem banco de dados (cache em disco).
- A biblioteca depende de amostras em `data/samples/` (fora do git); uploads funcionam sem elas.

### Testes e capturas

```bash
cd backend  && uv run pytest                          # backend (362 testes)
cd frontend && npm test                               # vitest (paleta, contraste, URL ⇄ estado)
cd frontend && npm run test:e2e                       # Playwright: fumaça (biblioteca → passo → dashboard → problema)
cd frontend && npm run screenshots                    # results/screenshots/*.png (1600×1000, tema claro, 2×)
cd backend  && uv run python scripts/pick_showcase.py # reescolhe as amostras das capturas
```

Os testes e2e sobem a API (porta 8011) e o front com cache e `results/` isolados (`frontend/test-results/`).

### Amostras das capturas (`results/screenshots/`)

| captura | amostra | por que |
|---|---|---|
| `01-biblioteca` | — | biblioteca + upload |
| `02-swe-rebench-resolvida-*` | `swe-rebench/chatcmpl-831fa55b…` (96 passos, PASS) | 8 ciclos edit→test (4 terminaram em pass), 6 erros |
| `03-swe-rebench-nao-resolvida-*` | `swe-rebench/chatcmpl-dd059e8e…` (56 passos, FAIL) | 1 loop, 6 ciclos (3 terminaram em test_fail) |
| `04-swe-smith-*` | `swe-smith/ticks/john-kurkowski__tldextract…` (76 passos) | 6 ciclos, 9 repetidos/sem informação nova; "resolved não validado" |
| `05-ctb-gabarito-*` | `codetracebench/terminus2-…fix-ocaml-gc…` (141 passos, FAIL) | 26 passos anotados no gabarito; modo compacto (o `loop` corrigido não marca esta trajetória) |

Cada trajetória tem `-grafo`, `-dashboard` (topo) e `-dashboard-completo` (viewport alto).

Para o fallback de rotulação por LLM (opcional), copie `backend/.env.example` para `backend/.env` e preencha
`ANTHROPIC_API_KEY`, `LABEL_LLM_ENABLED=1`, `LLM_MODEL`, `LLM_BUDGET_USD`. A chave nunca é impressa nem versionada;
a API só usa o LLM quando o upload pede (`use_llm=true`).

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
