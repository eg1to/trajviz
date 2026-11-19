"""Adaptadores do CodeTraceBench + ground truth (step_id → idx canônico). Exemplos do docs/formats.md §4.5."""
import json
import tarfile
from pathlib import Path

import pytest
import zstandard

from app.adapters import codetracebench as ctb
from app.adapters import ctb_openhands_events, ctb_terminus2
from app.adapters.base import UnsupportedArtifact
from app.adapters.detect import parse_any
from tests.conftest import CTB, ctb_path, manifest_row

M = {"manifest_dir": CTB}


def parse_prefix(prefix: str):
    return ctb.parse_dir(ctb_path(prefix), **M)


# ----------------------------------------------------------------------------- SWE-agent (step_ref_kind = index)
def test_sweagent_steps_and_annotations_keras_19636():
    t = parse_prefix("sweagent-")
    assert t.source_format == "ctb_sweagent" and t.agent == "SWE-agent" and len(t.steps) == 33
    gt = t.ground_truth
    assert gt.step_ref_kind == "index" and gt.manifest_step_count == 33 == len(t.steps)
    ann = {s.step_id: s for a in gt.annotations for s in a.steps}
    assert sorted(ann) == [30, 31, 32, 33]
    assert [ann[i].resolved_idx for i in (30, 31, 32, 33)] == [29, 30, 31, 32]
    assert ann[30].labels == ["incorrect"] and ann[32].labels == ["unuseful"]
    assert gt.annotations[0].incorrect_step_ids == [30, 31, 33] and gt.annotations[0].unuseful_step_ids == [32]
    # exemplo do formats.md: step 30 = `submit` recusado pelo gate PATCH_CONTEXT
    s30 = t.steps[ann[30].resolved_idx]
    assert s30.action.tool == "submit" and "STOP! BEFORE SUBMITTING" in s30.observation.content
    s32 = t.steps[ann[32].resolved_idx]
    assert s32.thought and s32.action.tool == "message" and s32.thought.startswith("Plan:")
    assert t.steps[-1].action.tool == "submit"


def test_sweagent_action_classification_and_pairs():
    t = parse_prefix("sweagent-")
    raw = json.loads(next(ctb_path("sweagent-").rglob("*.traj")).read_text())["trajectory"]
    assert [s.action.raw for s in t.steps] == [r["action"].strip() for r in raw]
    assert all(s.observation.content == r["observation"] for s, r in zip(t.steps, raw))
    ed = next(s for s in t.steps if s.action.tool == "editor")
    assert ed.action.tool_native == "str_replace_editor" and ed.action.args.get("path", "").startswith("/")
    assert any(s.thought_source == "field" and s.thought for s in t.steps)
    assert t.exit_status and t.problem_statement


# ----------------------------------------------------------------------------- mini-SWE-agent (assistant_rank)
def test_miniswe_steps_returncode_and_annotation():
    t = parse_prefix("miniswe-")
    raw = json.loads(next(ctb_path("miniswe-").rglob("*.traj.json")).read_text())["messages"]
    assert t.source_format == "ctb_miniswe" and len(t.steps) == sum(m["role"] == "assistant" for m in raw) == 27
    gt = t.ground_truth
    assert gt.step_ref_kind == "assistant_rank" and gt.manifest_step_count == 27
    ann = gt.annotations[0].steps[0]
    assert ann.step_id == 23 and ann.resolved_idx == 22 and ann.resolved_via == "rule"
    bash = [s for s in t.steps if s.action.tool == "bash"]
    assert bash and all(s.action.command and s.thought_source == "content" for s in bash)
    for s in t.steps:
        if s.observation and s.action.tool == "bash":  # exit code do <returncode>, ou erro de formato (ação não executada)
            assert s.observation.exit_code is not None or s.observation.is_error is True
    # observação = mensagem user seguinte
    assert "<returncode>" not in bash[0].observation.content
    assert t.steps[-1].action.tool in {"submit", "message"}
    assert any(s.action.tool == "submit" for s in t.steps)


