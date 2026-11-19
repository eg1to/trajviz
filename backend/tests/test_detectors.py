"""Detectores: trajetórias sintéticas pequenas (positivos e negativos) + 1 fixture real por formato."""
import pytest

from app.adapters.detect import parse_any
from app.analysis.detectors import detect_loop, norm_obs, run_detectors
from app.labeling import label_trajectory
from app.schema import Action, FileRef, Observation, Step, Trajectory
from tests.conftest import CTB, FX


def S(i, cat="read", tool="bash", cmd=None, obs=None, code=None, files=(), sub=None, args=None, native=None, truncated=False):
    a = Action(tool=tool, tool_native=native or tool, command=cmd, args=args or ({"command": cmd} if cmd else {}), raw=cmd or "")
    o = Observation(content=obs, exit_code=code, chars=len(obs), truncated=truncated) if obs is not None else None
    return Step(idx=i, action=a, observation=o, category=cat, subcategory=sub, files=[FileRef(path=p, mode=m) for p, m in files])


def T(*steps):
    return Trajectory(id="t", source_format="x", steps=list(steps))


def flags(traj, i):
    return set(traj.steps[i].flags)


# ----------------------------------------------------------------------------- error
@pytest.mark.parametrize("cmd,code,expected", [
    ("python reproduce.py", 1, True), ("python reproduce.py", 2, True), ("ls /nope", 2, True), ("grep foo a.py", 1, False),
    ("rg foo", 1, False), ("diff a b", 1, False), ("test -f x", 1, False), ("[ -f x ]", 1, False), ("cd /x && grep foo a.py", 1, False),
    ("grep foo a.py", 2, True),  # exit 2 = erro de verdade do grep
    ("some_cmd", 127, True), ("python x.py", 0, False), ("sleep 100", -1, False),
])
def test_error_exit_code(cmd, code, expected):
    t = run_detectors(T(S(0, "reproduce", cmd=cmd, obs="out", code=code)))
    assert ("error" in flags(t, 0)) == expected


def test_error_exit_code_reason():
    t = run_detectors(T(S(0, "reproduce", cmd="python x.py", obs="boom", code=3)))
    assert t.steps[0].flag_details["error"] == "exit code 3"


@pytest.mark.parametrize("cat,obs,expected", [
    ("reproduce", "Traceback (most recent call last):\n  File x\nValueError", True),
    ("reproduce", "bash: foo: command not found", True),
    ("reproduce", "python: can't open file 'x.py': [Errno 2] No such file or directory", True),
    ("reproduce", "  File \"a.py\", line 1\n    x =\nSyntaxError: invalid syntax", True),
    ("reproduce", "ModuleNotFoundError: No module named 'foo'", True),
    ("setup", "bash: /root/x: Permission denied", True),
    ("reproduce", "ok\nerror: something broke", True),
    ("reproduce", "all good, 0 errors found", False),
    ("reproduce", "Hello world", False),
    ("read", "cat: nope.py: No such file or directory", True),
    ("read", "def f():\n    # Traceback (most recent call last) appears in the docs\n    pass", False),  # conteúdo de arquivo ≠ erro
    ("read", "class SyntaxError(Exception):\n    pass", False),
    ("search", "src/a.py:3:No such file or directory", False),
    ("explore", "ls: cannot access 'x': No such file or directory", True),
])
def test_error_text_patterns_without_exit_code(cat, obs, expected):
    t = run_detectors(T(S(0, cat, cmd="x", obs=obs)))
    assert ("error" in flags(t, 0)) == expected, obs


@pytest.mark.parametrize("obs,expected", [
    ("No replacement was performed, old_str `x` did not appear verbatim in /a.py.", True),
    ("Invalid `view_range`: [5, 1]. Its first element should be within the range of lines", True),
    ("ERROR:\nInvalid `path` parameter: /x. The path /x does not exist. Please provide a valid path.", True),
    ("No replacement was performed. Multiple occurrences of old_str `a` in lines [1, 2].", True),
    ("The file /a.py has been edited. Here's the result of running `cat -n`", False),
    ("Here's the result of running `cat -n` on /a.py:\n     1\tdef f(): pass", False),
])
def test_error_editor_messages(obs, expected):
    t = run_detectors(T(S(0, "edit", tool="editor", cmd="str_replace", obs=obs, args={"command": "str_replace", "path": "/a.py"})))
    assert ("error" in flags(t, 0)) == expected


def test_error_ignores_keys_and_harness_and_missing_obs():
    t = run_detectors(T(S(0, "other", cmd="C-c", obs="Traceback (most recent call last)", code=1, sub="keys"),
                        S(1, "submit", obs="**STOP! BEFORE SUBMITTING** error: x", sub="harness_protocol"),
                        S(2, "reproduce", cmd="python x.py")))
    assert all(not s.flags for s in t.steps)


