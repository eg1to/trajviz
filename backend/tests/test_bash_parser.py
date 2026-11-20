"""Camada 2: comandos bash reais/típicos das amostras (docs/formats.md §9) — uma linha por regra."""
import pytest

from app.labeling.bash_parser import Ctx, classify_command, normalize_path
from app.labeling.taxonomy import Category as C

CREATED = ["reproduce_error.py", "test_edge_cases.py", "debug_foo.py", "check_x.py", "analyze.py"]

CASES = [
    # --- python (regras finas)
    ("python -m pytest tests/test_a.py -x", C.test),
    ("python3 -m unittest discover -s tests", C.test),
    ("python -m nose tests", C.test),
    ("python -m pytest -q 2>&1 | tail -20", C.test),
    ("pytest tests/test_a.py::test_x -k foo", C.test),
    ("tox -e py39", C.test),
    ("python tests/runtests.py foo.tests.test_bar", C.test),
    ("python reproduce_issue.py", C.reproduce),
    ("python /testbed/reproduce_bug.py", C.reproduce),
    ("python debug_foo.py", C.reproduce),
    ("python check_x.py --verbose", C.reproduce),
    ('python -c "import a; print(a.f())"', C.reproduce),
    ("python3 -c 'import sys; print(sys.path)'", C.reproduce),
    ("python - <<'EOF'\nimport a\nprint(a.f(1))\nEOF", C.reproduce),
    ("python <<EOF\nprint(1)\nEOF", C.reproduce),
    ("python -c \"open('/testbed/src/m.py','w').write('x=1')\"", C.edit),
    ("python - <<'EOF'\nfrom pathlib import Path\nPath('/testbed/src/m.py').write_text('x')\nEOF", C.edit),
    ("python -c \"open('reproduce_foo.py','w').write('print(1)')\"", C.reproduce),
    ("python -c \"open('/tmp/t.py', 'w').write('print(1)')\"", C.reproduce),
    ("cat > reproduce.py << 'EOF'\nprint(1)\nEOF\npython reproduce.py", C.reproduce),
    ("cat > /testbed/src/m.py << 'EOF'\nx = 1\nEOF", C.edit),
    ("python setup.py install", C.setup),
    ("python setup.py develop", C.setup),
    ("python -m pip install -e .", C.setup),
    ("python -m pip list", C.explore),
    ("python -m mypy src", C.test),
    ("python -m flake8 src", C.test),
    ("python3 -m pylint pkg", C.test),
    ("python --version", C.explore),
    ("python manage.py test app", C.test),
    ("python manage.py migrate", C.setup),
    ("python -m http.server 8000", C.setup),
    ("python scripts/gen.py out.txt", C.reproduce),
    ("python -m json.tool a.json", C.reproduce),
    # --- tabela §9
    ("sed -n '1,20p' a.py", C.read),
    ("sed -i 's/a/b/' f.py", C.edit),
    ("sed -i.bak 's/a/b/' f.py", C.edit),
    ("echo x > f.txt", C.edit),
    ("echo x >> /testbed/f.txt", C.edit),
    ("cat a.txt | tee out.txt", C.edit),
    ("cat > f.py << EOF\nx=1\nEOF", C.edit),
    ("printf 'a\\n' > conf.ini", C.edit),
    ("git diff", C.vcs), ("git status", C.vcs), ("git log --oneline -3", C.vcs), ("git show HEAD:a.py", C.vcs),
    ("git stash", C.vcs), ("git checkout main", C.vcs), ("git diff HEAD~1 -- a.py", C.vcs),
    ("git apply fix.patch", C.edit), ("git checkout -- a.py", C.edit),
    ("git grep -n foo", C.search),
    ("find . -name '*.py'", C.search), ('find /testbed -type f -name "*.c" | head -20', C.search),
    ("find /testbed -maxdepth 2", C.explore), ("find . -type d", C.explore),
    ("find . -name '*.pyc' -delete", C.edit),
    ("rm -f /tmp/x.py", C.setup), ("mkdir -p /tmp/x", C.setup), ("chmod +x run.sh", C.setup), ("touch /tmp/ok", C.setup),
    ("pip install requests", C.setup), ("pip3 install -r requirements.txt", C.setup), ("conda install numpy", C.setup),
    ("apt-get install -y gcc", C.setup), ("npm install", C.setup), ("pip list", C.explore), ("pip show foo", C.explore),
    ("flake8 src", C.test), ("pylint pkg", C.test), ("mypy .", C.test), ("make test", C.test), ("make check", C.test),
    ("make", C.setup), ("make install", C.setup), ("npm test", C.test), ("yarn lint", C.test), ("cargo test", C.test),
    ("go test ./...", C.test), ("./runtests.sh", C.test), ("./run_tests.sh -v", C.test),
    ("ls -la", C.explore), ("pwd", C.explore), ("tree -L 2", C.explore), ("which python", C.explore), ("ls /testbed/src", C.explore),
    ("cat setup.py", C.read), ("head -n 20 a.py", C.read), ("tail -50 log.txt", C.read), ("nl -ba a.py | sed -n 1,5p", C.read),
    ("wc -l a.py", C.read), ("awk '{print $1}' data.txt", C.read),
    ("grep -rn 'foo' src/", C.search), ("rg foo --type py", C.search), ("grep -n 'def f' a.py | head -3", C.search),
    # --- compostos e precedência
    ("cd /testbed && pytest -q", C.test),
    ("cd /x && grep foo a.py | sed -n 1,3p", C.search),
    ("cd /x && sed -i 's/a/b/' f.py && python reproduce.py", C.edit),
    ("ls && cat a.py", C.read),
    ("cd /testbed && git status && git diff", C.vcs),
    ("timeout 60 pytest tests", C.test), ("sudo apt-get install x", C.setup), ("FOO=1 python reproduce.py", C.reproduce),
    ("env PYTHONPATH=. pytest tests", C.test),
    ("cd /testbed", C.setup), ("export A=1", C.setup),
    ("sleep 5", C.other), ("kill -9 123", C.other), ("echo hello", C.other),
    ("for f in a.py b.py; do cat $f; done", C.read),
    ('bash -c "cd /x && pytest"', C.test),
    ("./reproduce.sh", C.reproduce), ("node script.js", C.reproduce), ("curl -O http://x.org/y.tgz", C.setup),
    ("tar xzf a.tgz", C.setup), ("patch -p1 < x.diff", C.edit),
    ("applypatch << 'PATCH'\n*** Begin Patch\n*** End Patch\nPATCH", C.edit),
    ("find . -name '*.py' | xargs grep -l foo", C.search), ("head -5 a.py | grep x", C.read),
]


