"""openhands_chat (SWE-rebench), sweagent_smith (SWE-smith, 3 sub-parsers) e generic_chat."""
import json

import pytest

from app.adapters import generic_chat, openhands_chat, sweagent_smith
from app.schema import Trajectory
from tests.conftest import jload


# ----------------------------------------------------------------------------- openhands_chat
def test_openhands_row_steps_and_pairing():
    row = jload("swe_rebench_row.json")
    t = openhands_chat.parse(row)
    assert isinstance(t, Trajectory) and t.source_format == "openhands_chat"
    raw_calls = [tc for m in row["trajectory"] if m["role"] == "assistant" for tc in (m.get("tool_calls") or [])]
    assert len(t.steps) == len(raw_calls) == 11
    tool_msgs = {m["tool_call_id"]: m for m in row["trajectory"] if m["role"] == "tool"}
    for s, tc in zip(t.steps, raw_calls):
        assert s.native_id == tc["id"]
        if s.observation is not None:  # par ação↔observação por tool_call_id
            assert s.observation.content == tool_msgs[tc["id"]]["content"]
    assert [s.idx for s in t.steps] == list(range(11))
    assert t.resolved is True and t.exit_status == "submit" and t.task_id and t.repo and t.problem_statement
    assert t.patch is None or isinstance(t.patch, str)


def test_openhands_finish_is_submit_without_observation_and_think_thought():
    t = openhands_chat.parse(jload("swe_rebench_row.json"))
    last = t.steps[-1]
    assert last.action.tool == "submit" and last.action.tool_native == "finish" and last.observation is None
    assert last.thought  # finish.message vira pensamento
    think = t.steps[0]
    assert think.action.tool == "think" and think.thought_source == "think_tool" and think.thought


def test_openhands_exit_code_regex():
    t = openhands_chat.parse(jload("swe_rebench_row.json"))
    bash = [s for s in t.steps if s.action.tool == "bash" and s.observation]
    assert bash and all(s.observation.exit_code is not None for s in bash)
    for s in bash:
        assert f"exit code {s.observation.exit_code}." in s.observation.content
        assert s.observation.is_error == (s.observation.exit_code != 0)
    # editor não tem exit code
    assert all(s.observation.exit_code is None for s in t.steps if s.action.tool == "editor" and s.observation)


def test_openhands_tool_normalization_and_args():
    t = openhands_chat.parse(jload("swe_rebench_row.json"))
    ed = next(s for s in t.steps if s.action.tool == "editor")
    assert ed.action.tool_native == "str_replace_editor" and ed.action.command in {"view", "create", "str_replace", "insert", "undo_edit"}
    assert isinstance(ed.action.args, dict) and ed.files and ed.files[0].path == ed.action.args['path']
    b = next(s for s in t.steps if s.action.tool == "bash")
    assert b.action.tool_native == "execute_bash" and b.action.command == b.action.args["command"]
    assert all(s.category == "other" and s.label_source == "fallback" for s in t.steps)


def test_openhands_bare_message_list():
    msgs = jload("swe_rebench_messages.json")
    assert openhands_chat.can_parse(msgs) >= 0.9
    t = openhands_chat.parse(msgs)
    assert len(t.steps) == 11 and t.resolved is None


# ----------------------------------------------------------------------------- sweagent_smith
@pytest.mark.parametrize("name,fmt", [("smith_native", "native"), ("smith_tool_xml", "xml"), ("smith_xml", "xml"),
                                      ("smith_ticks", "ticks")])
def test_smith_formats(name, fmt):
    row = jload(f"{name}.json")
    t = sweagent_smith.parse(row)
    assert t.source_format == "sweagent_smith" and set(t.meta["action_formats"]) == {fmt}
    assert len(t.steps) == 8
    assert t.resolved_validated is False and t.patch is None and t.agent == "SWE-agent"
    assert t.steps[-1].action.tool == "submit" and t.exit_status == "submitted"
    assert all(s.observation is not None for s in t.steps[:-1])  # toda ação não final tem observação
    assert all(not s.observation.content.startswith("OBSERVATION:") for s in t.steps[:-1] if s.observation)
    assert any(s.thought for s in t.steps)
    assert t.problem_statement and "uploaded" in t.problem_statement
    assert t.id == row["traj_id"] and t.task_id == row["instance_id"]


def test_smith_native_pairs_by_tool_call_id():
    row = jload("smith_native.json")
    t = sweagent_smith.parse(row)
    obs_by_id = {i: m for m in row["messages"] if m.get("role") == "tool" for i in m["tool_call_ids"]}
    for s in t.steps[:-1]:
        assert s.native_id in obs_by_id
        assert sweagent_smith.text_of(obs_by_id[s.native_id]["content"]).replace("OBSERVATION:\n", "", 1) == s.observation.content
    assert t.steps[0].thought_source == "field" and t.steps[0].action.tool_native in {"bash", "str_replace_editor"}


def test_smith_messages_as_json_string_parquet_style():
    row = jload("smith_ticks.json")
    assert isinstance(row["messages"], str)  # a fixture ticks guarda `messages` como string JSON (como no Parquet)
    assert sweagent_smith.can_parse(row) >= 0.9


def test_smith_ticks_action_is_last_bare_block():
    c = "Plan:\n```python\nprint(1)\n```\nNow view:\n\n```\nstr_replace_editor view /testbed/a.py --view_range 1 5\n```"
    acts, thought, src, fmt = sweagent_smith._actions({"role": "assistant", "content": c})
    assert fmt == "ticks" and acts[0][0].command == "view" and acts[0][0].args["path"] == "/testbed/a.py"
    assert acts[0][0].args["view_range"] == ["1", "5"] and "print(1)" in thought


def test_smith_editor_args_xml():
    t = sweagent_smith.parse(jload("smith_xml.json"))
    ed = next(s for s in t.steps if s.action.tool == "editor")
    assert ed.action.command == "view" and ed.action.args["path"].startswith("/testbed") and ed.files


# ----------------------------------------------------------------------------- generic_chat
def test_generic_openai_style():
    msgs = [{"role": "user", "content": "fix"},
            {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "type": "function",
                                                                  "function": {"name": "bash", "arguments": '{"command":"ls"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "a.py"},
            {"role": "assistant", "content": "done"}]
    assert 0.3 <= generic_chat.can_parse(msgs) < 0.9
    t = generic_chat.parse(msgs)
    assert [s.action.tool for s in t.steps] == ["bash", "message"]
    assert t.steps[0].observation.content == "a.py" and t.steps[0].thought == "ok"


def test_generic_anthropic_style():
    msgs = [{"role": "user", "content": "fix the bug"},
            {"role": "assistant", "content": [{"type": "text", "text": "Listing"},
                                              {"type": "tool_use", "id": "tu1", "name": "bash", "input": {"command": "ls"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "a.py", "is_error": False}]},
            {"role": "assistant", "content": [{"type": "text", "text": "All done"}]}]
    assert generic_chat.can_parse(msgs) > 0.5
    t = generic_chat.parse(msgs)
    assert t.problem_statement == "fix the bug"
    assert t.steps[0].action.command == "ls" and t.steps[0].observation.content == "a.py" and t.steps[0].observation.is_error is False
    assert t.steps[0].thought == "Listing" and t.steps[1].action.tool == "message"
