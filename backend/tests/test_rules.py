"""Camada 1 (ferramenta) + orquestração `label_trajectory`."""
import pytest

from app.adapters.detect import parse_any
from app.labeling import RULE_MIN_CONF, label_trajectory
from app.labeling.bash_parser import Ctx
from app.labeling.rules import label_step_rules
from app.labeling.taxonomy import DESCRIPTIONS, PHASE, PRECEDENCE, Category, Phase, pick_by_precedence
from app.schema import Action, Observation, Step
from tests.conftest import CTB, FX, ctb_path, jload

DIR_OBS = "Here's the files and directories up to 2 levels deep in /testbed, excluding hidden items:\n/testbed/\n/testbed/a.py"


def step(tool, native=None, command=None, args=None, raw="", obs=None, thought=None):
    return Step(idx=0, thought=thought, action=Action(tool=tool, tool_native=native, command=command, args=args or {}, raw=raw),
                observation=Observation(content=obs, chars=len(obs)) if obs is not None else None)


def lab(s, ctx=None):
    return label_step_rules(s, ctx or Ctx())


def test_taxonomy_complete():
    assert len(Category) == 11 and set(PHASE) == set(Category) == set(DESCRIPTIONS)
    assert set(PHASE.values()) == set(Phase) and all(len(DESCRIPTIONS[c][1]) == 2 for c in Category)
    assert PRECEDENCE == [Category.edit, Category.test, Category.reproduce, Category.search, Category.read, Category.explore,
                          Category.vcs, Category.setup, Category.other]
    assert pick_by_precedence([Category.vcs, Category.read, Category.test]) == Category.test


@pytest.mark.parametrize("s,cat,sub", [
    (step("editor", "str_replace_editor", "view", {"command": "view", "path": "/testbed"}, obs=DIR_OBS), "explore", "view_dir"),
    (step("editor", "str_replace_editor", "view", {"command": "view", "path": "/testbed/a.py"}, obs="Here's the result of running `cat -n`"), "read", "view"),
    (step("editor", "str_replace_editor", "view", {"command": "view", "path": "/testbed/src", "view_range": [1, 5]}, obs=DIR_OBS), "read", "view"),
    (step("editor", "str_replace_editor", "create", {"command": "create", "path": "/testbed/r.py", "file_text": "x"}), "edit", "create"),
    (step("editor", "str_replace_editor", "str_replace", {"command": "str_replace", "path": "/testbed/a.py"}), "edit", "str_replace"),
    (step("editor", "str_replace_editor", "insert", {"command": "insert", "path": "/testbed/a.py"}), "edit", "insert"),
    (step("editor", "str_replace_editor", "undo_edit", {"command": "undo_edit", "path": "/testbed/a.py"}), "edit", "undo_edit"),
    (step("editor", "read", "read", {"path": "/app/Makefile"}), "read", "view"),
    (step("editor", "edit", "str_replace", {"command": "str_replace", "path": "/app/a.c"}), "edit", "str_replace"),
    (step("swe_cmd", "open", "open", {"line": "open /testbed/a.py"}), "read", "open"),
    (step("swe_cmd", "scroll_down", "scroll_down", {"line": "scroll_down"}), "read", "scroll_down"),
    (step("swe_cmd", "goto", "goto", {"line": "goto 40"}), "read", "goto"),
    (step("swe_cmd", "search_file", "search_file", {"line": "search_file foo a.py"}), "search", "search_file"),
    (step("swe_cmd", "find_file", "find_file", {"line": "find_file a.py"}), "search", "find_file"),
    (step("swe_cmd", "edit", "edit", {"line": "edit 1:3"}), "edit", "edit"),
    (step("think", "think", args={"thought": "hmm"}), "think", None),
    (step("message", None, raw="Let me think"), "think", None),
    (step("task_tracker", "task_tracker", "plan"), "think", "plan"),
    (step("submit", "finish"), "submit", "finish"),
    (step("submit", "submit", raw="submit"), "submit", "submit"),
])
def test_tool_layer(s, cat, sub):
    r = lab(s)
    assert (r.category.value, r.subcategory, r.confidence, r.final) == (cat, sub, 1.0, True)


@pytest.mark.parametrize("s", [
    step("bash", "execute_bash", "C-c", {"command": "C-c", "is_input": "true"}),
    step("bash", "execute_bash", "y", {"command": "y", "is_input": True}),
    step("bash", "execute_bash", "", {"command": ""}),
    step("bash", "execute_bash", "C-c", {"command": "C-c"}),
    step("keys", "keystrokes", "C-c", {"commands": [{"keystrokes": "C-c", "duration": 0.1}]}),
    step("keys", "keystrokes", "", {"commands": [{"keystrokes": "", "duration": 5}]}),
    step("keys", "keystrokes", "C-d\n", {"commands": [{"keystrokes": "C-c"}, {"keystrokes": "C-d\n"}]}),
])
def test_keys_are_other_keys_not_llm(s):
    r = lab(s)
    assert (r.category.value, r.subcategory, r.confidence, r.final) == ("other", "keys", 1.0, True)


@pytest.mark.parametrize("s", [
    step("submit", "submit", obs="**STOP! BEFORE SUBMITTING:** You MUST provide the CODE CONTEXT you used"),
    step("message", None, raw="THOUGHT: Providing code context.\n\n<PATCH_CONTEXT>\nFile: /testbed/a.py\n</PATCH_CONTEXT>"),
    step("bash", "bash", "echo done", obs="<context_received>\nContext received and recorded (321 characters).\n</context_received>"),
])
def test_harness_protocol(s):
    r = lab(s)
    assert (r.category.value, r.subcategory, r.confidence, r.final) == ("submit", "harness_protocol", 1.0, True)


