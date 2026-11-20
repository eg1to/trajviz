# Roteiro da demo (5 minutos)

Para a banca ou o pôster. As URLs abaixo foram **validadas** em 20/11/2026 por `frontend/e2e/demo-urls.mjs` (abre cada uma e grava a captura em `results/screenshots/demo/`).
Os ids (`/t/<id>`) são o hash do conteúdo do arquivo, então são os mesmos em qualquer máquina que abra os mesmos arquivos.

## Preparação (antes de começar)

1. `docker compose up --build` (web em `http://localhost:5173`, API em `http://localhost:8010`), com `data/samples/` preenchida (as trajetórias abaixo vêm de lá).
2. Abrir o stack uma vez e rodar `cd frontend && node e2e/demo-urls.mjs` — confirma que todas as URLs respondem e **pré-aquece o cache** (a 1ª abertura de cada amostra processa o arquivo; as demais são instantâneas).
3. Abas prontas no navegador (tema claro, janela ≥ 1400 px de largura):
   - **A** editor com o log bruto: `data/samples/swe-rebench/chatcmpl-dd059e8e169114015e62f521024377e5.json` (368 KB; uma única linha de JSON gigante);
   - **B** `http://localhost:5173/`;
   - **C** TraceView: `cd ../traceview && uv run --python 3.14 streamlit run traceview.py` → `http://localhost:8501` (o TraceView exige Python ≥ 3.14; sem `--python 3.14` o `uv` desta máquina escolheu o 3.15 e o `pillow` não compilou).
4. Arquivo para o upload: o mesmo `chatcmpl-dd059e8e….json` (na janela de escolha de arquivo, deixar a pasta `data/samples/swe-rebench/` aberta).

## Roteiro

| min | momento | o que fazer | URL | o que dizer |
|---|---|---|---|---|
| 0:00–0:45 | **1. O problema** | Aba A: mostrar o JSON bruto no editor (368 KB numa linha; ~56 passos, 56 resultados de ferramenta, pensamentos misturados com comandos) | — (arquivo local) | "Um agente de código deixa isto como rastro. Responder 'onde ele se perdeu?' exige ler tudo. Ferramentas existentes pedem que você rotule cada ação e cada relação à mão antes de ver qualquer coisa." |
| 0:45–1:30 | **2. Upload → visualização em segundos, sem rotular** | Aba B: arrastar o arquivo para a área de upload | `http://localhost:5173/` → abre `http://localhost:5173/t/dfe5dad526a8d88f` | "Sem escolher formato nem rotular. O sistema detectou `openhands_chat` (97%), classificou os 56 passos por regras e calculou os detectores. Do upload ao grafo, cerca de 1 s; o processamento no servidor leva dezenas de ms." |
| 1:30–2:30 | **3. Faixa de fases: resolvida × não resolvida** | Mostrar a faixa do topo da não resolvida; trocar para a resolvida e comparar | resolvida: `http://localhost:5173/t/afc56e3505505b81` (96 passos, PASS) · não resolvida: `http://localhost:5173/t/dfe5dad526a8d88f` (56 passos, FAIL) | "Azul = entendimento, laranja = edição, rosa/verde = verificação. Na resolvida os ciclos editar→testar terminam em ✓ (4 de 8); na não resolvida há um `loop` e os testes terminam em ✕. É uma impressão visual de 2 casos, não uma prova — o agregado vem no minuto 4." |
| 2:30–3:30 | **4. Um detector em ação** | Abrir o passo 30, apontar o selo "sem informação nova" e clicar em "ir ao #9" (o link do passo original). Depois mostrar o loop | passo 30: `http://localhost:5173/t/dfe5dad526a8d88f?step=30&view=graph` → "ir ao #9": `http://localhost:5173/t/dfe5dad526a8d88f?step=9&view=graph` · loop: `http://localhost:5173/t/dfe5dad526a8d88f?step=24&view=graph&filter=loop` | "O passo 30 reabriu `test_response.py` sem nenhuma edição desde o passo 9: o detector marca e aponta o passo original. Aqui o agente editou e testou o mesmo arquivo 3 vezes com o mesmo erro (passos 24–41): é o loop." |
| 3:30–4:30 | **5. Dashboard e o achado resolvidas × não resolvidas** | Abrir o dashboard da não resolvida e depois o da resolvida; mostrar a figura do agregado | `http://localhost:5173/t/dfe5dad526a8d88f?view=dashboard` · `http://localhost:5173/t/afc56e3505505b81?view=dashboard` · agregado: `results/figures/metricas_resolvidas_vs_nao.png` | "Categorias, ferramentas, 1ª edição, ciclos editar→testar, erros. Em 2.000 trajetórias do SWE-rebench, as resolvidas são menores (mediana 56 × 68 passos), com mais passos de teste (12,8% × 10,7%) e menos releituras sem informação nova (2,0% × 2,9%). Efeitos pequenos a médios e **associativos**: o tamanho da tarefa e o agente confundem." |
| 4:30–5:00 | **6. O mesmo `.traj` no TraceView** | Aba C: enviar `../traceview/evaluation_samples/pytest-dev__pytest-5692__eval_02_fix-and-test.traj` → tela de Labeling ("Action labels 0 of 8 · Relationship labels 0 of 36"). Depois voltar ao trajviz | TraceView: `http://localhost:8501` · trajviz, mesmo arquivo: `http://localhost:5173/t/90b7a9c28a9c71a3` | "O mesmo arquivo: no TraceView são 44 rótulos manuais (8 ações + 36 relações) para a visualização completa, no mínimo 10 para liberar o botão; no trajviz, zero. O que o TraceView tem e nós não: relações semânticas entre passos (alinhamento, redundância…); é o trabalho do TCC II. E os nossos rótulos são automáticos: 94,3% de acurácia no gold manual de 210 passos." |

