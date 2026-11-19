"""CodeTraceBench · OpenHands · TerminalBench: `events/<id>.json` (event stream).
Só ações de agente run, edit, read, run_ipython, think, finish, message; observação ligada por `cause`
(step_ref_kind = run_rank). Nunca lê arquivos de segredo (.jwt_secret…): só `events/*.json`."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.adapters.base import Action, UnsupportedArtifact, files_from_args, make_obs, norm_tool
from app.schema import Step, Trajectory

NAME = "ctb_openhands_events"
KEEP = {"run", "edit", "read", "run_ipython", "think", "finish", "message"}


def can_parse(obj: Any) -> float:
    if isinstance(obj, Path) and obj.is_dir():
        d = next(obj.rglob("events"), None)
        if d is not None and d.is_dir() and next(d.glob("*.json"), None):
            return 0.95
    return 0.0


def load_events(d: Path) -> dict[int, dict]:
    ev = {}
    for p in d.glob("*.json"):
        try:
            e = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(e, dict) and "id" in e:
            ev[int(e["id"])] = e
    return ev


def _llm_content(e: dict) -> str | None:
    try:
        c = e["tool_call_metadata"]["model_response"]["choices"][0]["message"].get("content")
        return (c or "").strip() or None
    except Exception:
        return None


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if not isinstance(source, Path):
        raise UnsupportedArtifact("ctb_openhands_events exige um diretório com events/")
    ed = next(source.rglob("events"), None)
    if ed is None:
        raise UnsupportedArtifact(f"{source.name}: sem events/")
    ev = load_events(ed)
    by_cause = {int(e["cause"]): e for e in ev.values() if e.get("cause") is not None}
    steps: list[Step] = []
    problem = None
    for i in sorted(ev):
        e = ev[i]
        if e.get("source") == "user" and e.get("action") == "message" and problem is None:
            problem = (e.get("args") or {}).get("content") or e.get("message") or None
        a = e.get("action")
        if e.get("source") != "agent" or a not in KEEP:
            continue
        args = dict(e.get("args") or {})
        thought, src = None, None
        if args.get("thought"):
            thought, src = args.pop("thought"), "field"
        else:
            args.pop("thought", None)
            c = _llm_content(e)
            thought, src = (c, "content") if c else (None, None)
        if a == "run":
            act = Action(tool="bash", tool_native=a, command=args.get("command"), args=args, raw=str(args.get("command") or ""))
        elif a in ("edit", "read"):
            act = Action(tool="editor", tool_native=a, command=args.get("command") or a, args=args, raw=json.dumps(args, default=str)[:4000])
        elif a == "run_ipython":
            act = Action(tool="ipython", tool_native=a, command=args.get("code"), args=args, raw=str(args.get("code") or ""))
        elif a == "think":
            thought, src = args.get("thought") or thought or e.get("message"), "think_tool"
            act = Action(tool="think", tool_native=a, args=args, raw=str(thought or ""))
        elif a == "finish":
            thought = args.get("final_thought") or thought
            src = "field" if args.get("final_thought") else src
            act = Action(tool="submit", tool_native=a, args=args, raw=str(args.get("final_thought") or ""))
        else:  # message
            txt = args.get("content") or e.get("message") or ""
            thought, src = txt or None, "content" if txt else None
            act = Action(tool="message", tool_native=a, args={k: v for k, v in args.items() if k != "content"}, raw=txt)
        o = by_cause.get(i)
        obs = None
        if o is not None:
            code = ((o.get("extras") or {}).get("metadata") or {}).get("exit_code") if a == "run" else None
            obs = make_obs(o.get("content") or "", code if isinstance(code, int) else None)
        steps.append(Step(idx=len(steps), native_id=i, thought=thought, thought_source=src, action=act,
                          observation=obs, files=files_from_args(args)))
    t = Trajectory(id=source.name, source_format=NAME, agent="OpenHands", problem_statement=problem, steps=steps,
                   meta={"n_event_files": len(ev)})
    if meta:
        t.meta.update(meta)
    return t
