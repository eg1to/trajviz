# Registro de decisões

Uma linha por decisão. Vira a base da seção de metodologia do relatório.

| Data | Decisão | Motivo | Alternativas descartadas |
| --- | --- | --- | --- |
| 18/11/2026 | Stack React + TypeScript (Vite) no front e FastAPI no back | Grafo e dashboard interativos; parsing perto do ecossistema Python dos datasets | Streamlit (como o TraceView), Next.js só front |
| 18/11/2026 | Rotulação automática em camadas: ferramenta → comando bash → LLM | Reprodutível e barato; o LLM cobre só comandos ambíguos | Só regras; só LLM |
| 18/11/2026 | Relações entre passos fora do MVP; grafo com categoria + ordem cronológica + loops detectados | Relações são a parte mais arriscada de automatizar; viram trabalho do TCC II | Inferir relações com LLM |
| 18/11/2026 | Taxonomia de 10 categorias em 4 fases | Cobre as ações de agentes de reparo; comparável com o TraceView/AutoCodeRover | Usar a taxonomia do TraceView diretamente |
| 18/11/2026 | Esquema canônico único (TAR) com um adaptador por formato | O resto do sistema não conhece o formato original; resolve a lacuna "cada ferramenta assume um formato" | Visualizador específico por formato |
| 19/11/2026 | Fallback com Claude Haiku 5.5 (`claude-haiku-5-5`) | Modelo mais barato da Anthropic (US$ 0,10 / 0,50 por MTok); saldo de US$ 4,91 cobre a avaliação | gpt-oss via API OpenAI-compatível |
| 19/11/2026 | Avaliação sem estudo com usuários | Não exigida no TCC I; fica para o TCC II | — |
| 19/11/2026 | CodeTraceBench como gabarito dos detectores | Tem anotação humana de passos incorretos e inúteis por estágio | Rotular passos inúteis à mão |
| 19/11/2026 | CodeTraceBench: baixar só metadados + artefatos sob demanda (rate limit do HF) | `swe_raw/` tem ~17 mil arquivos e estourou o HTTP 429; manifests (~190 MB) bastam, e `backend/scripts/download_ctb_artifacts.py` baixa os `.tar.zst` do split verified de forma lenta e retomável (`--sample 60` para a Fase 1, `--all` depois) | `snapshot_download` do repo inteiro |
