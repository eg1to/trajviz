"""Trace do Ark (agente de código do orientador, https://github.com/mtov/ark): `agent_trace.log`, texto em blocos `[tipo]`.

Semântica confirmada em src/ark/{traces,agentic_loop,tools}.py do Ark:
  [request]                          prompt do usuário → problem_statement
  [response N]  thought:/action:     UM passo (N = nº da chamada ao modelo; sobem também nas respostas inválidas, então há buracos)
  [edit_file]   status: succeeded|failed|rejected, path, diff:, detail:   → observação do passo edit_file
  [tests]       status: passed|failed, detail: (só se falhou)               → observação do passo run_tests
  [finish]      status: completed|failed, stage: finish|finish_validation|post_apply_tests, detail:
  [validation_error] / [repair_attempt]   protocolo (resposta fora do formato / reparo): meta, ligados ao passo SEGUINTE
  [workspace] / [error] / [run_summary]   meta; run_summary.status = success | max_iterations_reached | failed

O Ark NÃO registra a saída de read_file, list_files, find_text nem a de testes que passaram → `observation=None` nesses passos; o aviso
`UNRECORDED_NOTE` fica em `meta["ark"]["unrecorded"]` (lista de idx) para o front mostrar. O resultado de edição/teste/finish (que o trace
registra) fica em `meta["ark"]["outcomes"][str(idx)]` e é lido pelo detector `detect_ark` e pelas regras de rotulação.
`tool_counts` do run_summary é guardado como veio (o `finish` conta como `run_tests` lá; não há conferência com os passos).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.adapters.base import UnknownFormat
from app.schema import Action, Observation, Step, Trajectory
from app.schema import FileRef

NAME = "ark_trace"
AGENT = "Ark"
UNRECORDED_NOTE = "saída não registrada pelo trace do Ark"
REJECTED_NOTE = "Edição rejeitada pelo usuário: o diff abaixo NÃO foi aplicado."
ARK_TOOLS = ("list_files", "read_file", "find_text", "run_tests", "edit_file", "finish")

HEADER_RE = re.compile(r"^\[(request|response (\d+)|edit_file|tests|finish|workspace|error|run_summary|validation_error|repair_attempt)\]$")
RESPONSE_SIG = re.compile(r"(?m)^\[response \d+\]\nthought: ")
WORKSPACE_PREFIX = re.compile(r"^(?:~|/[^\s]*?)/ark-workspace/?")
NAME_RE = re.compile(r"^(?P<task>.+?)__(?P<model>[^_].*?)__(?P<mode>[^_]+)__(?P<n>\d+)$")


class ArkLog(str):
    """Texto do trace + metadados do arquivo (`.meta.json` ao lado, ou o nome `tarefa__modelo__modo__n.log`)."""
    side: dict

    def __new__(cls, text: str, side: dict | None = None):
        o = super().__new__(cls, text)
        o.side = side or {}
        return o


def read(path: Path) -> ArkLog:
    """Lê o `.log`/`.txt` e o `.meta.json` irmão (quando existe). Sem sidecar, tenta o nome do arquivo."""
    side: dict = {}
    m = NAME_RE.match(path.stem)
    if m:
        side = {"task": m["task"], "model": m["model"], "mode": m["mode"]}
    sc = path.with_suffix(".meta.json")
    if sc.is_file():
        try:
            j = json.loads(sc.read_text(encoding="utf-8"))
            if isinstance(j, dict):
                side.update({k: j[k] for k in ("task", "model", "mode", "max_iterations", "started_at", "estimated_cost_usd") if k in j})
        except (OSError, ValueError):
            pass
    return ArkLog(path.read_text(encoding="utf-8", errors="replace"), side)


def obs_tail(text: str) -> str:
    return text[-3000:]


def can_parse(obj: Any) -> float:
    if not isinstance(obj, str):
        return 0.0
    head = obj.lstrip()[:20000]
    if head.startswith("[request]\n") and RESPONSE_SIG.search(obj):
        return 0.97
    if head.startswith("[request]\n") and re.search(r"(?m)^\[run_summary\]\nstatus: ", obs_tail(obj)):
        return 0.7  # run que falhou antes da 1ª resposta (ex.: recusa da API): 0 passos
    return 0.0


def _blocks(text: str) -> list[tuple[str, int | None, list[str]]]:
    out: list[tuple[str, int | None, list[str]]] = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = HEADER_RE.match(ln)
        if m:
            kind = "response" if m[1].startswith("response") else m[1]
            out.append((kind, int(m[2]) if m[2] else None, []))
        elif out:
            out[-1][2].append(ln)
    return out


def _body(lines: list[str]) -> str:
    return "\n".join(lines).strip("\n")


def _fields(lines: list[str], block_keys: tuple[str, ...] = ()) -> dict[str, str]:
    """`chave: valor` no início da linha. Chaves em `block_keys` (`diff`, `detail`, `response`) levam o resto do bloco;
    o bloco termina onde começa o próximo campo conhecido (`detail:` após o diff, `tools_called:` após o detail do [error]);
    linhas de diff começam com espaço, `+`, `-` ou `@`, nunca com esses nomes."""
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^(\w+):(?: (.*))?$", lines[i])
        if not m:
            i += 1
            continue
        k, v = m[1], m[2] or ""
        if k not in block_keys:
            out[k] = v
            i += 1
            continue
        rest = ([v] if v else []) + lines[i + 1:]
        end = next((j for j, ln in enumerate(rest) if re.match(r"^(?:detail|tools_called):(?: |$)", ln) and not ln.startswith(k + ":")), len(rest))
        out[k] = "\n".join(rest[:end]).strip("\n")
        if end == len(rest):
            break
        i += 1 + end - (1 if v else 0)
    return out


def _response(lines: list[str]) -> tuple[str, str]:
    """thought (pode ter várias linhas) e action (linha `action: …`; a última que aparece)."""
    thought: list[str] = []
    action = ""
    in_thought = False
    for ln in lines:
        if ln.startswith("action: ") or ln == "action:":
            action, in_thought = ln[len("action:"):].strip(), False
        elif ln.startswith("thought:"):
            thought, in_thought = [ln[len("thought:"):].strip()], True
        elif in_thought:
            thought.append(ln)
    return "\n".join(thought).strip(), action


def _path(s: str) -> str:
    return WORKSPACE_PREFIX.sub("", s.strip())


def _action(line: str) -> Action:
    name, _, rest = line.partition(" ")
    rest = rest.strip()
    args: dict[str, Any] = {"args": rest}
    if name == "read_file":
        p, _, rng = rest.partition("|")
        args["path"] = _path(p)
        if rng.strip():
            args["range"] = rng.strip()
    elif name == "find_text":
        q, _, d = rest.rpartition("|")
        args.update({"query": q.strip(), "dir": _path(d)})
    elif name in ("list_files", "edit_file"):
        args["path"] = _path(rest) if rest else "."
    return Action(tool="submit" if name == "finish" else name, tool_native=name, command=rest or None, args=args, raw=line)


def _meta_from_blocks(kind: str, lines: list[str]) -> dict[str, str]:
    return _fields(lines, ("response", "detail"))


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if not isinstance(source, str):
        raise UnknownFormat("trace do Ark deve ser texto")
    text = str(source)
    side = getattr(source, "side", {}) or {}
    blocks = _blocks(text)
    if not blocks or blocks[0][0] != "request":
        raise UnknownFormat("trace do Ark sem [request] no início")
    problem = _body(blocks[0][2]) or None

    steps: list[Step] = []
    outcomes: dict[str, dict] = {}
    unrecorded: list[int] = []
    protocol: list[dict] = []
    pending_proto: list[dict] = []
    extra: dict[str, Any] = {"workspace": [], "errors": [], "run_summary": None}

    def last_step(want: str) -> Step | None:
        s = steps[-1] if steps else None
        return s if s is not None and s.action.tool_native == want else None

    for kind, n, lines in blocks[1:]:
        if kind == "response":
            thought, act = _response(lines)
            s = Step(idx=len(steps), native_id=n, thought=thought or None, thought_source="field" if thought else None,
                     action=_action(act or "(sem ação)"))
            if pending_proto:
                for ev in pending_proto:
                    ev["next_step"] = s.idx
                protocol.extend(pending_proto)
                pending_proto = []
            if s.action.tool_native == "read_file" and s.action.args.get("path"):
                s.files = [FileRef(path=s.action.args["path"], mode="read")]
            elif s.action.tool_native == "edit_file" and s.action.args.get("path") not in (None, ".", "<invalid>"):
                s.files = [FileRef(path=s.action.args["path"], mode="edit")]
            steps.append(s)
        elif kind == "edit_file":
            s = last_step("edit_file")
            f = _fields(lines, ("diff", "detail"))
            if s is None:
                continue
            st, diff, detail = f.get("status", ""), f.get("diff", ""), f.get("detail", "")
            outcomes[str(s.idx)] = {"status": st, "detail": detail or None}
            if st == "failed":
                s.observation = Observation(content=detail, is_error=True, chars=len(detail))
            elif st == "rejected":
                c = f"{REJECTED_NOTE}\n{diff}" if diff else REJECTED_NOTE
                s.observation = Observation(content=c, chars=len(c))
                s.action.args["diff"] = diff
            else:
                s.observation = Observation(content=diff, is_error=False, chars=len(diff))
                s.action.args["diff"] = diff
        elif kind == "tests":
            s = last_step("run_tests")
            f = _fields(lines, ("detail",))
            if s is None:
                continue
            st, detail = f.get("status", ""), f.get("detail", "")
            outcomes[str(s.idx)] = {"status": st}
            if st != "passed":
                s.observation = Observation(content=detail, chars=len(detail))
        elif kind == "finish":
            s = last_step("finish")
            f = _fields(lines, ("detail",))
            if s is None:
                continue
            st, stage, detail = f.get("status", ""), f.get("stage", ""), f.get("detail", "")
            outcomes[str(s.idx)] = {"status": st, "stage": stage}
            if st != "completed":
                s.observation = Observation(content=detail, is_error=stage == "finish_validation" or None, chars=len(detail))
        elif kind in ("validation_error", "repair_attempt"):
            f = _meta_from_blocks(kind, lines)
            ev = {"type": kind, "reason": f.get("reason"), "next_step": None}
            if kind == "repair_attempt":
                ev["kind"] = f.get("kind")
            else:
                ev["response"] = (f.get("response") or "")[:4000]
            pending_proto.append(ev)
        elif kind == "workspace":
            extra["workspace"].append(_fields(lines, ()))
        elif kind == "error":
            extra["errors"].append(_fields(lines, ("detail",)))
        elif kind == "run_summary":
            extra["run_summary"] = _fields(lines, ())
    protocol.extend(pending_proto)  # sem passo seguinte (o run terminou em [error])

    for s in steps:
        if s.observation is None:
            unrecorded.append(s.idx)

    rs = extra["run_summary"] or {}
    status = rs.get("status")
    t = Trajectory(id="ark-" + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12], source_format=NAME, agent=AGENT,
                   model=side.get("model"), task_id=side.get("task"), problem_statement=problem,
                   resolved=(status == "success") if status else None, exit_status=status, steps=steps)
    t.meta["ark"] = {
        "unrecorded_note": UNRECORDED_NOTE, "unrecorded": unrecorded, "outcomes": outcomes, "protocol_events": protocol,
        "workspace": extra["workspace"], "errors": extra["errors"], "run_summary": rs or None,
        **{k: v for k, v in side.items() if k not in ("model", "task")},
    }
    t.meta["protocol_events"] = protocol
    if meta:
        t.meta.update(meta)
    return t