Folga: ~0 s. Se faltar tempo, cortar o momento 4 do loop (`?step=24`) e a segunda aba do dashboard.

## Perguntas previsíveis (respostas curtas)

- *Quão certos estão os rótulos?* Regras: 94,3% [90,5–97,4] contra um gold manual cego de 210 passos, 1 anotador; o gold saiu das mesmas amostras usadas no desenvolvimento (pode ser otimista); há um gold held-out de 90 passos pronto para rotular (`results/gold/gold_holdout_cego.csv`) — **sem resultado ainda**. A categoria fraca é `setup`.
- *Os detectores acham os passos ruins do CodeTraceBench?* `error ∪ test_fail` é 1,62× melhor que sorteio para passos incorretos; `repeated ∪ no_new_info` é indistinguível de sorteio para os "inúteis"; `loop` é inconclusivo (`results/eval_detectors.md`).
- *Por que não tem relações entre passos?* Decisão de escopo (18/11): é a parte mais arriscada de automatizar; fica para o TCC II.
- *E o custo do LLM?* US$ 0,0209 no projeto inteiro; só entra em 0,2–2,6% dos passos e é opcional.

## Plano B — se a API ou o Docker cair

1. **Capturas** (abrir no visualizador de imagens, na ordem do roteiro):
   1. problema → o JSON no editor (aba A) ou `results/screenshots/01-biblioteca.png` para a biblioteca;
   2. upload/visualização → `results/screenshots/01-biblioteca.png` e `results/screenshots/03-swe-rebench-nao-resolvida-grafo.png`;
   3. faixas → `results/screenshots/demo/02-faixa-resolvida.png` × `results/screenshots/demo/03-faixa-nao-resolvida.png`, ou `results/poster/faixas_exemplo.png`;
   4. detector → `results/screenshots/demo/04-detector-no-new-info-passo-30.png`, `…/04b-passo-original-9.png`, `…/04c-detector-loop-passo-24.png`;
   5. dashboard → `results/screenshots/demo/05-dashboard-nao-resolvida.png`, `…/05b-dashboard-resolvida.png`, `results/screenshots/02-swe-rebench-resolvida-dashboard-completo.png`, e o agregado `results/figures/metricas_resolvidas_vs_nao.png`;
   6. TraceView → `results/screenshots/comparacao/pytest-5692-traceview-ingest.png` (nada rotulado), `…-rotulacao-acoes.png`, `…-analise.png` ao lado de `pytest-5692-trajviz-grafo.png`.
2. **GIF** do fluxo completo: `docs/demo.gif` (17 s; biblioteca → upload → grafo → inspetor → dashboard).
3. **Só a API caiu, o front está de pé**: o front mostra "API indisponível" com "Tentar de novo"; subir de novo com `docker compose up -d api` (health em `http://localhost:8010/api/health`). O cache em `backend/.cache/` mantém os ids, então os links `/t/<id>` voltam a funcionar sem reprocessar.
4. **Sem o Docker**: modo desenvolvimento do README (`uv run uvicorn app.main:app --port 8010` + `npm run dev` com `frontend/.env.local`).
5. Se o TraceView não subir: usar as capturas de `results/screenshots/comparacao/` e os números de `docs/comparacao_traceview.md`.
