"""CodeTraceBench · Terminus2: diretório `agent-logs/episode-N/{prompt.txt,response.txt}`.
1 passo por episódio (step_ref_kind = episode). Observação = prompt.txt do episódio SEGUINTE."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.adapters.base import Action, UnsupportedArtifact, make_obs
from app.schema import Step, Trajectory

NAME = "ctb_terminus2"


def can_parse(obj: Any) -> float:
    if isinstance(obj, Path) and obj.is_dir():
        d = next(obj.rglob("agent-logs"), None)
        if d is not None and next(d.glob("episode-*/response.txt"), None):
            return 0.95
    return 0.0


def clean_terminal(text: str) -> str:
    """Remove o preenchimento em branco do terminal (linhas vazias no fim, espaços à direita)."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _read_json(txt: str) -> dict:
    try:
        v = json.loads(txt)
        return v if isinstance(v, dict) else {"_raw": txt}
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"_raw": txt}


def parse(source: Any, *, meta: dict | None = None) -> Trajectory:
    if not isinstance(source, Path):
        raise UnsupportedArtifact("ctb_terminus2 exige um diretório de episódios")
    ad = next(source.rglob("agent-logs"), None)
    eps = sorted(((int(p.name.split("-")[1]), p) for p in ad.glob("episode-*")), key=lambda x: x[0]) if ad else []
    if not eps:
        raise UnsupportedArtifact(f"{source.name}: sem agent-logs/episode-*")
    prompts = {n: (p / "prompt.txt").read_text(errors="replace") if (p / "prompt.txt").exists() else "" for n, p in eps}
    steps: list[Step] = []
    for k, (n, p) in enumerate(eps):
        rp = p / "response.txt"
        j = _read_json(rp.read_text(errors="replace")) if rp.exists() else {}
        cmds = [{"keystrokes": c.get("keystrokes", ""), "duration": c.get("duration")} for c in (j.get("commands") or [])]
        thought = "\n\n".join(x for x in (j.get("analysis"), j.get("plan")) if x) or (j.get("_raw") or None)
        done = bool(j.get("task_complete"))
        keys = "".join(c["keystrokes"] for c in cmds)
        args: dict[str, Any] = {"commands": cmds}
        if "task_complete" in j:
            args["task_complete"] = done
        tool = "submit" if (done and not cmds) else "keys"
        action = Action(tool=tool, tool_native="keystrokes", command=keys or None, args=args, raw=keys)
        obs = make_obs(clean_terminal(prompts[eps[k + 1][0]])) if k + 1 < len(eps) else None
        steps.append(Step(idx=len(steps), native_id=n, thought=thought,
                          thought_source="analysis_plan" if (j.get("analysis") or j.get("plan")) else ("content" if thought else None),
                          action=action, observation=obs))
    t = Trajectory(id=source.name, source_format=NAME, agent="Terminus2", problem_statement=prompts[eps[0][0]] or None,
                   steps=steps, meta={"n_episodes": len(eps)})
    if meta:
        t.meta.update(meta)
    return t
