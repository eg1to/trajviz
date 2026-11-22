# Mapa do relatório do TCC I

Proposta de capítulos para o relatório de ~20 páginas e, para cada um, de onde tirar texto, números, figuras e tabelas. Todos os números têm fonte em [AVALIACAO.md](AVALIACAO.md) ou nos documentos citados. Figuras: `results/figures/*.png` (300 dpi, com SVG ao lado), capturas em `results/screenshots/`.

| # | capítulo | páginas | base nos docs | figuras | tabelas |
|---|---|---:|---|---|---|
| 1 | Introdução | 2 | [README](../README.md) (problema), [PLAN.md §1](PLAN.md), [comparacao_traceview.md](comparacao_traceview.md) (motivação: 44–158 rótulos manuais) | `results/screenshots/05-ctb-gabarito-grafo.png` (visão do produto) | — |
| 2 | Trabalhos relacionados | 2 | [comparacao_traceview.md](comparacao_traceview.md) ("Recursos lado a lado"), [taxonomia_mapeamento.md](taxonomia_mapeamento.md); artigo ASE'25 (**pendente**: seção 2 do mapeamento está em TODO) | — | recursos TraceView × trajviz (resumida) |
| 3 | Dados | 2,5 | [DADOS.md](DADOS.md), [formats.md](formats.md) §0, §4.5, §6, [results/poster/achados_metodologicos.md](../results/poster/achados_metodologicos.md) | `formatos_unificados.png` | datasets (papel, volume, licença); achados sobre os dados |
| 4 | Metodologia | 4 | [ARQUITETURA.md §1 e §4](ARQUITETURA.md) (pipeline, modelo canônico TAR), [ROTULACAO_E_DETECTORES.md](ROTULACAO_E_DETECTORES.md) (taxonomia, camadas, detectores), [AVALIACAO.md §1–§3 (desenho)](AVALIACAO.md), [decisions.md](decisions.md) (justificativas) | diagrama Mermaid do pipeline (ARQUITETURA §1) | taxonomia (11 categorias × 4 fases); detectores (definição e exceções) |
| 5 | Implementação | 3 | [ARQUITETURA.md](ARQUITETURA.md) §2, §3, §5–§8; [PROCESSO.md](PROCESSO.md) (fases e desenvolvimento assistido por IA) | `results/screenshots/02-swe-rebench-resolvida-grafo.png`, `…-dashboard.png`, `06-ark-grafo.png`, `faixas_exemplo.png` | formatos suportados (README); endpoints |
| 6 | Avaliação | 4,5 | [AVALIACAO.md](AVALIACAO.md) §2–§6 | `matriz_confusao.png`, `detectores_vs_gabarito.png`, `metricas_resolvidas_vs_nao.png`, `fases_por_terco_resolvidas_vs_nao.png`, `results/screenshots/comparacao/express-3870-traceview-analise.png` × `express-3870-trajviz-grafo.png` | regras × LLM × gold; detectores × gabarito (recorte "todos"); auditorias; resolvidas × não resolvidas; comparação com o TraceView |
| 7 | Limitações e ameaças à validade | 1 | [LIMITACOES_E_TRABALHOS_FUTUROS.md §1](LIMITACOES_E_TRABALHOS_FUTUROS.md), [AVALIACAO.md §7](AVALIACAO.md#7-ameaças-à-validade) | — | — |
| 8 | Conclusão e trabalhos futuros | 1 | [LIMITACOES_E_TRABALHOS_FUTUROS.md §3](LIMITACOES_E_TRABALHOS_FUTUROS.md#3-trabalhos-futuros-tcc-ii), [results/poster/numeros.md](../results/poster/numeros.md) | — | — |

## Pontos de atenção na escrita

- **Transparência sobre o uso de IA** (cap. 5): dizer que o código foi escrito pelo Claude Code a partir de prompts por fase e listar o papel do aluno ([PROCESSO.md §2](PROCESSO.md#2-desenvolvimento-assistido-por-ia)).
- **Resultados negativos** (cap. 6): `repeated ∪ no_new_info` indistinguível de sorteio; `loop` inconclusivo. Apresentar como resultado.
- **Held-out** (cap. 6): se o gold held-out for rotulado antes da entrega, incluir a tabela desenvolvimento × held-out que o `evaluate.py --tag holdout` gera no `results/RESULTS.md`; senão, declarar como pendente.
- **Números a atualizar em relação ao pôster:** custo do LLM US$ 0,0320 (não US$ 0,0209); 468 testes de backend; 10 adaptadores (o pôster fala em 9 formatos brutos dos datasets, sem o genérico, o Claude Code e o Ark).
- **Associação ≠ causa** em resolvidas × não resolvidas; **`resolved` não validado** no SWE-smith.
- Termos: usar o [glossário](GLOSSARIO.md) (passo, trajetória, modelo canônico TAR, adaptador, rotulação em camadas, detector, gold, gabarito).