# ----------------------------------------------------------------------------- test_fail / test_pass
@pytest.mark.parametrize("obs,code,expected", [
    ("=== 3 failed, 2 passed in 1.2s ===", None, "test_fail"), ("FAILED tests/test_a.py::test_x - assert 1 == 2", None, "test_fail"),
    ("=== 5 passed in 0.5s ===", None, "test_pass"), ("=== 5 passed, 0 failed in 0.5s ===", None, "test_pass"),
    ("Ran 3 tests in 0.1s\n\nOK", None, "test_pass"), ("Ran 3 tests in 0.1s\n\nFAILED (failures=1)", None, "test_fail"),
    ("ERROR collecting tests/test_a.py\nImportError", None, "test_fail"), ("collected 0 items\n\nno tests ran in 0.01s", None, "test_fail"),
    ("whatever", 0, "test_pass"), ("whatever", 1, "test_fail"), ("whatever", 5, "test_fail"), ("whatever", None, None),
    ("E   AssertionError: x", None, "test_fail"), ("running", -1, None),
])
def test_test_flags(obs, code, expected):
    t = run_detectors(T(S(0, "test", cmd="pytest", obs=obs, code=code)))
    got = flags(t, 0) & {"test_fail", "test_pass"}
    assert got == ({expected} if expected else set())


def test_failing_test_is_not_a_command_error_but_missing_runner_is():
    t = run_detectors(T(S(0, "test", cmd="pytest", obs="1 failed", code=1), S(1, "test", cmd="pytest", obs="bash: pytest: command not found", code=127)))
    assert flags(t, 0) == {"test_fail"} and {"error", "test_fail"} <= flags(t, 1)


# ----------------------------------------------------------------------------- repeated
def test_repeated_same_action_and_reason():
    t = run_detectors(T(S(0, "search", cmd="grep -rn foo src"), S(1, "read", cmd="cat a.py"), S(2, "search", cmd="grep  -rn   foo src")))
    assert "repeated" in flags(t, 2) and t.steps[2].flag_details["repeated"] == "igual ao passo 0" and "repeated" not in flags(t, 1)


def test_repeated_normalizes_paths_and_cd_prefix():
    t = run_detectors(T(S(0, "read", cmd="cat /testbed/src/a.py"), S(1, "read", cmd="cd /testbed && cat src/a.py")))
    assert "repeated" in flags(t, 1)


def test_repeated_editor_range_matters():
    v = lambda i, r: S(i, "read", tool="editor", cmd="view", args={"command": "view", "path": "/testbed/a.py", "view_range": r}, obs="x")  # noqa: E731
    t = run_detectors(T(v(0, [1, 10]), v(1, [20, 30]), v(2, [1, 10])))
    assert flags(t, 1) == set() and "repeated" in flags(t, 2)


def test_repeated_skips_think_submit_message():
    mk = lambda i, tool: S(i, "think", tool=tool, cmd=None)  # noqa: E731
    t = run_detectors(T(mk(0, "think"), mk(1, "think"), S(2, "submit", tool="submit"), S(3, "submit", tool="submit"), mk(4, "message"), mk(5, "message")))
    assert all("repeated" not in s.flags for s in t.steps)


def test_repeated_rerun_after_edit_is_not_repeated_but_without_edit_is():
    t = run_detectors(T(S(0, "test", cmd="pytest -x", obs="1 failed", code=1), S(1, "edit", tool="editor", cmd="str_replace", args={"command": "str_replace", "path": "a.py", "old_str": "a", "new_str": "b"}),
                        S(2, "test", cmd="pytest -x", obs="1 passed", code=0), S(3, "test", cmd="pytest -x", obs="1 passed", code=0)))
    assert "repeated" not in flags(t, 2) and "repeated" in flags(t, 3)


def test_repeated_identical_edit_twice_even_with_edit_between():
    e = lambda i: S(i, "edit", tool="editor", cmd="str_replace", args={"command": "str_replace", "path": "a.py", "old_str": "a", "new_str": "b"})  # noqa: E731
    t = run_detectors(T(e(0), e(1)))
    assert "repeated" in flags(t, 1)


# ----------------------------------------------------------------------------- no_new_info
LONG = "line of output that is long enough to matter. " * 3


