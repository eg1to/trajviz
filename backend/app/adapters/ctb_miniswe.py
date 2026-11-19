"""CodeTraceBench · mini-SWE-agent: `*.traj.json`. Passo = mensagem `assistant` (step_ref_kind = assistant_rank)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.adapters.base import Action, UnsupportedArtifact, make_obs, text_of
from app.schema import Step, Trajectory

NAME = "ctb_miniswe"
BLOCK_RE = re.compile(r"```(?:bash|sh)?[ \t]*\n(.*?)```", re.S)
RC_RE = re.compile(r"<returncode>\s*(-?\d+)\s*</returncode>\s*(?:<output>\n?(.*?)</output>)?", re.S)
FORMAT_ERR = "Please always provide EXACTLY ONE action"
SUBMIT_MARK = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def can_parse(obj: Any) -> float:
    if isinstance(obj, dict) and str(obj.get("trajectory_format", "")).startswith("mini-swe-agent") \
            and isinstance(obj.get("messages"), list):
        return 0.97
    if isinstance(obj, Path) and obj.is_dir() and next(obj.rglob("*.traj.json"), None):
        return 0.9
    return 0.0


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if isinstance(source, Path):
        f = next(source.rglob("*.traj.json"), None)
        if f is None:
            raise UnsupportedArtifact(
                f"{source.name}: mini-SWE-agent sem trajetória estruturada (só logs/agent.cast); nada a extrair")
        j = json.loads(f.read_text())
    else:
        j = source
    msgs = j["messages"]
    steps: list[Step] = []
    problem = None
    for i, m in enumerate(msgs):
        if m["role"] == "user" and problem is None:
            problem = text_of(m.get("content")) or None
        if m["role"] != "assistant":
            continue
        c = text_of(m.get("content"))
        blk = BLOCK_RE.search(c)
        thought = (c[: blk.start()] if blk else c).strip()
        thought = re.sub(r"^THOUGHT:\s*", "", thought) or None
        if blk:
            cmd = blk.group(1).strip()
            tool = "submit" if SUBMIT_MARK in cmd else "bash"
            action = Action(tool=tool, tool_native="bash", command=cmd, args={"command": cmd}, raw=cmd)
        else:  # ex.: mensagem final com <PATCH_CONTEXT> (conta como passo no `step_id` do benchmark)
            action = Action(tool="message", raw=c)
        obs = None
        if i + 1 < len(msgs) and msgs[i + 1]["role"] == "user":
            ot = text_of(msgs[i + 1].get("content"))
            mm = RC_RE.search(ot)
            obs = make_obs((mm.group(2) or "").strip("\n") if mm else ot, int(mm.group(1)) if mm else None)
            if not mm and ot.startswith(FORMAT_ERR):  # a ação não foi executada (formato inválido do modelo)
                obs.is_error = True
        steps.append(Step(idx=len(steps), native_id=i, thought=thought, thought_source="content" if thought else None,
                          action=action, observation=obs))
    info = j.get("info") or {}
    t = Trajectory(id=source.name if isinstance(source, Path) else "ctb_miniswe", source_format=NAME, agent="mini-SWE-agent",
                   task_id=j.get("instance_id"), problem_statement=problem, exit_status=info.get("exit_status"),
                   patch=info.get("submission") or None, steps=steps,
                   meta={"mini_version": info.get("mini_version"), "trajectory_format": j.get("trajectory_format")})
    if meta:
        t.meta.update(meta)
    return t
