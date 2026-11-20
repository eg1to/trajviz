"""Núcleo compartilhado de mensagens estilo OpenAI (tool_calls): usado por openhands_chat, generic_chat e ctb_openhands_swe."""
from __future__ import annotations

from typing import Any

from app.adapters.base import (
    Action, exit_code_from_text, files_from_args, loads_args, make_obs, norm_tool, text_of,
)
from app.schema import Step

OH_TOOLS = {"execute_bash", "str_replace_editor", "finish", "think", "task_tracker"}


def is_openai_msgs(msgs: Any) -> bool:
    return (isinstance(msgs, list) and msgs and all(isinstance(m, dict) and "role" in m for m in msgs[:5])
            and any(m.get("role") == "assistant" and m.get("tool_calls") for m in msgs))


OH_FOOTER = "[The command completed with exit code"


def oh_signature(msgs: list) -> bool:
    """Evidência ESPECÍFICA de OpenHands: ferramenta `execute_bash`, ids `chatcmpl-tool-` ou o rodapé de shell do OpenHands.
    Nomes genéricos (bash, str_replace_editor, finish) também aparecem em logs OpenAI comuns e NÃO bastam."""
    for m in msgs:
        if not isinstance(m, dict):
            continue
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name") == "execute_bash" or str(tc.get("id", "")).startswith("chatcmpl-tool-"):
                return True
        if m.get("role") == "tool":
            if str(m.get("tool_call_id", "")).startswith("chatcmpl-tool-") or OH_FOOTER in (m.get("content") if isinstance(m.get("content"), str) else str(m.get("content"))):
                return True
    return False


def build_action(name: str, args: dict, raw: str) -> Action:
    tool = norm_tool(name)
    cmd = None
    if tool == "bash" or tool == "editor" or tool == "task_tracker":
        cmd = args.get("command")
    return Action(tool=tool, tool_native=name, command=cmd if isinstance(cmd, str) else None, args=args, raw=raw)


def chat_steps(msgs: list[dict]) -> tuple[list[Step], str | None]:
    """Um passo por tool_call. Observação = mensagem `tool` com o mesmo tool_call_id.
    Assistant sem tool_call vira passo `message` (resposta final/erro)."""
    by_id: dict[str, dict] = {}
    for m in msgs:
        if m.get("role") == "tool" and m.get("tool_call_id"):
            by_id[m["tool_call_id"]] = m
    steps: list[Step] = []
    problem = None
    for m in msgs:
        role = m.get("role")
        if role == "user" and problem is None:
            problem = text_of(m.get("content")) or None
        if role != "assistant":
            continue
        content = text_of(m.get("content")).strip() or None
        tcs = m.get("tool_calls") or []
        if not tcs:
            steps.append(Step(idx=len(steps), thought=content, thought_source="content" if content else None,
                              action=Action(tool="message", tool_native=None, raw=content or "")))
            continue
        for j, tc in enumerate(tcs):
            fn = tc.get("function") or {}
            name = fn.get("name") or "other"
            raw = fn.get("arguments") if isinstance(fn.get("arguments"), str) else str(fn.get("arguments"))
            args = loads_args(fn.get("arguments"))
            action = build_action(name, args, raw)
            thought, src = (content, "content") if (j == 0 and content) else (None, None)
            if action.tool == "think":
                t = args.get("thought")
                thought, src = (t, "think_tool") if t else (thought, src)
            elif action.tool == "submit" and not thought:
                thought = args.get("message") or args.get("final_thought") or None
                src = "field" if thought else None
            om = by_id.get(tc.get("id"))
            obs = None
            if om is not None:
                text = text_of(om.get("content"))
                obs = make_obs(text, exit_code_from_text(text) if action.tool == "bash" else None)
            steps.append(Step(idx=len(steps), native_id=tc.get("id"), thought=thought, thought_source=src,
                              action=action, observation=obs, files=files_from_args(args)))
    return steps, problem
