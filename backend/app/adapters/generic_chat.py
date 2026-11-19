"""Chat genérico: lista de mensagens estilo OpenAI (tool_calls) ou Anthropic (tool_use / tool_result)."""
from __future__ import annotations

from typing import Any

from app.adapters.base import Action, make_obs, norm_tool, text_of, files_from_args
from app.adapters.chat_core import build_action, chat_steps, is_openai_msgs
from app.schema import Step, Trajectory

NAME = "generic_chat"


def _msgs(obj: Any) -> list | None:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("messages", "trajectory", "conversation"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return None


def _is_anthropic(msgs: list) -> bool:
    for m in msgs:
        if isinstance(m, dict) and isinstance(m.get("content"), list):
            if any(isinstance(p, dict) and p.get("type") in ("tool_use", "tool_result") for p in m["content"]):
                return True
    return False


def can_parse(obj: Any) -> float:
    msgs = _msgs(obj)
    if not msgs or not all(isinstance(m, dict) and "role" in m for m in msgs[:5]):
        return 0.0
    if _is_anthropic(msgs):
        return 0.6
    if is_openai_msgs(msgs):
        return 0.5  # abaixo dos formatos específicos (openhands_chat 0.9)
    return 0.3 if any(m.get("role") == "assistant" for m in msgs) else 0.0


def _anthropic_steps(msgs: list[dict]) -> tuple[list[Step], str | None]:
    results = {}
    for m in msgs:
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            for p in m["content"]:
                if isinstance(p, dict) and p.get("type") == "tool_result":
                    results[p.get("tool_use_id")] = p
    steps, problem = [], None
    for m in msgs:
        if m.get("role") == "user" and problem is None:
            problem = text_of(m.get("content")) or None
        if m.get("role") != "assistant":
            continue
        parts = m["content"] if isinstance(m.get("content"), list) else [{"type": "text", "text": text_of(m.get("content"))}]
        thought = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text").strip() or None
        uses = [p for p in parts if p.get("type") == "tool_use"]
        if not uses:
            steps.append(Step(idx=len(steps), thought=thought, thought_source="content" if thought else None,
                              action=Action(tool="message", raw=thought or "")))
        for j, u in enumerate(uses):
            args = u.get("input") or {}
            act = build_action(u.get("name", "other"), args, str(args))
            r = results.get(u.get("id"))
            obs = None
            if r is not None:
                err = r.get("is_error")
                obs = make_obs(text_of(r.get("content")))
                if err is not None:
                    obs.is_error = bool(err)
            steps.append(Step(idx=len(steps), native_id=u.get("id"), thought=thought if j == 0 else None,
                              thought_source="content" if (j == 0 and thought) else None, action=act,
                              observation=obs, files=files_from_args(args)))
    return steps, problem


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    msgs = _msgs(source)
    steps, problem = _anthropic_steps(msgs) if _is_anthropic(msgs) else chat_steps(msgs)
    row = source if isinstance(source, dict) else {}
    t = Trajectory(id=str(row.get("id") or "generic"), source_format=NAME, problem_statement=problem, steps=steps,
                   model=row.get("model"), resolved=row.get("resolved"))
    if meta:
        t.meta.update(meta)
    return t
