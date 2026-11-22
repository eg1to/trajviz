# Processo de construção do MVP

Como o trajviz foi construído, por quem e com quais controles. Escrito para a transparência do TCC: o código foi produzido com um assistente de IA, e este documento separa o que foi feito pelo assistente do que foi decidido e verificado pelo aluno. Termos no [glossário](GLOSSARIO.md).

## 1. Linha do tempo

O [plano](PLAN.md) previa 7 dias (19/11 a 25/11/2026). As fases 0–7 foram concluídas em 19–20/11; o restante foi usado para o formato do Ark, ajustes de infraestrutura e a documentação. Datas e hashes vêm de `git log`.

| fase | data | objetivo | entregas principais | commits |
|---|---|---|---|---|
| Planejamento | 18/11 | Escopo, stack, taxonomia, modelo canônico | [PLAN.md](PLAN.md); primeiras linhas de [decisions.md](decisions.md) (stack, rotulação em camadas, relações fora do MVP, taxonomia, esquema canônico) | (anterior ao repositório) |
| 0 — estrutura | 19/11 | Esqueleto do repositório | `CLAUDE.md`, `PLAN.md`, `decisions.md`, script de download retomável do CodeTraceBench, prompt da Fase 1 | `611e069` |
| 1 — exploração | 19/11 | Entender os formatos dos três datasets | `explore_dataset.py`, [formats.md](formats.md), amostras em `data/samples/` | `e875fd2` |
| 2 — schema e adaptadores | 19/11 | Modelo canônico TAR, um adaptador por formato, detecção automática | `schema.py`, 8 adaptadores, `detect.py`, gabarito do CodeTraceBench, fixtures reais e testes, `results/parse_report.md` | `46cfb2d`, `75b5b0f`, `bf93002`, `1221eb2` |
| 3 — rotulação | 19/11 | Rotulação em camadas sem rotulação manual | `taxonomy.py`, `rules.py`, `bash_parser.py`, `llm.py`, `results/labeling_report.md`, amostra do gold | `4f3ff59`, `fc3bd5f` |
| 4 — detectores, métricas, API | 19/11 | Flags, métricas do dashboard, API com cache | `detectors.py`, `metrics.py`, `pipeline.py`, `main.py`, `library.py`, `docs/openapi.json`; `loop` sem passos `message`; `flag_refs` e fases por terço para o front | `a47ebb7`, `1cd6717`, `afd11df` |
| 5 — frontend | 19/11 | Biblioteca, faixa de fases, grafo, inspetor, dashboard | `frontend/`, capturas; **duas rodadas de revisão visual** do aluno no navegador | `1738bc9`, `76c9832`, `37e1ef8`, `fe037a0`, `f92492c`, `4ff1852` |
| 6 — avaliação | 19–20/11 | Medir rotulação e detectores | detectores × gabarito, auditorias, estatística em lote, figuras e pacote do pôster; correção de `test_fail` e `loop`; gold cego; **gold de 210 passos rotulado pelo aluno** e `evaluate.py` | `748cca2`, `d1a0c71`, `e2b0da9` |
| 7 — entrega do MVP | 20/11 | Fechar o MVP | gold held-out cego, comparação com o TraceView, mapeamento de taxonomias, Docker, README, GIF, roteiro da demo, adaptador `claude_code_session` | `d2a0fb4` … `b7b1a3e` (tag **`v0.1-mvp`**) |
| regras do assistente | 20/11 | Formalizar quando parar e perguntar | seção "Quando parar e perguntar" do `CLAUDE.md` | `456da78` |
| pós-MVP: Ark | 21/11 | Formato do agente do orientador | adaptador `ark_trace`, 15 traces reais na biblioteca, fixtures, captura `06-ark-*` | `739ad46` |
| pós-MVP: infraestrutura | 21/11 | Rodar com portas ocupadas | `VITE_PORT`, `VITE_API_URL`, `CORS_ORIGINS`; estado "API indisponível" na biblioteca | `63677e4` |
| pós-MVP: documentação | 21/11 | Documentar o MVP para usuários, banca e relatório | este conjunto de documentos | `docs: documentação completa do MVP` |

