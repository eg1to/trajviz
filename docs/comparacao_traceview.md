# trajviz × TraceView

TraceView (SOAR-Lab, <https://github.com/SOAR-Lab/agent-traj-visualization>) é a referência principal do trajviz. Este documento compara as duas
ferramentas **na mesma trajetória**, com medidas feitas em 20/11/2026 e capturas em `results/screenshots/comparacao/`.

## Como foi medido

- **TraceView**: clone em `../traceview` (commit de `master` do dia), `uv sync --python 3.14` + `uv run --python 3.14 streamlit run traceview.py`.
  Observação: sem fixar `--python 3.14`, o `uv` escolheu o Python 3.15 desta máquina e o `pillow` não compilou; com 3.14 subiu de primeira (< 1 min).
- **trajviz**: API (`uvicorn`, porta 8010) + front (`npm run dev`, porta 5173).
- **Automação**: `frontend/e2e/comparacao.mjs` (Playwright) conduz as duas ferramentas e grava `results/screenshots/comparacao/medidas.json`
  (`CTB_TRAJ=<.traj> node e2e/comparacao.mjs`).
- **Trajetórias** (as duas abrem nas duas ferramentas):
  1. `pytest-dev__pytest-5692__eval_02_fix-and-test.traj` — amostra de `evaluation_samples/` do TraceView (janela de 8 passos de uma execução SWE-agent).
     O trajviz **já abre** o arquivo sem ajuste (detectado como `ctb_sweagent`, confiança 0,85); não foi preciso mexer no adaptador.
  2. `expressjs__express-3870.traj` — `.traj` do SWE-agent extraído do artefato `sweagent-OpenAI__GPT-5-expressjs__express-3870-7594bfc0` do CodeTraceBench
     (27 passos; resolvida segundo o benchmark). O TraceView aceitou o arquivo sem ajuste.

## Resultados

| medida | pytest-5692 (8 passos) | express-3870 (27 passos) |
|---|---|---|
| **trajviz** — rotulações manuais | 0 | 0 |
| **trajviz** — ações do usuário até ver o grafo | 1 (escolher/soltar o arquivo na biblioteca; navega sozinho para `/t/<id>`) | 1 |
| **trajviz** — upload → grafo + faixa de fases visíveis (Playwright, cache frio no servidor) | 0,86 s | 0,85 s |
| **trajviz** — processamento no servidor (log da API: detect → parse → rótulo → detectores → métricas, 1ª vez) | 22 ms | 18 ms |
| **TraceView** — rotulações para rotular **tudo** (ações + relações) | 8 + 36 = **44** | 27 + 131 = **158** |
| **TraceView** — mínimo exigido para liberar "Send to overview" | 5 ações + 5 relações = **10** | **10** |
| **TraceView** — cliques/seleções do roteiro automatizado até abrir a Análise | 101 (rotulando tudo) | 25 (só o mínimo) |
| **TraceView** — tempo do roteiro automatizado até abrir a Análise | 54 s (rotulando tudo) | 22 s (só o mínimo) |

Leitura honesta dos números:

- Os tempos do TraceView são do **roteiro automatizado** (clique + espera fixa de 0,7 s por rótulo): são um piso, **não** o tempo de um humano, que precisa
  ler o pensamento, a ação e o resultado de cada passo para decidir o rótulo (não medi isso; seria o objeto de um estudo com usuários, fora do TCC I).
  Os rótulos que o roteiro escolheu são genéricos (ex.: "Generate fix"/"Run tests" alternados): a visualização resultante serve só para a captura.
- O "mínimo de 10" libera a visualização, mas ela fica **quase vazia**: na trajetória de 27 passos só 5 nós ficam coloridos e os outros 22 aparecem sem categoria
  (`express-3870-traceview-analise.png`). Para a visualização ser equivalente à do trajviz é preciso rotular tudo (44 e 158 rótulos).
- Os rótulos do trajviz são **automáticos e podem estar errados** (acurácia das regras 94,3% no gold de desenvolvimento; ver `results/RESULTS.md`).
  Os rótulos manuais do TraceView, em princípio, são a verdade do anotador. Eliminar o trabalho tem esse custo.
- O tempo do trajviz de ~0,85 s inclui o upload, a API, a resposta e o desenho do grafo na página; o processamento no servidor é de poucas dezenas de ms.
  O log da API passou a registrar uma linha `processado <arquivo>: formato=… passos=… tempo=… ms` por upload.

### Capturas (mesma trajetória nas duas ferramentas)

| | trajviz | TraceView |
|---|---|---|
| pytest-5692 | `pytest-5692-trajviz-grafo.png` | `pytest-5692-traceview-ingest.png` (nada rotulado), `…-rotulacao-acoes.png`, `…-rotulacao-relacoes.png`, `…-pronto-para-enviar.png`, `…-overview.png`, `…-analise.png` |
| express-3870 | `express-3870-trajviz-grafo.png` | os mesmos seis arquivos com o prefixo `express-3870-traceview-` (`…-analise.png` mostra o grafo com só 10 rótulos) |

## Recursos lado a lado

| recurso | TraceView | trajviz |
|---|---|---|
| Formatos de entrada | `.traj` (SWE-agent), JSON/JSONL, `.log`/`.txt` (parser de texto), `.zip`; mais as 40 execuções do AutoCodeRover já empacotadas | `.json`, `.jsonl`, `.traj`, `.parquet` (1 linha), `.tar.zst`, `.zip`; 8 adaptadores com detecção automática (OpenHands, SWE-agent/SWE-smith, mini-SWE, Terminus2, OpenAI/Anthropic genérico) sobre um esquema canônico. *Atualização de 21/11: hoje são 10 adaptadores (+ `claude_code_session` e `ark_trace`) e o upload aceita também `.log`/`.txt`.* |
| Rotulação | **Manual**: categoria por iteração (8 rótulos) + relação por aresta (5 famílias, 2–5 rótulos cada); mínimo 5 + 5 para enviar | **Automática** (regras por ferramenta e por comando bash + fallback opcional em LLM); correção manual opcional por `PATCH` |
| Taxonomia de ações | Explore, Locate, Search, Reproduce, Generate fix, Run tests, Refactor, Explain | `explore`, `search`, `read`, `edit`, `reproduce`, `test`, `setup`, `vcs`, `think`, `submit`, `other` em 4 fases (ver `docs/taxonomia_mapeamento.md`) |
| Visões | Grafo T→A→R em modo *Iteration* ou *Detailed* (streamlit-agraph); inspetor (na página ou separado); filtros por relação; controles de layout | Grafo em serpentina com modo compacto para trajetórias longas; **faixa de fases**; inspetor de passo com navegação por teclado; filtros por erro/loop; exportação PNG |
| Métricas / dashboard | Resumo de relações por tarefa e página *Overview* (tabela de execuções com desfecho, nº de iterações, sequência de comportamento) | **Dashboard** por trajetória: KPIs, categorias e fases, ferramentas e executáveis, 1ª edição, ciclos edit→teste, taxas de erro/repetição/loop, arquivos lidos × editados, tamanho das observações |
| Detectores automáticos | Não há; os problemas aparecem pelas relações rotuladas à mão (Misalignment, Repetition, Redundancy…) | `error`, `repeated`, `loop`, `no_new_info`, `truncated`, `test_fail`/`test_pass`, com motivo e link para o passo relacionado |
| **Relações entre passos** | **Sim, é o forte do TraceView**: 5 famílias (Thought→Action, Thought→Thought, Action→Action, Result→Thought, Result→Action) com rótulos semânticos (Alignment, Follow-up, Refinement, Informative, Triggering, Redundancy, Repetition, Misalignment, Misinterpretation, Contradiction, Divergence, No influence) e filtros "só relações ruins / só loops / só sem influência" | **Não tem.** O grafo do trajviz mostra categoria + ordem cronológica + loops detectados; inferir relações semânticas ficou fora do MVP (decisão de 18/11, trabalho do TCC II) |
| Comparação entre execuções | *Overview*: tabela de execuções com filtros (desfecho, tags, busca) e comportamento resumido; não há grafos lado a lado | Biblioteca com filtros; resolvidas × não resolvidas só no agregado (`results/batch_stats.md`); **a tela "Comparar" não foi implementada** |
| Desfecho (PASS/FAIL) | Para as execuções empacotadas do AutoCodeRover (`results.json`); uploads ficam "unscored" | `resolved` quando a fonte traz; selo "não validado" no SWE-smith |
| Escala | As 40 execuções empacotadas têm 4–10 iterações e as amostras de avaliação são janelas de 8 passos; o nº de relações a rotular cresce ~5 por passo (131 em 27 passos) | Testado em trajetórias de até centenas de passos (modo compacto) e em 3.576 trajetórias em lote |
| Avaliação | Pesquisa com usuários (`docs/TraceView_Survey.csv`) | Gold manual de 210 passos (+ held-out), detectores × gabarito do CodeTraceBench; **sem estudo com usuários** |
| Stack | Python ≥ 3.14, Streamlit, streamlit-agraph, pandas, plotly | Python 3.12 + FastAPI + Pydantic; React + TypeScript + React Flow + Recharts; Docker |

## O que o TraceView faz melhor

1. **Relações semânticas entre passos** (a contribuição central dele): permitem perguntar "este resultado influenciou o próximo pensamento?" ou "a ação seguiu o pensamento?" — o trajviz não responde a nada disso.
2. **Rótulos com autoridade humana**: a categoria e a relação vêm do anotador; no trajviz uma categoria errada da regra aparece sem aviso (só há a confiança e a correção opcional).
3. **Visão Thought→Action→Result explícita** (*Detailed*): cada passo vira três nós; o trajviz mostra um nó por passo e leva pensamento/ação/resultado para o inspetor.
4. **Fluxo de rotulação integrado e exportável** (CSVs no formato do viewer, retomada do trabalho): útil para construir conjuntos anotados; o trajviz só tem a correção de rótulo por passo.
5. **Taxonomia de intenção** (Locate, Explain, Refactor), mais próxima do *propósito* do passo, enquanto a do trajviz descreve o *tipo da ferramenta/comando*.
6. **Simplicidade de instalação em um comando** (`uv sync` + `streamlit run`), sem Node nem serviço separado.

## O que o trajviz faz melhor

1. Zero rotulação: 0 rótulos × 44–158 para a mesma visualização completa; o log bruto vira grafo em < 1 s.
2. Multiformato: o mesmo fluxo para 8 formatos de log na data da comparação (10 adaptadores em 21/11); o TraceView espera o formato SWE-agent ou texto estruturado.
3. Dashboard e detectores automáticos (erros, repetições, loops, leitura sem informação nova).
4. Trajetórias longas (modo compacto, faixa de fases) e avaliação quantitativa dos rótulos e detectores.

## Limitações desta comparação

- Duas trajetórias, um avaliador, tempos de roteiro automatizado (sem tempo de leitura humano); nenhum estudo de usabilidade.
- O TraceView foi usado como clonado (sem alterar o código); os resultados dependem da versão do dia 20/11/2026.
- As trajetórias foram escolhidas porque as duas ferramentas as aceitam; não representam o conjunto de logs que cada uma suporta.
