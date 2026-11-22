# Dados

Quais dados o trajviz usa, para quê, como obtê-los e o que se descobriu sobre eles. Os **formatos** (campos, exemplos, assinaturas de detecção) estão em [formats.md](formats.md); este documento não os repete.

## 1. Datasets públicos

| dataset | papel no projeto | agente · modelo | volume | licença (card do dataset) | local |
|---|---|---|---|---|---|
| [nebius/SWE-rebench-openhands-trajectories](https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories) | Base principal; resolvidas × não resolvidas | OpenHands v0.54 · Qwen3-Coder-480B | 67.074 trajetórias, 1 Parquet (~2,1 GB) | CC-BY-4.0 | `data/raw/swe-rebench/` |
| [SWE-bench/SWE-smith-trajectories](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories) | Segundo formato (3 variantes de ação) | SWE-agent · Claude 3.7 (72%), Claude 3.5 (26%), GPT-4o (2%) | 76.002 linhas: `tool` 24.100, `xml` 26.076, `ticks` 25.826 (~3 GB sem `train-*`) | MIT | `data/raw/swe-smith/` |
| [NJU-LINK/CodeTraceBench](https://huggingface.co/datasets/NJU-LINK/CodeTraceBench) | Gabarito dos detectores; 5 formatos brutos | OpenHands, mini-SWE-agent, Terminus2, SWE-agent | **3.316 trajetórias únicas** (`verified` 1.000 ⊂ `full` 3.316); 992 artefatos do `verified` baixados | MIT | `data/raw/codetracebench/` |

Fontes: volumes em [formats.md](formats.md) (§0, §1, §10) e [PLAN.md](PLAN.md) §2; licenças lidas do cabeçalho `license:` do `README.md` de cada dataset em `data/raw/`. Nada de `data/raw/` vai para o git.

### Como baixar

O comando exato usado na Fase 0 não ficou registrado; os comandos abaixo reproduzem o mesmo conteúdo de `data/raw/` com a CLI do Hugging Face (`pip install -U huggingface_hub`):

```bash
hf download nebius/SWE-rebench-openhands-trajectories --repo-type dataset --local-dir data/raw/swe-rebench
hf download SWE-bench/SWE-smith-trajectories --repo-type dataset --local-dir data/raw/swe-smith \
    --include "README.md" "data/tool-*" "data/xml-*" "data/ticks-*"          # sem os arquivos train-*
hf download NJU-LINK/CodeTraceBench --repo-type dataset --local-dir data/raw/codetracebench \
    --include "README.md" "bench_manifest*"                                    # só os manifests (~190 MB)
python backend/scripts/download_ctb_artifacts.py --sample 60                   # ou --all (992 do verified)
```

**Rate limit do CodeTraceBench.** Baixar o repositório inteiro estourou o HTTP 429: só `swe_raw/` tem ~17 mil arquivos. Por isso só os manifests vêm pelo `hf download`, e os artefatos (`bench_artifacts/full/<traj_id>.tar.zst`) vêm por `backend/scripts/download_ctb_artifacts.py`: um arquivo por vez, ~1 s entre downloads, backoff exponencial (60 s, 120 s…) em 429, retomável (pula os que já existem com o tamanho certo) e com log em `data/raw/codetracebench/_download_log.jsonl`. `--sample 60` faz uma amostra estratificada por agente × origem; `--all` baixa os 1.000 do `verified` (992 existem; 8 não têm artefato).

**Regra de memória:** nunca carregar um dataset inteiro. Parquet é lido com `pyarrow` em lotes (`iter_batches`), sem a coluna `tools` do SWE-rebench (repetida em toda linha).

## 2. Amostras

| pasta | conteúdo | no git? | gerada por |
|---|---|---|---|
| `data/samples/swe-rebench/` | 50 trajetórias (25 resolvidas, 25 não) | não (`*.json` ignorado) | `explore_dataset.py swe-rebench` |
| `data/samples/swe-smith/{tool,xml,ticks}/` | 20 por split, metade resolvidas | não | `explore_dataset.py swe-smith` |
| `data/samples/codetracebench/` | ids de 60 artefatos do `verified` (58 com trajetória estruturada) | não | `explore_dataset.py codetracebench` |
| `data/samples/ark/` | 15 traces reais do Ark (v2) + `.meta.json` | **sim** (os `.log`; os `.meta.json` são ignorados) | cópia de `data/inbox/ark/` |
| `data/holdout/` | trajetórias SWE do gold held-out | não | `make_gold_sample.py --holdout` |
| `data/inbox/ark/` | traces brutos do Ark (v2 e `v1_falhas_adaptador/`), com `README.md` por pasta | não (pasta não versionada) | `run_batch.py` do Ark |

A biblioteca da interface lista 185 amostras: SWE-rebench 50, SWE-smith 60, CodeTraceBench 60 e Ark 15 (`GET /api/library`, verificado em 21/11/2026). Sem `data/samples/` a biblioteca fica vazia, mas o upload funciona.

## 3. O que se descobriu sobre os dados

Cada achado muda como o dataset deve ser usado. Lista completa, com números, em [results/poster/achados_metodologicos.md](../results/poster/achados_metodologicos.md); detalhes técnicos em [formats.md §0](formats.md) e §4.

1. **O split `tool` do SWE-smith mistura dois formatos de ação** (~38% `tool_calls` nativo, ~62% o texto `<function=…>` do split `xml`): a detecção é por mensagem, não pelo nome do split.
2. **O `patch` do SWE-smith não corresponde à trajetória** (em ~83% das linhas não vazias nenhum arquivo do patch aparece na trajetória; 26–30% são vazios): o `patch` é ignorado e o `resolved` tratado como **não validado** em toda tabela, figura e selo.
3. **CodeTraceBench: 3.316 trajetórias únicas, não 4.316.** O README do dataset soma o `verified` (1.000) ao `full` (3.316), mas 1.000 de 1.000 `traj_id` do `verified` estão no `full`.
4. **O `step_id` do gabarito tem unidade diferente por agente** (índice em `trajectory[]`, n-ésima mensagem do assistente, k-ésimo evento `run`, comando dentro de episódio…); 34% dos passos anotados só se alinham por hipótese ([formats.md §4.5](formats.md)).
5. **Parte do gabarito mede o protocolo do harness:** no SWE-agent/mini-SWE, o submit recusado por "STOP! BEFORE SUBMITTING" (`<PATCH_CONTEXT>`) aparece como passo incorreto/inútil; o pipeline o marca como `submit/harness_protocol`.
6. Observações são cortadas em tamanhos diferentes por ferramenta (~10 mil a ~100 mil caracteres) e com marcadores diferentes; `Observation.truncated` unifica o que é detectável.
7. O exit code do OpenHands vem no texto (`[The command completed with exit code N.]`); SWE-smith, SWE-agent e Terminus2 não trazem exit code.

## 4. Traces do Ark

O Ark é o agente de código do orientador (<https://github.com/mtov/ark>, licença MIT; cópia local em `~/tcc/ark`). O formato do trace e como ele vira o modelo canônico TAR estão em [formats.md §11](formats.md).

**Como foram gerados.** Com `scripts/run_batch.py` do Ark (commit `de06556` no repositório do Ark), que roda o Ark em 6 tarefas de exemplo (`bugfix_001_date_range`, `bugfix_002_order_totals`, `feature_001_buy2get50`, `refactor_001_rename`, `refactor_002_remove_duplication`, `simple_greeting`) e copia cada `agent_trace.log` para `data/inbox/ark/` com um `.meta.json` (tarefa, modelo, modo, `max_iterations`, `run_summary`, custo estimado). Modos: `auto` (aprova todas as edições) e `reject-first` (recusa a 1ª edição, depois aprova); um run com `max_iterations = 4` para produzir `max_iterations_reached`.

**Sanitização.** O caminho da pasta pessoal é trocado por `~` na cópia (`run_batch.py`, `log.replace(str(Path.home()), "~")`); o `.meta.json` registra `"sanitized": true`.

**v1 × v2.**
- **v1** (`data/inbox/ark/v1_falhas_adaptador/`, 26 logs): gerados antes da correção do adaptador da Anthropic no Ark. Muitos runs falham com `EmptyModelResponseError` (resposta sem bloco de texto), `ValueError` de protocolo, `validation_error`/`repair_attempt` e `rollback`. Servem de **fixtures e teste de integração**, não entram na biblioteca. (O `README.md` da pasta tabela 23 desses logs; a pasta tem 26.)
- **Correção do adaptador** (commit `9d8b60a` do Ark, "adaptação Anthropic: thinking opcional e tratamento de respostas vazias"): torna o thinking opcional e trata respostas vazias com o motivo real da API.
- **v2** (`data/inbox/ark/`, 15 logs): Haiku 5.5, comportamento real; 14 `success` e 1 `max_iterations_reached`. Custo estimado: US$ 0,0454 no total (assumindo 85% dos tokens como entrada; `data/inbox/ark/README.md`).

**Recusa do Sonnet 5.5.** O Sonnet 5.5 não entrou no v2: a API recusou as requisições do Ark (`stop_reason: refusal`, categoria `reasoning_extraction`, mensagem sobre os termos de uso que restringem engenharia reversa ou duplicação de saídas do modelo), mesmo com o thinking desligado. Em 5 das 6 tarefas o Sonnet foi recusado; só `simple_greeting` passou. Nenhum prompt foi alterado para contornar a recusa. Os runs recusados antes da 1ª resposta têm 0 passos: o adaptador os abre, mas o pipeline responde 422 `empty_trajectory`.

**Limitação de fundo:** o trace do Ark **não registra a saída** de `read_file`, `list_files`, `find_text` nem de testes que passaram. Ver [formats.md §11](formats.md) e [LIMITACOES_E_TRABALHOS_FUTUROS.md](LIMITACOES_E_TRABALHOS_FUTUROS.md).

## 5. Dados que não foram incluídos

- **Sessões reais do Claude Code:** o adaptador `claude_code_session` foi testado em 3 sessões reais deste projeto (31, 285 e 92 passos; `other` entre 0% e 2%), mas nenhum log real foi incluído no repositório nem na biblioteca, porque contém caminhos pessoais e conteúdo de trabalho. A fixture de teste é sintética ([decisions.md](decisions.md#dados-e-formatos), 20/11).
- **TraceView:** usado como clonado (`../traceview`), sem copiar dados para este repositório; as capturas da comparação estão em `results/screenshots/comparacao/`.
