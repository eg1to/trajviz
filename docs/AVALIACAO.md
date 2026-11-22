# Avaliação — metodologia e resultados

Base do capítulo de resultados do relatório. Todo número traz o arquivo e a linha de onde vem; os relatórios completos estão em [`results/`](../results/RESULTS.md). As definições do que é avaliado estão em [ROTULACAO_E_DETECTORES.md](ROTULACAO_E_DETECTORES.md); termos no [glossário](GLOSSARIO.md).

**O que foi avaliado:** (1) a acurácia da rotulação em camadas contra um gold manual; (2) os detectores contra o gabarito humano do CodeTraceBench; (3) auditorias manuais dos detectores; (4) diferenças entre trajetórias resolvidas e não resolvidas; (5) uma comparação com o TraceView na mesma trajetória.
**O que não foi avaliado:** usabilidade (não houve estudo com usuários), concordância entre anotadores (o gold tem um anotador) e o gold held-out (ainda não rotulado).

Tudo é reprodutível com semente fixa (20251119, salvo indicação) a partir de `backend/scripts/` (§9).

## 1. Princípios adotados

- **Intervalos por trajetória.** Passos da mesma trajetória não são independentes, então todos os IC 95% vêm de bootstrap percentil **sobre trajetórias** (B = 2.000), nunca sobre passos ([decisions.md](decisions.md#avaliação), 19/11 e 20/11).
- **Nada é ajustado no conjunto de avaliação.** Nenhuma regra de rotulação foi alterada por causa do gold: os erros viraram sugestões, não aplicadas ([results/eval_classifier_sugestoes.md](../results/eval_classifier_sugestoes.md)). As auditorias de detectores são medição. Uma única exceção, declarada: a correção de `pytest … | tail` (defeito de implementação apontado na auditoria, não rótulo do gold).
- **Rotulação às cegas.** O CSV entregue ao anotador não mostra o rótulo da regra, do LLM, a confiança nem o `label_source` (evita viés de ancoragem).
- **Resultados negativos são reportados como tais.**

## 2. Acurácia da rotulação (gold manual)

### Como o gold foi construído

- **Amostra:** 210 passos de 112 trajetórias, semente 20251119: 70 por dataset (SWE-rebench, SWE-smith, CodeTraceBench); no CodeTraceBench, proporcional ao nº de passos por agente. Excluídos `harness_protocol` e passos `message` (trivialmente `think`). Fonte: `make_gold_sample.py`; [decisions.md](decisions.md#avaliação), 19/11.
- **Rotulação cega:** o anotador preencheu `results/gold/gold_steps_cego.csv` (só contexto: pensamento, ação, observação cortada; coluna `gold_category` vazia), salvo como `gold_steps_cego_pedro.csv`. As previsões ficam em arquivos separados (`gold_steps_previsoes.csv`, `eval_classifier_llm_labels.csv`) e o `evaluate.py` junta pelo `id`.
- **Critério:** as definições da taxonomia ([ROTULACAO_E_DETECTORES.md §1](ROTULACAO_E_DETECTORES.md#1-taxonomia)). O anotador marcou `duvida=1` em **21** passos e deixou nota em 22 ([results/eval_classifier.md](../results/eval_classifier.md), linha 5).
- **Anotador:** um só (o autor do projeto, que conhece a taxonomia).

### Resultados (regras × LLM × gold, nos mesmos 210 passos)

Fonte: [results/eval_classifier.md](../results/eval_classifier.md), linhas 102–110.

| método | acurácia [IC 95%] | F1 macro [IC 95%] | kappa com o gold [IC 95%] |
|---|---|---|---|
| regras | **0,943** [0,905; 0,974] | **0,915** [0,860; 0,959] | 0,932 [0,887; 0,969] |
| LLM (Haiku 5.5 em todos os passos, ignorando as regras) | 0,914 [0,874; 0,952] | 0,872 [0,794; 0,926] | 0,898 [0,850; 0,942] |
| regras + LLM só nos passos `fallback` (o que o app faz) | 0,948 [0,911; 0,980] | 0,923 [0,863; 0,970] | 0,938 [0,895; 0,976] |

- Diferença LLM − regras (pareada): acurácia **−2,9 p.p.** [−6,7; +1,0]: indistinguível (linha 107).
- Regras + LLM − regras: +0,5 p.p. [0,0; +1,5]; só 4 passos do gold caem em `fallback`, então esse ganho é pouco informativo (linha 108).
- Acertos: ambos 185, só regras 13, só LLM 7, nenhum 5 (linha 110).
- Concordância regra × LLM: 89,5% [84,6; 93,5], kappa 0,875 (linha 15). Concordância não é acerto.
- Linha de base trivial (sempre `read`): 22,4% (linha 37).
- Observação: a tabela "por recorte" do mesmo arquivo (linha 30) traz IC [0,904; 0,976] para as regras, de outra rodada do bootstrap; esta documentação usa os da tabela de três vias (linha 102), que é a citada no pôster.

### Por dataset e por categoria

| recorte (regras) | n | acurácia [IC 95%] | fonte |
|---|---:|---|---|
| SWE-rebench | 70 | 1,000 | `eval_classifier.md`, linha 32 |
| SWE-smith | 70 | 1,000 | linha 33 |
| CodeTraceBench | 70 | 0,829 [0,740; 0,912] | linha 31 |

- `setup` é a categoria fraca: F1 0,53 [0,15; 0,78], precisão 1,00, revocação 0,36 (linha 60).
- **Maiores confusões** (regras, gold → previsto; linhas 116–122): `setup` → `explore` (4; `which`, `ln && ls`), `setup` → `edit` (3; todos `cp`), e casos isolados `setup` → `reproduce`/`vcs`, `reproduce` → `edit`. Só há 7 pares distintos de confusão. As regras erram 12 dos 210 passos; 9 desses têm gold `setup` ([eval_classifier_sugestoes.md](../results/eval_classifier_sugestoes.md)).

### Sensibilidade aos casos duvidosos

Sem as 21 linhas `duvida=1` (n = 189): regras **0,979** [0,953; 1,000], F1 macro 0,962; LLM 0,963 (linhas 132–133). Só nas 21 duvidosas: regras 0,619 [0,421; 0,800], LLM 0,476 (linha 136). Ou seja, quase todos os erros estão em fronteiras que o próprio anotador considerou ambíguas (ex.: `which` é `setup` ou `explore`?).

### Ressalvas

- **Um anotador**, sem concordância entre anotadores.
- **O gold saiu de `data/samples/`, as mesmas amostras usadas na Fase 3 para medir a cobertura das regras.** O 100% no SWE-rebench e no SWE-smith pode ser otimista; o CodeTraceBench (formatos mais variados) é o recorte mais informativo. É por isso que existe o gold held-out (§2.1).
- Categorias raras (`explore` 6, `vcs` 5, `submit` 5, `other` 5, `think` 7 passos) têm IC muito largos ([results/poster/numeros.md](../results/poster/numeros.md), ressalvas).

### 2.1 Gold held-out (pendente)

- **O que é:** 90 passos (30 por dataset) de trajetórias **fora** de `data/samples/`, no máximo 2 por trajetória, semente 2026, sem `harness_protocol`/`message`. SWE-rebench: 200 linhas sorteadas no Parquet inteiro; SWE-smith: ~70 por split; CodeTraceBench: 150 dos 992 artefatos menos os 60 da amostra ([decisions.md](decisions.md#avaliação), 20/11).
- **Por quê:** medir a acurácia em dados que não influenciaram as regras.
- **Status: não rotulado.** O CSV cego está em `results/gold/gold_holdout_cego.csv`; as previsões em `results/gold_holdout_previsoes.csv`.
- **Como fechar:** rotular às cegas, salvar como `results/gold/gold_holdout_cego_pedro.csv` e rodar `cd backend && uv run python scripts/evaluate.py --gold ../results/gold/gold_holdout_cego_pedro.csv --tag holdout`. Isso gera `results/eval_classifier_holdout.md` e escreve no `results/RESULTS.md` a tabela desenvolvimento × held-out.

## 3. Detectores × gabarito do CodeTraceBench

Fonte: [results/eval_detectors.md](../results/eval_detectors.md).

### Desenho

- **Universo:** 976 das 1.000 trajetórias do split `verified` (8 sem artefato, 16 só com logs; linha 5). Só **392** têm algum passo anotado como incorreto ou inútil; as demais entram como "sem problemas" (negativos), o que pode não ser verdade (linha 6).
- **Alinhamento:** o `step_id` do gabarito tem unidade diferente por agente; **34%** dos passos anotados só se alinham por hipótese (linha 7; [formats.md §4.5](formats.md)).
- **Tarefas:** `repeated ∪ no_new_info` × passos inúteis; `error ∪ test_fail` × passos incorretos; `loop` × passos incorretos; estágio incorreto × estágio com flag.
- **Linha de base:** marcador aleatório com a **mesma quantidade de flags por trajetória** (100 sorteios); **lift** = F1 do detector ÷ F1 do aleatório. No nível de estágio a base ignora o tamanho do estágio (limitação declarada).
- **Recortes:** todos, por agente, por origem (SWE-bench × TerminalBench), com/sem `harness_protocol`, só alinhamento confirmado.

### Resultados (recorte "todos")

| tarefa | marcados | precisão | revocação | F1 | lift [IC 95%] | fonte |
|---|---:|---:|---:|---:|---|---|
| inútil × `repeated ∪ no_new_info` | 2.009 | 0,004 | 0,038 | 0,007 | **0,80×** [0,12; 1,67] | linha 34 |
| incorreto × `error ∪ test_fail` | 4.382 | 0,075 | 0,220 | 0,112 | **1,62×** [1,44; 1,80] | linha 49 |
| incorreto × `loop` | 48 | 0,125 | 0,004 | 0,008 | 2,43× [0,00; 3,33] | linha 64 |
| estágio incorreto × ≥ 1 flag | 3.065 | 0,069 | 0,401 | 0,118 | 0,84× [0,77; 0,93] | linha 79 |
| estágio incorreto × `error ∪ test_fail ∪ loop` | 2.462 | 0,076 | 0,350 | 0,124 | 0,95× [0,86; 1,03] | linha 94 |

Leitura:

1. **`repeated ∪ no_new_info` é indistinguível de sorteio** para os passos inúteis (o IC do lift contém 1). Resultado negativo.
2. **`error ∪ test_fail` é fraco, mas acima do acaso** para os passos incorretos. No mini-SWE-agent chega a F1 0,275 e lift 1,93× (linha 53); restrito ao alinhamento confirmado, lift 1,73× [1,52; 1,94] (linha 58).
3. **`loop` é inconclusivo:** depois da correção marca só 48 passos (antes 1.899) e o IC do lift contém 1.
4. **No nível de estágio** a revocação de 40% é efeito da taxa de flags: o lift fica abaixo de 1.
5. **O protocolo do harness quase não muda nada:** excluir `harness_protocol` mantém o lift de `error ∪ test_fail` em 1,62× (linha 57).

**Antes × depois da correção de `test_fail` e `loop`** (linhas 15–19): `error ∪ test_fail` não muda (1,62× → 1,62×; o que saiu de `test_fail` com o exit 2/4 do pytest entrou em `error`, e a união é a mesma); `loop` vai de 1.899 para 48 passos marcados, a precisão sobe de 7,1% para 12,5% e a revocação cai de 9,0% para 0,4%. Os números "antes" estão em `results/eval_detectors_before.md`.

**Por que os números são baixos:** os conceitos do gabarito ("incorreto", "inútil", julgados por um anotador olhando o estágio) não são os mesmos dos detectores ("comando falhou", "leitura repetida"). O resultado indica que detectores sintáticos não bastam para reproduzir esse julgamento: é a motivação para detectores semânticos no TCC II.

## 4. Auditorias manuais dos detectores

> Os vereditos das auditorias são uma **pré-avaliação do assistente** (marcados "revisar" nos arquivos), não de um humano. A revisão humana desses vereditos é uma pendência.

| detector | rodada | amostra | correto | duvidoso | falso positivo | fonte |
|---|---|---:|---:|---:|---:|---|
| `no_new_info` | 1 (regra original) | 20 | 2 | 2 | **16 (80%)** | [audit_no_new_info.md](../results/audit_no_new_info.md), linha 17 |
| `no_new_info` | 2 (corrigida, nova amostra) | 20 | 20 | 0 | 0 | idem, linhas 7–11 |
| `error` | 1 | 20 | 18 (90%) | 1 | 1 | [audit_flags.md](../results/audit_flags.md), linha 623 |
| `repeated` | 1 | 20 | 15 (75%) | 5 | 0 | idem, linha 624 |
| `test_fail` | 1 → 2 | 20 + 20 | 10 → **16** | 10 → 3 | 0 → 1 | idem, linhas 11–12 |
| `loop` | 1 → 2 | 20 + 20 | 5 → **20** | 8 → 0 | 7 → 0 | idem, linhas 13–14 |

- O critério para o `no_new_info` era ajustar a regra se mais de 25% fossem falsos positivos; com 80% a regra foi corrigida e a taxa de marcação no SWE-smith caiu de 12,6% para 2,8% dos passos.
- A rodada 2 (`test_fail` e `loop`) usou ~1.150 trajetórias **novas** (fora de `data/samples/`, semente diferente). A 1ª execução da rodada 2 expôs duas lacunas da implementação do `loop`, corrigidas **antes** da amostra final (as intermediárias foram descartadas e isso está registrado em `audit_flags.md`).
- Ressalva do `loop`: os 20 casos da rodada 2 vêm de só 11 trajetórias, e o detector perdeu revocação (§3).
- O único falso positivo do `test_fail` na rodada 2 (o exit do `grep` no fim de um pipe) motivou a correção de `pytest … | tail`; depois dela o `eval_detectors.py` mudou 1 passo (4.383 → 4.382) e a auditoria **não** foi refeita ([results/RESULTS.md](../results/RESULTS.md), "Correção posterior").

## 5. Resolvidas × não resolvidas

Fonte: [results/batch_stats.md](../results/batch_stats.md). Método ([decisions.md](decisions.md#avaliação), 19/11): Mann-Whitney U bilateral por métrica, **correção de Holm** dentro de cada estrato (13 métricas), tamanho de efeito = **δ de Cliff** (> 0 = maior nas resolvidas). Amostras: 2.000 trajetórias do SWE-rebench (1.000 resolvidas + 1.000 não, sorteadas em todo o arquivo e lidas em lotes), 976 do CodeTraceBench e 600 do SWE-smith (3.576 no total; linha 3).

| estrato | métrica | mediana resolvidas × não | δ de Cliff | p (Holm) | fonte |
|---|---|---|---:|---|---|
| SWE-rebench | nº de passos | 56 × 68 | −0,34 | < 0,001 | linha 28 |
| SWE-rebench | % de passos `test` | 12,8% × 10,7% | +0,26 | < 0,001 | linha 33 |
| SWE-rebench | taxa de `no_new_info` | 2,0% × 2,9% | −0,16 | < 0,001 | linha 37 |
| CodeTraceBench (todos) | nº de passos | 33 × 38 | −0,22 | < 0,001 | linha 48 |
| SWE-smith (**`resolved` não validado**) | nº de passos | 21 × 28 | −0,27 | < 0,001 | linha 148 |

- A taxa de `loop` não difere depois da correção (δ = −0,005, p(Holm) = 0,67; [results/RESULTS.md](../results/RESULTS.md)).
- Efeitos pequenos a médios e **associativos, não causais**: o tamanho e a dificuldade da tarefa, o limite de iterações e o agente confundem. Nenhuma conclusão sobre sucesso real vem do SWE-smith.
- **Tempo do pipeline** (detectar, converter, rotular, detectores, métricas; sem cache, sem I/O): mediana **34 ms**, p95 **89 ms** por trajetória nas 3.576 (linha 18).

## 6. Comparação com o TraceView

Detalhes, capturas e limitações em [comparacao_traceview.md](comparacao_traceview.md). Em duas trajetórias que as duas ferramentas aceitam (8 e 27 passos), a visualização completa exigiu **0 rótulos manuais no trajviz × 44 e 158 no TraceView** (o TraceView libera a visualização com no mínimo 10, mas ela fica quase vazia); do upload ao grafo, ~0,85 s no trajviz (roteiro Playwright). O TraceView tem **relações semânticas entre passos**, que o trajviz não tem. Tempos são de roteiro automatizado, não de humano.

## 7. Ameaças à validade

**Interna**
- Gold de desenvolvimento retirado das mesmas amostras usadas para escrever as regras (mitigação: gold held-out, ainda pendente).
- Um anotador, que é também o autor da taxonomia; sem concordância entre anotadores.
- Vereditos das auditorias dados pelo assistente, sem revisão humana.
- Implementação e avaliação feitas pelo mesmo assistente (risco de ajustar ao que se mede); mitigado pela regra de não ajustar no conjunto de avaliação e pelos registros em [decisions.md](decisions.md) e [PROCESSO.md](PROCESSO.md).

**Externa**
- Três datasets de agentes de reparo em Python e TerminalBench; o Ark só com Haiku 5.5 em 6 tarefas pequenas; o `generic_chat` só com mensagens sintéticas e a sessão do Claude Code só com uma fixture sintética (testada em 3 sessões reais, não incluídas).
- A comparação com o TraceView usa 2 trajetórias e um avaliador.

**De construto**
- "Incorreto/inútil" do gabarito ≠ "comando falhou/leitura repetida" dos detectores.
- O alinhamento do `step_id` é hipótese em 34% dos passos anotados; trajetórias sem anotação contam como negativas.
- `resolved` do SWE-smith não é validado.
- A taxonomia descreve o comando, não a intenção; acurácia alta não significa que o rótulo capture o propósito do passo.
- Cobertura das regras (≥ 97% dos passos com `rule`) mede confiança da regra, não acerto.

## 8. Resumo para o pôster e o relatório

Os 17 números-chave com fonte estão em [results/poster/numeros.md](../results/poster/numeros.md) e os achados sobre os dados em [results/poster/achados_metodologicos.md](../results/poster/achados_metodologicos.md). Duas correções em relação a esses arquivos: o custo total do LLM agora é US$ 0,0320 (201 requisições; o pôster cita US$ 0,0209, que era o total até a avaliação do gold de desenvolvimento), e as linhas citadas para `eval_detectors.md` lá (30, 45, 60) correspondem hoje às linhas 34, 49 e 64.

## 9. Como reproduzir

```bash
cd backend
uv run python scripts/evaluate.py [--gold CSV] [--tag holdout]   # classificador × gold
uv run python scripts/eval_detectors.py                          # detectores × gabarito (exige data/raw/codetracebench)
uv run python scripts/audit_no_new_info.py                       # auditoria do no_new_info
uv run python scripts/audit_flags.py                             # auditoria dos demais detectores
uv run python scripts/batch_stats.py                             # resolvidas × não resolvidas + tempo
uv run python scripts/figures.py && uv run python scripts/poster_pack.py
```
