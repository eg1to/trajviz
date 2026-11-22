# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Só a entrega do MVP tem tag (`v0.1-mvp`); as fases anteriores aparecem como marcos sem tag, com os commits correspondentes. Detalhes de cada fase em [docs/PROCESSO.md](docs/PROCESSO.md); decisões em [docs/decisions.md](docs/decisions.md).

## [Não lançado]

### Adicionado
- Documentação completa do MVP: [ARQUITETURA](docs/ARQUITETURA.md), [ROTULACAO_E_DETECTORES](docs/ROTULACAO_E_DETECTORES.md), [AVALIACAO](docs/AVALIACAO.md), [DADOS](docs/DADOS.md), [PROCESSO](docs/PROCESSO.md), [LIMITACOES_E_TRABALHOS_FUTUROS](docs/LIMITACOES_E_TRABALHOS_FUTUROS.md), [GLOSSARIO](docs/GLOSSARIO.md), [MAPA_RELATORIO](docs/MAPA_RELATORIO.md) e este changelog; README reescrito; `decisions.md` reorganizado por tema, sem apagar linhas.
- Variáveis de ambiente `VITE_PORT`, `VITE_API_URL` e `CORS_ORIGINS`, usadas também pelo Playwright (`63677e4`).
- Biblioteca mostra "API indisponível" com "Tentar de novo" quando a API está fora do ar (`63677e4`).
- Formato `ark_trace` (traces do Ark, o agente do orientador): adaptador, regras de camada 1, detector `detect_ark`, upload de `.log`/`.txt`, 15 traces reais na biblioteca (dataset "Ark"), 5 fixtures e teste de integração, captura `06-ark-*` (`739ad46`).

### Conhecido (não corrigido)
- Problemas da revisão no navegador de 21/11 (linhas +/− do Ark, edições recusadas contadas como edição, eventos de protocolo do Ark fora da interface, 422 sem mensagem, 404 depois de limpar o cache…): [docs/LIMITACOES_E_TRABALHOS_FUTUROS.md §2](docs/LIMITACOES_E_TRABALHOS_FUTUROS.md#2-problemas-conhecidos-do-mvp).

## [0.1-mvp] — 2026-11-20

Tag `v0.1-mvp` (`b7b1a3e`). Fase 7: entrega do MVP.

### Adicionado
- Gold held-out cego (90 passos, semente 2026) e `evaluate.py --tag` (`d2a0fb4`).
- Comparação com o TraceView na mesma trajetória, com medidas, capturas e roteiro Playwright; log de tempo por upload na API (`3fc5602`).
- Mapeamento de taxonomias TraceView → trajviz; seção do artigo ASE'25 como TODO (`b6a9eb3`, `a78c162`).
- Docker Compose (`api` + `web`/nginx), README e GIF da demo (`c0947b4`).
- Roteiro da demo com URLs validadas e capturas do plano B (`2cd65c3`).
- Adaptador `claude_code_session` (sessões do Claude Code), com fixture sintética (`0867f21`).
- Regras de "quando parar e perguntar" no `CLAUDE.md` (`456da78`, logo após a tag).

## Fase 6 — avaliação — 2026-11-19/20 (sem tag)

### Adicionado
- Detectores × gabarito do CodeTraceBench, auditorias, estatísticas em lote, figuras e pacote do pôster (`748cca2`).
- Gold cego e avaliação do classificador com o gold manual de 210 passos (`d1a0c71`, `e2b0da9`).

### Alterado
- `test_fail` segue os códigos de saída do pytest; `loop` exige a mesma ação normalizada ou o mesmo erro (`d1a0c71`).

### Corrigido
- `pytest … | tail`: veredito pelo texto da saída, não pelo exit code do pipe (`e2b0da9`).

## Fase 5 — frontend — 2026-11-19 (sem tag)

### Adicionado
- Frontend: biblioteca com upload, faixa de fases, grafo em serpentina com modo compacto, inspetor, dashboard com problemas clicáveis e exportação PNG (`1738bc9`, `76c9832`, `37e1ef8`, `fe037a0`).

### Corrigido
- 1ª revisão visual: rótulo do nó pelo segmento que definiu a categoria; arquivos criados pelo agente fora de "editado sem ler"; minimapa menor (`f92492c`).
- 2ª revisão: log genérico não é mais detectado como OpenHands; id estável (só conteúdo); 404 amigável; tema escuro; `no_new_info` corrigido após auditoria com 80% de falsos positivos (`4ff1852`).

## Fase 4 — detectores, métricas e API — 2026-11-19 (sem tag)

### Adicionado
- Detectores, métricas, pipeline com cache em disco, API REST e biblioteca (`a47ebb7`).
- `flag_refs` e contagem de fases por terço, para o front (`afd11df`).

### Alterado
- `loop` ignora passos `message` (loop no CodeTraceBench: 20,8% → 3,8% dos passos) (`1cd6717`).

## Fase 3 — rotulação — 2026-11-19 (sem tag)

### Adicionado
- Taxonomia, regras por ferramenta, `bash_parser`, fallback com Haiku 5.5 (`llm.py`) e relatório de cobertura (`4f3ff59`, `fc3bd5f`).

## Fase 2 — modelo canônico e adaptadores — 2026-11-19 (sem tag)

### Adicionado
- Modelo canônico TAR (`schema.py`), adaptadores `openhands_chat`, `sweagent_smith`, `generic_chat` e os 5 do CodeTraceBench, gabarito, `detect.py`, fixtures reais e testes (`46cfb2d`, `75b5b0f`, `bf93002`, `1221eb2`).

## Fase 1 — exploração dos datasets — 2026-11-19 (sem tag)

### Adicionado
- `explore_dataset.py`, `docs/formats.md` e amostras em `data/samples/` (`e875fd2`).

## Fase 0 — estrutura — 2026-11-19 (sem tag)

### Adicionado
- Estrutura do repositório, `CLAUDE.md`, `PLAN.md`, `decisions.md`, script de download retomável do CodeTraceBench e o prompt da Fase 1 (`611e069`).