def test_no_new_info_identical_observation():
    t = run_detectors(T(S(0, "search", cmd="grep -rn a src", obs=LONG), S(1, "read", cmd="cat b.py", obs="different content here, long enough to compare"),
                        S(2, "search", cmd="grep -rn b src", obs=LONG + "\n[The command completed with exit code 0.]\n")))
    assert "no_new_info" in flags(t, 2) and t.steps[2].flag_details["no_new_info"] == "observação idêntica ao passo 0" and not flags(t, 1) & {"no_new_info"}


def test_no_new_info_short_or_empty_observations_do_not_match():
    t = run_detectors(T(S(0, "search", cmd="grep a x", obs=""), S(1, "search", cmd="grep b x", obs=""), S(2, "read", cmd="cat a", obs="ok"), S(3, "read", cmd="cat b", obs="ok")))
    assert all("no_new_info" not in s.flags for s in t.steps)


def test_no_new_info_reread_without_edit_and_with_edit():
    r = lambda i, o: S(i, "read", tool="editor", cmd="view", args={"command": "view", "path": "/testbed/a.py"}, files=[("a.py", "read")], obs=o)  # noqa: E731
    ed = S(2, "edit", tool="editor", cmd="str_replace", args={"command": "str_replace", "path": "/testbed/a.py"}, files=[("a.py", "edit")], obs="edited")
    t = run_detectors(T(r(0, "version one " * 5), r(1, "version one " * 5 + "!"), ed, r(3, "version two " * 5)))
    assert "no_new_info" in flags(t, 1) and "releitura" in t.steps[1].flag_details["no_new_info"]
    assert "no_new_info" not in flags(t, 3)  # houve edição no meio


def test_no_new_info_ranges():
    r = lambda i, rg, o: S(i, "read", tool="editor", cmd="view", args={"command": "view", "path": "a.py", "view_range": rg}, files=[("a.py", "read")], obs=o)  # noqa: E731
    t = run_detectors(T(r(0, [1, 10], "aaa " * 10), r(1, [20, 30], "bbb " * 10), r(2, [1, 10], "ccc " * 10)))
    assert "no_new_info" not in flags(t, 1) and "no_new_info" in flags(t, 2)
    t = run_detectors(T(S(0, "read", cmd="cat a.py", files=[("a.py", "read")], obs="xx " * 10), r(1, [5, 9], "yy " * 10)))
    assert "no_new_info" in flags(t, 1)  # leitura inteira anterior cobre o intervalo


def test_no_new_info_only_for_read_search_explore():
    t = run_detectors(T(S(0, "reproduce", cmd="python a.py", obs=LONG), S(1, "reproduce", cmd="python b.py", obs=LONG)))
    assert all("no_new_info" not in s.flags for s in t.steps)


# ----------------------------------------------------------------------------- loop
def test_loop_ngram_three_times_and_negative_two_times():
    cyc = lambda i: [S(i, "read", cmd="cat a.py", files=[("a.py", "read")], obs="x" * 30 + str(i)), S(i + 1, "edit", tool="editor", cmd="str_replace", files=[("a.py", "edit")], obs="y" * 30 + str(i))]  # noqa: E731
    t = run_detectors(T(*(cyc(0) + cyc(2) + cyc(4))))
    assert all("loop" in s.flags for s in t.steps) and t.meta["loops"][0]["range"] == [0, 5] and t.meta["loops"][0]["kind"] == "ngram"
    assert "[0,5]" in t.steps[0].flag_details["loop"]
    t = run_detectors(T(*(cyc(0) + cyc(2))))
    assert not any("loop" in s.flags for s in t.steps) and "loops" not in t.meta


def test_loop_ignores_keys_and_harness_in_the_window():
    a = lambda i: S(i, "read", cmd="cat a.py", files=[("a.py", "read")], obs="o" * 25 + str(i))  # noqa: E731
    b = lambda i: S(i, "search", cmd="grep x a.py", files=[("a.py", "read")], obs="p" * 25 + str(i))  # noqa: E731
    steps = [a(0), b(1), S(2, "other", cmd="C-c", sub="keys"), a(3), b(4), S(5, "submit", sub="harness_protocol"), a(6), b(7)]
    t = run_detectors(T(*steps))
    assert t.meta["loops"][0]["range"] == [0, 7] and "loop" not in t.steps[2].flags and "loop" not in t.steps[5].flags


def test_loop_excludes_message_steps():
    t = run_detectors(T(*[S(i, "think", tool="message") for i in range(12)]))
    assert not any("loop" in s.flags for s in t.steps) and "loops" not in t.meta
    a = lambda i: S(i, "read", cmd="cat a.py", files=[("a.py", "read")], obs="o" * 25 + str(i))  # noqa: E731
    b = lambda i: S(i, "search", cmd="grep x a.py", files=[("a.py", "read")], obs="p" * 25 + str(i))  # noqa: E731
    t = run_detectors(T(a(0), b(1), S(2, "think", tool="message"), a(3), b(4), S(5, "think", tool="message"), a(6), b(7)))
    assert t.meta["loops"][0]["range"] == [0, 7] and "loop" not in t.steps[2].flags  # mensagens entre os ciclos não quebram nem entram


