"""CodeTraceBench · SWE-agent: arquivo `.traj` (JSON). trajectory[i] → passo (step_ref_kind = index)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.adapters.base import (
    SWE_CMDS, Action, UnsupportedArtifact, files_from_args, make_obs, parse_editor_string, text_of,
)
from app.schema import Step, Trajectory

NAME = "ctb_sweagent"


def can_parse(obj: Any) -> float:
    if isinstance(obj, dict) and isinstance(obj.get("trajectory"), list) and obj["trajectory"] \
            and isinstance(obj["trajectory"][0], dict) and "action" in obj["trajectory"][0] \
            and "observation" in obj["trajectory"][0]:
        return 0.97 if "history" in obj else 0.85
    if isinstance(obj, Path) and obj.is_dir() and next(obj.rglob("*.traj"), None):
        return 0.9
    return 0.0


def classify(act: str) -> Action:
    toks = act.split()
    first = toks[0] if toks else ""
    if not toks:
        return Action(tool="message", raw=act)
    if first == "str_replace_editor":
        args = parse_editor_string(act)
        return Action(tool="editor", tool_native=first, command=args.get("command"), args=args, raw=act)
    if first in ("submit", "exit_cost", "exit_format", "exit_context", "exit_error"):
        return Action(tool="submit", tool_native=first, raw=act)
    if first in SWE_CMDS:
        return Action(tool="swe_cmd", tool_native=first, command=first, args={"line": act.split("\n")[0]}, raw=act)
    return Action(tool="bash", tool_native="bash", command=act, args={"command": act}, raw=act)


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if isinstance(source, Path):
        f = next(source.rglob("*.traj"), None)
        if f is None:
            raise UnsupportedArtifact(f"{source}: sem .traj")
        j = json.loads(f.read_text())
    else:
        j = source
    steps = []
    for i, t in enumerate(j["trajectory"]):
        a = classify((t.get("action") or "").strip())
        th = (t.get("thought") or "").strip() or None
        steps.append(Step(idx=i, native_id=i, thought=th, thought_source="field" if th else None, action=a,
                          observation=make_obs(t.get("observation") or "") if t.get("observation") is not None else None,
                          files=files_from_args(a.args)))
    info = j.get("info") or {}
    problem = None
    for h in j.get("history") or []:
        if h.get("role") == "user":
            problem = text_of(h.get("content")) or None
            break
    t = Trajectory(id=source.name if isinstance(source, Path) else "ctb_sweagent", source_format=NAME, agent="SWE-agent",
                   problem_statement=problem, exit_status=info.get("exit_status"), patch=info.get("submission") or None,
                   steps=steps, meta={"swe_agent_version": info.get("swe_agent_version")})
    if meta:
        t.meta.update(meta)
    return t