@pytest.mark.parametrize("cmd,expected", CASES)
def test_classify(cmd, expected):
    r = classify_command(cmd, Ctx(created=set(CREATED)))
    assert r.category == expected, f"{cmd!r} → {r.category.value} ({r.subcategory})"


def test_case_count():
    assert len(CASES) >= 80


def test_python_test_script_depends_on_who_created_it():
    assert classify_command("python test_edge_cases.py", Ctx()).category == C.test  # script do repositório
    ctx = Ctx()
    ctx.add("test_edge_cases.py")  # o agente o criou antes (editor create)
    assert classify_command("python test_edge_cases.py", ctx).category == C.reproduce


def test_python_writes_file_target_decides():
    assert classify_command("python -c \"open('/testbed/a.py','w').write('x')\"").category == C.edit
    assert classify_command("python -c \"open('/tmp/reproduce.py','w').write('x')\"").category == C.reproduce


def test_subcategory_keeps_all_segments():
    r = classify_command("grep -n foo a.py | sed -n 1,3p ; cat b.py")
    assert r.category == C.search
    r = classify_command("ls && cat a.py")
    assert r.subcategory == "ls|cat"


def test_confidence_levels():
    assert classify_command("pytest").confidence == 0.9
    assert classify_command("mycli --flag").confidence < 0.6  # executável desconhecido → candidato ao LLM
    assert classify_command("run_unit_check").confidence == 0.6  # regra por padrão (*check*)


