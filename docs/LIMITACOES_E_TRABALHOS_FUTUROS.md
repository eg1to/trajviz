# Limitações e trabalhos futuros

Este é o "lar" das limitações do trajviz. Os números citados vêm de [AVALIACAO.md](AVALIACAO.md), onde estão as fontes.

## 1. Limitações do método

### Rotulação

- **Rótulos automáticos podem estar errados sem aviso.** A acurácia das regras é de 94,3% no gold de desenvolvimento; uma categoria errada aparece na interface só com a confiança e a opção de corrigir.
- **A taxonomia descreve o comando, não a intenção.** "Localizar o arquivo a mudar" e "refatorar" não são distinguíveis por regra ([taxonomia_mapeamento.md](taxonomia_mapeamento.md)).
- **`setup` é a categoria fraca** (F1 0,53): `cp`, `which`, `ln`, `git clone` de dependência caem em `edit`/`explore`/`vcs`. As sugestões de correção existem, mas não foram aplicadas para não ajustar no conjunto de avaliação ([results/eval_classifier_sugestoes.md](../results/eval_classifier_sugestoes.md)).

### Avaliação

- **Gold com um anotador**, que é também o autor da taxonomia; sem concordância entre anotadores.
- **Gold retirado das amostras usadas para escrever as regras:** o 100% no SWE-rebench e no SWE-smith pode ser otimista.
- **Gold held-out pendente:** 90 passos prontos para rotular, sem resultado ainda.
- **Vereditos das auditorias dados pelo assistente**, sem revisão humana.
- **Sem estudo com usuários:** não se sabe se a visualização ajuda alguém a entender uma trajetória mais rápido ou melhor; a comparação com o TraceView mede rótulos e tempo de roteiro, não uso humano.

### Detectores

- **Fracos contra o gabarito do CodeTraceBench:** `repeated ∪ no_new_info` é indistinguível de sorteio para passos inúteis (lift 0,80×); `error ∪ test_fail` fica 1,62× acima do acaso para passos incorretos, com precisão de 7,5%; no nível de estágio o lift fica abaixo de 1.
- **`loop` é conservador:** preciso na auditoria, mas marca só 48 passos em 976 trajetórias (revocação de 0,4%); o resultado contra o gabarito é inconclusivo.
- **São sintáticos:** "falhou", "repetiu", "releu"; não julgam utilidade nem coerência.
- **Alinhamento por hipótese** em 34% dos passos anotados do gabarito; trajetórias sem anotação contam como negativas.

### Dados e formatos

