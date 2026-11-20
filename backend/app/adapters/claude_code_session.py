"""Sessão do Claude Code: `.jsonl` de `~/.claude/projects/<projeto>/<sessão>.jsonl` (uma entrada JSON por linha).

Cada mensagem `assistant` traz UM bloco em `message.content` (`thinking`, `text` ou `tool_use`); o resultado vem numa entrada `user` posterior,
bloco `tool_result` com o mesmo `tool_use_id`. Um passo = um `tool_use`; os blocos `text`/`thinking` que o antecedem viram o pensamento; texto sem
ferramenta vira passo `message`. Entradas de outros tipos (`attachment`, `api-request`, `queue-operation`…) e de subagentes (`isSidechain`) são ignoradas.

Mapeamento (só preenche `tool`/`command`; a categoria vem das regras existentes, nada de regra nova):
Bash → bash (`command`) · Read → editor/view · Edit, MultiEdit, NotebookEdit → editor/str_replace · Write → editor/create ·
Grep → swe_cmd/search_dir · Glob → swe_cmd/find_file · TodoWrite/TaskCreate/TaskUpdate → task_tracker · demais (Agent, Skill, WebFetch, ToolSearch, Monitor…) → `other`.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.adapters.base import Action, files_from_args, make_obs, text_of
from app.schema import Step, Trajectory

NAME = "claude_code_session"

EDITOR = {"Read": "view", "Edit": "str_replace", "MultiEdit": "str_replace", "NotebookEdit": "str_replace", "Write": "create"}
SEARCH = {"Grep": "search_dir", "Glob": "find_file"}
TRACKER = {"TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
EXIT_RE = re.compile(r"^Exit code (-?\d+)")
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _blocks(entry: dict) -> list[dict]:
    c = (entry.get("message") or {}).get("content")
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def _is_main(e: Any) -> bool:
    return isinstance(e, dict) and e.get("type") in ("user", "assistant") and not e.get("isSidechain")


def can_parse(obj: Any) -> float:
    if not isinstance(obj, list) or not obj or not all(isinstance(e, dict) for e in obj[:5]):
        return 0.0
    if not any("sessionId" in e for e in obj[:20]):
        return 0.0
    for e in obj:
        if e.get("type") == "assistant" and any(b.get("type") == "tool_use" for b in _blocks(e)):
            return 0.95
    return 0.0


def _action(name: str, args: dict) -> tuple[Action, dict]:
    raw = str(args)
    if name == "Bash":
        cmd = args.get("command")
        return Action(tool="bash", tool_native=name, command=cmd if isinstance(cmd, str) else None, args=args, raw=raw), args
    if name in EDITOR:
        a = dict(args)
        path = a.get("file_path") or a.get("notebook_path")
        if path:
            a["path"] = path
        if name == "Read" and (a.get("offset") is not None or a.get("limit") is not None):
            off, lim = int(a.get("offset") or 1), a.get("limit")
            a["view_range"] = [off, off + int(lim) - 1 if lim else -1]
        a["command"] = EDITOR[name]
        return Action(tool="editor", tool_native=name, command=EDITOR[name], args=a, raw=raw), a
    if name in SEARCH:
        a = dict(args)
        a["line"] = f"{SEARCH[name]} {args.get('pattern', '')} {args.get('path', '')}".strip()
        return Action(tool="swe_cmd", tool_native=name, command=SEARCH[name], args=a, raw=raw), {}
    if name in TRACKER:
        return Action(tool="task_tracker", tool_native=name, command="plan", args=args, raw=raw), {}
    return Action(tool="other", tool_native=name, args=args, raw=raw), {}


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    entries = [e for e in source if isinstance(e, dict)]
    main = [e for e in entries if _is_main(e)]
    results: dict[str, dict] = {}
    for e in main:
        if e["type"] == "user":
            for b in _blocks(e):
                if b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = b
    steps: list[Step] = []
    pending: list[str] = []
    problem = None
    models: Counter[str] = Counter()

    def flush_message() -> None:
        txt = "\n".join(pending).strip()
        pending.clear()
        if txt:
            steps.append(Step(idx=len(steps), thought=txt, thought_source="content", action=Action(tool="message", raw=txt)))

    for e in main:
        if e["type"] == "user":
            c = (e.get("message") or {}).get("content")
            if problem is None and not e.get("isMeta") and not any(b.get("type") == "tool_result" for b in _blocks(e)):
                txt = REMINDER_RE.sub("", text_of(c)).strip()
                problem = txt or None
            continue
        m = e.get("message") or {}
        if m.get("model"):
            models[m["model"]] += 1
        for b in _blocks(e):
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                pending.append(b["text"].strip())
            elif bt == "thinking" and (b.get("thinking") or "").strip():
                pending.append(b["thinking"].strip())
            elif bt == "tool_use":
                args = b.get("input") if isinstance(b.get("input"), dict) else {}
                act, fargs = _action(b.get("name") or "other", args)
                thought = "\n".join(pending).strip() or None
                pending.clear()
                r = results.get(b.get("id"))
                obs = None
                if r is not None:
                    txt = text_of(r.get("content"))
                    mm = EXIT_RE.match(txt)
                    obs = make_obs(txt, int(mm.group(1)) if mm else (1 if r.get("is_error") and act.tool == "bash" else (0 if act.tool == "bash" else None)))
                    if r.get("is_error"):
                        obs.is_error = True
                steps.append(Step(idx=len(steps), native_id=b.get("id"), thought=thought, thought_source="content" if thought else None,
                                  action=act, observation=obs, files=files_from_args(fargs) if fargs else []))
    # texto depois da última ferramenta = resposta final
    flush_message()
    first = next((e for e in entries if e.get("sessionId")), {})
    t = Trajectory(id=str(first.get("sessionId") or "claude-code-session"), source_format=NAME, agent="Claude Code",
                   model=models.most_common(1)[0][0] if models else None, problem_statement=problem, steps=steps)
    t.meta["claude_code"] = {"version": first.get("version"), "entries": len(entries), "sidechain_ignored": sum(1 for e in entries if e.get("isSidechain"))}
    if meta:
        t.meta.update(meta)
    return t
