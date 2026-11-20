"""Detectores automáticos (flags). Cada um é uma função (traj) -> traj que só acrescenta flags + `flag_details`.

Ignoram passos `keys` e `harness_protocol` (marcados à parte nas métricas). `run_detectors` zera as flags antes
(é determinístico e idempotente). Ver docs/decisions.md (Fase 4) para as exceções do `error`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from app.adapters.base import TRUNC_RE
from app.labeling.bash_parser import PREFIX_RE, last_exe
from app.schema import Step, Trajectory

IGNORED_SUB = {"keys", "harness_protocol"}
SKIP_ACTIONS = {"think", "submit", "message", "task_tracker"}
FOOTER_RE = re.compile(r"\n?\[(?:The command completed[^\]]*|Current working directory:[^\]]*|Python interpreter:[^\]]*|Command finished[^\]]*)\]")
# exit 1 que NÃO indica falha (sem match / diferente / condição falsa)
EXIT1_OK = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "zgrep", "diff", "cmp", "test", "[", "[[", "comm", "pgrep", "git-grep"}
NOEXIT_CODES = {-1}  # OpenHands: -1 = processo ainda rodando


def ignored(s: Step) -> bool:
    return s.subcategory in IGNORED_SUB


def add_flag(s: Step, flag: str, reason: str, ref: int | None = None) -> None:
    if flag not in s.flags:
        s.flags.append(flag)  # type: ignore[arg-type]
        s.flag_details[flag] = reason
        if ref is not None:
            s.flag_refs[flag] = ref


def clear_flags(traj: Trajectory) -> Trajectory:
    for s in traj.steps:
        s.flags, s.flag_details, s.flag_refs = [], {}, {}
    traj.meta.pop("loops", None)
    return traj


def _obs(s: Step) -> str:
    return s.observation.content if s.observation else ""


def norm_obs(text: str) -> str:
    return re.sub(r"\s+", " ", FOOTER_RE.sub("", text or "")).strip()


# ----------------------------------------------------------------------------- error
ERR_ANY = [
    (re.compile(r"Traceback \(most recent call last\)"), "Traceback"),
    (re.compile(r"command not found"), "command not found"),
    (re.compile(r"No such file or directory"), "No such file or directory"),
    (re.compile(r"\bSyntaxError\b"), "SyntaxError"),
    (re.compile(r"\bModuleNotFoundError\b"), "ModuleNotFoundError"),
    (re.compile(r"Permission denied"), "Permission denied"),
    (re.compile(r"(?m)^[ \t]*(?:error|Error|ERROR):"), "error:"),
    (re.compile(r"(?m)^fatal:"), "fatal:"),
    (re.compile(r"introduced new syntax error"), "syntax error na edição"),
]
EDITOR_ERR = [
    (re.compile(r"No replacement was performed"), "No replacement was performed"),
    (re.compile(r"did not appear verbatim"), "did not appear verbatim"),
    (re.compile(r"Multiple occurrences of old_str"), "Multiple occurrences of old_str"),
    (re.compile(r"(?m)^(?:ERROR:\s*)?Invalid [`\w]"), "Invalid …"),
    (re.compile(r"does not exist\. Please provide a valid path"), "path inexistente"),
    (re.compile(r"Cannot overwrite files using command `create`"), "create sobre arquivo existente"),
    (re.compile(r"(?m)^Parameter `[^`]+` is required"), "parâmetro obrigatório ausente"),
    (re.compile(r"is a directory and only the `view` command"), "diretório: só view"),
    (re.compile(r"should be within the range"), "intervalo fora do arquivo"),
]
SHELL_ERR_LINE = re.compile(r"^(?:[\w./-]+: (?:.*)(?:No such file or directory|Permission denied|command not found|cannot access|Is a directory|not a directory|"
                            r"cannot open|invalid option|unrecognized option)|(?:error|Error|ERROR|fatal):)")
CMD_NOT_FOUND = re.compile(r"command not found|No such file or directory|file or directory not found")


# ----------------------------------------------------------------------------- pytest: códigos de saída
PYTEST_CMD = re.compile(r"(?:^|[\s/;&|(])(?:py\.test|pytest)\b|-m\s+pytest\b")
PYTEST_USAGE_TXT = re.compile(r"(?m)^ERROR: (?:usage:|file or directory not found|not found:)|unrecognized arguments|Interrupted: \d+ errors? during collection")
PYTEST_NO_TESTS = re.compile(r"no tests ran|collected 0 items")
PYTEST_EXIT = {2: "execução interrompida (ex.: erro de coleta)", 3: "erro interno do pytest", 4: "erro de uso/coleta"}


def is_pytest(s: Step) -> bool:
    a = s.action
    cmd = " ".join(c.get("keystrokes", "") for c in a.args["commands"]) if a.tool == "keys" and a.args.get("commands") else (a.command or a.raw or "")
    return bool(PYTEST_CMD.search(cmd))


def pytest_verdict(code: int) -> str:
    """Códigos do pytest: 0 passou · 1 testes falharam · 5 nenhum teste coletado · 2/3/4 (e qualquer outro) = a execução em si falhou."""
    return {0: "pass", 1: "fail", 5: "none"}.get(code, "error")


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln
    return ""


def detect_error(traj: Trajectory) -> Trajectory:
    for s in traj.steps:
        if ignored(s) or s.observation is None or s.category in ("think", "submit"):
            continue
        o, cat = s.observation, s.category
        text = o.content or ""
        if o.exit_code is not None:
            code = o.exit_code
            if code in NOEXIT_CODES:
                continue
            if cat == "test":
                if code in (126, 127) or CMD_NOT_FOUND.search(text[:500]):
                    add_flag(s, "error", f"exit code {code}" if code else "comando de teste não executou")
                elif is_pytest(s) and pytest_verdict(code) == "error":  # a execução do pytest falhou: não é "teste falhou"
                    add_flag(s, "error", f"pytest exit code {code}: {PYTEST_EXIT.get(code, 'saída anormal')}")
                continue
            if code == 0:
                continue
            exe = last_exe(s.action.command or "") if s.action.tool in ("bash", "keys", "ipython") else None
            if code == 1 and exe in EXIT1_OK:
                continue  # grep/diff/test sem match ou diferente não é falha
            add_flag(s, "error", f"exit code {code}")
            continue
        # --- sem exit code (SWE-smith, SWE-agent, Terminus2, eventos sem metadata): padrões de texto
        if s.action.tool in ("editor", "swe_cmd"):
            for rx, why in EDITOR_ERR:
                if rx.search(text[:3000]):
                    add_flag(s, "error", f"editor: {why}")
                    break
            else:
                for rx, why in ERR_ANY:
                    if rx.search(_first_line(text)):
                        add_flag(s, "error", f"padrão: {why}")
                        break
            continue
        if cat == "test":
            if CMD_NOT_FOUND.search(text[:500]):
                add_flag(s, "error", "comando de teste não executou")
            elif is_pytest(s) and PYTEST_USAGE_TXT.search(text):
                add_flag(s, "error", "pytest: erro de uso/coleta (equivale a exit 2/4)")
            continue
        if cat in ("read", "search", "explore", "vcs"):  # a saída é conteúdo: só vale erro no estilo `ferramenta: …` na 1ª linha
            line = _first_line(text)
            if SHELL_ERR_LINE.match(line):
                add_flag(s, "error", "padrão: " + next((why for rx, why in ERR_ANY if rx.search(line)), "erro de shell"))
            continue
        for rx, why in ERR_ANY:
            if rx.search(text[:20000]):
                add_flag(s, "error", f"padrão: {why}")
                break
    return traj


# ----------------------------------------------------------------------------- test_fail / test_pass
FAIL_RX = [
    (re.compile(r"\b(\d+) (?:failed|failures?)\b"), "failed"),
    (re.compile(r"(?m)^FAILED\b"), "FAILED"),
    (re.compile(r"\bFAILED \((?:failures|errors)"), "FAILED (unittest)"),
    (re.compile(r"(?m)^=+ .*\bERRORS?\b.* =+$"), "ERRORS"),
    (re.compile(r"(?m)^ERROR collecting"), "ERROR collecting"),
    (re.compile(r"(?m)^(?:FAIL|ERROR): \w+"), "FAIL/ERROR: teste"),
    (re.compile(r"\b\d+ errors? in [\d.]+s"), "N errors"),
    (re.compile(r"(?m)^E\s+\w*(?:Error|Exception)\b"), "exceção no teste"),
    (re.compile(r"no tests ran"), "no tests ran"),
]
PASS_RX = [re.compile(r"\b(\d+) passed\b"), re.compile(r"(?m)^OK(?: \(.*\))?$"), re.compile(r"(?m)^Ran \d+ tests? in .*\n+OK")]


def detect_test_result(traj: Trajectory) -> Trajectory:
    """pytest segue seus códigos de saída: 1 = test_fail · 0 = test_pass · 5 = sem flag · 2/3/4/outros = `error` (ver detect_error).
    unittest, tox e demais executores: qualquer exit ≠ 0 = test_fail (regra anterior)."""
    for s in traj.steps:
        if ignored(s) or s.category != "test" or s.observation is None:
            continue
        o = s.observation
        text = o.content or ""
        code = o.exit_code
        if code in NOEXIT_CODES:
            continue
        py = is_pytest(s)
        why = None
        if py and code not in (None, 0):
            if pytest_verdict(code) == "fail":
                why = f"pytest exit code {code}"
            else:
                continue  # 5 = nada coletado (sem flag); 2/3/4/outros = error
        elif py and code is None and (PYTEST_NO_TESTS.search(text) or PYTEST_USAGE_TXT.search(text)):
            continue  # sem exit code: "no tests ran" (= exit 5) e erro de uso/coleta (= exit 2/4) não são "teste falhou"
        elif code not in (None, 0):
            why = f"exit code {code}"
        else:
            for rx, name in FAIL_RX:
                m = rx.search(text)
                if m and not (name == "failed" and m.group(1) == "0"):
                    why = f"padrão: {name}"
                    break
        if why:
            add_flag(s, "test_fail", why)
        elif code == 0 or any(rx.search(text) for rx in PASS_RX):
            add_flag(s, "test_pass", f"exit code 0" if code == 0 else "padrão: passed/OK")
    return traj


# ----------------------------------------------------------------------------- repeated
def _h(x) -> str | None:
    return hashlib.sha1(str(x).encode()).hexdigest()[:10] if x else None


PATH_PREFIX_IN_CMD = re.compile(r"(?<![\w.])/(?:workspace/[^/\s]+|testbed|app|repo)/")


def _collapse(cmd: str) -> str:
    cmd = PATH_PREFIX_IN_CMD.sub("", cmd or "")
    cmd = re.sub(r"^\s*cd\s+\S+\s*&&\s*", "", cmd)
    return re.sub(r"\s+", " ", cmd).strip()


def action_key(s: Step):
    a = s.action
    if a.tool in SKIP_ACTIONS or ignored(s):
        return None
    if a.tool == "editor":
        p = a.args.get("path") if isinstance(a.args.get("path"), str) else ""
        return ("editor", a.command, PREFIX_RE.sub("", p or ""), json.dumps(a.args.get("view_range")), _h(a.args.get("old_str")),
                _h(a.args.get("new_str")), _h(a.args.get("file_text")))
    if a.tool in ("bash", "keys", "ipython"):
        if a.tool == "keys" and a.args.get("commands"):
            cmd = " ⏎ ".join(c.get("keystrokes", "") for c in a.args["commands"])
        else:
            cmd = a.command or a.raw or ""
        cmd = _collapse(cmd)
        return (a.tool, cmd) if cmd else None
    raw = _collapse(str(a.args.get("line") or a.raw or a.command or ""))
    return (a.tool, a.command, raw) if raw else None


def detect_repeated(traj: Trajectory) -> Trajectory:
    """Ação normalizada idêntica a uma anterior. Refinamento: para passos que observam/executam (não `edit`), repetir DEPOIS de uma
    edição não conta (o estado mudou: ex. rodar o mesmo teste de novo)."""
    last_seen: dict = {}
    edit_marks: list[int] = []  # idx de cada passo edit
    for s in traj.steps:
        if s.category == "edit" and not ignored(s):
            edit_marks.append(s.idx)
        k = action_key(s)
        if k is None:
            continue
        prev = last_seen.get(k)
        if prev is not None:
            changed = s.category != "edit" and any(prev < e < s.idx for e in edit_marks)
            if not changed:
                add_flag(s, "repeated", f"igual ao passo {prev}", prev)
        last_seen[k] = s.idx
    return traj


# ----------------------------------------------------------------------------- no_new_info
SED_RANGE = re.compile(r"sed\s+-n\s+['\"]?(\d+),(\d+)p")
ABBREVIATED = "<NOTE>This file is too large to display entirely"
EMPTY_OUT = re.compile(r"did not produce any output|^\(?no output\)?\.?$|^$", re.I)
INF = 10**9
WHOLE = (1, INF)
UNKNOWN = None


def _as_int(x) -> int | None:
    try:
        return int(str(x).strip())
    except ValueError:
        return None


def _range(s: Step):
    """(início, fim) lido; WHOLE = arquivo inteiro; UNKNOWN (None) = intervalo ilegível (nunca conta como cobertura)."""
    vr = s.action.args.get("view_range")
    if isinstance(vr, str):  # xml/ticks entregam "[10, 20]" como string
        try:
            vr = json.loads(vr)
        except ValueError:
            return UNKNOWN
    if isinstance(vr, (list, tuple)):
        if len(vr) != 2:
            return UNKNOWN
        a, b = _as_int(vr[0]), _as_int(vr[1])
        if a is None or b is None:
            return UNKNOWN
        return (a, INF if b == -1 else b)
    m = SED_RANGE.search(s.action.command or "")
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return WHOLE if (s.action.tool == "editor" or s.action.command) else UNKNOWN


def _covers(prior: tuple[int, int], new: tuple[int, int]) -> bool:
    return prior[0] <= new[0] and prior[1] >= new[1]


def detect_no_new_info(traj: Trajectory) -> Trajectory:
    """(a) observação idêntica (≥ 20 chars, fora de "sem saída") a uma anterior de read/search/explore;
    (b) releitura de um trecho já COBERTO por uma leitura anterior do mesmo arquivo sem edição nesse arquivo desde então.
    Cobertura exige intervalo legível (view_range lista/string/sed -n) e leitura completa e não abreviada: o `<NOTE>This file is too
    large…` do SWE-agent mostra só um resumo, então ver um trecho depois dele traz informação nova."""
    seen_obs: dict[str, int] = {}
    reads: dict[str, list[tuple[tuple[int, int], int]]] = {}  # path -> [((ini, fim), idx)]
    for s in traj.steps:
        if ignored(s):
            continue
        for f in s.files:  # edição invalida as leituras anteriores daquele arquivo
            if f.mode == "edit":
                reads.pop(f.path, None)
        if s.category not in ("read", "search", "explore") or s.observation is None:
            continue
        o = s.observation
        # (b) releitura coberta
        if s.category == "read" and s.files:
            f = next((f for f in s.files if f.mode == "read"), None)
            rg = _range(s) if f else UNKNOWN
            if f and rg is not UNKNOWN and "error" not in s.flags:  # observação de erro (ex.: view_range inválido) não é releitura redundante
                hit = next((i for prior, i in reads.get(f.path, []) if _covers(prior, rg)), None)
                if hit is not None:
                    add_flag(s, "no_new_info", f"releitura de {f.path} sem edição desde o passo {hit}", hit)
                if ABBREVIATED not in (o.content or "")[:200] and not o.truncated and "error" not in s.flags:
                    reads.setdefault(f.path, []).append((rg, s.idx))
        # (a) observação idêntica
        n = norm_obs(o.content)
        if len(n) >= 20 and not EMPTY_OUT.search(n):
            if n in seen_obs and "no_new_info" not in s.flags:
                add_flag(s, "no_new_info", f"observação idêntica ao passo {seen_obs[n]}", seen_obs[n])
            seen_obs.setdefault(n, s.idx)
    return traj


# ----------------------------------------------------------------------------- loop
FAILED_ID = re.compile(r"(?m)^(?:FAILED|ERROR|FAIL)[:\s]+(?!\()(\S+(?: \([^)\n]+\))?)")  # pytest `FAILED t::x` e unittest `FAIL: test_x (mod.Class)`
E_LINE = re.compile(r"(?m)^E\s+(.+)$")


def error_signature(s: Step) -> str:
    """Assinatura do erro de um passo test_fail: ids dos testes que falharam; senão as linhas `E …`; senão o fim da saída (sem números)."""
    t = s.observation.content if s.observation else ""
    ids = sorted(set(FAILED_ID.findall(t)))
    if ids:
        return "ids:" + ",".join(ids)
    es = E_LINE.findall(t)[:3]
    if es:
        return "E:" + "|".join(re.sub(r"\d+", "#", e)[:80] for e in es)
    return "fim:" + re.sub(r"\d+", "#", norm_obs(t)[-160:])


def _loop_token(s: Step):
    """Alvo normalizado: a AÇÃO normalizada (ferramenta + comando + arquivo + intervalo + trecho editado). Trechos/intervalos diferentes do
    mesmo arquivo são alvos diferentes; só a repetição da mesma ação conta."""
    k = action_key(s)
    return (s.category, k if k is not None else s.action.tool)


def _loop_label(s: Step) -> str:
    a = s.action
    if a.tool == "editor":
        vr = a.args.get("view_range")
        return f"{a.command} {os.path.basename(str(a.args.get('path', '')))}" + (f" {vr}" if vr else "")
    return (s.summary or a.command or a.raw or a.tool).split("\n")[0][:40]


def detect_loop(traj: Trajectory) -> Trajectory:
    """(1) n-grama (n = 2..4) de AÇÕES NORMALIZADAS idênticas repetido ≥ 3 vezes seguidas;
    (2) ciclo edit → test_fail no mesmo arquivo ≥ 3 vezes COM O MESMO ERRO (mesma assinatura de falha)."""
    loops: list[dict] = []
    # sem alvo normalizado não há laço: message/think/task_tracker/submit ficam fora (como keys/harness)
    live = [s for s in traj.steps if not ignored(s) and s.action.tool not in SKIP_ACTIONS]
    seq = [(s.idx, _loop_token(s)) for s in live]
    labels = {s.idx: f"{s.category}:{_loop_label(s)}" for s in live}
    i = 0
    while i + 6 <= len(seq):
        for n in (2, 3, 4):
            if i + 3 * n > len(seq):
                continue
            pat = [t for _, t in seq[i:i + n]]
            reps, j = 1, i + n
            while j + n <= len(seq) and [t for _, t in seq[j:j + n]] == pat:
                reps += 1
                j += n
            if reps >= 3:
                loops.append({"kind": "ngram", "n": n, "reps": reps, "range": [seq[i][0], seq[j - 1][0]], "pattern": [labels[x] for x, _ in seq[i:i + n]]})
                i = j - 1
                break
        i += 1
    # ciclo edit → test_fail no mesmo arquivo, mesmo erro, ≥ 3 vezes
    edited_since_test: dict[str, int] = {}  # arquivo → 1ª edição desde o último teste
    cycles: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for s in live:
        if s.category == "edit":
            for f in s.files:
                if f.mode == "edit":
                    edited_since_test.setdefault(f.path, s.idx)
        elif s.category == "test" and s.observation is not None and "test_fail" in s.flags:
            sig = error_signature(s)
            for p, e_idx in edited_since_test.items():
                cycles.setdefault((p, sig), []).append((e_idx, s.idx))
            edited_since_test = {}
        elif s.category == "test" and "test_pass" in s.flags:
            edited_since_test = {}
    for (p, sig), cs in cycles.items():
        if len(cs) >= 3:
            loops.append({"kind": "edit_test_fail", "file": p, "cycles": len(cs), "range": [min(c[0] for c in cs), max(c[1] for c in cs)],
                          "signature": sig[:120], "tests": [c[1] for c in cs]})
    for lp in loops:
        a, b = lp["range"]
        why = (f"ciclo {lp['pattern']} ×{lp['reps']}" if lp["kind"] == "ngram" else f"edit→test_fail ×{lp['cycles']} em {lp['file']} (mesmo erro)")
        for s in live:
            if a <= s.idx <= b:
                if lp["kind"] == "edit_test_fail" and not (s.idx in lp["tests"] or (s.category == "edit" and any(f.path == lp["file"] for f in s.files))):
                    continue
                add_flag(s, "loop", f"{why} [{a},{b}]")
    if loops:
        traj.meta["loops"] = loops
    return traj


# ----------------------------------------------------------------------------- truncated (conferência)
def detect_truncated(traj: Trajectory) -> Trajectory:
    for s in traj.steps:
        o = s.observation
        if o is None or ignored(s):
            continue
        if o.truncated or TRUNC_RE.search(o.content[:400] + o.content[-400:]):
            add_flag(s, "truncated", "marcador de truncamento na observação")
    return traj


def run_detectors(traj: Trajectory) -> Trajectory:
    """Ordem importa: test_fail/test_pass antes do loop (que os usa)."""
    clear_flags(traj)
    for fn in (detect_error, detect_test_result, detect_repeated, detect_no_new_info, detect_loop, detect_truncated):
        fn(traj)
    return traj
