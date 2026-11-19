# Formatos dos datasets — Fase 1

Gerado a partir de `backend/scripts/explore_dataset.py` (estatísticas em amostras de ~2.000 linhas espalhadas pelos
arquivos; amostras salvas em `data/samples/<dataset>/`, números brutos em `data/samples/<dataset>/_stats.json`).
Tudo aqui foi **medido nos dados**, salvo quando marcado como *hipótese*.

Convenções: "passo" = uma ação do agente (+ o pensamento que a precede e a observação que a segue).

## 0. Visão geral e pegadinhas que mudam o desenho

| # | Achado | Impacto |
|---|---|---|
| 1 | **O split `tool` do SWE-smith mistura dois formatos de ação**: 38% das linhas usam `tool_calls` nativo, 62% usam o mesmo texto `<function=…>` do split `xml`. | A detecção de formato é **por mensagem**, não pelo nome do split. |
| 2 | **SWE-smith: `patch` quase nunca corresponde à trajetória** (só ~17% das linhas não vazias citam na trajetória algum arquivo do patch; 26–30% dos patches são vazios). | Não usar `patch` do SWE-smith como verdade; derivar do `submit`/edições se precisar. `resolved` do SWE-smith também não pôde ser validado. |
| 3 | **CodeTraceBench: `verified` (1.000) ⊂ `full` (3.316)**. O README diz "4.316 trajetórias", mas 4.316 = 3.316 + 1.000 contado em dobro. | Total único = 3.316. |
| 4 | **CodeTraceBench: o `step_id` não é o mesmo índice nos 4 agentes** e o `step_count` do manifest nem sempre bate com os passos reais (ver §4.6). | Mapear por agente; usar `action_ref` quando existir. |
| 5 | **CodeTraceBench: 4 formatos brutos completamente diferentes** (logs de chamadas LLM, `.traj`, `mini.traj.json`, episódios do Terminus). Nenhum é igual ao do SWE-rebench/SWE-smith (só o mini-SWE e o SWE-agent *lembram* os de SWE-smith). | 4 adaptadores só para o CodeTraceBench. |
| 6 | SWE-rebench: **código de saída vem embutido no texto** da observação (`[The command completed with exit code N.]`), não há campo próprio. | Regex no adaptador. |
| 7 | Cada passo do SWE-rebench pode ter `content` vazio (29% dos `assistant`): o "pensamento" muitas vezes só existe na ferramenta `think`. | `thought` = `content` **ou** `args.thought`. |

## 1. SWE-rebench (OpenHands v0.54 + Qwen3-Coder-480B)

Arquivo único `data/raw/swe-rebench/trajectories.parquet` — **67.074 linhas**, 17 row groups, ~2,08 GB.

### 1.1 Campos de topo
| coluna | tipo | nota |
|---|---|---|
| `trajectory_id` | string | `chatcmpl-<hash>` |
| `instance_id` | string | ex. `gitpython-developers__GitPython-1224` |
| `repo` | string | `owner/repo` |
| `trajectory` | list<struct{content, name, role, tool_call_id, tool_calls}> | mensagens |
| `tools` | list<struct> | **definição JSON-schema das ferramentas, repetida em toda linha** (enorme). Ler com `columns=[…]` sem `tools`. |
| `model_patch` | string | patch final (vazio em 1/2.040) |
| `exit_status` | string | `submit` (91,8%), `RuntimeError: Agent reached maximum iteration…` (7,8%), `AgentStuckInLoopError…` (0,4%), erro de serviço (1) |
| `resolved` | int64 (0/1) | 48,5% resolvidas na amostra (990/2.040) |
| `gen_tests_correct`, `pred_passes_gen_tests` | double | métricas do benchmark |

### 1.2 Exemplo de um passo (truncado)
```jsonc
// assistant: pensamento em `content` (às vezes vazio) + 1 tool_call
{"role":"assistant","content":"Let me first explore the repository structure…",
 "tool_calls":[{"id":"chatcmpl-tool-c52500ad…","type":"function",
   "function":{"name":"str_replace_editor",
               "arguments":"{\"command\": \"view\", \"path\": \"/workspace\"}"}}]}
// tool: observação, ligada pelo tool_call_id
{"role":"tool","name":"str_replace_editor","tool_call_id":"chatcmpl-tool-c52500ad…",
 "content":"Here's the files and directories up to 2 levels deep in /workspace…"}
// execute_bash: o exit code vem NO TEXTO
{"role":"tool","name":"execute_bash","content":"/workspace/…\n[The command completed with exit code 0.]\n[Current working directory: …]\n[Python interpreter: …]"}
```

### 1.3 Regras de extração
- **Mensagens**: `system` (1), `user` (1: enunciado; 10 linhas da amostra têm 2), `assistant`, `tool`. Passo = **um `tool_call`**.
- `thought` = `assistant.content` se não vazio; senão, `arguments.thought` (ferramenta `think`).
- `action`: `function.name` + `json.loads(function.arguments)`. `arguments` **é sempre string JSON** (130.520/130.520 válidos na amostra).
  - `execute_bash` → `args.command` (+ `timeout`, `is_input`, `security_risk`). `is_input=true` envia teclas (`C-c`) a um processo em execução.
  - `str_replace_editor` → `args.command` ∈ {`view` 61%, `create` 20%, `str_replace` 19%, `undo_edit`, `insert`} + `path`, `old_str`, `new_str`, `file_text`, `view_range`.
  - `think` → `args.thought`; `task_tracker` → `args.command` (`plan`/`view`) + `task_list`; `finish` → `args.message`.
