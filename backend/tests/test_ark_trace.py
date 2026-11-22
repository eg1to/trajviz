"""Adaptador `ark_trace`: traces REAIS do Ark (agente do orientador), copiados de data/inbox/ark/ (v2 = Haiku 5.5; v1/ = traces com falhas do protocolo).

Fixtures: success, rejected (reject-first), max_iterations_reached, v1 com validation_error/repair_attempt + rollback, v1 com [error]."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, library, main, pipeline
from app.adapters import ark_trace
from app.adapters.detect import BY_NAME, UnknownFormat, detect, load, parse_any
from app.analysis.detectors import run_detectors
from app.labeling import label_trajectory

FX = Path(__file__).parent / "fixtures" / "ark"
INBOX = Path(__file__).resolve().parents[2] / "data" / "inbox" / "ark"
SUCCESS = FX / "bugfix_001_date_range__claude-haiku-5-5__auto__1.log"
REJECTED = FX / "bugfix_002_order_totals__claude-haiku-5-5__reject-first__1.log"
MAXIT = FX / "refactor_002_remove_duplication__claude-haiku-5-5__auto__3.log"
V1_PROTOCOL = FX / "v1" / "refactor_001_rename__claude-haiku-5-5__auto__1.log"
V1_ERROR = FX / "v1" / "bugfix_002_order_totals__claude-haiku-5-5__reject-first__2.log"
NOTE = "saída não registrada pelo trace do Ark"


def full(path: Path):
    t = parse_any(path)
    label_trajectory(t)
    run_detectors(t)
    return t


def test_detecta_e_ignora_outros_formatos():
    assert detect(SUCCESS) == ("ark_trace", 0.97)
    assert BY_NAME["ark_trace"].can_parse("[request]\nfoo\n") == 0.0  # sem [response N] nem [run_summary]
    assert BY_NAME["ark_trace"].can_parse({"trajectory": []}) == 0.0
    assert BY_NAME["ark_trace"].can_parse("hello\n[response 1]\nthought: x\naction: y\n") == 0.0  # [request] tem de abrir o arquivo


def test_texto_qualquer_nao_vira_ark(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("hello world\nnothing here\n")
    with pytest.raises(UnknownFormat):
        detect(p)
    assert isinstance(load(p), ark_trace.ArkLog)


def test_success_passos_e_ferramentas():
    t = full(SUCCESS)
    assert (t.source_format, t.agent, t.model, t.task_id) == ("ark_trace", "Ark", "claude-haiku-5-5", "bugfix_001_date_range")  # modelo vem do .meta.json
    assert t.problem_statement.startswith("Users reported that date-based")
    assert (t.resolved, t.exit_status) == (True, "success")
    assert [s.action.tool_native for s in t.steps] == ["list_files", "read_file", "edit_file", "read_file", "run_tests", "finish"]
    assert [s.native_id for s in t.steps] == [1, 2, 3, 4, 5, 6]
    assert [s.category for s in t.steps] == ["explore", "read", "edit", "read", "test", "submit"]
    assert all(s.label_source == "rule" and s.confidence == 1.0 for s in t.steps)
    s1 = t.steps[1]
    assert s1.action.args["path"] == "src/dates.py" and s1.thought and s1.thought_source == "field"
    assert [(f.path, f.mode) for f in s1.files] == [("src/dates.py", "read")]
    assert [(f.path, f.mode) for f in t.steps[2].files] == [("src/dates.py", "edit")]


def test_success_observacoes_e_flags():
    t = full(SUCCESS)
    # list/read/find e teste que passou: o Ark não registra a saída → observation=None + aviso para o front
    assert [s.observation for s in t.steps if s.action.tool_native in ("list_files", "read_file", "run_tests", "finish")] == [None] * 5
    assert t.meta["ark"]["unrecorded"] == [0, 1, 3, 4, 5] and t.meta["ark"]["unrecorded_note"] == NOTE
    edit = t.steps[2].observation
    assert edit.content.startswith("--- a/src/dates.py\n+++ b/src/dates.py") and edit.is_error is False
    assert "test_pass" in t.steps[4].flags and "test_pass" in t.steps[5].flags  # [tests] passed e [finish] completed
    assert not any(f in s.flags for s in t.steps for f in ("error", "no_new_info", "test_fail"))
    assert t.meta["ark"]["workspace"] == [{"status": "committed"}]
    assert t.meta["ark"]["run_summary"]["tool_counts"] == "list_files=1, read_file=2, edit_file=1, run_tests=2, finish=1"  # guardado como veio (finish conta como run_tests)


def test_rejected_vira_edit_rejected_com_nota():
    t = full(REJECTED)
    rej, ok = t.steps[4], t.steps[5]
    assert (rej.category, rej.subcategory) == ("edit", "edit_rejected") and (ok.category, ok.subcategory) == ("edit", "edit_file")
    assert rej.observation.content.startswith("Edição rejeitada pelo usuário") and "--- a/src/checkout.py" in rej.observation.content
    assert "error" not in rej.flags and rej.observation.is_error is None  # rejeição é decisão do usuário, não erro
    assert t.meta["ark"]["outcomes"]["4"]["status"] == "rejected" and t.resolved is True
    # edit rejeitado e re-proposto com diff diferente não é "repetido"
    assert not any("repeated" in s.flags for s in t.steps)


def test_max_iterations_falha_de_edit_e_resolved_false():
    t = full(MAXIT)
    assert (t.exit_status, t.resolved) == ("max_iterations_reached", False)
    edit = t.steps[-1]
    assert edit.action.tool_native == "edit_file" and edit.observation.is_error is True and "error" in edit.flags
    assert edit.observation.content.startswith("Invalid edit_file input")
    assert not any("test_pass" in s.flags for s in t.steps)


def test_v1_protocolo_validation_error_repair_rollback():
    t = full(V1_PROTOCOL)
    ev = t.meta["ark"]["protocol_events"]
    assert [(e["type"], e["next_step"]) for e in ev] == [("validation_error", 11), ("repair_attempt", 11), ("validation_error", 13), ("repair_attempt", 13)]
    assert ev[0]["reason"] == "Model response is missing the required Action field." and ev[0]["response"].startswith("Thought:")
    assert ev[1]["kind"] == "Protocol repair" and t.meta["protocol_events"] == ev
    assert t.meta["ark"]["workspace"] == [{"status": "rolled_back", "reason": "Agent stopped after reaching the maximum number of steps."}]
    assert (t.exit_status, t.resolved) == ("max_iterations_reached", False) and len(t.steps) == 20
    # numeração [response N] tem buracos (respostas inválidas consomem N): native_id guarda o N, idx é contínuo
    assert [s.idx for s in t.steps] == list(range(20)) and t.steps[11].native_id == 15
    # 3 edições de teste com formato inválido seguidas: erros, nunca "repetido" (conteúdo desconhecido)
    assert [s.idx for s in t.steps if "error" in s.flags][:3] == [6, 7, 8]
    assert "repeated" in t.steps[11].flags  # find_text igual ao do passo 10, sem edição no meio (vale pela ação)
    assert "no_new_info" not in [f for s in t.steps for f in s.flags]  # não se aplica: a saída nunca é registrada


def test_v1_error_final_e_protocolo_sem_passo_seguinte():
    t = full(V1_ERROR)
    assert t.meta["ark"]["errors"][0]["type"] == "ValueError" and "missing the required Action" in t.meta["ark"]["errors"][0]["detail"]
    assert t.meta["ark"]["errors"][0]["tools_called"].startswith("list_files, read_file")
    ev = t.meta["ark"]["protocol_events"]
    assert [(e["type"], e["next_step"]) for e in ev] == [("validation_error", 5), ("repair_attempt", 5), ("validation_error", None), ("repair_attempt", None)]
    assert (t.exit_status, t.resolved) == ("failed", False) and t.steps[-1].category == "edit"


def test_finish_recusado_e_testes_finais_falhos_viram_flags(tmp_path):
    def trace(block: str, action: str = "finish") -> Path:
        p = tmp_path / f"t{abs(hash(block))}.log"
        p.write_text(f"[request]\nfaça x\n\n[response 1]\nthought: a\naction: {action}\n\n" + block + "\n[run_summary]\nstatus: failed\n")
        return p
    a = full(trace("[finish]\nstatus: failed\nstage: finish_validation\ndetail: Finish requires at least one approved edit_file action.\n"))
    assert a.steps[0].category == "submit" and "error" in a.steps[0].flags and "Finish requires" in a.steps[0].observation.content
    b = full(trace("[finish]\nstatus: failed\nstage: post_apply_tests\ndetail: FAILED tests/test_x.py::test_a - assert 1 == 2\n1 failed in 0.1s\n"))
    assert "test_fail" in b.steps[0].flags and "error" not in b.steps[0].flags and "1 failed in 0.1s" in b.steps[0].observation.content
    c = full(trace("[tests]\nstatus: failed\ndetail:\nE   assert 1 == 2\n", "run_tests"))
    assert c.steps[0].category == "test" and "test_fail" in c.steps[0].flags and "assert 1 == 2" in c.steps[0].observation.content


def test_modelo_pelo_nome_do_arquivo_quando_nao_ha_sidecar(tmp_path):
    p = tmp_path / "bugfix_001_date_range__claude-haiku-5-5__auto__2.log"
    shutil.copy(SUCCESS, p)
    t = parse_any(p)
    assert (t.model, t.task_id) == ("claude-haiku-5-5", "bugfix_001_date_range") and t.meta["ark"]["mode"] == "auto"
    q = tmp_path / "qualquer.txt"
    shutil.copy(SUCCESS, q)
    assert parse_any(q).model is None  # nem sidecar nem padrão de nome


# --------------------------------------------------------------------------- integração: todos os traces das duas pastas
ALL = sorted(INBOX.glob("*.log")) + sorted((INBOX / "v1_falhas_adaptador").glob("*.log"))


@pytest.mark.skipif(not ALL, reason="data/inbox/ark não está presente")
def test_abre_todos_os_traces_das_duas_pastas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    assert len(list(INBOX.glob('*.log'))) == 15
    sem_passos = []
    for p in ALL:
        t = full(p)  # adaptador + regras + detectores sem erro
        assert t.source_format == "ark_trace" and t.model in ("claude-haiku-5-5", "claude-sonnet-5-5") and t.exit_status
        # toda ferramenta do Ark tem regra de camada 1; só uma ação inválida (v1: `action: edit_`) fica como other/fallback
        assert all((s.category != "other" and s.label_source == "rule") if s.action.tool_native in ark_trace.ARK_TOOLS else s.category == "other" for s in t.steps)
        assert t.meta["ark"]["unrecorded"] == [s.idx for s in t.steps if s.observation is None]
        if not t.steps:
            sem_passos.append(p.name)
            continue
        pt = pipeline.process(p, p.name, use_llm=False)  # caminho completo: detecção → rótulos → métricas (+ .meta.json ao lado)
        assert pt.format_detected == "ark_trace" and pt.trajectory.model == t.model and pt.metrics is not None
    # recusas do Sonnet antes da 1ª resposta: 0 passos → o adaptador abre, o pipeline responde o erro padrão de trajetória vazia
    assert sem_passos  # há recusas do Sonnet na v1/
    for name in sem_passos:
        with pytest.raises(pipeline.PipelineError) as e:
            pipeline.process(next(p for p in ALL if p.name == name), name, use_llm=False)
        assert e.value.code == "empty_trajectory"


def test_api_upload_log_e_txt(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("TRAJVIZ_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("LABEL_LLM_ENABLED", "0")
    c = TestClient(main.app)
    for name in ("agent_trace.log", "agent_trace.txt"):
        r = c.post("/api/trajectories", files={"file": (name, SUCCESS.read_bytes())}, data={"use_llm": "false"})
        assert r.status_code == 200 and r.json()["format_detected"] == "ark_trace" and r.json()["n_steps"] == 6
    t = c.get(f"/api/trajectories/{r.json()['id']}").json()["trajectory"]
    assert t["agent"] == "Ark" and t["meta"]["ark"]["unrecorded_note"] == NOTE and t["steps"][1]["observation"] is None
    bad = c.post("/api/trajectories", files={"file": ("x.log", b"so texto\n")}, data={"use_llm": "false"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unknown_format"


def test_biblioteca_lista_ark_sem_v1(tmp_path, monkeypatch):
    if not (INBOX.exists()):
        pytest.skip("sem data/inbox/ark")
    samples = tmp_path / "samples"
    (samples / "ark").mkdir(parents=True)
    for p in INBOX.glob("*"):
        if p.is_file():
            shutil.copy(p, samples / "ark" / p.name)
    monkeypatch.setattr(library, "SAMPLES", samples)
    monkeypatch.setattr(library, "CTB_RAW", tmp_path / "noctb")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    items = library.list_items(dataset="ark")
    assert len(items) == 15 and {i.agent for i in items} == {"Ark"} and {i.model for i in items} == {"claude-haiku-5-5"}
    assert not any("v1" in i.id for i in items) and sum(1 for i in items if i.resolved) == 14
