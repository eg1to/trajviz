"""Taxonomia fixa de ações (CLAUDE.md) — usada pelas regras e reutilizada no prompt do LLM."""
from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    explore = "explore"
    search = "search"
    read = "read"
    edit = "edit"
    reproduce = "reproduce"
    test = "test"
    setup = "setup"
    vcs = "vcs"
    think = "think"
    submit = "submit"
    other = "other"


class Phase(str, Enum):
    understanding = "Entendimento"
    modification = "Modificação"
    verification = "Verificação"
    control = "Controle"


PHASE: dict[Category, Phase] = {
    Category.explore: Phase.understanding, Category.search: Phase.understanding, Category.read: Phase.understanding,
    Category.edit: Phase.modification,
    Category.reproduce: Phase.verification, Category.test: Phase.verification, Category.vcs: Phase.verification,
    Category.setup: Phase.control, Category.think: Phase.control, Category.submit: Phase.control,
    Category.other: Phase.control,
}

# (descrição de 1 linha, 2 exemplos)
DESCRIPTIONS: dict[Category, tuple[str, tuple[str, str]]] = {
    Category.explore: ("Listar/navegar a estrutura do repositório ou do ambiente, sem filtrar por conteúdo.",
                       ("ls -la /testbed", "view de um diretório")),
    Category.search: ("Procurar por texto ou nome de arquivo no código.",
                      ("grep -rn 'def foo' src/", "find . -name '*.py'")),
    Category.read: ("Ler o conteúdo de um arquivo ou de um trecho dele.",
                    ("cat setup.py", "sed -n '10,40p' a.py / view de um arquivo")),
    Category.edit: ("Modificar ou criar arquivos (código, configuração, scripts).",
                    ("str_replace_editor str_replace …", "sed -i 's/a/b/' f.py; cat > f <<EOF")),
    Category.reproduce: ("Executar código para reproduzir o problema ou observar um comportamento (script de reprodução, python -c).",
                         ("python reproduce_issue.py", "python -c 'import m; print(m.f(1))'")),
    Category.test: ("Rodar a suíte de testes, linters ou checagens do projeto.",
                    ("pytest tests/test_a.py -x", "make test; flake8 src")),
    Category.setup: ("Preparar o ambiente: instalar dependências, build, variáveis, criar/remover arquivos de apoio.",
                     ("pip install -e .", "mkdir -p /tmp/x; rm reproduce.py; export A=1")),
    Category.vcs: ("Usar o controle de versão para inspecionar o estado das mudanças.",
                   ("git diff", "git status; git log -3")),
    Category.think: ("Raciocinar, planejar ou comentar sem agir (ferramenta think, mensagem sem ação, task_tracker).",
                     ("think: 'preciso olhar o parser'", "task_tracker plan")),
    Category.submit: ("Encerrar a tarefa entregando a solução.", ("finish", "submit")),
    Category.other: ("Nada acima se aplica ou não dá para saber (inclui teclas de controle como C-c).",
                     ("C-c", "sleep 5")),
}

# precedência em comandos compostos (a primeira categoria presente vence)
PRECEDENCE = [Category.edit, Category.test, Category.reproduce, Category.search, Category.read, Category.explore,
              Category.vcs, Category.setup, Category.other]
_RANK = {c: i for i, c in enumerate(PRECEDENCE)}


def pick_by_precedence(cats: list[Category]) -> Category:
    return min(cats, key=lambda c: _RANK.get(c, len(PRECEDENCE))) if cats else Category.other


def taxonomy_prompt() -> str:
    lines = []
    for c in Category:
        d, ex = DESCRIPTIONS[c]
        lines.append(f"- {c.value} [{PHASE[c].value}]: {d} Exemplos: {ex[0]} | {ex[1]}")
    return "\n".join(lines)