Versões no formato "Keep a Changelog": [CHANGELOG.md](../CHANGELOG.md).

## 2. Desenvolvimento assistido por IA

### Como funcionou

- O código, os testes, os scripts de avaliação e a maior parte do texto dos relatórios em `results/` foram escritos pelo **Claude Code** (assistente de programação da Anthropic), executando um prompt por fase. Os commits trazem a linha `Co-Authored-By: Claude …`.
- Cada prompt definia objetivo, restrições, entregas, critérios de aceite e a mensagem de commit, e pedia **plano antes de executar**. O `CLAUDE.md` na raiz guarda o contexto permanente (objetivo, arquitetura, regras, estado atual) que o assistente lê a cada sessão.
- **Só o prompt da Fase 1 está versionado** ([prompts/01-explorar-datasets.md](../prompts/01-explorar-datasets.md)). Os das fases 2–7 e os posteriores não foram salvos no repositório (pendência; ver §5).
- Toda decisão de design tomada durante a execução vira uma linha em [decisions.md](decisions.md), com motivo e alternativas descartadas.

### Papel do aluno

| atividade | o que o aluno fez |
|---|---|
| Escopo e taxonomia | Definiu o problema (visualizar sem rotulação manual, em contraste com o TraceView), o escopo do MVP (relações entre passos fora), a taxonomia de categorias e fases e o plano ([PLAN.md](PLAN.md); decisões de 18/11). |
| Prompts e planos | Escreveu os prompts de cada fase, revisou os planos propostos antes da execução e as entregas depois. |
| Decisões de design | Aprovou ou pediu as decisões registradas (ex.: Haiku 5.5 como fallback e o orçamento de US$ 4,91; ignorar o `patch` do SWE-smith; nunca ajustar regras no conjunto de avaliação; não incluir sessões reais do Claude Code). |
| Revisões visuais | Revisou a interface no navegador em rodadas (commits `f92492c` e `4ff1852` na Fase 5; nova rodada em 21/11, cujos problemas estão listados em [LIMITACOES_E_TRABALHOS_FUTUROS.md](LIMITACOES_E_TRABALHOS_FUTUROS.md#2-problemas-conhecidos-do-mvp)). |
| Gold | Rotulou às cegas os 210 passos do gold de desenvolvimento, marcando 21 como duvidosos e anotando 22 ([AVALIACAO.md](AVALIACAO.md#2-acurácia-da-rotulação-gold-manual)). |
| Validação | Conferiu números e ressalvas dos resultados e pediu correções de consistência entre arquivos. |
| Dados do Ark | Gerou os traces do Ark com o `run_batch.py` no repositório do Ark e escolheu o que entra na biblioteca. |

**O que não foi feito por humano** (e precisa ser dito na banca): os vereditos das auditorias de detectores são uma pré-avaliação do assistente, marcada "revisar" nos arquivos, e ainda não foram revisados pelo aluno ([AVALIACAO.md §4](AVALIACAO.md#4-auditorias-manuais-dos-detectores)).

### Quando o assistente devia parar e perguntar

Regra do [CLAUDE.md](../CLAUDE.md) (formalizada em `456da78`). O assistente devia consultar o aluno antes de:

- (a) gastar com a API acima do orçamento definido para a tarefa (o LLM tem trava `LLM_BUDGET_USD` por execução; total gasto: US$ 0,0320 de US$ 4,91);
- (b) apagar dados ou arquivos fora do repositório;
- (c) mudar o modelo canônico (`schema.py`), do qual o frontend depende;
- (d) pular algum item de um prompt.

Exemplos de aplicação: o formato do Ark foi implementado **sem** mudar `schema.py` (o que faltava foi para `Trajectory.meta`); quando a porta pedida estava ocupada por outro projeto, o assistente usou outra porta e avisou em vez de parar o serviço alheio; quando um item do prompt não podia ser cumprido literalmente (ex.: abrir "sem erro" traces de 0 passos), isso foi reportado na entrega.

## 3. O que deu errado e como foi corrigido

| problema | como apareceu | correção | registro |
|---|---|---|---|
| **`no_new_info` com 80% de falsos positivos** | Auditoria de 20 casos no SWE-smith: 16 falsos positivos (leitura abreviada tratada como cobertura total; `view_range` em texto lido como "arquivo inteiro") | Cobertura exige intervalo legível e leitura não abreviada nem truncada; marcação caiu de 12,6% para 2,8% dos passos; 0 de 20 falsos positivos na nova amostra | `4ff1852`; [results/audit_no_new_info.md](../results/audit_no_new_info.md) |
| **Alertas falsos de "editado sem ler"** | Revisão visual: arquivos criados pelo próprio agente apareciam como "editado sem ler" | `FileRef.created` e `Files.created_by_agent`; criados ficam fora do alerta | `f92492c` |
| **Log genérico detectado como OpenHands (90%)** | Revisão visual com um log de chat genérico | `openhands_chat` só vence com evidência específica (`execute_bash`, ids `chatcmpl-tool-`, rodapé de exit code); o resto vira `generic_chat` com agente "desconhecido" | `4ff1852`; [decisions.md](decisions.md#dados-e-formatos) |
| **Ids instáveis** | Links e capturas quebravam a cada mudança de regra (o id incluía a versão do pipeline) | Id público = hash só do conteúdo; a versão fica só na chave do cache; 404 amigável "reabra pela biblioteca" | `4ff1852`; [decisions.md](decisions.md#infraestrutura) |
| **`loop` inflado por mensagens** | 20,8% dos passos do CodeTraceBench marcados como loop (uma trajetória com 445 mensagens seguidas) | Passos `message` fora da janela: 3,8% | `1cd6717` |
| **`loop` com falsos positivos** | Auditoria: 7 de 20 (edição em lote, leituras de intervalos diferentes) | Exige a mesma ação normalizada ou o mesmo erro no ciclo edit → test_fail; custo: revocação de 0,4% contra o gabarito | `d1a0c71` |
| **`test_fail` confundindo erro de execução com teste falhando** | Auditoria: 9 de 10 duvidosos eram exit 2/4/5 do pytest | Códigos de saída do pytest; depois, `pytest … \| tail` pelo texto | `d1a0c71`, `e2b0da9` |
| **Ids do gold colidindo** | Os prefixos de `traj_id` do CodeTraceBench colidiam ao juntar gold e previsões | `id` único por linha | `d1a0c71`; [decisions.md](decisions.md#avaliação) |
| **Gold não cego** | O 1º CSV mostrava as previsões ao anotador | CSV cego; previsões em arquivos separados; o antigo foi removido antes da rotulação | `d1a0c71` |
| **Números divergentes entre arquivos** | Tempo do pipeline citado como 31/92 ms em vez de 34/89 ms | Corrigido no `RESULTS.md` e no README | [decisions.md](decisions.md#avaliação), 20/11 |
| **Traces do Ark com falhas do adaptador** | Runs com `EmptyModelResponseError` genérico na v1 | Adaptador da Anthropic corrigido no Ark (`9d8b60a`); v1 virou fixture e a v2 foi gerada de novo | [DADOS.md §4](DADOS.md#4-traces-do-ark) |

## 4. Controles de qualidade

- **Testes:** 468 no backend (`uv run pytest`, com fixtures reais), 13 no vitest e 14 e2e no Playwright, contados em 21/11/2026 (`pytest --collect-only`, `vitest list`, `e2e/smoke.spec.ts`). Mais 6 roteiros de captura (`npm run screenshots`).
- **Regra de fixture real:** todo adaptador e toda regra de rotulação têm teste com fixture real em `backend/tests/fixtures/` (exceções declaradas: `generic_chat` e `claude_code_session`, com fixtures sintéticas).
- **Sementes fixas** em todas as amostragens e bootstraps.
- **Antes × depois** guardados quando uma regra muda (`eval_detectors_before.*`, `batch_stats_before.json`, `audit_flags_round1.md`).

## 5. Pendências do processo

- Versionar em `prompts/` os prompts das fases 2–7 e dos trabalhos posteriores.
- Revisão humana dos vereditos das auditorias de detectores.
- Rotular o gold held-out ([AVALIACAO.md §2.1](AVALIACAO.md#21-gold-held-out-pendente)).
