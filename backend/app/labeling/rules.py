"""Camada 1 (ferramenta) + orquestra a camada 2 (bash_parser) para um passo. Tabela §8 do docs/formats.md."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from app.labeling.bash_parser import (
    BashResult, Ctx, _python_code, classify_command, fref, normalize_path,
)
from app.labeling.taxonomy import Category as C
from app.labeling.taxonomy import pick_by_precedence
from app.schema import FileRef, Step

CONTROL_KEYS = re.compile(r"^(?:C-[a-zA-Z\\\[]|Enter|Escape|Esc|Tab|Up|Down|Left|Right|BSpace|Space|Home|End|PageUp|PageDown|q|y|n|Y|N|yes|no)$")
DIR_LISTING = "Here's the files and directories"
HARNESS_OBS = ("**STOP! BEFORE SUBMITTING", "<context_received>", "Context received and recorded")
HARNESS_TXT = "<PATCH_CONTEXT>"
EDIT_CMDS = {"create", "str_replace", "insert", "undo_edit", "edit", "write", "replace", "append"}
SWE_READ = {"open", "goto", "scroll_up", "scroll_down"}
SWE_SEARCH = {"search_file", "search_dir", "find_file"}
SWE_EDIT = {"edit", "create", "insert", "replace", "undo_edit"}


@dataclass
class Label:
    category: C = C.other
    subcategory: str | None = None
    confidence: float = 0.3
    files: list[FileRef] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    summary: str | None = None  # segmento que definiu a categoria
    final: bool = False  # True = rótulo definitivo (não vai para o LLM): keys, harness, ferramenta exata


def _truthy(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


def is_keys_only(s: str) -> bool:
    toks = s.replace("\\n", "\n").split()
    return not toks or all(CONTROL_KEYS.match(t) for t in toks)


def harness_protocol(step: Step) -> bool:
    obs = step.observation.content if step.observation else ""
    return (any(m in obs[:400] for m in HARNESS_OBS) or HARNESS_TXT in (step.action.raw or "")
            or HARNESS_TXT in (step.thought or "")[:300] or "<PATCH_CONTEXT>" in str(step.action.args)[:300])


def _from_bash(r: BashResult, final: bool = False) -> Label:
    return Label(r.category, r.subcategory, r.confidence, r.files, r.writes, summary=r.segment, final=final or r.keys_only)


def label_step_rules(step: Step, ctx: Ctx) -> Label:
    a = step.action
    obs = step.observation.content if step.observation else ""
    if harness_protocol(step):
        return Label(C.submit, "harness_protocol", 1.0, final=True)
    t = a.tool
    if t == "submit":
        return Label(C.submit, a.tool_native, 1.0, final=True)
    if t == "think" or t == "message":
        return Label(C.think, None, 1.0, final=True)
    if t == "task_tracker":
        return Label(C.think, "plan", 1.0, final=True)
    if t == "editor":
        cmd = (a.command or "").strip()
        path = a.args.get("path") if isinstance(a.args.get("path"), str) else None
        if cmd in ("view", "read", ""):
            is_dir = bool(path) and not os.path.splitext(path)[1] and obs.startswith(DIR_LISTING) and not a.args.get("view_range")
            if is_dir:
                return Label(C.explore, "view_dir", 1.0, final=True)
            f = fref(path, "read")
            return Label(C.read, "view", 1.0, [f] if f else [], final=True)
        if cmd in EDIT_CMDS:
            f = fref(path, "edit")
            if f is not None and cmd == "create":
                f.created = True
            if cmd == "create" and path:
                ctx.add(normalize_path(path) or path)
            return Label(C.edit, cmd, 1.0, [f] if f else [], [normalize_path(path) or path] if cmd == "create" and path else [], final=True)
        # subcomando malformado (ex.: command="grep -n …"): tratar como bash
        r = classify_command(cmd, ctx)
        r.confidence = min(r.confidence, 0.6)
        return _from_bash(r)
    if t == "swe_cmd":
        name = (a.command or "").strip()
        line = str(a.args.get("line") or a.raw or "")
        tok = line.split()
        path = next((w for w in tok[1:] if not w.startswith("-") and "/" in w or re.search(r"\.\w+$", w)), None) if tok else None
        if name in SWE_READ:
            f = fref(tok[1] if name == "open" and len(tok) > 1 else path, "read")
            return Label(C.read, name, 1.0, [f] if f else [], final=True)
        if name in SWE_SEARCH:
            return Label(C.search, name, 1.0, final=True)
        if name in SWE_EDIT:
            return Label(C.edit, name, 1.0, final=True)
        return Label(C.other, name, 0.3)
    if t in ("bash", "keys", "ipython"):
        return _label_shell(step, ctx)
    return Label(C.other, a.tool_native, 0.3)


def _label_shell(step: Step, ctx: Ctx) -> Label:
    a = step.action
    if a.tool == "ipython":
        r = _python_code(a.command or a.raw or "", None, ctx, "ipython")  # type: ignore[arg-type]
        return _from_bash(r)
    if a.tool == "keys":
        cmds = [c.get("keystrokes", "") for c in (a.args.get("commands") or [])] or [a.command or ""]
        if all(is_keys_only(c) for c in cmds):
            return Label(C.other, "keys", 1.0, final=True)
        rs = [classify_command(c, ctx) for c in cmds if not is_keys_only(c)]
        cat = pick_by_precedence([r.category for r in rs])
        chosen = next(r for r in rs if r.category is cat)
        sub = "|".join(dict.fromkeys(r.subcategory for r in rs if r.subcategory))
        files = [f for r in rs for f in r.files]
        return Label(cat, sub or None, chosen.confidence, files, [w for r in rs for w in r.writes], summary=chosen.segment)
    if _truthy(a.args.get("is_input")) or is_keys_only(a.command or ""):
        return Label(C.other, "keys", 1.0, final=True)
    return _from_bash(classify_command(a.command or a.raw or "", ctx))
