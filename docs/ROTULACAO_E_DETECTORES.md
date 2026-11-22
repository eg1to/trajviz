# Rotulação e detectores

Como cada passo recebe uma categoria (rotulação em camadas) e como os detectores marcam problemas. Este documento é o "lar" das **definições**; os **resultados** (acurácia, comparação com o gabarito, auditorias) estão em [AVALIACAO.md](AVALIACAO.md) e o histórico linha a linha das decisões em [decisions.md](decisions.md#rotulação). Termos no [glossário](GLOSSARIO.md).

## 1. Taxonomia

11 categorias fixas em 4 fases (`backend/app/labeling/taxonomy.py`). A taxonomia descreve **o que a ferramenta ou o comando faz**, não a intenção do agente (diferença central em relação ao TraceView; ver [taxonomia_mapeamento.md](taxonomia_mapeamento.md)).

| fase | categoria (rótulo na interface) | definição | exemplos |
|---|---|---|---|
| Entendimento | `explore` (Explorar) | Listar/navegar a estrutura do repositório ou do ambiente, sem filtrar por conteúdo. | `ls -la /testbed`; `view` de um diretório; `list_files` do Ark |
| Entendimento | `search` (Buscar) | Procurar texto ou nome de arquivo no código. | `grep -rn 'def foo' src/`; `find . -name '*.py'`; `find_text` do Ark |
| Entendimento | `read` (Ler) | Ler um arquivo ou trecho. | `cat setup.py`; `sed -n '10,40p' a.py`; `view` de arquivo; `read_file` |
| Modificação | `edit` (Editar) | Modificar ou criar arquivos (código, configuração, scripts). | `str_replace`; `sed -i`; `cat > f <<EOF`; `edit_file` |
| Verificação | `reproduce` (Reproduzir) | Executar código para reproduzir o problema ou observar um comportamento. | `python reproduce_issue.py`; `python -c '…'` |
| Verificação | `test` (Testar) | Rodar testes, linters ou checagens do projeto. | `pytest tests/test_a.py -x`; `make test`; `flake8 src`; `run_tests` |
| Verificação | `vcs` (Versionar) | Usar o controle de versão para inspecionar mudanças. | `git diff`; `git status`; `git log -3` |
| Controle | `setup` (Preparar) | Preparar o ambiente: dependências, build, variáveis, arquivos de apoio. | `pip install -e .`; `mkdir -p /tmp/x`; `export A=1` |
| Controle | `think` (Pensar) | Raciocinar, planejar ou comentar sem agir. | ferramenta `think`; mensagem sem ação; `task_tracker` |
| Controle | `submit` (Entregar) | Encerrar a tarefa entregando a solução. | `finish`; `submit` |
| Controle | `other` (Outro) | Nada acima se aplica (inclui teclas de controle). | `C-c`; `sleep 5` |

O plano original tinha 10 categorias; `other` existia como resto e entrou formalmente na taxonomia ([PLAN.md](PLAN.md)).

## 2. Rotulação em camadas

```
passo ─► camada 1: nome da ferramenta ──(exato)──► rótulo final (confiança 1,0)
            │ shell / ipython / teclas
            ▼
         camada 2: comando de shell (bash_parser) ──(confiança ≥ 0,6)──► rule
            │ confiança < 0,6
            ▼
         fallback (melhor palpite da regra) ──(se use_llm e LLM habilitado)──► camada 3: LLM ──► llm
```

### Camada 1 — ferramenta (`labeling/rules.py`)

- `editor` `view`/`read` → `read` (ou `explore` se o alvo é um diretório); `create`/`str_replace`/`insert`/`undo_edit`/… → `edit`.
- Comandos legados do SWE-agent (`swe_cmd`): `open`/`goto`/`scroll_*` → `read`; `search_file`/`search_dir`/`find_file` → `search`; `edit`/`create`/`insert` → `edit`.
- `think`, `message` → `think`; `task_tracker` → `think/plan`; `submit` (`finish`, `submit`, `task_complete`) → `submit`.
- **Ark** (por `tool_native`): `list_files` → `explore`, `read_file` → `read`, `find_text` → `search`, `run_tests` → `test`, `edit_file` → `edit` (subcategoria `edit_rejected` quando o usuário recusou), `finish` → `submit`.
- **Sessão do Claude Code**: o adaptador traduz as ferramentas para os nomes acima (Read → `editor/view`, Grep → `swe_cmd/search_dir`…), sem regra nova.

### Camada 2 — comando de shell (`labeling/bash_parser.py`)

- Análise com **bashlex**, com fallback para `shlex`/regex quando o comando não é analisável. Cada segmento (`&&`, `;`, `|`) é classificado; prefixos como `cd x &&`, `timeout`, `env` são ignorados.
- **Precedência** entre segmentos: `edit > test > reproduce > search > read > explore > vcs > setup > other`. `cd`/`export`/`source` e palavras de controle (`for`, `do`, `fi`) só valem se forem o único segmento. Em pipes o 1º comando define, mas `> f`/`tee f` em qualquer estágio vira `edit`. Todos os segmentos ficam na subcategoria (ex.: `grep|sed -n`).
- **Regras de `python`** (≈ 46% dos comandos; `classify_python`):
  - `-m pytest|unittest|nose|mypy|flake8|pylint` → `test`; `-m pip`, `setup.py install|develop` → `setup`;
  - `-c` ou heredoc → `reproduce`;
  - script que **escreve arquivo**: se o alvo é script de reprodução (`reproduce*`, `debug*`, `check*`, `verify*`, `/tmp/`, ou criado pelo agente com nome de teste/debug) → `reproduce`, senão `edit`;
  - `script.py` criado antes pelo próprio agente → `reproduce`, mesmo com nome `test_*`; se já existia no repositório → `test`. O contexto `Ctx.created` acompanha os arquivos criados ao longo da trajetória.
- **Teclas** (`C-c`, `is_input=true`, keystrokes só de controle) → `other/keys`, confiança 1,0, nunca vão ao LLM.
- **Protocolo do harness** (`<PATCH_CONTEXT>`, `<context_received>`, submit recusado por "STOP! BEFORE SUBMITTING") → `submit/harness_protocol`, confiança 1,0.
- **Passos `message`** (agente fala sem agir) → `think`.
- `keys`, `harness_protocol` e `message` aparecem à parte no dashboard e **não** entram nas contagens por categoria e fase (uma trajetória do CodeTraceBench tinha 445 mensagens seguidas).

### `label_source` e confiança

`rule` = regra exata ou confiança ≥ 0,6; `fallback` = confiança < 0,6, com o melhor palpite da regra preservado (não vira `other`); `llm` = o LLM respondeu; `user` = corrigido na interface (`PATCH`).

### Camada 3 — fallback com Haiku 5.5 (`labeling/llm.py`)

- Só para passos `fallback`, só se `LABEL_LLM_ENABLED=1` + `ANTHROPIC_API_KEY` e só quando o upload pede `use_llm=true` (a biblioteca abre sempre só com regras).
- Modelo `claude-haiku-5-5` (US$ 0,10 / 0,50 por milhão de tokens de entrada/saída, `llm.py:25`).
- **Lote:** uma requisição por trajetória, dividida em lotes de até 80 mil tokens estimados (`MAX_BATCH_TOKENS`, abaixo do limite de 100 mil a partir do qual o preço sobe).
- **Prompt caching:** a taxonomia (com descrições e exemplos) vai no system prompt com `cache_control`.
- **Saída estruturada** por tool use (`label_steps`), validada com Pydantic; categoria inválida vira `other`.
- **Cache local** por hash (modelo + versão do prompt + passo): nunca se paga duas vezes pelo mesmo passo.
- **Trava de orçamento** `LLM_BUDGET_USD` (padrão 0,50 por execução): para quando o gasto acumulado atinge o orçamento ou quando a próxima requisição estimada o ultrapassaria; os passos restantes ficam `fallback`.
- **Contador** de tokens e custo em `backend/.cache/llm_usage.json`.
- **Custo real:** US$ 0,0320 em 201 requisições no projeto inteiro (`backend/.cache/llm_usage.json`, consultado em 21/11/2026), contra um orçamento de US$ 4,91. Desse total, US$ 0,0209 foram gastos até a avaliação do gold de desenvolvimento ([results/eval_classifier.md](../results/eval_classifier.md), linha 11); os US$ 0,011 restantes vieram do LLM rodando nos 90 passos do gold held-out, no teste do `evaluate.py --tag` ([decisions.md](decisions.md#avaliação), linha de 20/11 sobre o `--tag`; o cache será reaproveitado quando o held-out for rotulado).

### Cobertura das regras

Nas amostras da biblioteca, 97,4% dos passos do CodeTraceBench e 99,8% do SWE-rebench e do SWE-smith ficam com `label_source = rule` ([results/labeling_report.md](../results/labeling_report.md), linhas 11, 16 e 18); `other` (sem teclas) fica entre 0,0% e 1,6%, abaixo da meta de 15% da Fase 3. Cobertura não é acerto: a acurácia está em [AVALIACAO.md](AVALIACAO.md#2-acurácia-da-rotulação-gold-manual).

## 3. Detectores (`backend/app/analysis/detectors.py`)

Cada detector só acrescenta flags e um motivo curto (`flag_details`); `run_detectors` zera as flags antes, então é determinístico e idempotente. Passos `keys` e `harness_protocol` são ignorados. Ordem: `error` → `test_fail`/`test_pass` → `detect_ark` → `repeated` → `no_new_info` → `loop` → `truncated`.

### `error` — o comando falhou

- **Com exit code:** ≠ 0 é erro, **exceto** exit 1 de `grep`/`egrep`/`rg`/`ag`/`diff`/`cmp`/`test`/`[`/`pgrep` (sem correspondência ou diferença não é falha; decidido pelo executável que define o exit code), exit −1 do OpenHands (processo ainda rodando) e passos `test` (exit ≠ 0 em teste é `test_fail`; só 126/127 ou "command not found" viram `error`). No pytest, exit 2/3/4 e outros = `error` (a execução falhou, não o teste).
- **Sem exit code:** padrões de texto (`Traceback`, `command not found`, `No such file or directory`, `SyntaxError`, `error:`, `fatal:`…). Em passos `read`/`search`/`explore`/`vcs` só vale um erro no estilo `ferramenta: …` na 1ª linha, porque a saída é conteúdo de arquivo que pode citar `Traceback`. Editor: `No replacement was performed`, `did not appear verbatim`, `Multiple occurrences`, `Invalid …`, caminho inexistente.
- **Ark:** vem do resultado registrado (`detect_ark`): edição `failed` e `finish` recusado (`finish_validation`) → `error`; edição recusada pelo usuário não é erro.

### `test_fail` / `test_pass` — resultado de teste

- **pytest segue seus códigos de saída:** 1 = `test_fail`; 0 = `test_pass`; 5 (nada coletado) = sem flag; 2, 3, 4 e outros = `error`. Sem exit code: "Interrupted"/erro de uso → `error`; "no tests ran"/"collected 0 items" → sem flag; "N failed", `FAILED`, linhas `E …` → `test_fail`; "N passed", `OK` → `test_pass`.
- **`pytest … | cmd`:** com o pytest num pipe (fora de aspas e de `2>&1`), o exit code observado é o do último comando, então o veredito vem do texto da saída.
- unittest, tox, make e demais executores: exit ≠ 0 = `test_fail`.
- **Ark:** `[tests] failed` e `finish/post_apply_tests` → `test_fail`; `[tests] passed` e `finish completed` → `test_pass`.
- **Histórico:** a auditoria da rodada 1 mostrou que 9 de 10 casos duvidosos eram exit 2/4/5 do pytest tratados como teste falhando; a regra passou a seguir os códigos do pytest (19/11) e depois a tratar o pipe (20/11). Efeitos em [AVALIACAO.md](AVALIACAO.md#4-auditorias-manuais-dos-detectores).

### `repeated` — ação idêntica a uma anterior

- Chave da ação normalizada: espaços, prefixos `/workspace/<repo>/`, `/testbed/`, `/app/`, `cd x &&`, `view_range`, hash de `old_str`/`new_str`/`file_text`.
- Uma ação que observa ou executa repetida **depois de uma edição** não conta (o estado mudou; rodar o mesmo teste após editar é esperado). Edições idênticas contam sempre.
- **Ark:** a ação de `edit_file` só traz o caminho, então a chave inclui o hash do diff; edição que falhou (sem diff, conteúdo desconhecido) nunca é "repetida".

### `no_new_info` — leitura, busca ou exploração sem informação nova

- (a) Observação normalizada idêntica (≥ 20 caracteres, fora de "sem saída") a uma anterior de `read`/`search`/`explore`; (b) releitura de um trecho **já coberto** por uma leitura anterior do mesmo arquivo sem edição nesse arquivo desde então.
- Cobertura exige intervalo legível (`view_range` em lista ou texto, `sed -n a,bp`), intervalo contido no já lido, e uma leitura inteira só cobre se não foi abreviada (`<NOTE>This file is too large…` do SWE-agent) nem truncada; observações de erro não contam. Edições, inclusive via shell, invalidam as leituras anteriores do arquivo.
- **Não se aplica ao Ark** (a saída das leituras não é registrada).
- **Histórico:** a 1ª regra tinha **80% de falsos positivos** no SWE-smith (16 de 20 auditados: tratava leitura abreviada como cobertura total e `view_range` em texto como arquivo inteiro). Depois da correção: 0 de 20 numa nova amostra e a taxa de marcação caiu de 12,6% para 2,8% dos passos ([results/audit_no_new_info.md](../results/audit_no_new_info.md), linhas 3–15).

### `loop` — ciclo repetido

- (1) n-grama (n = 2 a 4) de **ações normalizadas idênticas** (ferramenta + comando + arquivo + intervalo + trecho editado) repetido ≥ 3 vezes seguidas; ou (2) ciclo `edit` → `test_fail` no mesmo arquivo ≥ 3 vezes **com a mesma assinatura de erro** (ids `FAILED t::x` do pytest, `FAIL: test (mod.Class)` do unittest, linhas `E …`, ou o fim da saída sem números).
- Passos sem alvo (`think`, `task_tracker`, `message`, `submit`, teclas, harness) ficam fora; edições em trechos diferentes e leituras de intervalos diferentes do mesmo arquivo não contam. Os intervalos ficam em `meta.loops`.
- **Histórico:** (19/11) passos `message` saíram da janela (loop no CodeTraceBench: 20,8% → 3,8% dos passos, commit `1cd6717`); depois a auditoria apontou 7 de 20 falsos positivos (edição em lote, leituras de intervalos diferentes) e o detector passou a exigir o mesmo alvo. **É conservador de propósito:** ficou preciso na auditoria (20/20), mas marca só 48 passos nas 976 trajetórias do CodeTraceBench e a revocação contra o gabarito caiu para 0,4%.

### `truncated` — observação cortada pela ferramenta

Marcadores conhecidos (`<response clipped>`, `<NOTE>This file is too large`, `Output too long`, `[Observation truncated`, `(truncated)`…), unificados no adaptador em `Observation.truncated`.

### O que os detectores não são

Os detectores são **sintáticos**: "comando falhou", "leitura repetida", "mesma ação três vezes". Eles não julgam se um passo foi **inútil** ou **incorreto** no sentido do gabarito do CodeTraceBench, e a comparação com esse gabarito mostra exatamente isso ([AVALIACAO.md](AVALIACAO.md#3-detectores--gabarito-do-codetracebench)). Detectores semânticos ficam para o TCC II ([LIMITACOES_E_TRABALHOS_FUTUROS.md](LIMITACOES_E_TRABALHOS_FUTUROS.md)).