- `observation` = mensagem `tool` com o mesmo `tool_call_id`. `exit_code` = regex `\[The command completed with exit code (-?\d+)\.\]` (presente em 1.655/1.662 respostas de `execute_bash`).
- **Fim da tarefa**: ferramenta `finish` (sem mensagem `tool` de resposta); ou a trajetória termina sem `finish` quando `exit_status` ≠ `submit` (limite de 100 iterações, loop, erro de serviço).
- **Ferramentas (todas, na amostra)**: `execute_bash` 66.840 · `str_replace_editor` 54.562 · `think` 5.471 · `finish` 1.872 · `task_tracker` 1.775. (O card só mostrava `bash`.)

### 1.4 Onde estão os metadados
`resolved`, `exit_status`, `model_patch`, `instance_id`, `repo` na linha. **Modelo/agente não estão na linha** (constantes por README: Qwen3-Coder-480B / OpenHands).

### 1.5 Assinatura de detecção
Parquet com coluna `trajectory` (lista de structs com `tool_calls[].function.arguments` string) **ou**, em JSON avulso, lista de mensagens com `role` ∈ {system,user,assistant,tool} e `tool_calls[].function`. Ferramenta `execute_bash` + `str_replace_editor` + `finish`; ids `chatcmpl-tool-…`.

### 1.6 Armadilhas
- Passos por trajetória: min 26, p50 61, p90 94, **max 100** (limite do agente); mensagens: p50 123.
- **Vários `tool_calls` num `assistant`**: 1 caso em 130.528 (OpenHands normalmente só permite 1) → tratar como lista, 1 passo por call.
- `assistant` sem `tool_call`: 9. `tool_call` sem resposta: 2.038 (= `finish`, 1.872, + trajetórias cortadas).
- 29% dos `assistant` têm `content` vazio (`None`/`""`). `tool_calls` é `None` (não `[]`) nas outras mensagens.
- Observações: p50 889 chars, p90 5.715, **máx 30.047** (o agente já corta em ~30k; marcadores como `<response clipped>`/"truncated" aparecem em ~1% das observações).
- Os caminhos usam `/workspace/<owner>__<repo>__<versão>/` (`__unknown` quando não há versão).

---

## 2. SWE-smith (SWE-agent + Claude 3.7 Sonnet, principalmente)

`data/raw/swe-smith/data/{tool,xml,ticks}-0000N-of-00008.parquet` (8 arquivos por split). Linhas: **tool 24.100 · xml 26.076 · ticks 25.826 = 76.002**. (O split `train-*` do Hub foi ignorado: não consta do README.)
Modelos (amostra): `claude-3-7-sonnet-20250219` ~72%, `claude-3-5-sonnet-20241022` ~26%, `gpt-4o-2024-08-06` ~2% — **não é só Claude 3.7**.

