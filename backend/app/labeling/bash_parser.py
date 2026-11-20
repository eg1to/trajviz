"""Camada 2: classifica um comando bash (docs/formats.md §9). bashlex primeiro; fallback shlex+regex.

classify_command(cmd, ctx) -> BashResult(category, subcategory, confidence, files, writes)
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field

import bashlex

from app.labeling.taxonomy import Category as C
from app.labeling.taxonomy import pick_by_precedence
from app.schema import FileRef

# ----------------------------------------------------------------------------- contexto e resultado


@dataclass
class Ctx:
    """Estado acumulado da trajetória: arquivos criados pelo agente (scripts de reprodução/teste dele)."""
    created: set[str] = field(default_factory=set)  # caminhos normalizados e basenames

    def add(self, path: str) -> None:
        self.created.add(path)
        self.created.add(os.path.basename(path))

    def has(self, path: str) -> bool:
        return path in self.created or os.path.basename(path) in self.created


@dataclass
class BashResult:
    category: C = C.other
    subcategory: str | None = None
    confidence: float = 0.3
    files: list[FileRef] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)  # arquivos escritos (para Ctx.created)
    keys_only: bool = False
    segment: str | None = None  # texto (limpo) do segmento que definiu a categoria


# ----------------------------------------------------------------------------- normalização de caminhos
PREFIX_RE = re.compile(r"^/(?:workspace/[^/]+|testbed|app|repo|src/repo|home/[^/]+/repo)/")
KNOWN_NAMES = {"Makefile", "Dockerfile", "README", "LICENSE", "CMakeLists.txt", "Gemfile", "Rakefile", "Procfile", "tox.ini"}


def looks_like_path(p: str) -> bool:
    if not p or len(p) > 200 or p.startswith(("-", "<", "=", "$", "~~")) or re.search(r"[\s$*?`{}()|;&\\!\"'<>=]", p):
        return False
    if "://" in p or re.fullmatch(r"[\d.:,/-]+", p) and "/" not in p.strip("/"):
        return False
    if p in ("/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", ".", "..", "/", "-"):
        return False
    if p.endswith("/"):
        return False
    base = os.path.basename(p)
    return "/" in p and "." in base or bool(re.search(r"\.\w{1,8}$", base)) or base in KNOWN_NAMES


def normalize_path(p: str) -> str | None:
    p = p.strip().strip("'\"")
    if p.startswith("/workspace/") and p.count("/") == 2:  # /workspace/<repo> (diretório raiz)
        return None
    p = PREFIX_RE.sub("", p)
    p = p[2:] if p.startswith("./") else p
    return p if looks_like_path(p) or looks_like_path("/" + p) and "/" in p else None


def fref(path: str | None, mode: str) -> FileRef | None:
    n = normalize_path(path) if path else None
    return FileRef(path=n, mode=mode) if n else None  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- parsing de segmentos
@dataclass
class Seg:
    words: list[str]
    text: str
    redirects: list[tuple[str, str]] = field(default_factory=list)  # saídas (op, alvo)
    heredoc: str | None = None
    pipe_next: list["Seg"] = field(default_factory=list)


HD_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(.*?)(?:\n[ \t]*\2[ \t]*(?=\n|$)|\Z)", re.S)
OUT_REDIR = re.compile(r"(?<![\w&<>])(?:1)?(>>?|&>>?)\s*(?!&)([^\s&|;<>()]+)")


def _strip_heredocs(cmd: str) -> tuple[str, list[str]]:
    bodies: list[str] = []

    def rep(m: re.Match) -> str:
        bodies.append(m.group(4))
        return f"< __HD{len(bodies) - 1}__{m.group(3)}"
    return HD_RE.sub(rep, cmd), bodies


def _is_devnull(t: str) -> bool:
    return t in ("/dev/null", "/dev/stderr", "/dev/stdout") or t.startswith("&") or t.isdigit()


def _seg_from_bashlex(node, cmd: str, bodies: list[str]) -> Seg:
    words, redirs, hd = [], [], None
    for p in node.parts:
        if p.kind == "word":
            words.append(p.word)
        elif p.kind == "assignment":
            words.append(p.word)
        elif p.kind == "redirect":
            tgt = getattr(p.output, "word", None) if p.output is not None else None
            if p.type in (">", ">>", "&>", ">|") and tgt and not _is_devnull(tgt) and p.input in (None, 1):
                redirs.append((p.type, tgt))
            elif p.type == "<" and tgt and tgt.startswith("__HD"):
                hd = bodies[int(tgt[4:-2])]
    return Seg(words, cmd[node.pos[0]:node.pos[1]], redirs, hd)


def _walk(node, cmd: str, bodies: list[str], out: list[Seg]) -> None:
    k = node.kind
    if k == "list":
        for p in node.parts:
            if p.kind != "operator":
                _walk(p, cmd, bodies, out)
    elif k == "pipeline":
        stages = [_seg_from_bashlex(p, cmd, bodies) for p in node.parts if p.kind == "command"]
        if stages:
            stages[0].pipe_next = stages[1:]
            out.append(stages[0])
    elif k == "command":
        out.append(_seg_from_bashlex(node, cmd, bodies))
    elif k in ("compound", "function"):
        for p in getattr(node, "list", None) or getattr(node, "parts", None) or []:
            if p.kind not in ("reservedword", "operator"):
                _walk(p, cmd, bodies, out)


def _split_top(cmd: str) -> list[tuple[str, str]]:
    """Fallback: divide por ; && || | & e quebra de linha respeitando aspas e $( ). → [(texto, separador_anterior)]"""
    segs, cur, q, depth, i, prev = [], [], None, 0, 0, ""
    while i < len(cmd):
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q == '"' and i + 1 < len(cmd):
                cur.append(cmd[i + 1]); i += 1
            elif ch == q:
                q = None
        elif ch in "'\"":
            q = ch; cur.append(ch)
        elif ch == "\\" and i + 1 < len(cmd):
            cur.append(ch); cur.append(cmd[i + 1]); i += 1
        elif ch == "(" and cmd[max(0, i - 1)] == "$":
            depth += 1; cur.append(ch)
        elif ch == ")" and depth:
            depth -= 1; cur.append(ch)
        elif ch == "&" and (cmd[i - 1:i] in (">", "<") or cmd[i + 1:i + 2] == ">"):
            cur.append(ch)
        elif depth == 0 and ch in ";\n|&":
            segs.append(("".join(cur), prev))
            sep = ch
            if ch in "|&" and cmd[i + 1:i + 2] == ch:
                sep = ch * 2; i += 1
            prev = sep
            cur = []
        else:
            cur.append(ch)
        i += 1
    segs.append(("".join(cur), prev))
    return [(s.strip(), p) for s, p in segs if s.strip()]


def _seg_fallback(text: str, hd: str | None) -> Seg:
    redirs = [(m.group(1), m.group(2)) for m in OUT_REDIR.finditer(text) if not _is_devnull(m.group(2))]
    cleaned = OUT_REDIR.sub(" ", text)
    cleaned = re.sub(r"\d?>&\d|\d>\s*/dev/null|< __HD\d+__", " ", cleaned)
    try:
        words = shlex.split(cleaned)
    except ValueError:
        words = cleaned.split()
    return Seg(words, text, redirs, hd)


def parse_segments(cmd: str) -> list[Seg]:
    body_cmd, bodies = _strip_heredocs(cmd)
    try:
        out: list[Seg] = []
        for n in bashlex.parse(body_cmd):
            _walk(n, body_cmd, bodies, out)
        if out:
            return out
    except Exception:  # bashlex não cobre tudo (heredocs, `[[`, aspas desbalanceadas…)
        pass
    out, last = [], None
    for text, sep in _split_top(body_cmd):
        hm = re.search(r"< __HD(\d+)__", text)
        seg = _seg_fallback(text, bodies[int(hm.group(1))] if hm else None)
        if sep == "|" and last is not None:
            last.pipe_next.append(seg)
        else:
            out.append(seg)
            last = seg
    return out


# ----------------------------------------------------------------------------- tabelas de executáveis
WRAPPERS = {"sudo", "env", "time", "nohup", "timeout", "command", "builtin", "exec", "nice", "stdbuf", "xvfb-run", "unbuffer"}
NAV = {"cd", "pushd", "popd", "export", "set", "unset", "source", ".", "alias", "ulimit", "umask", "shopt", "trap", "declare", "local"}
CTRL = {"for", "while", "until", "case", "select", "function", "done", "fi", "esac", "then", "do", "else", "elif", "if", "}", "{", "!"}
CTRL_PREFIX = {"then", "do", "else", "if", "elif", "while", "until", "!", "{"}
EXPLORE = {"ls", "ll", "la", "tree", "pwd", "du", "df", "stat", "file", "which", "type", "whereis", "whoami", "uname", "env",
           "printenv", "hostname", "id", "lsb_release", "nproc", "free", "locale", "arch", "lscpu", "readlink", "realpath",
           "dirname", "basename", "ps", "top", "pgrep", "lsof", "netstat", "ss", "ifconfig", "ip", "mount", "lsblk", "uptime",
           "date", "getconf", "ldd", "nm", "objdump", "readelf", "ldconfig"}
SEARCH = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "locate", "fd", "ctags", "cscope", "zgrep"}
READ = {"cat", "head", "tail", "nl", "less", "more", "bat", "wc", "strings", "hexdump", "xxd", "od", "cut", "sort", "uniq",
        "tr", "column", "jq", "sqlite3", "diff", "cmp", "md5sum", "sha256sum", "sha1sum", "zcat", "base64", "awk", "gawk",
        "paste", "comm", "join", "fold", "rev", "tac", "yq", "csvlook", "pdftotext", "exiftool", "hd", "unzip -l"}
SETUP_EXE = {"mkdir", "rm", "chmod", "chown", "touch", "ln", "tar", "unzip", "gunzip", "gzip", "bzip2", "xz", "zip", "rmdir",
             "apt", "apt-get", "yum", "dnf", "apk", "brew", "pip", "pip3", "conda", "mamba", "poetry", "pipenv", "uv",
             "npm", "yarn", "pnpm", "bundle", "gem", "cargo", "go", "mvn", "gradle", "cmake", "ninja", "meson", "gcc", "g++",
             "cc", "c++", "clang", "clang++", "javac", "rustc", "ld", "ar", "as", "make", "docker", "service", "systemctl",
             "useradd", "usermod", "ssh-keygen", "mount", "umount", "export", "nvm", "pyenv", "virtualenv", "wget", "curl",
             "git-lfs", "dpkg", "rpm", "ldconfig", "update-alternatives", "tsc", "npx", "pip-compile"}
OTHER_EXE = {"echo", "printf", "sleep", "kill", "pkill", "killall", "wait", "clear", "true", "false", "exit", "history", "yes",
             "read", "test", "[", "[[", ":", "fg", "bg", "jobs", "disown", "reset", "tput", "stty", "xdg-open"}
LINTERS = {"mypy", "flake8", "pylint", "ruff", "black", "isort", "pyflakes", "pycodestyle", "yamllint", "sqlfluff", "eslint",
           "prettier", "tsc --noEmit", "shellcheck", "bandit", "pyright", "pydocstyle", "tslint", "rubocop", "golint",
           "clippy", "cppcheck", "pre-commit", "codespell", "autopep8", "yapf"}
TEST_EXE = {"pytest", "py.test", "tox", "nox", "nosetests", "nose2", "unittest", "rspec", "phpunit", "jest", "mocha", "vitest",
            "karma", "bats", "ctest", "stestr", "testr", "trial", "behave", "robot", "coverage", "hypothesis", "pytest-xdist",
            "gotestsum"}
EDIT_EXE = {"applypatch", "apply_patch", "patch", "ed", "vim", "vi", "nano", "emacs", "ex", "dos2unix", "unix2dos", "truncate", "dd", "shred", "install"}
GIT_VCS = {"diff", "status", "log", "show", "stash", "blame", "branch", "remote", "rev-parse", "ls-files", "config", "describe",
           "fetch", "add", "commit", "tag", "shortlog", "reflog", "cat-file", "ls-tree", "rev-list", "for-each-ref", "init",
           "clone", "show-ref", "diff-tree", "name-rev", "merge-base", "whatchanged", "bisect", "worktree", "submodule", "mv"}
GIT_EDIT = {"apply", "am", "restore", "checkout --", "revert", "cherry-pick", "merge", "rebase", "pull", "reset --hard", "clean"}
INTERP = {"node", "nodejs", "ruby", "php", "perl", "lua", "Rscript", "julia", "java", "dotnet", "deno", "bun", "tclsh", "bash",
          "sh", "zsh", "ruby -e", "ts-node", "swipl", "ghc", "runghc", "ocaml", "octave"}

REPRO_NAME = re.compile(r"^(repro|reproduce|reproduction|debug|check|verify|validate|demo|example|try|poc|exploit|minimal|sanity|"
                        r"quick|simple|scratch|tmp|temp|issue|bug|trace|probe|inspect|explore|show|print|run_)", re.I)
TESTY = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.\w+$|_tests?\.\w+$|(^|/)tests?\.\w+$|(^|/)conftest\.py$")


def is_repro_name(path: str) -> bool:
    b = os.path.basename(path)
    return bool(REPRO_NAME.match(b)) or path.startswith(("/tmp/", "tmp/")) or "/tmp/" in path or b.startswith("test_") and False


def is_repro_path(path: str, ctx: Ctx) -> bool:
    """Script de reprodução: nome típico, em /tmp, ou criado pelo próprio agente com nome de teste/depuração."""
    n = normalize_path(path) or path
    b = os.path.basename(n)
    return is_repro_name(n) or (ctx.has(n) or ctx.has(path)) and bool(re.match(r"(test|debug|check|verify)", b, re.I))


# ----------------------------------------------------------------------------- python
PY_WRITE_OPEN = re.compile(r"open\(\s*(?:[rf]?['\"]([^'\"]+)['\"]|(\w[\w.]*))\s*,\s*[rf]?['\"][wax]\+?b?['\"]")
PY_WRITE_FN = re.compile(r"(?:Path\(\s*['\"]([^'\"]+)['\"]\s*\)|(\w+))\.write_(?:text|bytes)\(")
PY_TESTMOD = {"pytest", "unittest", "nose", "nose2", "doctest", "tox", "coverage", "pytest_cov", "behave", "trial", "testtools"}
PY_LINTMOD = {"mypy", "flake8", "pylint", "black", "isort", "ruff", "pyflakes", "pycodestyle", "pydocstyle", "bandit", "pyright"}
PY_FLAG_ARG = {"-W", "-X", "-Q"}


def _py_args(words: list[str]) -> tuple[str | None, str | None, str | None, list[str]]:
    """→ (módulo -m, código -c, script, args do script)."""
    i, mod, code, script = 1, None, None, None
    while i < len(words):
        w = words[i]
        if w == "-m" and i + 1 < len(words):
            mod = words[i + 1]; return mod, None, None, words[i + 2:]
        if w == "-c" and i + 1 < len(words):
            code = words[i + 1]; return None, code, None, words[i + 2:]
        if w in PY_FLAG_ARG:
            i += 2; continue
        if w.startswith("-") and w != "-":
            i += 1; continue
        script = w
        return None, None, script, words[i + 1:]
    return mod, code, script, []


def classify_python(seg: Seg, ctx: Ctx) -> BashResult:
    w = seg.words
    mod, code, script, rest = _py_args(w)
    src = code if code is not None else (seg.heredoc if seg.heredoc is not None else "")
    r = BashResult()
    if mod:
        m0 = mod.split(".")[0]
        if m0 in PY_TESTMOD:
            return BashResult(C.test, f"python -m {mod}", 0.9)
        if m0 in PY_LINTMOD:
            return BashResult(C.test, f"python -m {mod}", 0.9)
        if m0 == "pip" or m0 == "ensurepip":
            sub = rest[0] if rest else ""
            return BashResult(C.explore if sub in ("show", "list", "freeze", "--version", "check") else C.setup, f"python -m pip {sub}".strip(), 0.9)
        if m0 in ("venv", "virtualenv", "build", "wheel", "http", "pip"):
            return BashResult(C.setup, f"python -m {mod}", 0.9)
        return BashResult(C.reproduce, f"python -m {mod}", 0.6)
    if code is not None or (script is None and seg.heredoc is not None) or script == "-":
        return _python_code(src, seg, ctx, "python -c" if code is not None else "python <<EOF")
    if script is None:
        sub = "python --version" if any(x in ("--version", "-V") for x in w) else "python"
        return BashResult(C.explore if "python --version" == sub else C.reproduce, sub, 0.9 if sub != "python" else 0.5)
    n = normalize_path(script) or script
    base = os.path.basename(n)
    if base == "setup.py":
        sub = rest[0] if rest else ""
        if sub in ("install", "develop", "build", "build_ext", "egg_info", "bdist_wheel", "sdist"):
            return BashResult(C.setup, f"python setup.py {sub}", 0.9)
        if sub == "test":
            return BashResult(C.test, "python setup.py test", 0.9)
        return BashResult(C.setup, "python setup.py", 0.6)
    if re.match(r"(runtests?|run_tests?|pytest|test_runner|run_unittests?)\.py$", base) or base == "manage.py" and rest[:1] == ["test"]:
        return BashResult(C.test, f"python {base}", 0.9, [FileRef(path=n, mode="run")] if looks_like_path(n) else [])
    if base == "manage.py":
        sub = rest[0] if rest else ""
        cat = C.setup if sub in ("migrate", "makemigrations", "collectstatic", "createsuperuser", "syncdb") else C.reproduce
        return BashResult(cat, f"manage.py {sub}", 0.6)
    fr = [f for f in [fref(script, "run")] if f]
    if ctx.has(n) or ctx.has(script):  # criado pelo agente → reproduce (mesmo com nome test_*)
        return BashResult(C.reproduce, f"python {base}", 0.9, fr)
    if REPRO_NAME.match(base) or "/tmp/" in script:
        return BashResult(C.reproduce, f"python {base}", 0.9, fr)
    if TESTY.search(n) or base.startswith("test"):
        return BashResult(C.test, f"python {base}", 0.9, fr)
    return BashResult(C.reproduce, f"python {base}", 0.6, fr)


def _python_code(src: str, seg: Seg, ctx: Ctx, sub: str) -> BashResult:
    targets = [a or b for a, b in PY_WRITE_OPEN.findall(src)] + [a or b for a, b in PY_WRITE_FN.findall(src)]
    reads = re.findall(r"open\(\s*[rf]?['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]r[b+]*['\"])?\s*\)", src)
    files = [f for f in (fref(t, "edit") for t in targets if not t.isidentifier()) if f]
    files += [f for f in (fref(t, "read") for t in reads if t not in targets) if f]
    if targets:
        lit = [t for t in targets if not t.isidentifier() and "." not in t.split("/")[0] or "/" in t or "." in t]
        known = [t for t in targets if looks_like_path(t)]
        if known and all(is_repro_path(t, ctx) for t in known):
            return BashResult(C.reproduce, sub + " (escreve script)", 0.9, files, [normalize_path(t) or t for t in known])
        if known:
            return BashResult(C.edit, sub + " (escreve arquivo)", 0.9, files, [normalize_path(t) or t for t in known])
        return BashResult(C.edit, sub + " (escreve arquivo)", 0.6, files)
    return BashResult(C.reproduce, sub, 0.9, files)


# ----------------------------------------------------------------------------- classificação de um segmento
def _positional(words: list[str], skip_flags_with_arg: set[str] = frozenset()) -> list[str]:
    out, i = [], 1
    while i < len(words):
        w = words[i]
        if w == "--":
            out += words[i + 1:]
            break
        if w in skip_flags_with_arg:
            i += 2; continue
        if w.startswith("-") and w != "-":
            i += 1; continue
        out.append(w); i += 1
    return out


def _files(words: list[str], mode: str, skip_first: bool = False, flag_args=frozenset()) -> list[FileRef]:
    pos = _positional(words, set(flag_args))
    pos = pos[1:] if skip_first else pos
    return [f for f in (fref(p, mode) for p in pos) if f]


def _git(words: list[str]) -> BashResult:
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in ("-C", "-c") else 1
    sub = words[i] if i < len(words) else ""
    rest = words[i + 1:]
    if sub == "grep":
        return BashResult(C.search, "git grep", 0.9, _files(words[i:], "read", skip_first=True))
    if sub == "checkout" and "--" in rest:
        return BashResult(C.edit, "git checkout --", 0.9, [f for f in (fref(p, "edit") for p in rest[rest.index("--") + 1:]) if f])
    if sub in ("apply", "am", "restore"):
        return BashResult(C.edit, f"git {sub}", 0.9, [f for f in (fref(p, "edit") for p in rest if not p.startswith("-")) if f])
    if sub == "reset" and "--hard" in rest or sub in ("revert", "cherry-pick", "merge", "rebase", "pull", "clean"):
        return BashResult(C.edit, f"git {sub}", 0.6)
    if sub == "stash" and rest[:1] in (["pop"], ["apply"], ["drop"]):
        return BashResult(C.edit, "git stash pop", 0.6)
    if sub in ("diff", "show", "log", "blame"):
        files = []
        if "--" in rest:
            files = [f for f in (fref(p, "read") for p in rest[rest.index("--") + 1:]) if f]
        else:
            files = [f for f in (fref(p, "read") for p in rest if not p.startswith("-")) if f]
        return BashResult(C.vcs, f"git {sub}", 0.9, files)
    if sub in GIT_VCS or sub in ("reset", "checkout", "switch"):
        return BashResult(C.vcs, f"git {sub}".strip(), 0.9)
    return BashResult(C.vcs, f"git {sub}".strip(), 0.6)


def _is_test_target(words: list[str]) -> bool:
    return any(re.search(r"(^|[/_.-])(tests?|spec|check|lint)\b", w) for w in words[1:3])


def strip_prefix(words: list[str]) -> list[str]:
    """Remove VAR=x, sudo/env/timeout N…, e palavras de controle (then/do/if…) do início."""
    words = list(words)
    while words:
        w = words[0]
        if w in CTRL_PREFIX:
            words.pop(0)
        elif re.match(r"^[A-Za-z_]\w*=", w):
            words.pop(0)
        elif w in WRAPPERS:
            words.pop(0)
            while words and (words[0].startswith("-") or re.fullmatch(r"\d+[smhd]?", words[0]) or re.match(r"^[A-Za-z_]\w*=", words[0])):
                words.pop(0)
        else:
            break
    return words


def _exe_name(w: str) -> str:
    return os.path.basename(w) if "/" in w and not w.startswith("./") else w


def executables(cmd: str) -> list[str]:
    """Todos os executáveis do comando (1 por segmento/estágio de pipe), sem cd/export e palavras de controle."""
    out: list[str] = []
    for seg in parse_segments(cmd or ""):
        for st in [seg, *seg.pipe_next]:
            w = strip_prefix(st.words)
            if w and w[0] not in CTRL and w[0] not in NAV:
                out.append(_exe_name(w[0]))
    return out


def last_exe(cmd: str) -> str | None:
    """Executável que define o exit code do comando: último estágio do último segmento não-neutro."""
    last = None
    for seg in parse_segments(cmd or ""):
        st = [seg, *seg.pipe_next][-1]
        w = strip_prefix(st.words)
        if w and w[0] not in CTRL and w[0] not in NAV:
            last = _exe_name(w[0])
    return last


def classify_seg(seg: Seg, ctx: Ctx, depth: int = 0) -> BashResult:
    words = strip_prefix(seg.words)
    if not words:
        return _finish_redirects(BashResult(C.setup, "env", 0.9), seg, ctx)
    exe_raw = words[0]
    if exe_raw in CTRL:  # `for x in …`, `done`, `fi`: sem efeito próprio
        return BashResult(C.setup, "ctl", 0.9)
    exe = os.path.basename(exe_raw) if "/" in exe_raw and not exe_raw.startswith("./") else exe_raw
    s2 = Seg(words, seg.text, seg.redirects, seg.heredoc, seg.pipe_next)
    r = _classify_exe(exe, words, s2, ctx, depth)
    return _finish_redirects(r, seg, ctx)


def _finish_redirects(r: BashResult, seg: Seg, ctx: Ctx) -> BashResult:
    """`> f`, `>> f`, `tee f` no segmento ou em estágios do pipe → edit (alvo = script de reprodução?)."""
    reds = list(seg.redirects)
    for st in seg.pipe_next:
        reds += st.redirects
        if st.words and os.path.basename(st.words[0]) == "tee":
            reds += [(">", p) for p in _positional(st.words)]
    reds = [(op, t) for op, t in reds if looks_like_path(t) or t.startswith("/")]
    if not reds:
        return r
    tg = [normalize_path(t) or t for _, t in reds]
    for _, t in reds:
        f = fref(t, "edit")
        if f:
            f.created = True
            r.files.append(f)
    r.writes += tg
    if r.category is not C.edit:
        r.subcategory = f"{r.subcategory or ''} > {tg[0]}".strip()
        r.category, r.confidence = C.edit, max(r.confidence, 0.9)
    return r


def _classify_exe(exe: str, words: list[str], seg: Seg, ctx: Ctx, depth: int) -> BashResult:
    e = exe
    if e in ("bash", "sh", "zsh") and "-c" in words and depth < 2:
        i = words.index("-c")
        if i + 1 < len(words):
            return classify_command(words[i + 1], ctx, depth + 1)
    if e in ("python", "python3", "python2") or re.fullmatch(r"python3?\.\d+", e):
        return classify_python(seg, ctx)
    if e in ("ipython", "jupyter"):
        return BashResult(C.reproduce, e, 0.6)
    if e == "git":
        return _git(words)
    if e == "xargs":
        inner = [w for w in words[1:]]
        while inner and inner[0].startswith("-"):
            inner = inner[2:] if inner[0] in ("-I", "-n", "-P", "-d", "-L") else inner[1:]
        return classify_seg(Seg(inner, seg.text), ctx, depth + 1) if inner else BashResult(C.other, "xargs", 0.5)
    if e in NAV:
        if e == "cd" or e in ("pushd", "popd"):
            return BashResult(C.setup, "cd", 0.9)
        return BashResult(C.setup, e, 0.9)
    if e == "find":
        f = [w for w in words if w in ("-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-wholename")]
        paths = [w for w in words[1:] if not w.startswith("-")][:1]
        if "-delete" in words or ("-exec" in words and any(x in words for x in ("rm", "sed", "mv"))):
            return BashResult(C.edit, "find -delete/-exec", 0.6)
        if "-exec" in words and any(x in words for x in ("grep", "egrep", "rg")):
            return BashResult(C.search, "find -exec grep", 0.9)
        return BashResult(C.search if f else C.explore, "find -name" if f else "find", 0.9)
    if e in SEARCH:
        pos = _positional(words, {"-e", "-f", "-m", "-A", "-B", "-C", "--include", "--exclude", "--exclude-dir", "-g", "-t", "-T"})
        paths = pos[1:] if not any(w in ("-e", "-f") for w in words) else pos
        return BashResult(C.search, e, 0.9, [f for f in (fref(p, "read") for p in paths) if f])
    if e == "sed":
        inplace = any(w.startswith("-i") or w == "--in-place" for w in words[1:]) or any(re.fullmatch(r"-[a-zA-Z]*i[a-zA-Z]*", w) for w in words[1:])
        pos = _positional(words, {"-e", "-f"})
        files = pos if any(w in ("-e", "-f") for w in words) else pos[1:]
        mode = "edit" if inplace else "read"
        cat = C.edit if inplace else C.read
        return BashResult(cat, "sed -i" if inplace else ("sed -n" if "-n" in words else "sed"), 0.9, [f for f in (fref(p, mode) for p in files) if f])
    if e in ("perl", "ruby") and any(re.fullmatch(r"-[a-zA-Z]*[pn]?i[a-zA-Z]*", w) for w in words[1:3]):
        return BashResult(C.edit, f"{e} -i", 0.9)
    if e in ("awk", "gawk") and "-i" in words and "inplace" in " ".join(words):
        return BashResult(C.edit, "awk -i inplace", 0.9)
    if e in READ:
        flag_args = {"-n", "-c", "-d", "-f", "-F", "-v", "-k", "-t"} if e in ("head", "tail", "cut", "sort") else set()
        pos = _positional(words, flag_args)
        if e in ("awk", "gawk", "jq", "yq", "cut", "tr", "sqlite3"):
            pos = pos[1:] if e not in ("sqlite3",) else pos[:1]
        if e == "tr":
            pos = []
        return BashResult(C.read, e, 0.9 if e not in ("diff", "cmp", "md5sum", "sha256sum", "sha1sum") else 0.6,
                          [f for f in (fref(p, "read") for p in pos) if f])
    if e in EXPLORE:
        if e == "ls" and any(looks_like_path(w) and not w.endswith("/") and os.path.basename(w).count(".") for w in words[1:]):
            pass
        return BashResult(C.explore, e, 0.9 if e not in ("ps", "top", "pgrep", "lsof", "netstat", "ss", "ip", "ifconfig", "mount") else 0.6)
    if e in EDIT_EXE:
        return BashResult(C.edit, e, 0.9 if e in ("patch", "applypatch", "apply_patch") else 0.6, _files(words, "edit"))
    if e in ("cp", "mv"):
        pos = _positional(words)
        fl = [f for f in (fref(p, "read" if i < len(pos) - 1 and e == "cp" else "edit") for i, p in enumerate(pos)) if f]
        return BashResult(C.edit, e, 0.5, fl, [normalize_path(pos[-1]) or pos[-1]] if pos else [])
    if e in ("rm", "rmdir", "touch", "mkdir", "chmod", "chown", "ln"):
        pos = _positional(words)
        repro = all(is_repro_path(p, ctx) or p.startswith("/tmp") or ctx.has(p) for p in pos) if pos else True
        return BashResult(C.setup, e, 0.9 if (repro or e in ("mkdir", "chmod", "chown", "ln", "touch")) else 0.5)
    if e in ("pip", "pip3"):
        sub = words[1] if len(words) > 1 else ""
        return BashResult(C.explore if sub in ("show", "list", "freeze", "--version", "check", "index", "config") else C.setup, f"pip {sub}".strip(), 0.9)
    if e in ("conda", "mamba"):
        sub = words[1] if len(words) > 1 else ""
        return BashResult(C.explore if sub in ("list", "info", "search", "--version") else C.setup, f"{e} {sub}".strip(), 0.9)
    if e in ("npm", "yarn", "pnpm", "bun") or e == "npx":
        sub = words[1] if len(words) > 1 else ""
        if sub in ("test", "t", "lint", "check", "typecheck") or (sub == "run" and len(words) > 2 and re.match(r"(test|lint|check|typecheck)", words[2])):
            return BashResult(C.test, f"{e} {' '.join(words[1:3])}".strip(), 0.9)
        if e == "npx" and len(words) > 1 and words[1] in TEST_EXE | LINTERS:
            return BashResult(C.test, f"npx {words[1]}", 0.9)
        return BashResult(C.setup, f"{e} {sub}".strip(), 0.9 if sub in ("install", "i", "ci", "add", "update", "build", "init") else 0.6)
    if e == "make":
        tg = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
        if any(re.match(r"(test|check|tests|lint|ci|verify)", t) for t in tg):
            return BashResult(C.test, f"make {tg[0]}", 0.9)
        return BashResult(C.setup, f"make {tg[0] if tg else ''}".strip(), 0.6)
    if e in ("cargo", "go", "mvn", "gradle", "./gradlew", "gradlew", "dotnet", "bundle", "rake", "poetry", "uv", "pipenv", "gem"):
        sub = words[1] if len(words) > 1 else ""
        if sub in ("test", "check", "clippy", "verify", "vet", "lint", "spec"):
            return BashResult(C.test, f"{e} {sub}", 0.9)
        if e == "uv" and sub == "run" and len(words) > 2:
            return classify_seg(Seg(words[2:], seg.text), ctx, depth + 1)
        if e in ("poetry", "pipenv") and sub == "run" and len(words) > 2:
            return classify_seg(Seg(words[2:], seg.text), ctx, depth + 1)
        if e in ("cargo", "go") and sub == "run":
            return BashResult(C.reproduce, f"{e} run", 0.6)
        return BashResult(C.setup, f"{e} {sub}".strip(), 0.9 if sub in ("install", "build", "add", "get", "mod", "sync", "update") else 0.6)
    if e in TEST_EXE or re.match(r"(\./)?(run_?tests?|runtests?)(\.\w+)?$", os.path.basename(e)):
        pos = [re.sub(r"::.*", "", p) for p in _positional(words, {"-k", "-m", "-c", "-p", "-n", "--tb", "--maxfail", "-o"})]
        return BashResult(C.test, e if e != "python" else "pytest", 0.9, [f for f in (fref(p, "run") for p in pos) if f])
    if e in LINTERS:
        return BashResult(C.test, e, 0.6 if e in ("black", "isort", "autopep8", "yapf", "prettier", "pre-commit") else 0.9,
                          _files(words, "run"))
    if e in ("curl", "wget"):
        local = any(h in " ".join(words) for h in ("localhost", "127.0.0.1", "0.0.0.0"))
        return BashResult(C.test if local else C.setup, e, 0.5 if local else 0.6)
    if e in SETUP_EXE:
        return BashResult(C.setup, e, 0.9 if e not in ("docker", "service", "systemctl") else 0.6)
    if e in OTHER_EXE:
        if e in ("echo", "printf") and False:
            pass
        return BashResult(C.other, e, 0.9)
    if e in ("tee",):
        return BashResult(C.edit, "tee", 0.9, [f for f in (fref(p, "edit") for p in _positional(words)) if f], [normalize_path(p) or p for p in _positional(words)])
    if e in ("bash", "sh", "zsh", "source") or e in INTERP or e.startswith("./") or e.endswith((".sh", ".js", ".rb", ".pl")) \
            or e.startswith("/") and "/" in e[1:]:
        script = next((w for w in words[1:] if not w.startswith("-")), None) if e in INTERP else e
        base = os.path.basename(script or e)
        fr = [f for f in [fref(script, "run")] if f]
        if re.match(r"(run_?tests?|runtests?|test|check|lint)", base, re.I) and not ctx.has(script or ""):
            return BashResult(C.test, base, 0.9, fr)
        if REPRO_NAME.match(base) or (script and ctx.has(script)):
            return BashResult(C.reproduce, f"{e if e in INTERP else ''} {base}".strip(), 0.9, fr)
        return BashResult(C.reproduce, f"{e if e in INTERP else ''} {base}".strip(), 0.5, fr)
    # executável desconhecido: padrões no nome
    if re.search(r"(test|spec)", e):
        return BashResult(C.test, e, 0.6)
    if re.search(r"(lint|check|verify|valid)", e):
        return BashResult(C.test, e, 0.6)
    if re.search(r"(repro|demo|poc|exploit)", e):
        return BashResult(C.reproduce, e, 0.6)
    if re.search(r"(install|setup|build|compile|config)", e):
        return BashResult(C.setup, e, 0.6)
    return BashResult(C.other, e, 0.3)


# ----------------------------------------------------------------------------- texto curto do segmento
_WRAP_RE = re.compile(r"^\s*(?:[A-Za-z_]\w*=\S*\s+|sudo\s+(?:-\S+\s+)*|env\s+(?:-\S+\s+)*|nohup\s+|time\s+|command\s+|timeout\s+(?:-\S+\s+)*\d+[smhd]?\s+)")
_PATH_IN_CMD = re.compile(r"(?<![\w.])/(?:workspace/[^/\s]+|testbed|app|repo)/")


def clean_segment(text: str) -> str:
    """Segmento sem prefixos (env/sudo/timeout), sem `cd x &&` e sem /workspace/<repo>/, /testbed/…; 1ª linha, espaços colapsados."""
    t = re.sub(r"\s*<\s*__HD\d+__", "", text or "")
    t = t.split("\n", 1)[0] if "<<" in t else t
    for _ in range(6):
        n = _WRAP_RE.sub("", t, count=1)
        if n == t:
            break
        t = n
    t = re.sub(r"^\s*cd\s+\S+\s*(?:&&|;)\s*", "", t)
    t = _PATH_IN_CMD.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


# ----------------------------------------------------------------------------- comando completo
def classify_command(cmd: str, ctx: Ctx | None = None, depth: int = 0) -> BashResult:
    ctx = ctx or Ctx()
    cmd = (cmd or "").strip()
    if not cmd:
        return BashResult(C.other, "empty", 1.0, keys_only=True)
    segs = parse_segments(cmd)
    if not segs:
        return BashResult(C.other, None, 0.3)
    results: list[tuple[Seg, BashResult]] = [(s, classify_seg(s, ctx, depth)) for s in segs]
    # escreve um script e o executa no mesmo comando → reproduce (spec: `cat > f <<EOF … ; python f`)
    writes = {os.path.basename(w): w for _, r in results for w in r.writes}
    for s, r in results:
        for w in s.words[1:]:
            if os.path.basename(w) in writes and r.category in (C.reproduce, C.test) and is_repro_path(writes[os.path.basename(w)], ctx):
                for _, rr in results:
                    if rr.category is C.edit and set(rr.writes) <= set(writes.values()):
                        rr.category = C.reproduce
                        rr.subcategory = (rr.subcategory or "") + " (script de reprodução)"
    def _neutral(s: Seg) -> bool:
        return bool(s.words) and (s.words[0] in NAV or s.words[0] in CTRL)
    nav_only = all(_neutral(s) for s, _ in results)
    kept = [(s, r) for s, r in results if nav_only or not _neutral(s)]
    cat = pick_by_precedence([r.category for _, r in kept])
    chosen = next(r for _, r in kept if r.category is cat)
    out = BashResult(cat, "|".join(dict.fromkeys(r.subcategory for _, r in kept if r.subcategory)) or None,
                     chosen.confidence, [], [])
    chosen_seg = next(sg for sg, r in kept if r.category is cat)
    out.segment = clean_segment(chosen_seg.text)
    for _, r in results:
        for f in r.files:
            if f not in out.files:
                out.files.append(f)
        out.writes += r.writes
    return out
