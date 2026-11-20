# Sugestões de ajuste das regras (NÃO aplicadas)

Decisão: as regras de rotulação **não** foram alteradas por causa do resultado do gold (evita ajustar no conjunto de avaliação; ver `docs/decisions.md`).
Se alguma for aplicada depois, medir em amostra nova. Base: `results/eval_classifier.md` — as regras erram 12 dos 210 passos; 9 desses 12 têm gold `setup`
(4 sem dúvida do anotador, 5 com `duvida=1`).

| # | padrão | hoje | gold | evidência | observação |
|---|---|---|---|---|---|
| 1 | `cp`/`cp -r` de arquivo ou diretório no ambiente (ex.: backup `.backup`) | `edit` (confiança < 0,6, `fallback`) | `setup` (3 passos, **sem dúvida**) | é o erro mais claro: 3 casos, nenhum duvidoso; em produção o LLM decide estes passos | `cp` copia/arquiva, não edita o código: poderia ser `setup` quando o destino não é um arquivo-fonte novo |
| 2 | `ln -sf … && ls -la` (criar link e conferir) | `explore` (`ln\|ls`) | `setup` (1, **sem dúvida**) | `ln` é preparação de ambiente; o `ls` só confere | o comando composto herda o `explore` do `ls` por precedência |
| 3 | `which X` / `which a b` | `explore` | `setup` (2, `duvida=1`) | a nota do anotador reconhece a ambiguidade (setup × explore) | decisão de taxonomia, não bug: `which` olha o ambiente, não o repositório |
| 4 | `nginx -s reload && ps aux \| grep nginx` | `explore` | `setup` (1, `duvida=1`) | recarregar serviço é setup; o `ps` só verifica | idem 2 |
| 5 | `git clone --branch …` | `vcs` | `setup` (1, `duvida=1`) | clonar dependência é instalação, não inspeção de histórico | só quando o destino não é o repositório da tarefa |
| 6 | `python -c "import pacote…; print('ok')"` | `reproduce` | `setup` (1, `duvida=1`) | verifica instalação de pacotes, não reproduz o bug | regra possível: corpo do `-c` só com `import`/`print` → `setup` |
| 7 | `python -c` que lê arquivo de dados (`read_parquet`) | `reproduce` | `read` (1, `duvida=1`) | inspeção de dado, não do código sob teste | difícil de regrar sem falso positivo |
| 8 | `sqlite3 db "SELECT …"` | `read` | `reproduce` (1, `duvida=1`) | testa a lógica de uma consulta escrita pelo agente | fronteira read × reproduce |
| 9 | `make runtime > build.log 2>&1 && echo …` | `edit` | `reproduce` (1, `duvida=1`) | o `>` redireciona para um log e vira `edit` | regra possível: `>` para `*.log` ou `/dev/null` não conta como edição |

Só os itens 1 e 2 (4 passos) são erros indiscutíveis segundo o anotador; os demais (8 passos) são fronteiras que ele próprio marcou como duvidosas.
Os dois erros do LLM que mais se repetem (edit → reproduce ×3 e search → explore ×2) não coincidem com estes.
