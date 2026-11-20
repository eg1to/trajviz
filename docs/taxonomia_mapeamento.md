# Mapeamento de taxonomias

Como as categorias de ação de outras ferramentas/trabalhos se relacionam com a taxonomia fixa do trajviz
(`explore`, `search`, `read`, `edit`, `reproduce`, `test`, `setup`, `vcs`, `think`, `submit`, `other`; fases: Entendimento · Modificação · Verificação · Controle).

**Como ler.** O mapeamento é **conceitual**, feito a partir das definições escritas; **não foi validado** por nenhuma anotação (nenhum rótulo do TraceView foi comparado aos do trajviz
nas mesmas trajetórias). Uma diferença de fundo explica quase tudo: as categorias do TraceView descrevem a **intenção** do passo (ex.: *Locate* = "achar o arquivo a mudar");
as do trajviz descrevem **o que a ferramenta/comando faz** (ex.: `read`, `search`), porque o trajviz classifica por regras sobre o comando, sem ler a intenção.

## 1. TraceView → trajviz

Fonte: definições em `traceview_app/labeling/common_ui.py` e `docs/evaluation_instructions.md` do TraceView; uso real nas 40 execuções empacotadas em `autocoderover_csv/actions_categories/`
(218 iterações: Explain 67, Search 55, Locate 53, Generate Fix 42 e Explore 1; **Reproduce, Run tests e Refactor não aparecem nessas 40 execuções**).

| categoria do TraceView (definição resumida) | categoria do trajviz | tipo | observações |
|---|---|---|---|
| **Explore** — inspecionar de forma ampla a tarefa, o repositório, o ambiente ou o contexto | `explore` (+ parte de `read`) | 1:1 no nome, **mais amplo** no TraceView | `explore` do trajviz é só listar/navegar estrutura (`ls`, `tree`, `view` de diretório). O "contexto" do TraceView também cobre ler arquivos para se orientar, que no trajviz é `read`. |
| **Locate** — identificar o arquivo, símbolo, função ou trecho de código a mudar | `search` ou `read` (conforme o comando) | **sem equivalente direto** (categoria de intenção) | Localizar é o *objetivo*; o trajviz só vê o meio (um `grep`/`find -name` vira `search`; abrir o arquivo vira `read`). Não dá para separar "localizar" de "entender" sem inferir a intenção, o que as regras não fazem. |
| **Search** — busca dirigida por texto, referências, exemplos ou comportamento | `search` | 1:1 | `grep`, `rg`, `find -name`, `git grep`. |
| **Reproduce** — rodar comandos/checagens para observar, reproduzir ou isolar o problema | `reproduce` | 1:1 | `python reproduce*.py`, `python -c`, script criado pelo agente. Parte do que o TraceView chamaria de *Reproduce* (ex.: rodar o teste que falha) o trajviz classifica como `test` quando o alvo é um teste do repositório. |
| **Generate fix** — criar ou editar código para resolver a tarefa | `edit` | 1:1 (com ressalva) | `edit` também cobre criar scripts auxiliares (que, por regra, viram `reproduce` quando o alvo é um script de reprodução). |
| **Run tests** — rodar testes, linters ou validação após uma mudança | `test` | 1:1 | O trajviz inclui `mypy`/`flake8`/`pylint`/`make test`, de acordo com a definição. Não olha "após uma mudança"; é só o tipo de comando. |
| **Refactor** — reorganizar/simplificar código sem mudar o comportamento | `edit` | **fusão** (muitos → 1) | Distinguir refatoração de correção exige ler a intenção da edição; o trajviz funde as duas em `edit`. |
| **Explain** — raciocinar, resumir ou planejar sem alterar nem validar código | `think` | ≈ 1:1 | `think` cobre a ferramenta `think`, mensagens sem ação e `task_tracker`. No trajviz o texto de raciocínio de *cada* passo fica no campo `thought` do passo, não vira passo próprio, exceto quando não há ação. |
| *(sem categoria no TraceView)* | `read` | sem origem | Ler um arquivo/trecho. No TraceView cai em Explore ou Locate, conforme a intenção. |
| *(sem categoria no TraceView)* | `setup` | sem origem | `pip install`, `export`, `cd`, criar/remover arquivos de apoio. |
| *(sem categoria no TraceView)* | `vcs` | sem origem | `git diff/status/log/checkout`. |
| *(sem categoria no TraceView)* | `submit` | sem origem | `finish`/`submit`. |
| *(sem categoria no TraceView)* | `other` | sem origem | Teclas de controle, `sleep`, não classificável. |

### Resumo

- **1:1 (6)**: Search → `search`, Reproduce → `reproduce`, Run tests → `test`, Generate fix → `edit`, Explain → `think`, Explore → `explore` (esta com a ressalva de abrangência).
- **Fusão**: Refactor e Generate fix → `edit` (o trajviz perde a distinção).
- **Divisão**: Locate → `search`/`read` (uma categoria de intenção vira duas de ferramenta, decididas pelo comando).
- **Sem equivalente no TraceView (5)**: `read`, `setup`, `vcs`, `submit`, `other`.
- **Sem equivalente no trajviz (1)**: Locate como categoria própria (e a noção de intenção, em geral).

### Por que as diferenças (inferência — não é uma explicação dada pelos autores do TraceView)

1. **Fonte dos dados.** As 40 execuções empacotadas no TraceView são do AutoCodeRover, em que, segundo meu conhecimento geral do AutoCodeRover (**não verificado nos arquivos do TraceView**), o agente trabalha com chamadas de API de busca e de edição, sem shell livre;
   o uso real das categorias (acima) se concentra em Search/Locate/Explain/Generate Fix. A taxonomia do trajviz nasceu de logs de agentes com shell (OpenHands, SWE-agent, mini-SWE, Terminus2),
   onde `setup`, `vcs`, `read` e `submit` são frequentes e precisam existir para não inflar `other` (meta da Fase 3: `other` < 15%).
2. **Classificação automática.** Sem rotulador humano, só se consegue separar o que é visível no comando. Intenção (Locate, Refactor) fica fora; por isso as fusões e a divisão acima.
3. **Fases.** O trajviz agrupa as categorias em quatro fases (Entendimento, Modificação, Verificação, Controle) para a faixa de fases; o TraceView não tem esse agrupamento. Aproximação por fase:
   Explore/Locate/Search ↔ Entendimento; Generate fix/Refactor ↔ Modificação; Reproduce/Run tests ↔ Verificação; Explain ↔ Controle.

### Em que as taxonomias não são comparáveis

Não se pode converter os rótulos de uma em outra sem perda e comparar acurácia: converter TraceView → trajviz funciona com perda (fusões); trajviz → TraceView é **impossível** para Locate/Refactor
e ambíguo para `read`. Qualquer comparação quantitativa deve ser feita **no nível de fase** ou com as categorias 1:1 apenas.

## 2. Artigo ASE'25 (Thought-Action-Result)

> **TODO (Pedro):** completar com as categorias do artigo. **Não preenchi nada**: não tenho o texto do artigo aqui e não vou inventar categorias.
> Para cada categoria do artigo, preencher a tabela abaixo (mesma estrutura da seção 1) e depois os quatro itens do resumo.

Referência: TODO (título, autores, DOI/URL).

| categoria do artigo (definição resumida) | categoria do trajviz | tipo (1:1 · fusão · divisão · sem equivalente) | observações |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

### Resumo

- 1:1: TODO
- Fusões: TODO
- Divisões: TODO
- Sem equivalente no trajviz: TODO
- Categorias do trajviz sem origem no artigo: TODO

### Por que as diferenças

TODO
