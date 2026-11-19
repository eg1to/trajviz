import pytest

from app.adapters.detect import parse_any
from app.analysis.detectors import run_detectors
from app.analysis.metrics import compute_metrics
from app.labeling import label_trajectory
from tests.conftest import CTB, ctb_path
from tests.test_detectors import S, T


def build():
    ed = lambda i, p, new="x\ny": S(i, "edit", tool="editor", native="str_replace_editor", cmd="str_replace", files=[(p, "edit")], obs="edited",  # noqa: E731
                                  args={"command": "str_replace", "path": p, "old_str": "a", "new_str": new})
    steps = [
        S(0, "explore", tool="editor", cmd="view", obs="dir listing " * 5, native="str_replace_editor"),
        S(1, "read", cmd="cat a.py", files=[("a.py", "read")], obs="code " * 10),
        S(2, "read", cmd="cat a.py", files=[("a.py", "read")], obs="code " * 10),  # repeated + no_new_info
        S(3, "read", cmd="cat a.py | head", files=[("a.py", "read")], obs="code " * 11),
        S(4, "reproduce", cmd="python reproduce.py", files=[("reproduce.py", "run")], obs="Traceback (most recent call last)\nboom", code=1),
        S(5, "reproduce", cmd="python reproduce.py", files=[("reproduce.py", "run")], obs="Traceback (most recent call last)\nboom2", code=1),
        ed(6, "b.py"),
        S(7, "test", cmd="pytest", obs="2 failed", code=1),
        ed(8, "b.py"),
        S(9, "test", cmd="pytest", obs="3 passed", code=0),
        S(10, "think", tool="think"),
        S(11, "other", cmd="C-c", sub="keys", obs=""),
        S(12, "think", tool="message"),
        S(13, "submit", tool="submit", sub="finish"),
    ]
    t = T(*steps)
    t.steps[13].observation = None
    return run_detectors(t)


def test_effort_separates_message_keys_and_percentages():
    m = compute_metrics(build())
    e = m.effort
    assert e.n_steps == 14 and e.n_core_steps == 12 and e.message.count == 1 and e.keys.count == 1 and e.harness_protocol.count == 0
    assert e.message.idx == [12] and e.keys.idx == [11]
    assert e.by_category["think"].count == 1  # só o think de verdade; message fora
    assert e.by_category["other"].count == 0  # keys fora de other
    c = e.by_category["read"]
    assert c.count == 3 and c.pct_total == round(100 * 3 / 14, 1) and c.pct_core == round(100 * 3 / 12, 1)
    assert sum(p.count for p in e.by_phase) == 12 and [p.phase for p in e.by_phase][0] == "Entendimento"
    assert e.executables_ranking[0].name in {"cat", "python"} and any(r.name == "pytest" for r in e.executables_ranking)
    assert e.tools_ranking and all(r.name not in ("message",) for r in e.tools_ranking)


def test_dynamics_first_edit_and_cycles():
    d = compute_metrics(build()).dynamics
    assert d.first_edit_idx == 6 and d.pct_before_first_edit == round(100 * 6 / 14, 1)
    assert (d.edit_test_cycles, d.cycles_passed, d.cycles_failed) == (2, 1, 1)
    assert sum(sum(t.counts.values()) for t in d.dominant_phase_by_third) == 12 and len(d.dominant_phase_by_third) == 3 and d.dominant_phase_by_third[0].phase == "Entendimento"
    assert d.dominant_phase_by_third[2].phase in ("Verificação", "Modificação", "Controle")


def test_problems_lists_idx_and_streak():
    p = compute_metrics(build()).problems
    assert p.error.idx == [4, 5] and p.longest_error_streak.length == 2 and (p.longest_error_streak.start_idx, p.longest_error_streak.end_idx) == (4, 5)
    assert 2 in p.repeated.idx and 2 in p.no_new_info.idx and p.test_fail.idx == [7] and p.test_pass.idx == [9]
    assert p.error.count == 2 and p.error.rate == round(100 * 2 / 13, 1)  # taxa sobre passos analisáveis (sem keys)
    assert p.loop.count == 0 and p.loop_ranges == []


def test_files_table_and_lists():
    f = compute_metrics(build()).files
    by = {x.path: x for x in f.table}
    assert (by["a.py"].reads, by["a.py"].edits, by["a.py"].first_idx, by["a.py"].last_idx) == (3, 0, 1, 3)
    assert (by["b.py"].edits, by["b.py"].reads) == (2, 0) and by["reproduce.py"].runs == 2
    assert "b.py" in f.edited_never_read and f.read_3plus_no_edit == ["a.py"]


def test_outcome_derives_patch_from_edit_steps_when_untrusted():
    t = build()
    t.resolved, t.resolved_validated, t.patch = True, False, "diff --git a/x b/x\n+z"
    o = compute_metrics(t).outcome
    assert o.patch_source == "steps" and o.patch_files == 1 and o.patch_lines_added == 4 and o.patch_lines_removed == 2
    assert o.ended_with_submit and o.n_steps == 14
    t.resolved_validated = True
    t.patch = "diff --git a/x b/x\n--- a/x\n+++ b/x\n-old\n+new1\n+new2\ndiff --git a/y b/y\n+z\n"
    o = compute_metrics(t).outcome
    assert (o.patch_source, o.patch_files, o.patch_lines_added, o.patch_lines_removed) == ("patch", 2, 3, 1)


def test_context_series():
    c = compute_metrics(build()).context
    assert len(c.obs_chars) == 14 and c.obs_chars[13] == 0 and c.max_obs_chars == max(c.obs_chars) and c.total_obs_chars == sum(c.obs_chars)


def test_ground_truth_only_for_ctb():
    assert compute_metrics(build()).ground_truth is None
    t = run_detectors(label_trajectory(parse_any(ctb_path("sweagent-"), manifest_dir=CTB)))
    g = compute_metrics(t).ground_truth
    assert g.n_incorrect == 3 and g.n_unuseful == 1 and g.incorrect_idx == [29, 30, 32] and g.unuseful_idx == [31] and g.unresolved == 0
    assert g.resolved_via == {"rule": 4} and g.incorrect_vs_error_or_test_fail.annotated == 3


def test_metrics_schema_is_json_serializable_for_every_ctb_fixture():
    for p in CTB.iterdir():
        if p.is_dir() and "mlflow" not in p.name:
            t = run_detectors(label_trajectory(parse_any(p, manifest_dir=CTB)))
            assert compute_metrics(t).model_dump_json()
