"""Adaptador `claude_code_session`: fixture SINTÉTICA e anonimizada (tests/fixtures/claude_code_session.jsonl), no formato dos .jsonl de ~/.claude/projects/."""
from pathlib import Path

import pytest

from app.adapters.detect import BY_NAME, detect, load, parse_any
from app.analysis.detectors import run_detectors
from app.labeling import label_trajectory

FIX = Path(__file__).parent / "fixtures" / "claude_code_session.jsonl"


@pytest.fixture(scope="module")
def traj():
    t = parse_any(FIX)
    label_trajectory(t)
    run_detectors(t)
    return t


def test_detecta_sessao_inteira_como_uma_trajetoria():
    obj = load(FIX)
    assert isinstance(obj, list) and len(obj) > 20  # o arquivo todo, não só a linha 0
    assert detect(FIX) == ("claude_code_session", 0.95)


def test_outros_formatos_nao_sao_capturados():
    assert BY_NAME["claude_code_session"].can_parse({"trajectory": []}) == 0.0
    assert BY_NAME["claude_code_session"].can_parse([{"role": "user", "content": "oi"}]) == 0.0


def test_passos_e_metadados(traj):
    assert traj.source_format == "claude_code_session" and traj.agent == "Claude Code" and traj.model == "claude-test-1"
    assert traj.id == "00000000-0000-4000-8000-000000000001"
    assert traj.problem_statement.startswith("Fix the bug in calc.average")  # sem o <system-reminder> nem a mensagem meta
    # 11 tool_use do agente principal + 1 mensagem final; o tool_use do subagente (isSidechain) fica de fora
    assert len(traj.steps) == 12
    assert not any("subagent" in (s.action.command or "") for s in traj.steps)
    assert traj.steps[-1].action.tool == "message" and "Fixed" in traj.steps[-1].thought


def test_categorias_pelas_regras_existentes(traj):
    cats = [s.category for s in traj.steps]
    assert cats == ["explore", "search", "search", "read", "test", "edit", "test", "vcs", "edit", "think", "other", "think"]
    tools = [s.action.tool_native for s in traj.steps]
    assert tools[:4] == ["Bash", "Glob", "Grep", "Read"] and tools[8] == "Write"


def test_pensamento_resultado_e_arquivos(traj):
    assert traj.steps[0].thought == "I'll start by looking at the project structure."  # thinking vazio (redigido) é ignorado
    assert traj.steps[0].observation.content.startswith("total 12")
    assert traj.steps[3].thought.startswith("The function is in utils.py")
    assert [(f.path, f.mode) for f in traj.steps[3].files] == [("/work/project/calc/utils.py", "read")]
    assert traj.steps[5].files and traj.steps[5].files[0].mode == "edit"


def test_erro_do_pytest_vem_do_exit_code_no_texto(traj):
    s = traj.steps[4]
    assert s.observation.exit_code == 1 and s.observation.is_error
    assert "test_fail" in s.flags
    assert "test_pass" in traj.steps[6].flags


def test_upload_pela_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config, library, main

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("TRAJVIZ_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("LABEL_LLM_ENABLED", "0")
    monkeypatch.setattr(library, "CTB_RAW", tmp_path / "noctb")
    c = TestClient(main.app)
    r = c.post("/api/trajectories", files={"file": ("sessao.jsonl", FIX.read_bytes())})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["format_detected"] == "claude_code_session" and j["n_steps"] == 12
    m = c.get(f"/api/trajectories/{j['id']}/metrics").json()
    assert m["outcome"]["n_steps"] == 12