def test_miniswe_without_structured_trajectory_raises_clear_error():
    d = next(p for p in CTB.iterdir() if "mlflow-register" in p.name)
    with pytest.raises(UnsupportedArtifact, match="sem trajetória estruturada"):
        parse_any(d, manifest_dir=CTB)
    with pytest.raises(UnsupportedArtifact):
        ctb.parse(d, **M)


# ----------------------------------------------------------------------------- Terminus2 (episode)
def test_terminus2_episodes_and_annotations():
    t = parse_prefix("terminus2-")
    d = ctb_path("terminus2-")
    n_ep = len(list(next(d.rglob("agent-logs")).glob("episode-*")))
    assert t.source_format == "ctb_terminus2" and len(t.steps) == n_ep == 60
    gt = t.ground_truth
    assert gt.step_ref_kind == "episode" and gt.manifest_step_count == 59
    ann = {s.step_id: s for a in gt.annotations for s in a.steps}
    assert {k: v.resolved_idx for k, v in ann.items()} == {7: 6, 8: 7, 9: 8, 10: 9}
    assert all(v.resolved_via == "action_ref" for v in ann.values())
    assert t.steps[6].native_id == 6  # episode-6/response.txt
    ep6 = json.loads((next(d.rglob("episode-6")) / "response.txt").read_text())
    assert t.steps[6].action.args["commands"] == [{"keystrokes": c["keystrokes"], "duration": c.get("duration")} for c in ep6["commands"]]
    assert t.steps[6].action.command == "".join(c["keystrokes"] for c in ep6["commands"])
    assert t.steps[6].thought and t.steps[6].thought_source == "analysis_plan"
    # a observação do passo k = prompt.txt do episódio k+1, sem o preenchimento em branco
    p7 = (next(d.rglob("episode-7")) / "prompt.txt").read_text()
    assert t.steps[6].observation.content == ctb_terminus2.clean_terminal(p7)
    assert not t.steps[6].observation.content.endswith("\n")
    assert t.steps[-1].action.tool == "submit" and t.steps[-1].action.args["task_complete"] is True
    assert t.steps[-1].observation is None


def test_clean_terminal():
    assert ctb_terminus2.clean_terminal("a  \nb\n\n\n   \n\n") == "a\nb"


# ----------------------------------------------------------------------------- OpenHands · eventos (run_rank)
def test_openhands_events_steps_and_action_ref():
    t = parse_prefix("openhands-Anthropic__Claude-Sonnet-4-20250514-Thinking-leelachess0")
    assert t.source_format == "ctb_openhands_events" and len(t.steps) == 41 == t.ground_truth.manifest_step_count
    assert {s.action.tool_native for s in t.steps} <= {"run", "edit", "read", "run_ipython", "think", "finish", "message"}
    ann = {s.step_id: s for a in t.ground_truth.annotations for s in a.steps}
    ids = {19: 59, 20: 61, 21: 63, 22: 71, 23: 75}  # action_ref → id do evento (formats.md §4.5)
    for sid, ev in ids.items():
        assert ann[sid].resolved_via == "action_ref"
        s = t.steps[ann[sid].resolved_idx]
        assert s.native_id == ev and s.action.tool_native == "run"
    # a regra "k-ésimo run" concorda com os action_ref
    runs = [s.idx for s in t.steps if s.action.tool_native == "run"]
    assert [runs[k - 1] for k in ids] == [ann[k].resolved_idx for k in ids]
    assert t.ground_truth.step_ref_kind == "run_rank"


def test_openhands_events_observation_by_cause_and_exit_code():
    d = ctb_path("openhands-Anthropic__Claude-Sonnet-4-20250514-Thinking-leelachess0")
    ev = ctb_openhands_events.load_events(next(d.rglob("events")))
    t = ctb_openhands_events.parse(d)
    by_cause = {e["cause"]: e for e in ev.values() if e.get("cause") is not None}
    runs = [s for s in t.steps if s.action.tool_native == "run"]
    assert runs
    for s in runs:
        o = by_cause[s.native_id]
        assert s.observation.content == (o.get("content") or "")
        assert s.observation.exit_code == o["extras"]["metadata"]["exit_code"]
        assert s.action.command == ev[s.native_id]["args"]["command"]
    assert t.steps[-1].action.tool == "submit" and t.steps[-1].observation is None
    assert any(s.thought for s in t.steps)


