import json
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import zstandard

from app.adapters.base import UnknownFormat, UnsupportedArtifact
from app.adapters.detect import detect, parse_any
from tests.conftest import CTB, FX, ctb_path, jload

EXPECTED_FILES = {
    "swe_rebench_row.json": "openhands_chat", "swe_rebench_messages.json": "openhands_chat",
    "smith_native.json": "sweagent_smith", "smith_tool_xml.json": "sweagent_smith",
    "smith_xml.json": "sweagent_smith", "smith_ticks.json": "sweagent_smith",
}
EXPECTED_DIRS = {"sweagent-": "ctb_sweagent", "miniswe-OpenAI": "ctb_miniswe", "terminus2-": "ctb_terminus2",
                 "openhands-Anthropic": "ctb_openhands_events", "openhands-OpenAI": "ctb_openhands_swe"}


@pytest.mark.parametrize("name,expected", EXPECTED_FILES.items())
def test_detect_json_fixtures(name, expected):
    got, conf = detect(FX / name)
    assert got == expected and conf >= 0.9
    assert parse_any(FX / name).source_format.startswith(expected.split("_")[0])


@pytest.mark.parametrize("prefix,expected", EXPECTED_DIRS.items())
def test_detect_ctb_dirs_and_tar(prefix, expected, tmp_path):
    d = next(p for p in CTB.iterdir() if p.is_dir() and p.name.startswith(prefix) and "mlflow" not in p.name)
    assert detect(d)[0] == expected
    arc = tmp_path / f"{d.name}.tar.zst"
    with open(arc, "wb") as fh, zstandard.ZstdCompressor().stream_writer(fh) as w, tarfile.open(fileobj=w, mode="w|") as tf:
        tf.add(d, arcname=d.name)
    assert detect(arc) == (expected, 0.95)
    assert parse_any(arc, manifest_dir=CTB).source_format == expected


def test_detect_single_file_ctb_forms():
    traj = next(ctb_path("sweagent-").rglob("*.traj"))
    assert detect(traj)[0] == "ctb_sweagent"  # extensão .traj
    assert detect(next(ctb_path("miniswe-OpenAI").rglob("*.traj.json")))[0] == "ctb_miniswe"
    assert detect(next(ctb_path("openhands-OpenAI").rglob("tensorblock*.json")))[0] == "ctb_openhands_swe"
    assert len(parse_any(traj).steps) == 33


def test_detect_jsonl_and_parquet_rows(tmp_path):
    row = jload("swe_rebench_row.json")
    jl = tmp_path / "x.jsonl"
    jl.write_text(json.dumps(row) + "\n" + json.dumps(jload("smith_native.json")) + "\n")
    assert detect(jl, row=0)[0] == "openhands_chat" and detect(jl, row=1)[0] == "sweagent_smith"
    smith = jload("smith_ticks.json")  # `messages` string JSON, como no Parquet real
    pq.write_table(pa.Table.from_pylist([smith, smith]), tmp_path / "s.parquet")
    assert detect(tmp_path / "s.parquet", row=1)[0] == "sweagent_smith"
    assert parse_any(tmp_path / "s.parquet", row=0).source_format == "sweagent_smith"
    with pytest.raises(IndexError):
        detect(tmp_path / "s.parquet", row=5)


def test_detect_generic_chat():
    msgs = [{"role": "user", "content": "x"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "bash", "input": {"command": "ls"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "a"}]}]
    assert detect(msgs)[0] == "generic_chat"


def test_unknown_format_lists_top_keys():
    with pytest.raises(UnknownFormat) as e:
        detect({"foo": 1, "bar": [1, 2]})
    assert e.value.top_keys == ["bar", "foo"] and "bar" in str(e.value)
    with pytest.raises(UnknownFormat):
        detect([{"a": 1}])


def test_detect_unsupported_artifact_dir():
    d = next(p for p in CTB.iterdir() if "mlflow" in p.name)
    with pytest.raises(UnsupportedArtifact):
        detect(d)
