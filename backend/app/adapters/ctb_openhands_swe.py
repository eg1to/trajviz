"""CodeTraceBench · OpenHands · SWE-bench: um JSON por chamada ao LLM. A trajetória é a chamada com mais
`messages` + `response.choices[0].message`; depois reusa o núcleo do openhands_chat (docs/formats.md §4.2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.adapters.base import UnsupportedArtifact
from app.adapters.openhands_chat import parse as parse_chat
from app.schema import Trajectory

NAME = "ctb_openhands_swe"


def _is_call(j: Any) -> bool:
    return isinstance(j, dict) and isinstance(j.get("messages"), list) and isinstance(j.get("response"), dict) \
        and "choices" in j["response"] and "kwargs" in j


def find_calls(d: Path) -> list[Path]:
    out = []
    for p in d.rglob("*.json"):
        if p.name in ("report.json",) or p.name.endswith(("_result.json", "_metrics.json")):
            continue
        out.append(p)
    return sorted(out)


def can_parse(obj: Any) -> float:
    if _is_call(obj):
        return 0.95
    if isinstance(obj, Path) and obj.is_dir() and not (obj / "events").exists():
        for p in find_calls(obj)[:3]:
            try:
                if _is_call(json.loads(p.read_text())):
                    return 0.9
            except Exception:
                continue
    return 0.0


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if isinstance(source, Path):
        best, bn, n_files = None, -1, 0
        for p in find_calls(source):
            try:
                j = json.loads(p.read_text())
            except Exception:
                continue
            if _is_call(j):
                n_files += 1
                if len(j["messages"]) > bn:
                    best, bn = j, len(j["messages"])
        if best is None:
            raise UnsupportedArtifact(f"{source}: nenhum JSON de chamada LLM (messages+response) encontrado")
    else:
        best, n_files = source, 1
    msgs = list(best["messages"]) + [best["response"]["choices"][0]["message"]]
    t = parse_chat(msgs, source_format=NAME)
    t.id = (source.name if isinstance(source, Path) else "ctb_openhands_swe")
    t.agent = "OpenHands"
    t.model = best["response"].get("model")
    t.meta.update({"n_llm_call_files": n_files, "cost": best.get("cost")})
    if meta:
        t.meta.update(meta)
    return t
