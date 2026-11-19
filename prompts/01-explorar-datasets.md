# Fase 1 — Explorar e entender os formatos dos datasets

> Cole este prompt no Claude Code, na raiz do repositório. Peça para ele **planejar antes de executar**.

---

Leia `CLAUDE.md` e `docs/PLAN.md` antes de começar. Estamos na **Fase 1**: entender a fundo o formato dos três
datasets de trajetórias de agentes que estão em `data/raw/`. **Não implemente adaptadores, schema nem
rotulação ainda.** O objetivo é produzir documentação e amostras confiáveis para as próximas fases.

Os dados baixados estão em:
- `data/raw/swe-rebench/` — nebius/SWE-rebench-openhands-trajectories (OpenHands + Qwen3-Coder, Parquet, ~67 mil linhas)
- `data/raw/swe-smith/` — SWE-bench/SWE-smith-trajectories (SWE-agent + Claude 3.7, Parquet, splits `tool`, `xml`, `ticks`)
- `data/raw/codetracebench/` — NJU-LINK/CodeTraceBench (manifests Parquet/JSONL + `bench_artifacts/full/*.tar.zst`, splits `verified` e `full`)

Primeiro, liste o que existe em cada pasta (arquivos, tamanhos, extensões) e me diga se falta algo antes de seguir.

## Restrições
- Nunca carregue um arquivo Parquet inteiro na memória: use `pyarrow.parquet.ParquetFile(...).iter_batches()`.
- Para o CodeTraceBench, extraia **apenas** os `.tar.zst` das trajetórias amostradas, em `data/tmp/` (use `zstandard` + `tarfile`).
- Use `uv` em `backend/` para dependências (`pyarrow`, `pandas`, `zstandard`, `orjson`, `rich`). Se `backend/pyproject.toml` não existir, crie um mínimo.
- Scripts em `backend/scripts/`. Nada de notebooks.

## Tarefas

### 1. Script de exploração
Crie `backend/scripts/explore_dataset.py` com uma subcomando por dataset
(`uv run python scripts/explore_dataset.py swe-rebench|swe-smith|codetracebench`) que:

1. Mostra o schema Arrow (colunas e tipos) e o número de linhas por arquivo/split.
2. Estatísticas em uma amostra de ~2.000 linhas (ou tudo, se for barato):
   - distribuição do nº de mensagens/passos por trajetória (min, p50, p90, max);
   - taxa de `resolved`/`solved`; valores de `exit_status`; modelos e agentes presentes;
   - tamanho em caracteres das observações (p50, p90, max) e quantas parecem truncadas.
3. **Estrutura das mensagens:** papéis (`role`) e suas frequências, chaves presentes em cada tipo de
   mensagem, e como aparecem: (a) o pensamento, (b) a ação, (c) a observação, (d) o fim da tarefa.
4. **Ferramentas:** frequência de cada nome de ferramenta e, para ferramentas com subcomando
   (ex.: `str_replace_editor` com `command=view|create|str_replace|insert|undo_edit`), a frequência de cada subcomando.
5. **Comandos bash:** para as ações que executam shell, extraia o primeiro executável de cada comando
   (tratando `cd x && ...`, pipes `|`, `;`, `&&`) e liste os 60 mais frequentes com contagem.
   Isso vai virar a tabela de regras da rotulação.
6. Salva uma amostra estratificada em `data/samples/<dataset>/` (um JSON por trajetória, nome = id):
   - SWE-rebench: 50 trajetórias (25 resolvidas, 25 não), variando o nº de passos;
   - SWE-smith: 20 por split (`tool`, `xml`, `ticks`), metade resolvidas;
   - CodeTraceBench: 60 do split `verified`, cobrindo os 4 agentes (OpenHands, mini-SWE-agent,
     Terminus2, SWE-agent) e SWE-bench + TerminalBench, com os metadados e as anotações de `stages` juntos.

### 2. Pontos que exigem atenção especial
- **SWE-rebench:** confirme que `tool_calls[].function.arguments` é string JSON; verifique o pareamento
  `tool_call_id` entre `assistant` e `tool`; liste **todas** as ferramentas (o card só mostra `bash`);
  veja se um `assistant` pode ter vários `tool_calls` de uma vez.
- **SWE-smith:** `messages` é uma string — descubra se é JSON ou outra serialização. Compare os 3 splits
  lado a lado com o **mesmo passo** de exemplo: como a ação é representada em `tool` (tool call nativo?),
  `xml` (tags?) e `ticks` (bloco entre crases?). Que papel tem `message_type` e `agent`? A observação
  vem como `user` ou `tool`?
- **CodeTraceBench:** abra alguns `.tar.zst` de cada agente e descreva a estrutura interna (arquivos,
  formato de cada um). Descubra **como os `step_id` das anotações (`incorrect_step_ids`,
  `unuseful_step_ids`) se mapeiam para os passos da trajetória** (índice de mensagem? de ação? começa em 0 ou 1?).
  Mostre 2 exemplos concretos: um passo anotado como incorreto e um como inútil, com a ação e a observação.
  Diga também quais agentes do CodeTraceBench usam o mesmo formato de OpenHands/SWE-agent dos outros datasets.

### 3. Documentação: `docs/formats.md`
Para cada formato (SWE-rebench, SWE-smith `tool`, `xml`, `ticks`, e cada agente do CodeTraceBench), escreva:
1. Colunas/campos de topo e tipos.
2. Um exemplo real **curto** de um passo completo (pensamento → ação → observação), com textos longos truncados.
3. Regra para extrair `thought`, `action` (ferramenta, comando, args), `observation` (conteúdo, exit code se houver), fim da tarefa.
4. Onde estão `resolved`, patch, modelo, id da tarefa.
5. Assinatura para detecção automática do formato (que chaves/padrões distinguem este formato dos outros).
6. Armadilhas encontradas (campos nulos, truncamento, mensagens fora de ordem, múltiplas ações por mensagem…).

Feche o documento com:
- uma tabela comparativa dos formatos;
- uma proposta de mapeamento de cada formato para o modelo `Trajectory`/`Step` do `CLAUDE.md`,
  apontando campos que o modelo ainda não cobre e sugerindo ajustes ao schema;
- a lista de ferramentas e dos 60 executáveis bash mais frequentes (unindo os datasets) com uma
  **sugestão de categoria da taxonomia** para cada um, marcando os casos ambíguos;
- números-chave para o pôster: nº de trajetórias, agentes, modelos, média de passos, taxa de sucesso.

### 4. Encerramento
- Atualize `docs/decisions.md` com as decisões que tomou (ex.: como tratar múltiplas ações por mensagem).
- Marque a Fase 1 como concluída em `CLAUDE.md` e corrija o que estiver errado nele ou no `docs/PLAN.md`
  com base no que descobriu.
- Me dê um resumo de no máximo 15 linhas: o que surpreendeu, os riscos para os adaptadores e o que sugere para a Fase 2.
- Faça um commit: `fase 1: exploração dos datasets e docs/formats.md`.