- **`resolved` do SWE-smith não validado.**
- **Ark: observações não registradas.** O trace não grava a saída de `read_file`, `list_files`, `find_text` nem de testes que passaram; nesses passos não há observação, `no_new_info` não se aplica e `repeated` vale só pela ação.
- **Ark só com Haiku 5.5:** o Sonnet 5.5 foi recusado pela API (`refusal`, categoria `reasoning_extraction`) em 5 das 6 tarefas ([DADOS.md §4](DADOS.md#4-traces-do-ark)).
- **`generic_chat` só foi testado com mensagens sintéticas** e mostra o agente como "desconhecido"; **`claude_code_session`** tem fixture sintética (testado em 3 sessões reais não incluídas).
- **Sem relações semânticas entre passos** (Thought→Action, Result→Thought…), que são a contribuição central do TraceView.

### Infraestrutura

- Sem banco de dados (cache em disco); sem autenticação; a biblioteca depende de `data/samples/` (fora do git, exceto os logs do Ark).

## 2. Problemas conhecidos do MVP

Encontrados na revisão no navegador de 21/11/2026 e **ainda não corrigidos** (a correção foi pedida e interrompida antes de qualquer alteração de código):

| # | problema | onde | efeito |
|---|---|---|---|
| 1 | **"linhas +/−" fica +0 −0 nos traces do Ark**, mesmo com diffs nos blocos `[edit_file]` aplicados | `analysis/metrics.py` (`_outcome` só conta edições do `editor`) | Dashboard subestima o tamanho da mudança no Ark |
| 2 | **Edições recusadas (`edit_rejected`) ou que falharam contam como edição**: arquivo marcado "editado" no inspetor, contagem de edições e de arquivos alterados, e "1ª edição" | `ark_trace.py` (`files` com `mode=edit`), `metrics.py` (`_files`, `_dynamics`) | Métricas de edição e o alerta "editado sem ler" ficam errados no Ark; a tabela de arquivos não separa "recusadas" e "falhas" |
| 3 | **Edição recusada sem marca própria no grafo** | `components/graph/` | Só o inspetor mostra a nota de recusa |
| 4 | **`validation_error`, `repair_attempt` e rollback do Ark não aparecem na interface** (estão em `meta.protocol_events` e `meta.ark.workspace`) | `Inspector.tsx`, `DashboardTab.tsx` | O usuário não vê que o modelo saiu do protocolo antes de um passo nem se houve rollback; `max_iterations_reached` aparece só como FAIL |
| 5 | **Upload inválido (422/413) não mostra mensagem**, e o mesmo arquivo não pode ser reenviado sem recarregar | `pages/Library.tsx` | Falha silenciosa |
| 6 | **Links `/t/<id>` dão 404 depois de limpar `backend/.cache/`** (ou de mudar as regras) até a amostra ser reaberta pela biblioteca | `main.get_processed` | Links da demo quebram num ambiente novo; ver aviso em [roteiro_demo.md](roteiro_demo.md#preparação-antes-de-começar) |
| 7 | **Selo "sem exit code" em passos sem comando de shell** (edição, `finish`, `read_file` do Ark) | `Inspector.tsx` | Ruído visual |
| 8 | **Minimapa sobre os nós em grafos longos** | `components/graph/` | Esconde nós no canto inferior direito |
| 9 | **A tela "Comparar"** (duas trajetórias lado a lado), prevista como stretch no plano, **não foi implementada** | — | Resolvidas × não resolvidas só no agregado ([AVALIACAO.md §5](AVALIACAO.md#5-resolvidas--não-resolvidas)) |
| 10 | **Modo da biblioteca para o Ark** (auto/reject-first) não aparece na coluna Tarefa | `library.py`, `Library.tsx` | O modo só está no nome do arquivo |

Pendências de documentação e de dados que dependem do aluno estão em [CLAUDE.md](../CLAUDE.md) ("Estado atual").

## 3. Trabalhos futuros (TCC II)

1. **Relações semânticas entre passos** (Thought→Action, Result→Thought, Action→Action…), inferidas automaticamente, comparáveis às rotuladas à mão no TraceView. É a principal lacuna do trajviz em relação à referência.
2. **Detectores semânticos:** coerência entre o pensamento e a observação anterior (o agente leu o resultado?), ação que contradiz o plano, edição que não tem relação com o que foi lido. A avaliação contra o gabarito do CodeTraceBench mostra que detectores sintáticos não reproduzem "incorreto/inútil".
3. **Estudo com usuários:** tarefas de compreensão de trajetórias com e sem a ferramenta (tempo, acerto, preferência), incluindo uma comparação controlada com o TraceView.
4. **Mais formatos:** outros agentes (Aider, Codex CLI, Cursor), mais logs reais para o `generic_chat` e sessões reais do Claude Code (com anonimização).
5. **Trace estruturado no Ark** (sugestão a discutir com o orientador): registrar a saída de todas as ferramentas, ids de passo e os eventos de protocolo num formato estruturado (ex.: JSONL), o que eliminaria a principal limitação do formato atual.
6. **Fechar a avaliação da rotulação:** rotular o gold held-out, um segundo anotador para medir concordância e, só depois, aplicar e medir as sugestões para `setup` em amostra nova.
7. **Tela "Comparar"** e os problemas da §2.