def test_loop_edit_test_fail_cycle_three_times_same_file():
    steps = []
    for k in range(3):
        steps.append(S(len(steps), "edit", tool="editor", cmd="str_replace", args={"command": "str_replace", "path": "a.py", "new_str": str(k)}, files=[("a.py", "edit")], obs="ok"))
        steps.append(S(len(steps), "read", cmd=f"cat other{k}.py", files=[(f"other{k}.py", "read")], obs="z" * 30 + str(k)))  # rompe o n-grama
        steps.append(S(len(steps), "test", cmd="pytest", obs=f"{k + 1} failed", code=1))
    t = run_detectors(T(*steps))
    lp = [x for x in t.meta["loops"] if x["kind"] == "edit_test_fail"]
    assert lp and lp[0]["file"] == "a.py" and lp[0]["cycles"] == 3 and lp[0]["range"] == [0, 8]
    assert "loop" in flags(t, 0) and "loop" in flags(t, 2) and "loop" not in flags(t, 1)


def test_loop_edit_test_fail_two_cycles_or_pass_does_not_count():
    def cyc(i, ok):
        return [S(i, "edit", tool="editor", cmd="str_replace", files=[("a.py", "edit")], obs=f"e{i}" * 8, args={"command": "str_replace", "new_str": str(i)}),
                S(i + 1, "read", cmd=f"cat f{i}.py", files=[(f"f{i}.py", "read")], obs="q" * 30 + str(i)),
                S(i + 2, "test", cmd="pytest", obs="1 passed" if ok else "1 failed", code=0 if ok else 1)]
    t = run_detectors(T(*(cyc(0, False) + cyc(3, False))))
    assert not any(x["kind"] == "edit_test_fail" for x in t.meta.get("loops", []))
    t = run_detectors(T(*(cyc(0, False) + cyc(3, True) + cyc(6, False))))
    assert not any(x["kind"] == "edit_test_fail" for x in t.meta.get("loops", []))


# ----------------------------------------------------------------------------- truncated + geral
def test_truncated_checked():
    t = run_detectors(T(S(0, "read", cmd="cat a", obs="x", truncated=True), S(1, "read", cmd="cat b", obs="<response clipped> y"), S(2, "read", cmd="cat c", obs="fine")))
    assert "truncated" in flags(t, 0) and "truncated" in flags(t, 1) and "truncated" not in flags(t, 2)


def test_run_detectors_is_idempotent_and_does_not_touch_steps():
    t = T(S(0, "reproduce", cmd="python x.py", obs="Traceback (most recent call last)\nboom", code=1), S(1, "reproduce", cmd="python x.py", obs="Traceback (most recent call last)\nboom", code=1))
    before = [s.action.model_dump() for s in t.steps]
    a = run_detectors(t).model_dump()
    b = run_detectors(t).model_dump()
    assert a == b and [s.action.model_dump() for s in t.steps] == before


def test_norm_obs_strips_shell_footer():
    assert norm_obs("a  b\n[The command completed with exit code 0.]\n[Current working directory: /x]") == "a b"


# ----------------------------------------------------------------------------- fixtures reais
@pytest.mark.parametrize("name", ["swe_rebench_row.json", "smith_native.json", "smith_tool_xml.json", "smith_xml.json", "smith_ticks.json"])
def test_real_json_fixtures_no_exceptions(name):
    t = run_detectors(label_trajectory(parse_any(FX / name)))
    assert all(set(s.flags) <= {"error", "repeated", "loop", "no_new_info", "truncated", "test_fail", "test_pass"} for s in t.steps)
    assert all(f in s.flag_details for s in t.steps for f in s.flags)


@pytest.mark.parametrize("prefix", ["sweagent-", "miniswe-OpenAI", "terminus2-", "openhands-Anthropic", "openhands-OpenAI"])
def test_real_ctb_fixtures_no_exceptions(prefix):
    d = next(p for p in CTB.iterdir() if p.is_dir() and p.name.startswith(prefix) and "mlflow" not in p.name)
    t = run_detectors(label_trajectory(parse_any(d, manifest_dir=CTB)))
    assert t.steps and all(f in s.flag_details for s in t.steps for f in s.flags)
    assert all(not s.flags for s in t.steps if s.subcategory in ("keys", "harness_protocol"))
