## Rodada 1 — regra original (231 passos marcados = 12,6% dos 1.838 analisados)

Sorteio com a mesma semente sobre a regra original: **16 falsos positivos (80%)**, 2 duvidosos, 2 corretos → passou do limite de 25%, a regra foi ajustada.

| # | arquivo | passo | caso | veredito |
|---|---|---|---|---|
| 1 | `patsy/constraint.py` | #9 | [333,351] depois de uma leitura inteira ABREVIADA (`<NOTE>This file is too large…`) | falso positivo |
| 2 | `pandas/reshape/pivot.py` | #4 | [618,665] depois de [523,616]: intervalos diferentes (view_range chegou como string no xml e virou "arquivo inteiro") | falso positivo |
| 3 | `sqlfluff/linter.py` | #15 | [891,918] depois de [73,108]: intervalos diferentes | falso positivo |
| 4 | `tldextract/cli.py` | #17 | arquivo inteiro de novo, sem edição nele | correto |
| 5 | `pdfminer/ccitt.py` | #4 | [480,500] depois de leitura abreviada | falso positivo |
| 6 | `conan/install.py` | #15 | [90,95] dentro da leitura completa do passo 4 | correto |
| 7 | `pyopenssl/crypto.py` | #21 | [936,950] depois de [936,947]: 3 linhas novas | duvidoso |
| 8 | `gpxpy/gpx.py` | #10 | [45,47] depois de [1330,1350] | falso positivo |
| 9 | `pydantic/_known_annotated_metadata.py` | #3 | [180,200] depois de [169,180]: quase só 1 linha em comum | falso positivo |
| 10 | `pandas/indexing.py` | #15 | [1230,1250] depois de leitura abreviada | falso positivo |
| 11 | `sqlfluff/fluffconfig.py` | #16 | [142,151] depois de [501,535] | falso positivo |
| 12 | `astroid/raw_building.py` | #5 | [420,450] depois de [420,425]: 25 linhas novas | falso positivo |
| 13 | `parse.py` | #12 | [590,596] depois de [665,685] | falso positivo |
| 14 | `dask (2 greps)` | #6 | duas buscas diferentes, ambas "sem saída" | duvidoso |
| 15 | `xmltodict.py` | #2 | [454,492] depois de leitura abreviada | falso positivo |
| 16 | `oauthlib/parameters.py` | #6 | [333,336] depois de leitura abreviada | falso positivo |
| 17 | `mido/meta.py` | #22 | [489,510] depois de [478,498]: 11 linhas novas | falso positivo |
| 18 | `jinja/test_core_tags.py` | #23 | [301,339] depois de leitura abreviada | falso positivo |
| 19 | `deepdiff/diff.py` | #3 | [882,957] depois de leitura abreviada | falso positivo |
| 20 | `click/decorators.py` | #2 | [169,248] depois de leitura abreviada | falso positivo |

**Causas** (as duas respondem por todos os falsos positivos):

1. Leitura inteira **abreviada** (`<NOTE>This file is too large to display entirely…`) tratada como cobertura total do arquivo: o SWE-agent só mostra um resumo, então ver um trecho depois dela traz informação nova.
2. `view_range` que chega como **string** (`"[a, b]"`, formatos xml/ticks) não era lido como intervalo e caía em "arquivo inteiro": qualquer trecho diferente era marcado como releitura.

**Ajuste** (`detect_no_new_info`): intervalo legível obrigatório (lista, string JSON ou `sed -n 'a,bp'`); só um intervalo **contido** em outro já lido (ou igual) é releitura; leitura inteira só cobre se não for abreviada nem truncada; superset/sobreposição parcial não conta; observação de erro (`view_range` inválido) e "sem saída" não contam; edição do arquivo invalida as leituras dele.

## Rodada 2 — regra ajustada (51 passos marcados = 2,8%)