def test_terminus2_commands_use_precedence_and_keep_list():
    s = step("keys", "keystrokes", "x", {"commands": [{"keystrokes": "ls -la\n"}, {"keystrokes": "cat a.py\n"}, {"keystrokes": "C-c"}]})
    r = lab(s)
    assert r.category == Category.read and r.subcategory == "ls|cat" and r.confidence == 0.9
    s = step("keys", "keystrokes", "x", {"commands": [{"keystrokes": "cat > f.py << 'EOF'\nx=1\nEOF\n"}, {"keystrokes": "pytest\n"}]})
    assert lab(s).category == Category.edit


def test_created_script_then_run_is_reproduce():
    ctx = Ctx()
    lab(step("editor", "str_replace_editor", "create", {"command": "create", "path": "/testbed/test_my_fix.py"}), ctx)
    assert lab(step("bash", "execute_bash", "python test_my_fix.py", {"command": "python test_my_fix.py"}), ctx).category == Category.reproduce
    assert lab(step("bash", "execute_bash", "python test_other.py", {"command": "python test_other.py"}), ctx).category == Category.test


def test_ipython_and_malformed_editor_command():
    assert lab(step("ipython", "run_ipython", "import a\nprint(a.f())")).category == Category.reproduce
    r = lab(step("editor", "str_replace_editor", 'grep -n "x" /testbed/a.py', {"command": 'grep -n "x" /testbed/a.py'}))
    assert r.category == Category.search and r.confidence <= 0.6 and not r.final


def test_unknown_things_become_fallback_candidates():
    r = lab(step("bash", "bash", "dvc repro", {"command": "dvc repro"}))
    assert r.category == Category.other and r.confidence < RULE_MIN_CONF and not r.final
    assert lab(step("browser", "browser")).confidence < RULE_MIN_CONF


def test_label_trajectory_sets_sources_and_files_modes():
    t = parse_any(FX / "swe_rebench_row.json")
    label_trajectory(t)
    assert all(s.label_source == "rule" and s.confidence >= RULE_MIN_CONF for s in t.steps)
    assert t.steps[0].category == "think" and t.steps[-1].category == "submit" and t.steps[-1].subcategory == "finish"
    modes = {f.mode for s in t.steps for f in s.files}
    assert modes <= {"read", "edit", "run"} and "read" in modes
    assert all(not f.path.startswith(("/testbed", "/workspace", "/app")) for s in t.steps for f in s.files)
    n_steps = len(t.steps)
    label_trajectory(t)  # idempotente e nunca muda os passos
    assert len(t.steps) == n_steps


def test_labeling_never_changes_steps_only_labels():
    t = parse_any(FX / "smith_xml.json")
    before = [(s.idx, s.native_id, s.thought, s.action.model_dump(), s.observation.model_dump() if s.observation else None) for s in t.steps]
    label_trajectory(t)
    after = [(s.idx, s.native_id, s.thought, s.action.model_dump(), s.observation.model_dump() if s.observation else None) for s in t.steps]
    assert before == after


# ----------------------------------------------------------------------------- integração: uma fixture de cada formato
INTEGRATION = ["swe_rebench_row.json", "swe_rebench_messages.json", "smith_native.json", "smith_tool_xml.json", "smith_xml.json",
               "smith_ticks.json"]


@pytest.mark.parametrize("name", INTEGRATION)
def test_integration_json_fixtures(name):
    t = label_trajectory(parse_any(FX / name))
    valid = {c.value for c in Category}
    assert t.steps and all(s.category in valid and s.label_source in ("rule", "fallback") for s in t.steps)
    assert all(0.0 <= s.confidence <= 1.0 for s in t.steps)
    assert t.steps[-1].category == "submit"


@pytest.mark.parametrize("prefix", ["sweagent-", "miniswe-OpenAI", "terminus2-", "openhands-Anthropic", "openhands-OpenAI"])
def test_integration_ctb_fixtures(prefix):
    d = next(p for p in CTB.iterdir() if p.is_dir() and p.name.startswith(prefix) and "mlflow" not in p.name)
    t = label_trajectory(parse_any(d, manifest_dir=CTB))
    valid = {c.value for c in Category}
    assert t.steps and all(s.category in valid for s in t.steps)  # nenhum passo fica sem category
    assert sum(1 for s in t.steps if s.category == "other" and s.subcategory != "keys") / len(t.steps) < 0.15


def test_sweagent_gate_steps_are_harness_protocol():
    t = label_trajectory(parse_any(ctb_path("sweagent-"), manifest_dir=CTB))
    ann = {s.step_id: s for a in t.ground_truth.annotations for s in a.steps}
    s30 = t.steps[ann[30].resolved_idx]  # submit recusado pelo "STOP! BEFORE SUBMITTING"
    assert s30.category == "submit" and s30.subcategory == "harness_protocol"


def test_terminus2_keys_steps_and_mini_harness():
    t = label_trajectory(parse_any(ctb_path("terminus2-"), manifest_dir=CTB))
    assert all(s.category != "other" or s.subcategory == "keys" or s.confidence < 0.6 for s in t.steps)
    m = label_trajectory(parse_any(ctb_path("miniswe-OpenAI"), manifest_dir=CTB))
    assert any(s.subcategory == "harness_protocol" for s in m.steps)  # <PATCH_CONTEXT> / <context_received>
