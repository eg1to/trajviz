# Glossário

Termos usados em toda a documentação do trajviz. Os outros documentos usam **sempre** estes nomes.

| termo | definição | onde aparece no código |
|---|---|---|
| **trajetória** | O registro completo de uma execução de um agente de código numa tarefa: enunciado, sequência de passos, desfecho. Um arquivo de log pode conter uma trajetória (`.traj`, `.log` do Ark, sessão do Claude Code) ou várias (Parquet, `.jsonl`; escolhe-se a linha com `row`). | `schema.Trajectory` |
| **passo** | Uma unidade *pensamento → ação → resultado* do agente: o pensamento que antecede uma ação, a ação (uma chamada de ferramenta ou comando) e a observação que ela produziu. A unidade exata depende do formato (ver [formats.md](formats.md) e [decisions.md](decisions.md#dados-e-formatos)). | `schema.Step` |
| **modelo canônico TAR** | O esquema único (Thought-Action-Result) para o qual todo formato é convertido: `Trajectory` → `Step` → `Action` + `Observation` (+ `GroundTruth`). O resto do sistema só conhece esse modelo. É o contrato entre backend e frontend. | `backend/app/schema.py` |
| **adaptador** | Módulo que reconhece um formato bruto (`can_parse → confiança`) e o converte no modelo canônico TAR (`parse → Trajectory`). | `backend/app/adapters/*.py` |
| **detecção de formato** | Escolha automática do adaptador de maior confiança (mínimo 0,3) para um arquivo enviado. | `adapters/detect.py` |
| **taxonomia** | As 11 **categorias** fixas de ação (`explore`, `search`, `read`, `edit`, `reproduce`, `test`, `setup`, `vcs`, `think`, `submit`, `other`) agrupadas em 4 **fases** (Entendimento, Modificação, Verificação, Controle). | `labeling/taxonomy.py` |
| **rotulação em camadas** | O classificador que atribui uma categoria a cada passo: (1) nome da ferramenta → (2) comando de shell → (3) LLM, só para passos de baixa confiança e só se pedido. | `labeling/` |
| **`label_source`** | Origem do rótulo de um passo: `rule` (regra exata ou confiança ≥ 0,6), `fallback` (palpite da regra com confiança < 0,6), `llm` (o LLM respondeu), `user` (corrigido na interface). | `Step.label_source` |
| **subcategoria** | Detalhe do rótulo (ex.: `grep\|sed -n`, `view_dir`, `edit_rejected`). Duas subcategorias têm papel especial: **`keys`** (teclas de controle, `other`) e **`harness_protocol`** (protocolo de submissão do harness, `submit`). Junto com os passos **`message`** (`Action.tool = message`: o agente fala sem agir, rotulado `think`), ficam fora das contagens por categoria. | `Step.subcategory` |
| **detector** | Regra automática que marca um passo com uma **flag**: `error`, `test_fail`, `test_pass`, `repeated`, `no_new_info`, `loop`, `truncated`. Cada flag traz um motivo (`flag_details`) e, quando houver, o passo relacionado (`flag_refs`). | `analysis/detectors.py` |
| **métricas** | Números calculados por trajetória para o dashboard (desfecho, esforço, dinâmica, problemas, arquivos, contexto, gabarito). | `analysis/metrics.py` |
| **pipeline** | detectar formato → converter (adaptador) → rotular → detectores → métricas. | `app/pipeline.py` |
| **gold** | Conjunto de passos rotulados **à mão** com a categoria correta, usado para medir a acurácia da rotulação em camadas. O **gold de desenvolvimento** tem 210 passos (já rotulado); o **gold held-out** tem 90 passos de trajetórias fora das amostras (ainda não rotulado). Rotulado **às cegas** (sem ver o rótulo da regra nem do LLM). | `results/gold/` |
| **gabarito** | As anotações humanas do CodeTraceBench: passos **incorretos** e **inúteis** por estágio. Usado para avaliar os detectores. Não confundir com o gold (que é de categorias). | `Trajectory.ground_truth` |
| **alinhamento por hipótese** | Quando o `step_id` do gabarito só pode ser ligado a um passo por uma regra não confirmada (cauda do OpenHands-TB/Terminus2, OpenHands-SWE). Marcado em `resolved_via="hypothesis"`. | `GroundTruth`, `AnnotatedStep` |
| **lift** | F1 de um detector ÷ F1 de um marcador aleatório com o mesmo nº de flags por trajetória. Lift ≈ 1 = indistinguível de sorteio. | `scripts/eval_detectors.py` |
| **resolvida / não resolvida** | `resolved` da fonte. No SWE-smith é **não validado** (o `patch` não corresponde à trajetória). | `Trajectory.resolved`, `resolved_validated` |
| **observação não registrada** | Passo do Ark cuja saída o próprio Ark não grava (`read_file`, `list_files`, `find_text`, testes que passaram): `observation = null` e aviso no inspetor. | `meta.ark.unrecorded` |
| **biblioteca** | Lista de amostras pré-carregadas (`data/samples/`) que a interface abre com um clique. | `app/library.py` |
| **id estável** | Identificador público de uma trajetória processada: hash só do conteúdo (+ `row` + `format_hint`); não muda quando as regras mudam. | `pipeline.content_id` |
| **versão do pipeline** | Hash do código de `schema`, `adapters`, `labeling`, `analysis` e `pipeline`; mudar qualquer um invalida o cache. | `pipeline.PIPELINE_VERSION` |
| **faixa de fases** | Barra horizontal no topo da tela da trajetória: um segmento por passo, colorido pela categoria, com marcas de erro/teste/loop. | `components/PhaseStrip.tsx` |
| **grafo em serpentina** | Grafo dos passos em ordem cronológica, em linhas de 12 nós da esquerda para a direita; **modo compacto** agrupa passos consecutivos da mesma categoria. | `components/graph/` |
| **inspetor** | Painel lateral com o rótulo, as flags, o pensamento, a ação, a observação e os arquivos do passo selecionado. | `components/Inspector.tsx` |
| **dashboard** | Aba com as métricas da trajetória; cada problema é clicável e leva ao passo. | `components/dashboard/` |
| **Ark** | Agente de código do orientador (<https://github.com/mtov/ark>); seus traces (`agent_trace.log`) são um dos formatos suportados. | `adapters/ark_trace.py` |
| **TraceView** | Visualizador de trajetórias do SOAR-Lab, referência principal do projeto; exige rotulação manual de ações e relações. | [comparacao_traceview.md](comparacao_traceview.md) |
