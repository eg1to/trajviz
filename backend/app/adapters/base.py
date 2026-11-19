"""Utilidades comuns aos adaptadores."""
from __future__ import annotations

import json
import re
import shlex
from typing import Any

from app.schema import Action, FileRef, Observation

EXIT_CODE_RE = re.compile(r"\[The command completed with exit code (-?\d+)\.\]")
TRUNC_RE = re.compile(
    r"<response clipped>|<NOTE>This file is too large|Output too long|\[Observation truncated|"
    r"\.\.\. ?\[?output truncated|\(truncated\)|\[\.\.\. ?\d* ?(?:lines|chars|characters)? ?(?:truncated|omitted)",
    re.I,
)


class UnknownFormat(ValueError):
    def __init__(self, msg: str, top_keys: list[str] | None = None):
        super().__init__(msg + (f" (chaves de topo: {top_keys})" if top_keys is not None else ""))
        self.top_keys = top_keys or []


class UnsupportedArtifact(ValueError):
    """Artefato reconhecido, mas sem trajetória estruturada para ler (ex.: só agent.cast)."""


# ferramenta nativa → ferramenta normalizada
TOOL_MAP = {
    "execute_bash": "bash", "bash": "bash", "run": "bash", "shell": "bash", "terminal": "bash",
    "str_replace_editor": "editor", "str_replace_based_edit_tool": "editor", "edit": "editor", "read": "editor",
    "think": "think", "finish": "submit", "submit": "submit", "task_tracker": "task_tracker",
    "message": "message", "run_ipython": "ipython", "execute_ipython_cell": "ipython", "keystrokes": "keys",
}
# comandos legados do SWE-agent (strings de ação, não ferramentas nativas)
SWE_CMDS = {"open", "goto", "scroll_up", "scroll_down", "create", "edit", "search_file", "search_dir", "find_file",
            "insert", "replace", "undo_edit"}


def norm_tool(native: str | None) -> str:
    return TOOL_MAP.get(native or "", native or "other")


def text_of(content: Any) -> str:
    """content pode ser str, lista de partes {type,text}, None."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


def make_obs(content: str | None, exit_code: int | None = None) -> Observation:
    c = content or ""
    return Observation(content=c, exit_code=exit_code, is_error=None if exit_code is None else exit_code != 0,
                       chars=len(c), truncated=bool(TRUNC_RE.search(c)))


def exit_code_from_text(text: str) -> int | None:
    m = EXIT_CODE_RE.search(text or "")
    return int(m.group(1)) if m else None


def loads_args(s: Any) -> dict:
    if isinstance(s, dict):
        return s
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {"_value": v}
    except Exception:
        return {"_raw": s}


def editor_action(native: str, args: dict, raw: str) -> Action:
    return Action(tool="editor", tool_native=native, command=args.get("command"), args=args, raw=raw)


def parse_editor_string(act: str) -> dict:
    """`str_replace_editor view /p --view_range 1 10` / `... str_replace /p --old_str '..' --new_str '..'` → args."""
    try:
        toks = shlex.split(act)
    except ValueError:
        toks = act.split()
    args: dict[str, Any] = {}
    if len(toks) > 1:
        args["command"] = toks[1]
    i = 2
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            key, vals = t[2:], []
            i += 1
            while i < len(toks) and not toks[i].startswith("--"):
                vals.append(toks[i]); i += 1
            args[key] = vals[0] if len(vals) == 1 else vals
        else:
            args.setdefault("path", t)
            i += 1
    return args


def files_from_args(args: dict) -> list[FileRef]:
    """Arquivo do editor (`args.path`); modo read para view/read, edit para o resto. A Fase 3 refina (bash, normalização)."""
    p = args.get("path")
    if not (isinstance(p, str) and p):
        return []
    return [FileRef(path=p, mode="read" if args.get("command") in ("view", "read", None) else "edit")]
