"""SWE-smith (SWE-agent + Claude): `messages` é string JSON. A ação é lida POR MENSAGEM:
tool_calls → nativo · `<function=` → xml · último bloco ``` sem linguagem → ticks (docs/formats.md §2)."""
from __future__ import annotations

import json
import re
from typing import Any

from app.adapters.base import (
    Action, files_from_args, loads_args, make_obs, norm_tool, parse_editor_string, text_of, UnknownFormat,
)
from app.schema import Step, Trajectory

NAME = "sweagent_smith"
XML_FN = re.compile(r"<function=([\w\-]+)>(.*?)</function>", re.S)
XML_PARAM = re.compile(r"<parameter=([\w\-]+)>(.*?)</parameter>", re.S)


def _messages(obj: Any) -> list[dict] | None:
    if not isinstance(obj, dict) or "messages" not in obj:
        return None
    m = obj["messages"]
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except Exception:
            return None
    return m if isinstance(m, list) else None


def can_parse(obj: Any) -> float:
    msgs = _messages(obj)
    if not msgs or not isinstance(msgs[0], dict):
        return 0.0
    native = any(m.get("message_type") in ("action", "observation") for m in msgs if isinstance(m, dict))
    textual = any(isinstance(m, dict) and m.get("role") == "user" and text_of(m.get("content")).startswith("OBSERVATION:")
                  for m in msgs)
    if "instance_id" in obj and isinstance(obj["messages"], str):
        return 0.95  # linha Parquet do SWE-smith
    if native or textual:
        return 0.9 if "instance_id" in obj else 0.75
    return 0.0


def action_format(m: dict) -> str:
    if m.get("tool_calls") is not None or m.get("message_type") == "action":
        return "native"
    c = text_of(m.get("content"))
    if "<function=" in c:
        return "xml"
    return "ticks" if _last_bare_block(c) is not None else "none"


def _last_bare_block(c: str) -> tuple[str, str] | None:
    """(texto antes, conteúdo do último bloco ``` sem linguagem) ou None."""
    parts = c.split("```")
    if len(parts) < 3 or len(parts) % 2 == 0:
        return None
    inner = [(i, b) for i, b in enumerate(parts) if i % 2 == 1 and b.startswith("\n")]
    if not inner:
        return None
    i, body = inner[-1]
    return "```".join(parts[:i]).strip(), body[1:].strip()


def _action_from_args(name: str, args: dict, raw: str) -> Action:
    tool = norm_tool(name)
    cmd = args.get("command") if tool in ("bash", "editor") else None
    return Action(tool=tool, tool_native=name, command=cmd if isinstance(cmd, str) else None, args=args, raw=raw)


def _actions(m: dict) -> tuple[list[tuple[Action, str | None]], str | None, str | None, str]:
    """→ ([(ação, native_id)], pensamento, origem do pensamento, formato)."""
    fmt = action_format(m)
    c = text_of(m.get("content"))
    if fmt == "native":
        out = []
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            out.append((_action_from_args(fn.get("name", "other"), loads_args(fn.get("arguments")),
                                          str(fn.get("arguments"))), tc.get("id")))
        thought = (m.get("thought") or c or "").strip() or None
        return out, thought, "field" if thought else None, fmt
    if fmt == "xml":
        fns = XML_FN.findall(c)
        thought = c.split("<function=")[0].strip() or None
        out = []
        for name, body in fns[:1]:  # 0 casos com >1 bloco na amostra; ignoramos extras
            params = {k: v.strip("\n") for k, v in XML_PARAM.findall(body)}
            out.append((_action_from_args(name, params, f"<function={name}>{body}</function>"), None))
        return out, thought, "content" if thought else None, fmt
    if fmt == "ticks":
        thought, act = _last_bare_block(c)
        toks = act.split()
        first = toks[0] if toks else ""
        if first == "str_replace_editor":
            args = parse_editor_string(act)
            a = Action(tool="editor", tool_native="str_replace_editor", command=args.get("command"), args=args, raw=act)
        elif first == "submit":
            a = Action(tool="submit", tool_native="submit", raw=act)
        else:
            a = Action(tool="bash", tool_native="bash", command=act, args={"command": act}, raw=act)
        return [(a, None)], thought or None, "content" if thought else None, fmt
    t = c.strip() or None
    return [], t, "content" if t else None, fmt


def _obs_text(m: dict) -> str:
    return re.sub(r"^OBSERVATION:\n", "", text_of(m.get("content")))


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    msgs = _messages(source)
    if msgs is None:
        raise UnknownFormat("sweagent_smith: sem `messages` legível", list(source) if isinstance(source, dict) else None)
    steps: list[Step] = []
    by_id: dict[str, Step] = {}
    last_open: Step | None = None
    problem, fmts = None, {}
    seen_user = 0
    for m in msgs:
        role = m.get("role")
        if role == "assistant":
            acts, thought, src, fmt = _actions(m)
            fmts[fmt] = fmts.get(fmt, 0) + 1
            if not acts:  # mensagem sem ação (resposta/erro)
                steps.append(Step(idx=len(steps), thought=thought, thought_source=src,
                                  action=Action(tool="message", raw=thought or "")))
                last_open = None
                continue
            for j, (a, nid) in enumerate(acts):
                s = Step(idx=len(steps), native_id=nid, thought=thought if j == 0 else None,
                         thought_source=src if j == 0 else None, action=a, files=files_from_args(a.args))
                steps.append(s)
                if nid:
                    by_id[nid] = s
                last_open = s
        elif role in ("user", "tool"):
            if role == "user" and seen_user == 0:
                seen_user = 1
                problem = text_of(m.get("content")) or None
                continue
            ids = m.get("tool_call_ids") or []
            targets = [by_id[i] for i in ids if i in by_id] or ([last_open] if last_open is not None else [])
            for s in targets:
                if s.observation is None:
                    s.observation = make_obs(_obs_text(m))
            last_open = None
    row = source
    inst = row.get("instance_id")
    last = steps[-1] if steps else None
    t = Trajectory(
        id=str(row.get("traj_id") or inst or "unknown"), source_format=NAME, agent="SWE-agent", model=row.get("model"),
        task_id=inst, repo=inst.split(".")[0].replace("__", "/", 1) if inst else None, problem_statement=problem,
        resolved=row.get("resolved"), resolved_validated=False, patch=None,
        exit_status="submitted" if last is not None and last.action.tool == "submit" else None, steps=steps,
        meta={"action_formats": fmts, "patch_unreliable": True},
    )
    if meta:
        t.meta.update(meta)
    return t