def test_secret_files_are_never_extracted(tmp_path):
    src = ctb_path("sweagent-")
    arc = tmp_path / f"{src.name}.tar.zst"
    with open(arc, "wb") as fh, zstandard.ZstdCompressor().stream_writer(fh) as w, tarfile.open(fileobj=w, mode="w|") as tf:
        tf.add(src, arcname=src.name)
        sec = tmp_path / ".jwt_secret"
        sec.write_text("segredo")
        tf.add(sec, arcname=f"{src.name}/sessions/.jwt_secret")
    out = ctb.extract(arc, tmp_path / "out")
    assert not list(out.rglob(".jwt_secret")) and list(out.rglob("*.traj"))
    assert ctb.is_secret("a/b/.jwt_secret") and not ctb.is_secret("a/b/events/1.json")
    for p in CTB.rglob("*"):  # nenhuma fixture contém segredos
        assert not ctb.is_secret(p.name)


# ----------------------------------------------------------------------------- OpenHands · SWE-bench (reusa openhands_chat)
def test_openhands_swe_reuses_chat_core():
    t = parse_prefix("openhands-OpenAI__GPT-5-sympy")
    d = ctb_path("openhands-OpenAI__GPT-5-sympy")
    call = json.loads(next(d.rglob("tensorblock*.json")).read_text())
    msgs = call["messages"] + [call["response"]["choices"][0]["message"]]
    n_calls = sum(len(m.get("tool_calls") or []) for m in msgs if m["role"] == "assistant")
    n_plain = sum(1 for m in msgs if m["role"] == "assistant" and not m.get("tool_calls"))
    assert t.source_format == "ctb_openhands_swe" and len(t.steps) == n_calls + n_plain
    assert t.steps[-1].action.tool == "submit" and t.steps[-1].observation is None
    gt = t.ground_truth
    assert gt.step_ref_kind == "tool_call_rank" and gt.ref_rule_confirmed is False
    a = gt.annotations[0].steps[0]
    assert a.step_id == 19 and a.resolved_via == "hypothesis"
    calls = [s for s in t.steps if s.action.tool != "message"]
    assert t.steps[a.resolved_idx] is calls[18]
    assert any(s.observation and s.observation.exit_code is not None for s in t.steps)


# ----------------------------------------------------------------------------- manifest e .tar.zst
def test_manifest_meta_and_ground_truth_attached():
    t = parse_prefix("sweagent-")
    row = manifest_row(t.id)
    assert t.agent == row["agent"] and t.model == row["model"] and t.resolved == row["solved"]
    assert t.meta["origin"] == "SWE-bench" and t.meta["difficulty"] == row["difficulty"]
    assert [s.stage_id for s in t.ground_truth.stages] == list(range(1, 7))
    assert t.ground_truth.stages[-1].end_step_id == 33


def test_no_manifest_means_no_ground_truth(tmp_path):
    t = ctb.parse_dir(ctb_path("sweagent-"), manifest_dir=tmp_path)
    assert t.ground_truth is None and len(t.steps) == 33


def test_tar_zst_equals_directory(tmp_path):
    src = ctb_path("terminus2-")
    arc = tmp_path / f"{src.name}.tar.zst"
    with open(arc, "wb") as fh, zstandard.ZstdCompressor().stream_writer(fh) as w, tarfile.open(fileobj=w, mode="w|") as tf:
        tf.add(src, arcname=src.name)
    a = parse_any(arc, manifest_dir=CTB)
    b = ctb.parse_dir(src, **M)
    assert a.model_dump() == b.model_dump()