def test_pipe_first_command_defines_and_later_writes_edit():
    assert classify_command("cat a.py | grep x").category == C.read
    assert classify_command("grep x a.py | sort > out.txt").category == C.edit


def test_files_read_edit_run_modes():
    r = classify_command("sed -n '1,5p' /testbed/src/a.py")
    assert [(f.path, f.mode) for f in r.files] == [("src/a.py", "read")]
    r = classify_command("sed -i 's/a/b/' /testbed/src/a.py")
    assert [(f.path, f.mode) for f in r.files] == [("src/a.py", "edit")]
    r = classify_command("python /workspace/org__repo__1.0/reproduce.py")
    assert [(f.path, f.mode) for f in r.files] == [("reproduce.py", "run")]
    r = classify_command("pytest tests/test_a.py::test_x tests/test_b.py")
    assert [(f.path, f.mode) for f in r.files] == [("tests/test_a.py", "run"), ("tests/test_b.py", "run")]
    r = classify_command("grep -n foo src/a.py src/b.py")  # 1º posicional = padrão
    assert [f.path for f in r.files] == ["src/a.py", "src/b.py"]
    r = classify_command("cat a.py > /app/out.txt")
    assert ("out.txt", "edit") in [(f.path, f.mode) for f in r.files] and ("a.py", "read") in [(f.path, f.mode) for f in r.files]


@pytest.mark.parametrize("raw,expected", [
    ("/testbed/src/a.py", "src/a.py"), ("/workspace/org__repo__1.0/pkg/m.py", "pkg/m.py"), ("/app/x.json", "x.json"),
    ("./a.py", "a.py"), ("a.py", "a.py"), ("'quoted.py'", "quoted.py"),
    ("/dev/null", None), ("-n", None), ("$HOME/x", None), ("*.py", None), ("http://x.org/a.py", None), ("12", None),
    ("src/", None), ("/workspace/org__repo__1.0", None),
])
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected


def test_bashlex_failure_falls_back_to_regex():
    # heredoc sem terminador + aspas desbalanceadas: bashlex falha, o fallback ainda classifica
    r = classify_command("cat > /testbed/a.py << 'EOF'\nx = \"unclosed\nprint(1)")
    assert r.category == C.edit
    r = classify_command("grep -n \"foo bar src/a.py")
    assert r.category == C.search


@pytest.mark.parametrize("cmd,segment", [
    ('cd /workspace/org__repo__1.0 && python -c "import git; print(git.__version__)"', 'python -c "import git; print(git.__version__)"'),
    ("cd /testbed && pytest test/test_x.py -x", "pytest test/test_x.py -x"),
    ("cd /testbed && FOO=1 timeout 60 python reproduce.py", "python reproduce.py"),
    ("sudo -E apt-get install -y gcc", "apt-get install -y gcc"),
    ("cd /app && grep -rn 'foo' /testbed/src | head -5", "grep -rn 'foo' src"),
    ("ls && cat /workspace/org__repo__1.0/a.py", "cat a.py"),  # precedência: read vence explore
    ("cd /x && sed -i 's/a/b/' f.py && python reproduce.py", "sed -i 's/a/b/' f.py"),  # edit vence reproduce
    ("python - <<'EOF'\nimport a\nprint(a.f())\nEOF", "python -"),
    ("git status", "git status"),
])
def test_segment_is_the_part_that_defined_the_category(cmd, segment):
    assert classify_command(cmd, Ctx()).segment == segment
