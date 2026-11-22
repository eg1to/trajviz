"""API (TestClient): upload por formato, biblioteca, passo, métricas, PATCH, erros e segurança."""
import io
import json
import tarfile
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import zstandard
from fastapi.testclient import TestClient

from app import config, library, main, pipeline
from tests.conftest import CTB, FX, ctb_path, jload


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("TRAJVIZ_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("LABEL_LLM_ENABLED", "0")
    monkeypatch.setattr(library, "CTB_RAW", tmp_path / "noctb")
    return TestClient(main.app)


def up(client, name, data, **form):
    return client.post("/api/trajectories", files={"file": (name, data)}, data={k: str(v) for k, v in form.items()})


def tar_zst(d, name=None) -> bytes:
    buf = io.BytesIO()
    with zstandard.ZstdCompressor().stream_writer(buf, closefd=False) as w, tarfile.open(fileobj=w, mode="w|") as tf:
        tf.add(d, arcname=name or d.name)
    return buf.getvalue()


def zipdir(d, extra=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in d.rglob("*"):
            if p.is_file():
                z.write(p, f"{d.name}/{p.relative_to(d)}")
        for n, c in (extra or {}).items():
            z.writestr(n, c)
    return buf.getvalue()


CASES = [
    ("swe_rebench_row.json", "openhands_chat"), ("swe_rebench_messages.json", "openhands_chat"), ("smith_native.json", "sweagent_smith"),
    ("smith_tool_xml.json", "sweagent_smith"), ("smith_xml.json", "sweagent_smith"), ("smith_ticks.json", "sweagent_smith"),
]


@pytest.mark.parametrize("name,fmt", CASES)
def test_upload_json_fixtures(client, name, fmt):
    r = up(client, name, (FX / name).read_bytes(), use_llm="false")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["format_detected"] == fmt and b["confidence"] >= 0.9 and b["n_steps"] > 0 and isinstance(b["warnings"], list) and len(b["id"]) == 16
    t = client.get(f"/api/trajectories/{b['id']}").json()
    assert len(t["trajectory"]["steps"]) == b["n_steps"] and t["format_detected"] == fmt


@pytest.mark.parametrize("prefix,fmt", [("sweagent-", "ctb_sweagent"), ("miniswe-OpenAI", "ctb_miniswe"), ("terminus2-", "ctb_terminus2"),
                                        ("openhands-Anthropic", "ctb_openhands_events"), ("openhands-OpenAI", "ctb_openhands_swe")])
def test_upload_ctb_tar_zst_and_zip(client, prefix, fmt, monkeypatch):
    d = next(p for p in CTB.iterdir() if p.is_dir() and p.name.startswith(prefix) and "mlflow" not in p.name)
    monkeypatch.setattr("app.adapters.codetracebench.DEFAULT_DIR", CTB)
    monkeypatch.setattr("app.adapters.codetracebench._MANIFESTS", {})
    r = up(client, f"{d.name}.tar.zst", tar_zst(d), use_llm="false")
    assert r.status_code == 200, r.text
    assert r.json()["format_detected"] == fmt
    r2 = up(client, f"{d.name}.zip", zipdir(d), use_llm="false")
    assert r2.status_code == 200 and r2.json()["format_detected"] == fmt, r2.text
    m = client.get(f"/api/trajectories/{r.json()['id']}/metrics").json()
    assert m["ground_truth"] is not None  # manifest anexado pelo nome do arquivo


def test_upload_single_file_ctb_traj_jsonl_parquet(client, tmp_path):
    traj = next(ctb_path("sweagent-").rglob("*.traj"))
    r = up(client, "x.traj", traj.read_bytes(), use_llm="false")
    assert r.status_code == 200 and r.json()["format_detected"] == "ctb_sweagent"
    row = jload("smith_ticks.json")
    jl = (json.dumps(jload("swe_rebench_row.json")) + "\n" + json.dumps(row) + "\n").encode()
    assert up(client, "x.jsonl", jl, row=1, use_llm="false").json()["format_detected"] == "sweagent_smith"
    pq.write_table(pa.Table.from_pylist([row, row]), tmp_path / "s.parquet")
    r = up(client, "s.parquet", (tmp_path / "s.parquet").read_bytes(), row=1, use_llm="false")
    assert r.status_code == 200 and r.json()["format_detected"] == "sweagent_smith"
    assert up(client, "s.parquet", (tmp_path / "s.parquet").read_bytes(), row=9, use_llm="false").status_code == 422


def test_format_override_and_hint_errors(client):
    data = (FX / "smith_xml.json").read_bytes()
    assert up(client, "a.json", data, format="sweagent_smith", use_llm="false").json()["format_detected"] == "sweagent_smith"
    r = up(client, "a.json", data, format="nope")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_format_hint"


def test_get_trajectory_cuts_observation_and_step_is_full(client):
    big = "A" * 5000
    msgs = [{"role": "user", "content": "do it"}, {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": '{"command":"cat big.txt"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": big}, {"role": "assistant", "content": "done"}]
    tid = up(client, "big.json", json.dumps(msgs).encode(), use_llm="false").json()["id"]
    t = client.get(f"/api/trajectories/{tid}").json()["trajectory"]["steps"][0]["observation"]
    assert len(t["content"]) == 2000 and t["content_cut"] is True and t["chars"] == 5000
    full = client.get(f"/api/trajectories/{tid}/steps/0").json()["step"]["observation"]
    assert full["content"] == big and full["content_cut"] is False
    assert client.get(f"/api/trajectories/{tid}/steps/99").status_code == 404
    assert client.get(f"/api/trajectories/{tid}/steps/-1").status_code == 404


def test_metrics_endpoint_matches_schema(client):
    tid = up(client, "r.json", (FX / "swe_rebench_row.json").read_bytes(), use_llm="false").json()["id"]
    m = client.get(f"/api/trajectories/{tid}/metrics").json()
    assert {"outcome", "effort", "dynamics", "problems", "files", "context", "ground_truth"} <= set(m)
    assert m["outcome"]["n_steps"] == 11 and m["effort"]["by_category"]["think"]["count"] >= 1
    assert client.get("/api/trajectories/doesnotexist/metrics").status_code == 404


def test_patch_correction_records_user_label_and_recomputes(client, tmp_path):
    tid = up(client, "r.json", (FX / "swe_rebench_row.json").read_bytes(), use_llm="false").json()["id"]
    before = client.get(f"/api/trajectories/{tid}/metrics").json()["effort"]["by_category"]
    old = client.get(f"/api/trajectories/{tid}").json()["trajectory"]["steps"][3]["category"]
    r = client.patch(f"/api/trajectories/{tid}/steps/3", json={"category": "setup", "note": "era instalação"})
    assert r.status_code == 200 and r.json()["step"]["category"] == "setup" and r.json()["step"]["label_source"] == "user"
    assert r.json()["metrics"]["effort"]["by_category"]["setup"]["count"] == before["setup"]["count"] + (old != "setup")
    again = client.get(f"/api/trajectories/{tid}").json()["trajectory"]["steps"][3]
    assert again["category"] == "setup" and again["label_source"] == "user" and again["confidence"] == 1.0
    line = json.loads((tmp_path / "results" / "gold" / "corrections.jsonl").read_text().splitlines()[-1])
    assert line["idx"] == 3 and line["new_category"] == "setup" and line["previous_category"] == old and line["traj_id"] == tid
    assert client.patch(f"/api/trajectories/{tid}/steps/3", json={"category": "dance"}).status_code == 422
    assert client.patch(f"/api/trajectories/{tid}/steps/999", json={"category": "edit"}).status_code == 404


def test_errors_are_clear_422(client):
    r = up(client, "bad.json", b"{not json", use_llm="false")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_file" and "inválido" in r.json()["detail"]["message"]
    r = up(client, "u.json", json.dumps({"foo": 1, "bar": [1]}).encode(), use_llm="false")
    d = r.json()["detail"]
    assert r.status_code == 422 and d["code"] == "unknown_format" and d["top_keys"] == ["bar", "foo"]
    r = up(client, "a.exe", b"MZ")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unsupported_extension" and ".tar.zst" in r.json()["detail"]["message"]
    assert up(client, "e.json", b"[]", use_llm="false").status_code == 422
    assert up(client, "z.zip", b"not a zip", use_llm="false").json()["detail"]["code"] == "invalid_file"
    bad_tar = io.BytesIO()
    with zstandard.ZstdCompressor().stream_writer(bad_tar, closefd=False) as w, tarfile.open(fileobj=w, mode="w|") as tf:
        info = tarfile.TarInfo("random/file.txt"); info.size = 2; tf.addfile(info, io.BytesIO(b"hi"))
    r = up(client, "r.tar.zst", bad_tar.getvalue(), use_llm="false")
    assert r.status_code == 422 and r.json()["detail"]["code"] in ("unknown_format", "unsupported_artifact")
    assert client.get("/api/trajectories/zzzz").json()["detail"]["code"] == "not_found"


def test_unsupported_artifact_only_logs(client):
    d = next(p for p in CTB.iterdir() if "mlflow" in p.name)
    r = up(client, f"{d.name}.tar.zst", tar_zst(d), use_llm="false")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unsupported_artifact"


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_UPLOAD_BYTES", 1000)
    r = up(client, "big.json", b"[" + b"1," * 1000 + b"1]")
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"


def test_secrets_not_extracted_or_returned_and_zip_slip_blocked(client, tmp_path):
    d = ctb_path("sweagent-")
    z = zipdir(d, extra={f"{d.name}/.jwt_secret": "TOPSECRET", f"{d.name}/id_rsa": "KEY", "../../evil.txt": "pwned", f"{d.name}/server.pem": "PEM"})
    r = up(client, f"{d.name}.zip", z, use_llm="false")
    assert r.status_code == 200
    body = client.get(f"/api/trajectories/{r.json()['id']}").text + client.get(f"/api/trajectories/{r.json()['id']}/metrics").text
    assert "TOPSECRET" not in body and "PEM" not in body and "KEY" not in body.replace("KEYS", "")
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()
    # symlink no zip é ignorado
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zi = zipfile.ZipInfo(f"{d.name}/link.traj"); zi.external_attr = (0o120777 << 16); zf.writestr(zi, "/etc/passwd")
        for p in d.rglob("*"):
            if p.is_file():
                zf.write(p, f"{d.name}/{p.relative_to(d)}")
    assert up(client, f"{d.name}.zip", buf.getvalue(), use_llm="false").status_code == 200


def test_cache_hit_returns_same_id_and_no_reprocessing(client, monkeypatch):
    data = (FX / "smith_xml.json").read_bytes()
    a = up(client, "a.json", data, use_llm="false").json()
    monkeypatch.setattr(pipeline, "label_trajectory", lambda *a, **k: (_ for _ in ()).throw(AssertionError("reprocessou")))
    b = up(client, "a.json", data, use_llm="false").json()
    assert a["id"] == b["id"]


def test_cache_key_changes_with_pipeline_version(monkeypatch):
    k1 = pipeline.cache_key("abc", "f.json", 0, None, False)
    monkeypatch.setattr(pipeline, "PIPELINE_VERSION", "other")
    assert pipeline.cache_key("abc", "f.json", 0, None, False) != k1


# ----------------------------------------------------------------------------- biblioteca, taxonomia, saúde
@pytest.fixture()
def lib_client(client, tmp_path, monkeypatch):
    s = tmp_path / "samples"
    (s / "swe-rebench").mkdir(parents=True); (s / "swe-smith" / "xml").mkdir(parents=True); (s / "swe-smith" / "tool").mkdir(parents=True)
    row = jload("swe_rebench_row.json"); row["n_steps"] = 11
    (s / "swe-rebench" / "chatcmpl-abc.json").write_text(json.dumps(row))
    sm = jload("smith_xml.json")
    (s / "swe-smith" / "xml" / "x1.json").write_text(json.dumps(sm))
    sm2 = dict(sm, resolved=False, instance_id="other__repo.123.bug")
    (s / "swe-smith" / "xml" / "x2.json").write_text(json.dumps(sm2))
    monkeypatch.setattr(library, "SAMPLES", s)
    monkeypatch.setattr(library, "_INDEX", None)
    return client


def test_library_listing_filters_and_processed_flag(lib_client):
    items = lib_client.get("/api/library").json()
    assert {i["id"] for i in items} == {"swe-rebench/chatcmpl-abc", "swe-smith/xml/x1", "swe-smith/xml/x2"} and not any(i["processed"] for i in items)
    assert all({"id", "dataset", "format", "agent", "model", "task", "n_steps", "resolved"} <= set(i) for i in items)
    assert [i["id"] for i in lib_client.get("/api/library?dataset=swe-rebench").json()] == ["swe-rebench/chatcmpl-abc"]
    assert [i["id"] for i in lib_client.get("/api/library?resolved=false").json()] == ["swe-smith/xml/x2"]
    assert [i["id"] for i in lib_client.get("/api/library?agent=openhands").json()] == ["swe-rebench/chatcmpl-abc"]
    assert [i["id"] for i in lib_client.get("/api/library?q=other__repo").json()] == ["swe-smith/xml/x2"]
    assert lib_client.get("/api/library?q=zzzz").json() == []


def test_library_open_then_processed_without_reprocessing(lib_client, monkeypatch):
    r = lib_client.post("/api/library/swe-smith/xml/x1/open?use_llm=false")
    assert r.status_code == 200 and r.json()["format_detected"] == "sweagent_smith"
    it = next(i for i in lib_client.get("/api/library").json() if i["id"] == "swe-smith/xml/x1")
    assert it["processed"] is True and it["n_steps"] == r.json()["n_steps"]
    assert lib_client.post("/api/library/swe-smith/xml/nao-existe/open").status_code == 404
    t = lib_client.get(f"/api/trajectories/{r.json()['id']}").json()
    assert t["trajectory"]["steps"]


def test_taxonomy_and_health_and_cors(client):
    t = client.get("/api/taxonomy").json()
    assert [c["id"] for c in t["categories"]] == t["display_order"] and len(t["categories"]) == 11
    assert t["phases"] == ["Entendimento", "Modificação", "Verificação", "Controle"] and {"error", "test_fail", "loop"} <= {f["id"] for f in t["flags"]}
    assert all(c["description"] and len(c["examples"]) == 2 and c["phase"] in t["phases"] for c in t["categories"])
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and "pipeline_version" in h and "api_key" not in json.dumps(h).lower()
    r = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_openapi_has_all_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/trajectories", "/api/trajectories/{tid}", "/api/trajectories/{tid}/steps/{idx}", "/api/trajectories/{tid}/metrics",
              "/api/library", "/api/library/{sample_id}/open", "/api/taxonomy", "/api/health"]:
        assert p in paths, p
    assert "patch" in paths["/api/trajectories/{tid}/steps/{idx}"]


def test_id_is_stable_when_the_pipeline_version_changes(client, monkeypatch):
    data = (FX / "smith_xml.json").read_bytes()
    a = up(client, "a.json", data, use_llm="false").json()["id"]
    monkeypatch.setattr(pipeline, "PIPELINE_VERSION", "versao-nova")
    # cache da versão antiga não é servido: reabrir pela biblioteca/upload reprocessa e MANTÉM o id
    r = client.get(f"/api/trajectories/{a}")
    assert r.status_code == 404 and "reabra pela biblioteca" in r.json()["detail"]["message"]
    b = up(client, "a.json", data, use_llm="false").json()["id"]
    assert a == b and client.get(f"/api/trajectories/{a}").status_code == 200
    assert pipeline.content_id("x", 0, None) == pipeline.content_id("x", 0, None) != pipeline.content_id("x", 1, None)
    assert pipeline.content_id("x", 0, None) != pipeline.content_id("x", 0, "generic_chat")


def test_generic_upload_detected_as_generic(client):
    r = up(client, "generic_calc.json", (FX / "generic_calc.json").read_bytes(), use_llm="false")
    assert r.status_code == 200 and r.json()["format_detected"] == "generic_chat" and r.json()["n_steps"] == 10
    t = client.get(f"/api/trajectories/{r.json()['id']}").json()
    assert t["trajectory"]["agent"] == "desconhecido" and t["source_filename"] == "generic_calc.json" and t["trajectory"]["task_id"] is None


def test_cors_origins_por_ambiente(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert main.cors_origins() == ["http://localhost:5173"]
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:5174 ,http://127.0.0.1:5174,, ")
    assert main.cors_origins() == ["http://localhost:5174", "http://127.0.0.1:5174"]
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert main.cors_origins() == ["http://localhost:5173"]
