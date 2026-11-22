"""Biblioteca de amostras (data/samples/): metadados baratos lidos do arquivo cru; o que já está em cache usa o resumo (.meta.json)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app import config, pipeline
from app.adapters import ark_trace, codetracebench as ctb

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = Path(__import__("os").environ.get("TRAJVIZ_SAMPLES_DIR", ROOT / "data" / "samples"))
CTB_RAW = ctb.DEFAULT_DIR
CTB_FORMAT = {("SWE-agent", None): "ctb_sweagent", ("mini-SWE-agent", None): "ctb_miniswe", ("Terminus2", None): "ctb_terminus2"}


class LibraryItem(BaseModel):
    id: str
    dataset: str
    format: str | None = None
    agent: str | None = None
    model: str | None = None
    task: str | None = None
    n_steps: int | None = None
    resolved: bool | None = None
    processed: bool = False
    cache_id: str | None = None
    split: str | None = None


def _ctb_format(row: dict) -> str:
    a = row.get("agent")
    if a == "OpenHands":
        return "ctb_openhands_swe" if ctb.origin_of(row) == "SWE-bench" else "ctb_openhands_events"
    return CTB_FORMAT.get((a, None), "codetracebench")


def _entries() -> list[tuple[str, Path, dict]]:
    """(sample_id, caminho do arquivo, metadados crus)."""
    out: list[tuple[str, Path, dict]] = []
    for p in sorted((SAMPLES / "swe-rebench").glob("chat*.json")):
        j = json.loads(p.read_text())
        n = j.get("n_steps") or sum(len(m.get("tool_calls") or []) for m in j["trajectory"] if m["role"] == "assistant")
        out.append((f"swe-rebench/{p.stem}", p, {"dataset": "swe-rebench", "format": "openhands_chat", "agent": "OpenHands",
                                                 "model": "Qwen3-Coder-480B", "task": j.get("instance_id"), "n_steps": n,
                                                 "resolved": bool(j["resolved"]) if j.get("resolved") is not None else None}))
    for split in ("tool", "xml", "ticks"):
        for p in sorted((SAMPLES / "swe-smith" / split).glob("*.json")):
            j = json.loads(p.read_text())
            msgs = j["messages"] if isinstance(j["messages"], list) else json.loads(j["messages"])
            out.append((f"swe-smith/{split}/{p.stem}", p, {"dataset": "swe-smith", "split": split, "format": "sweagent_smith",
                                                         "agent": "SWE-agent", "model": j.get("model"), "task": j.get("instance_id"),
                                                         "n_steps": sum(1 for m in msgs if m.get("role") == "assistant"),
                                                         "resolved": j.get("resolved")}))
    for p in sorted((SAMPLES / "ark").glob("*.log")):  # traces reais do Ark (v2); o .meta.json ao lado dá modelo/tarefa
        a = ark_trace.read(p)
        steps = ark_trace.parse(a)
        out.append((f"ark/{p.stem}", p, {"dataset": "ark", "format": "ark_trace", "agent": ark_trace.AGENT, "model": a.side.get("model"),
                                         "task": a.side.get("task"), "n_steps": len(steps.steps), "resolved": steps.resolved}))
    ids_file = SAMPLES / "codetracebench" / "_sample_ids.json"
    if ids_file.exists():
        man = ctb.load_manifest()
        for tid in json.loads(ids_file.read_text()):
            row = man.get(tid)
            p = CTB_RAW / "bench_artifacts" / "full" / f"{tid}.tar.zst"
            if row is None or not p.exists():
                continue
            out.append((f"codetracebench/{tid}", p, {"dataset": "codetracebench", "format": _ctb_format(row), "agent": row["agent"],
                                                     "model": row["model"], "task": row["task_name"], "n_steps": row["step_count"],
                                                     "resolved": row.get("solved")}))
    return out


_INDEX: list[tuple[LibraryItem, Path]] | None = None


def _build() -> list[tuple[LibraryItem, Path]]:
    items = []
    for sid, path, meta in _entries():
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append((LibraryItem(id=sid, cache_id=pipeline.content_id(sha, 0, None), **meta), path))  # id estável: só o conteúdo
    return items


def index(refresh: bool = False) -> list[tuple[LibraryItem, Path]]:
    global _INDEX
    if _INDEX is None or refresh:
        _INDEX = _build()
    return _INDEX


def list_items(dataset: str | None = None, agent: str | None = None, resolved: bool | None = None, q: str | None = None) -> list[LibraryItem]:
    out = []
    for it, _ in index():
        if dataset and it.dataset != dataset:
            continue
        if agent and (it.agent or "").lower() != agent.lower():
            continue
        if resolved is not None and it.resolved != resolved:
            continue
        if q and q.lower() not in " ".join(str(x or "") for x in (it.id, it.task, it.agent, it.model, it.format)).lower():
            continue
        item = it.model_copy()
        for m in pipeline._files(it.cache_id or "", ".meta.json"):  # já processado (versão atual): usa o resumo real
            d = json.loads(m.read_text())
            item.processed, item.n_steps = True, d["n_steps"]
            item.resolved = d["resolved"] if d.get("resolved") is not None else item.resolved
        out.append(item)
    return out


def find(sample_id: str) -> tuple[LibraryItem, Path] | None:
    return next(((it, p) for it, p in index() if it.id == sample_id), None)