### 2.1 Campos de topo (iguais nos 3 splits)
| coluna | tipo | nota |
|---|---|---|
| `messages` | **string = JSON** (`json.loads` → lista de dicts) | confirmado nos 3 splits |
| `instance_id` | string | `<owner>__<repo>.<hash>.<tipo_de_bug>` |
| `traj_id` | string | `instance_id` + `.` + sufixo de 8 chars (sempre ≠ `instance_id`) |
| `resolved` | bool | tool 39% · xml 43% · ticks 44% |
| `model` | string | |
| `patch` | string | **não confiável** (ver §0 #2) |

Não existe `exit_status`: "terminou por `submit`" = última ação é `submit` (tool 96%, xml 99%, ticks 91%).

### 2.2 A mesma ação nos três formatos
Sistema: `system` (1) → `user` (enunciado) → pares `assistant`/observação. A **observação vem como `role=tool`** no formato nativo e como **`role=user`** nos formatos textuais; em todos o texto começa com `OBSERVATION:\n` (e os `\r\n` das saídas de arquivo são preservados).

**`tool` (nativo)** — chaves extras `agent`, `message_type`:
```jsonc
{"role":"assistant","message_type":"action","agent":"main",
 "content":"Let's start with config_parser.py:",  "thought":"Let's start with config_parser.py:",
 "action":"str_replace_editor view /testbed/monai/bundle/config_parser.py",       // string pronta p/ exibição
 "tool_calls":[{"index":1,"id":"toolu_019B…","type":"function",
   "function":{"name":"str_replace_editor","arguments":"{\"command\":\"view\",\"path\":\"/testbed/monai/…\"}"}}]}
{"role":"tool","message_type":"observation","agent":"main","tool_call_ids":["toolu_019B…"],
 "content":[{"type":"text","text":"OBSERVATION:\n<NOTE>This file is too large…"}]}   // content é LISTA de partes
```
**`xml`** — tudo em `content` de texto:
```
{"role":"assistant","content":"Let's examine this file:\n\n<function=str_replace_editor>\n<parameter=command>view</parameter>\n<parameter=path>/testbed/x.py</parameter>\n</function>"}
{"role":"user","content":"OBSERVATION:\nHere's the result of running `cat -n` on /testbed/x.py:\r\n     1\t…"}
```
**`ticks`** — a ação é o **último bloco ``` sem linguagem**; blocos ```` ```python ```` no texto fazem parte do pensamento:
```
{"role":"assistant","content":"Let's examine the file:\n\n```\nstr_replace_editor view /testbed/x.py\n```"}
{"role":"user","content":"OBSERVATION:\n…"}
```
Final: nativo → `tool_calls[0].function.name == "submit"` (`arguments:"{}"`); xml → `<function=submit>\n</function>`; ticks → ```` ```\nsubmit\n``` ````.

### 2.3 Regras de extração
| | tool (nativo) | xml | ticks |
|---|---|---|---|
| thought | `thought` (= `content`) | texto antes de `<function=` | texto antes do último bloco ``` |
| ferramenta | `tool_calls[0].function.name` | `<function=NOME>` | 1ª palavra do bloco: `str_replace_editor`, `submit`, senão **bash** |
| args | `json.loads(arguments)` | `<parameter=NOME>valor</parameter>` | o resto do bloco como string (`--old_str '…'`, `--view_range`) |
| comando bash | `args.command` | `parameter=command` | bloco inteiro |
| observação | próxima `role=tool` (`content[*].text`) | próxima `role=user` | próxima `role=user` |
| fim | ação `submit` | `<function=submit>` | bloco `submit` |

Ferramentas (amostra): `str_replace_editor` ~56% (subcomandos `view` 47% · `str_replace` 37% · `create` 18% · `insert`, `undo_edit` raros), `bash` ~38%, `submit` ~5%.
`agent` é sempre `"main"` e `message_type` ∈ {`system_prompt`, `observation`, `action`} — **só existem no formato nativo**; servem de assinatura, não de dado útil.

### 2.4 Assinatura de detecção
- `messages` é string JSON → SWE-smith.
- Por mensagem `assistant`: tem `tool_calls` (lista) → **nativo**; `content` contém `<function=` → **xml**; senão bloco ``` final → **ticks**.
- O system prompt do xml/ticks-textual descreve `---- BEGIN FUNCTION #1: bash ----` (nativo tem prompt curto de uma frase).

### 2.5 Armadilhas
- **Split ≠ formato** (§0 #1). 189 `assistant` nativos sem `tool_calls` (resposta final/erro) e 87–219 xml/nativas sem nenhuma ação.
- **Múltiplas ações por mensagem**: xml 0 casos (sempre 1 bloco `<function>`); nativo 0 com >1 call; ticks: 0,4% das mensagens têm 2+ blocos sem linguagem — só o último é a ação (**a primeira abordagem "primeiro bloco" errava**).
- Subcomando malformado do modelo (`str_replace_editor` com `command="grep -n …"`): raro, mas existe.
- Observações: p50 ~850 chars, p90 ~5,5k, **máx 100k** (SWE-agent corta com `<NOTE>This file is too large…`/`Observation: Output too long`); ~3,5% casam o heurístico de truncamento.
- Mensagens: p50 ~52, p90 ~119, máx 303; **passos: média ~31, p50 25–26, p90 ~59, máx 151**.
- O sufixo `\r\n` e o `cat -n` (`   12\t…`) fazem parte do texto das observações de `view`.

---

## 3. Mapa das categorias de formato (resumo)
Ver tabela comparativa no §6.

---

## 4. CodeTraceBench (NJU-LINK)

### 4.1 Manifests (`bench_manifest.{verified,full}.{parquet,jsonl}`)
| coluna | tipo | nota |
|---|---|---|
| `traj_id` | string | `<agente>-<modelo>-<tarefa>-<hash8>` (também nome do `.tar.zst`) |
| `agent` | string | `OpenHands`, `mini-SWE-agent`, `Terminus2`, `SWE-agent` |
| `model` | string | verified: GPT-5 (489), Claude-Sonnet-4-Thinking (264), DeepSeek-V3.2 (247); full inclui Kimi-K2, Qwen3-Coder, DeepSeekChat |
| `task_name`, `task_slug`, `trial_name` | string | `trial_name` só no TerminalBench |
| `difficulty` | string | easy/medium/hard |
| `category` | string | 26 categorias |
| `tags` | string(JSON) | |
| `solved` | bool **ou null** | 28 nulos em `verified`, 106 em `full` |
| `step_count`, `stage_count`, `incorrect_error_stage_count` | int | |
| `stages` | string(JSON) | `[{stage_id,start_step_id,end_step_id}]` (1-based, inclusivo, contíguos) |
| `incorrect_stages` | string(JSON) | `[{stage_id, incorrect_step_ids[], unuseful_step_ids[], steps:[{step_id,labels[],action_ref,observation_ref}], reasoning?}]` |
| `source_relpath`, `annotation_relpath` | string | `swe_raw/…` ⇒ origem SWE-bench; nulo/outro ⇒ TerminalBench |
| `artifact_path` | string | `bench_artifacts/full/<traj_id>.tar.zst` |
| `generated_at` | string | |

**Contagens verificadas**: `verified` = 1.000 (489 SWE-bench + 511 TerminalBench); `full` = 3.316 (646 SWE-bench + 2.670 TerminalBench); **`verified` ⊂ `full`** (1.000/1.000 `traj_id` em comum). Em `verified`, 405 linhas têm anotação de passos incorretos/inúteis (a maioria é "sem erros").

**Diferença entre a contagem por agente do README e do manifest `verified`** (pedido da Fase 0): a tabela "Agent Coverage" do README (OpenHands 1.242 · mini-SWE 1.024 · Terminus2 923 · SWE-agent 127) soma 3.316 — é a contagem do split **`full`**, não do `verified`. O `verified` tem OpenHands 520 · Terminus2 222 · mini-SWE 150 · SWE-agent 108, o que o README não informa. Não há erro nos dados; a tabela do README é que não indica a qual split se refere. Além disso, "4.316 trajetórias" no README é 3.316 + 1.000 (contado em dobro).

**Linhas sem artefato**: 8 em `verified` (todas OpenHands/DeepSeek-V3.2, TerminalBench, `source_relpath` nulo — ex. `break-filter-js-…`, `fibonacci-server…`) e 25 em `full` (todas OpenHands). Não dá para baixar a trajetória delas; só têm metadados/anotação.
Artefatos no repo: 3.291 = 3.316 − 25 (consistente).

### 4.2 Estrutura interna do `.tar.zst` (por agente)
`zstd -d | tar -x` produz uma árvore **diferente por agente** (lista completa em `_stats.json › artifact_structure`):

| agente · origem | conteúdo principal | granularidade |
|---|---|---|
| **OpenHands · SWE-bench** | `swe_raw/openhands__verified/<inst>/{tensorblock__gpt-5-<ts>.json × N, report.json, patch.diff, eval.sh, run_instance.log}` | **um JSON por chamada ao LLM** (`messages` cumulativas + `response` + `kwargs.tools` + `cost`). A trajetória é a **última** chamada (mais mensagens) + o `response.choices[0].message`. |
| **OpenHands · TerminalBench** | os `R` primeiros `step_id` = k-ésimo evento `run` (**confirmado**: 25/25 `action_ref`), seguidos de uma *cauda* com as demais ações (`edit`, `read`, `run_ipython`, `think`, `finish`) em ordem de tempo (*hipótese*; **`message` não conta**) | todos os 9 `step_id` sem `action_ref` são > R; `step_count == nº de ações ≠ message` em 11/12 |
| **SWE-agent · SWE-bench** | `swe_raw/swe_agent__poly/<inst>/<inst>.traj` (4,5 MB), `.checkpoints.jsonl`, `.config.yaml`, `.debug/info/trace.log`, `.pred`, `_result.json`, `_metrics.json` | `.traj` = JSON `{trajectory[], history[], info, replay_config, environment}`; `trajectory[i]` = `{action, observation, response, thought, execution_time, state, query, extra_info}`. |
| **mini-SWE-agent · SWE-bench** | `swe_raw/mini_swe_agent__poly/<inst>/<inst>.traj.json` (+ `_result.json`, `_metrics.json`) | `{info, messages[], trajectory_format:"mini-swe-agent-1", instance_id}` |
| **mini-SWE-agent · TerminalBench** | `miniswe/<modelo>/<run>/<tarefa>/agent-logs/mini.traj.json` **ou, em alguns modelos, só `agent.cast`/`agent.log`** (sem JSON estruturado — 2 de 5 na amostra) | idem acima |
| **Terminus2 · TerminalBench** | `terminus2/<modelo>/<run>/<tarefa>/<tarefa>.1-of-1.<ts>/agent-logs/episode-N/{prompt.txt,response.txt,debug.json}` + `panes/`, `sessions/agent.cast` | **um diretório por episódio**; `response.txt` = JSON `{analysis, plan, commands:[{keystrokes,duration}], task_complete?}`; a observação é o `prompt.txt` **do episódio seguinte** ("New Terminal Output:…"). |

### 4.3 Como cada agente codifica pensamento → ação → observação
| agente | thought | action | observation | fim |
|---|---|---|---|---|
| mini-SWE | texto `THOUGHT: …` antes do bloco | **um** bloco ```` ```bash ```` (1 comando, pode ter `&&`) | próxima `user`: `<returncode>N</returncode>\n<output>…</output>` | `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`; depois mensagens extras `<PATCH_CONTEXT>` + `<context_received>` e a mensagem final com o diff |
| SWE-agent | `thought` (campo) | `action` (string: comando bash **ou** `str_replace_editor …`, `open`, `edit N:M … end_of_edit`, `scroll_down`, `submit`) | `observation` | ação `submit` (a 1ª pode ser **recusada** pelo "STOP! BEFORE SUBMITTING"; ver §4.5) |
| OpenHands · SWE | `assistant.content` / `think` | `tool_calls` (`execute_bash`, `str_replace_editor`, `task_tracker`, `think`, `finish`) | mensagem `tool` | `finish` |
| OpenHands · TB | `args.thought` / mensagem | evento `action` ∈ {`run` 430, `message` 445*, `edit`, `read`, `run_ipython`, `think`, `finish`} com `args.command` etc. | evento `observation` com `cause == id` da ação | `action=finish` + `agent_state_changed` |
| Terminus2 | `analysis` + `plan` | `commands[].keystrokes` (**vários por episódio**, texto com `\n`; podem ser `C-c`) | `prompt.txt` do episódio N+1 | `task_complete: true` no último `response.txt` |

\* uma trajetória OpenHands-TerminalBench da amostra tem ~445 eventos `message` (o agente "conversando" sem agir).

### 4.4 Quais usam o mesmo formato dos outros datasets?
- **OpenHands · SWE-bench**: mesma família do SWE-rebench (`tool_calls` estilo OpenAI, `execute_bash`/`str_replace_editor`/`think`/`finish`/`task_tracker`), mas **empacotado como log de chamadas LLM**, não como uma lista única de mensagens. Dá para **reconstruir** uma lista idêntica à do SWE-rebench a partir da última chamada → reaproveita a lógica do SWE-rebench.
- **OpenHands · TerminalBench**: OpenHands, mas **formato de eventos** (event stream) — não é o do SWE-rebench.
- **SWE-agent**: mesmo agente do SWE-smith, mas formato `.traj` (`trajectory[]` com `action`/`observation`/`thought`) — **não** é o `messages` do SWE-smith. A string `action` é a mesma do campo `action` do SWE-smith nativo.
- **mini-SWE-agent**: formato próprio (`messages` com bloco ```` ```bash ````). Parecido com o split `ticks` do SWE-smith (a ação é um bloco de crases), mas com `THOUGHT:` e `<returncode>`.
- **Terminus2**: sem equivalente nos outros datasets.

### 4.5 Mapeamento `step_id` das anotações ↔ passos
`stages` e `incorrect_stages` são **1-based**, estágios contíguos cobrindo `1..step_count`. Resultado por agente (verificado contra `action_ref`/`observation_ref` e contra os manifests; `action_ref` só existe em OpenHands-TB, Terminus2 e mini-SWE-TB):

| agente | `step_id` = | evidência |
|---|---|---|
| **SWE-agent** | `trajectory[step_id − 1]` (1-based) | `step_count == len(trajectory)` em 7/7; 0 `action_ref` para conferir |
| **mini-SWE-agent** | **n-ésima mensagem `assistant`** (1-based) | `step_count == nº de assistant` em 6/7 (os outros 2 não têm trajetória estruturada); `action_ref` do `fix-ocaml-gc`: passos 54, 56, 58, 59, 60 ↔ 54ª…60ª `assistant` (5/5) |
| **Terminus2** | o benchmark numera **comandos** (`keystrokes`), não episódios: os `E` primeiros `step_id` = episódio `step_id − 1` (**confirmado**: 34/34 `action_ref`), depois vem uma *cauda* com o 2º+ comando de cada episódio (*hipótese*, ordem por episódio) | `step_count == Σ len(commands)` em 10/13 exatos e 13/13 ±1 (episódios sozinhos: 1/13); mesmo prefixo ≤ E nas trajetórias com vários comandos por episódio (ocaml-gc: `step_id` 31→`episode-30`) |
| **OpenHands · SWE-bench** | *hipótese*: n-ésima `tool_call` (1-based), **sem contar a última** (`finish`) | `step_count = nº de tool_calls − 1` em 11/11; sem `action_ref` para confirmar |
| **OpenHands · TerminalBench** | **posição entre as ações `run`** (1-based), **não** entre todas as ações | 25/25 pares `action_ref` ↔ id de evento (4 trajetórias) ajustam a regra "k-ésimo `run`"; ⚠ mas `step_count` = **todas** as ações (run + edit + read + …) |

⚠ **Em OpenHands-TB e Terminus2 a lista do benchmark é "primárias + cauda"** (resolvido na Fase 2, `adapters/codetracebench.py`): o `step_id` só é seguro para o prefixo; use o `action_ref` como chave quando existir. A cauda é alinhada por hipótese e marcada `resolved_via="hypothesis"` no `GroundTruth`. Nas 58 trajetórias da amostra, 110/149 anotações são confirmadas e 39 são hipótese (`results/parse_report.md`).

Exemplos concretos (SWE-agent, `sweagent-OpenAI__GPT-5-keras-team__keras-19636-be8c419a`, estágio 6, `incorrect=[30,31,33]`, `unuseful=[32]`):
- **incorreto, `step_id` 30** = `trajectory[29]`: ação `submit`; observação = `**STOP! BEFORE SUBMITTING:** You MUST provide the CODE CONTEXT… output a <PATCH_CONTEXT> block…`. O "erro" é submeter sem o bloco `PATCH_CONTEXT` exigido pelo harness.
- **inútil, `step_id` 32** = `trajectory[31]`: sem ação, `thought` = longo plano reescrito ("Plan: - Explore repository to locate autocast…"), observação vazia.
- ⚠ Os 4 passos anotados (30–33) são o **protocolo de submissão do harness** (PATCH_CONTEXT), não comportamento de exploração. Isso afeta a avaliação dos detectores (§ PLAN 9): parte do "gabarito" mede peculiaridades do harness.
- O campo `reasoning` por estágio, descrito no README, **veio nulo** em todos os casos da amostra.

### 4.6 `step_count` do manifest × passos extraídos (amostra de 60)
`step_count == nº de passos extraídos`: SWE-agent 7/7 · OpenHands-TB 10/12 · mini-SWE 6/9 (2 sem trajetória estruturada; 1 off-by-one, provavelmente mensagens extras de `PATCH_CONTEXT`) · OpenHands-SWE 0/19 (sempre −1) · **Terminus2 1/13**.

### 4.7 Armadilhas
- 8 linhas `verified` sem artefato; 28 `solved` nulos; 2 mini-SWE-TB sem trajetória estruturada.
- OpenHands-SWE: o nº de arquivos JSON ≠ nº de passos (um tinha 112 arquivos para 49 passos: provavelmente re-tentativas/chamadas extras) e nem todo JSON tem `messages`; usar o de maior `messages`.
- Observações: OpenHands-SWE p50 920, **p90 9,2k, máx 30k**; SWE-agent máx 83k; Terminus2 máx 10k (corta em ~10k bytes).
- Terminus2: observação em `prompt.txt` contém ~30 linhas em branco de preenchimento do terminal.
- `.tar.zst` do OpenHands-TB contém **segredos locais** (`.jwt_secret`); nunca versionar `data/tmp/`.

---

## 5. Assinaturas de detecção automática (resumo)

| formato | assinatura (nesta ordem) |
|---|---|
| SWE-rebench/OpenHands-chat | lista de mensagens com `tool_calls[].function.arguments` (str JSON), `role` ∈ {system,user,assistant,tool}, ferramentas `execute_bash`/`str_replace_editor`/`finish`; ou coluna parquet `trajectory` |
| SWE-smith (nativo) | `messages` com `message_type` + `agent:"main"` + `tool_calls` (lista) e `tool_call_ids` |
| SWE-smith (xml) | `assistant.content` com `<function=NOME>` + `<parameter=…>`; observação em `role=user` começando com `OBSERVATION:` |
| SWE-smith (ticks) | `assistant.content` terminando em bloco ``` sem linguagem; observação em `role=user` com `OBSERVATION:` |
| SWE-agent `.traj` | JSON com `trajectory[]` (`action`,`observation`,`thought`,`response`) + `history` + `info.swe_agent_version` |
| mini-SWE-agent | JSON com `trajectory_format` que começa com `mini-swe-agent` + `messages`; ação em ```` ```bash ```` |
| OpenHands (log de LLM) | JSON com `messages`, `response.choices`, `kwargs.tools`, `cost` |
| OpenHands (eventos) | arquivos `events/N.json` com `id`, `source`, `action`/`observation`, `cause` |
| Terminus2 | diretório `agent-logs/episode-N/{prompt.txt,response.txt}` com JSON `{analysis,plan,commands[].keystrokes}` |

Nos uploads de um **único arquivo** (`.json`/`.jsonl`/`.parquet` de 1 linha/`.traj`): as 7 primeiras linhas acima bastam. Os formatos OpenHands-eventos e Terminus2 exigem o **`.tar.zst`/diretório** (vários arquivos).

---

## 6. Tabela comparativa

| | SWE-rebench | SWE-smith `tool` | `xml` | `ticks` | CTB · OpenHands-SWE | CTB · OpenHands-TB | CTB · SWE-agent | CTB · mini-SWE | CTB · Terminus2 |
|---|---|---|---|---|---|---|---|---|---|
| contêiner | Parquet 1 linha/traj | Parquet; `messages` str JSON | idem | idem | N JSONs (1/chamada LLM) | N JSONs (1/evento) | 1 `.traj` | 1 `.traj.json` | dir. de episódios |
| unidade do passo | `tool_call` | `tool_calls[0]` (ou xml, 62%) | bloco `<function>` | último bloco ``` | `tool_call` | evento `action` | `trajectory[i]` | msg `assistant` | episódio |
| pensamento | `content`/`think` | `thought` | texto antes | texto antes | `content`/`think` | `args.thought` | `thought` | `THOUGHT:` | `analysis`+`plan` |
| observação | `role=tool` (id) | `role=tool` (id) | `role=user` | `role=user` | `role=tool` | evento `cause` | `observation` | `user` seguinte | `prompt.txt` seguinte |
| exit code | no texto | não | não | não | no texto | `extras`/texto | não | `<returncode>` | não |
| multi-ação/msg | 1 em 130k | 0 | 0 | 0,4% (só o último) | possível | 1 | 1 | 1 | **vários** `keystrokes` |
| resolvido | `resolved` int | `resolved` bool | idem | idem | `solved` (manifest) | idem | idem | idem | idem |
| fim | `finish` | `submit` | `submit` | `submit` | `finish` | `finish` | `submit` | `COMPLETE_TASK…` | `task_complete` |

---

## 7. Mapeamento proposto para `Trajectory` / `Step` (CLAUDE.md)

| campo canônico | SWE-rebench | SWE-smith | CTB (por agente) |
|---|---|---|---|
| `id` | `trajectory_id` | `traj_id` | `traj_id` |
| `source_format` | `openhands_chat` | `sweagent_tool\|xml\|ticks` | `ctb_openhands_swe`, `ctb_openhands_events`, `ctb_sweagent`, `ctb_miniswe`, `ctb_terminus2` |
| `agent`, `model` | constantes (OpenHands, Qwen3-Coder) | `SWE-agent`, `model` | `agent`, `model` do manifest |
| `task_id`/`repo` | `instance_id`/`repo` | `instance_id` (repo = prefixo) | `task_name` |
| `problem_statement` | 1ª msg `user` | 1ª msg `user` | 1ª mensagem/`prompt.txt` do ep. 0 |
| `resolved` | `resolved` | `resolved` | `solved` (pode ser `null`) |
| `exit_status` | `exit_status` | derivado (última ação = submit?) | `info.exit_status` (SWE-agent, mini) |
| `patch` | `model_patch` | **ignorar** (`patch` não alinha) | `patch.diff` (OH-SWE) / `info.submission` |
| `ground_truth` | — | — | `stages`, `incorrect_stages` |
| `Step.thought/action/observation` | §1.3 | §2.3 | §4.3 |

**Campos que o modelo ainda não cobre → ajustes sugeridos ao `schema.py`:**
1. `Step.actions[]` (lista) **ou** `Step.sub_index`: Terminus2 tem N `keystrokes` por passo; OpenHands pode ter >1 call. Decisão: **1 passo por tool_call/bloco; Terminus2 = 1 passo por episódio** com `args.commands[]` (ver decisions.md).
2. `Step.thought_source`: `content` vs ferramenta `think` (para não duplicar `think` como passo).
3. `Observation.exit_code` opcional + `truncated: bool`.
4. `Trajectory.resolved: bool | None` (CTB tem nulos) e `exit_status` livre (string longa no SWE-rebench).
5. `Trajectory.ground_truth.stages[]` com `step_ref` por agente (`kind`: `index` | `assistant_rank` | `episode` | `event_id`), porque o `step_id` não tem semântica única (§4.5).
6. `Step.native_id` (id da mensagem/evento/episódio original) para ligar anotações.
7. `Trajectory.meta` livre (dificuldade, categoria, `source_origin`).
8. `files[]`: derivável de `args.path` (editor) e do comando bash; não vem pronto em nenhum formato.

---

## 8. Ferramentas (união dos datasets, amostras)

| ferramenta (nome nativo) | onde | categoria sugerida |
|---|---|---|
| `execute_bash` / `bash` / `run` / `keystrokes` / ação bash do SWE-agent | todos | **depende do comando** (§9) |
| `str_replace_editor view` | rebench, smith, OH-SWE, SWE-agent | `read` (arquivo) / `explore` (diretório) |
| `str_replace_editor create` / `str_replace` / `insert` / `undo_edit` | idem | `edit` |
| `think` | rebench, OH | `think` |
| `task_tracker` | rebench, OH-SWE | `think` (planejamento) — **ambíguo** (`other`?) |
| `finish` / `submit` / `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` / `task_complete` | todos | `submit` |
| OpenHands-TB `read` / `edit` / `run_ipython` | CTB | `read` / `edit` / `reproduce` (ambíguo) |
| OpenHands-TB `message` (agente fala sem agir) | CTB | `think` |
| SWE-agent legado: `open`, `scroll_down/up`, `goto`, `search_file`, `search_dir`, `find_file`, `edit N:M … end_of_edit`, `create` | CTB-SWE-agent | `read`, `read`, `read`, `search`, `search`, `search`, `edit`, `edit` |
| tecla `C-c` (`is_input`/`keystrokes`) | rebench, Terminus2 | `other` |

## 9. 60 executáveis bash mais frequentes (união)

Contagem do 1º executável de cada segmento (`;`, `&&`, `||`, `|`, quebra de linha, respeitando aspas, `$( )` e heredocs; `cd`/`export`/`echo` isolados descartados quando há outro comando; prefixos `sudo/env/timeout/VAR=x` ignorados). Fontes somadas: SWE-rebench (2.040 traj.), SWE-smith (6.100 + 8.000 + 7.826) e CTB (60). Lixo de parsing (corpo de heredoc, prosa) filtrado por regex+lista de ruído.

| # | executável | ocorrências | categoria sugerida | observação |
|---|---|---:|---|---|
| 1 | `python` | 205.355 | reproduce / test / edit | **ambíguo**: `python x.py`=reproduce. `python -m pytest`=test. `python -c`/heredoc que escreve arquivo=edit; olhar argumentos |
| 2 | `grep` | 94.280 | search |  |
| 3 | `find` | 31.254 | search / explore | `find -name`=search; `find .`/`-type d` sem filtro=explore; `find … -delete`/`-exec rm`=edit/other |
| 4 | `rm` | 17.998 | other | limpeza de scripts de reprodução; ambíguo (edit?) |
| 5 | `sort` | 12.704 | other | quase sempre fim de pipe (`find ∣ sort`): herda a categoria do 1º comando do pipe |
| 6 | `head` | 11.778 | read | fim de pipe herda o 1º comando; sozinho (`head -n 50 f`)=read |
| 7 | `pip` | 6.453 | setup | `pip install`=setup; `pip show/list`=explore |
| 8 | `xargs` | 5.034 | other | herda do comando que recebe (`xargs grep`=search) |
| 9 | `git` | 4.637 | vcs | `git diff/status/log/stash/checkout`=vcs; `git apply`/`git checkout -- f` revertendo=edit (ambíguo) |
| 10 | `python3` | 3.821 | reproduce / test | **ambíguo** (igual a `python`) |
| 11 | `ls` | 1.907 | explore |  |
| 12 | `cat` | 1.675 | read | `cat > f <<EOF`=edit |
| 13 | `chmod` | 1.186 | setup |  |
| 14 | `sed` | 815 | read / edit | **ambíguo**: `sed -n`=read. `sed -i`=edit |
| 15 | `pytest` | 748 | test |  |
| 16 | `pwd` | 666 | explore |  |
| 17 | `mkdir` | 658 | setup | ou edit (cria estrutura) |
| 18 | `tail` | 532 | read | fim de pipe herda; `tail -f` log=read |
| 19 | `curl` | 525 | setup / other | download=setup; `curl localhost`=test (ambíguo) |
| 20 | `cp` | 511 | edit / setup | ambíguo |
| 21 | `sleep` | 503 | setup | espera; `other` |
| 22 | `apt-get` | 492 | setup |  |
| 23 | `conan` | 426 | setup / test | depende do subcomando (install=setup. test=test) |
| 24 | `dvc` | 415 | other | ferramenta do repo-alvo; ambíguo |
| 25 | `C-c` | 280 | other | tecla (interrompe processo). não é executável |
| 26 | `kill` | 274 | other |  |
| 27 | `conda` | 267 | setup |  |
| 28 | `wc` | 234 | read |  |
| 29 | `mv` | 219 | edit / setup | ambíguo |
| 30 | `pkill` | 189 | other |  |
| 31 | `mypy` | 163 | test | linter/typecheck do repo-alvo |
| 32 | `make` | 145 | test / setup | **ambíguo**: `make test`=test. `make`/`make install`=setup |
| 33 | `sqlfluff` | 123 | test | linter do repo-alvo (reproduce?) |
| 34 | `which` | 99 | explore |  |
| 35 | `yamllint` | 86 | test | ambíguo |
| 36 | `cd` | 84 | setup | `cd` sozinho; em `cd x && cmd` classifique `cmd` |
| 37 | `echo` | 84 | other | `echo > f`=edit |
| 38 | `moto_server` | 84 | setup | repo-alvo |
| 39 | `nl` | 83 | read |  |
| 40 | `pylint` | 66 | test | linter |
| 41 | `ps` | 63 | explore |  |
| 42 | `printf` | 54 | other | `printf > f`=edit |
| 43 | `awk` | 53 | read / edit | ambíguo |
| 44 | `diff` | 48 | vcs / read | ambíguo |
| 45 | `touch` | 47 | edit / setup | ambíguo |
| 46 | `hexdump` | 47 | read |  |
| 47 | `unzip` | 44 | setup |  |
| 48 | `planet` | 42 | other | CLI do repo-alvo (reproduce?) |
| 49 | `cantools` | 35 | other | CLI do repo-alvo |
| 50 | `./reproduce.sh` | 33 | reproduce | padrão `reproduce*` |
| 51 | `node` | 33 | reproduce / test | ambíguo |
| 52 | `flask` | 30 | other | CLI do repo-alvo |
| 53 | `./runtests.sh` | 28 | test |  |
| 54 | `streamlink` | 26 | other | CLI do repo-alvo |
| 55 | `hy` | 25 | other | CLI do repo-alvo |
| 56 | `patch` | 25 | edit |  |
| 57 | `meson` | 21 | setup | build |
| 58 | `nosetests` | 20 | test |  |
| 59 | `poetry` | 20 | setup |  |
| 60 | `flake8` | 19 | test | linter |

**Regras práticas para o `bash_parser`** (derivadas da tabela):
- Classificar **o último comando útil do `&&`** (`cd x && pytest` → `test`), e para pipes usar o **1º comando** (`find … | sort | head` → `search`); `sort`/`head`/`xargs`/`tail` no fim herdam.
- `python`/`python3` (≈ 4,6 em cada 10 comandos) **exigem olhar os argumentos**: `-m pytest|unittest` → test; `-c`/heredoc → reproduce (ou edit se escreve arquivo); `script.py` criado pelo agente → reproduce; `pip install` → setup.
- `sed -n` = read; `sed -i` = edit; `cat > f`/heredoc/`tee`/`>` = edit; `git diff|status|log|stash|checkout` = vcs; `git apply` = edit.
- `rm`/`mkdir`/`chmod`/`touch` de arquivos de reprodução (`reproduce*`, `test_*`) aparecem muito (`rm` é o 4º): `other` ou `setup`, nunca `edit` do código-alvo.
- Comandos específicos do repo-alvo (`conan`, `dvc`, `sqlfluff`, `planet`, …) são cauda longa: 221 executáveis distintos nesta amostra → regra por padrão (`test|check|lint`) e LLM.

## 10. Números-chave para o pôster

| | SWE-rebench | SWE-smith | CodeTraceBench |
|---|---|---|---|
| trajetórias | **67.074** | **76.002** (24.100 + 26.076 + 25.826) | **3.316** únicas (`verified` 1.000 ⊂ `full`) |
| agentes | OpenHands | SWE-agent | OpenHands, mini-SWE-agent, Terminus2, SWE-agent |
| modelos | Qwen3-Coder-480B | Claude 3.7 (72%), Claude 3.5 (26%), GPT-4o (2%) | `verified`: GPT-5, Claude Sonnet 4, DeepSeek-V3.2 (`full`: +Kimi-K2, Qwen3-Coder, DeepSeekChat) |
| passos/traj. (média · p50 · p90 · máx) | 64 · 61 · 94 · 100 | tool 30,8 · 26 · 59 · 151 / xml 30,1 · 25 · 58 · 140 / ticks 31,5 · 26 · 60 · 140 | `verified` 46,5 · 37 · 77 · 327 (`full`: 44,5 · 30 · 85 · 666) |
| taxa de sucesso | 48,5% (`resolved`) | 39% / 43% / 44% (não validada) | `verified` 50,4% (504/1.000; 28 nulos); `full` 39,4% (1.307/3.316; 106 nulos) |
| origem | SWE-bench-like (repos Python) | bugs sintéticos em repos Python | 646 SWE-bench + 2.670 TerminalBench (`full`) |
| obs. p50 / p90 / máx (chars) | 889 / 5.715 / 30.047 | ~850 / ~5.5k / ~100k | 300–1.500 / 2,4k–10k / 83k |
| fim por `submit`/`finish` | 91,8% | 91–99% | — |
| anotação humana | — | — | passos incorretos/inúteis por estágio (405/1.000 `verified` com ≥1) |

*Amostras*: SWE-rebench 2.040 linhas (120 primeiras de cada um dos 17 row groups); SWE-smith ~250 primeiras linhas de cada um dos 8 arquivos/split; CTB: manifests completos + 60 artefatos. As médias podem estar levemente enviesadas pela ordem dos arquivos.
