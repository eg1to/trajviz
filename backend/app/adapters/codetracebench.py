"""CodeTraceBench: recebe um `.tar.zst` (ou diretório já extraído), descobre o agente pela estrutura (formats.md §4.2),
chama o adaptador certo e anexa o ground_truth do manifest (por traj_id), resolvendo `resolved_idx`."""
from __future__ import annotations

import json
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import zstandard

from app.adapters import (
    ctb_miniswe, ctb_openhands_events, ctb_openhands_swe, ctb_sweagent, ctb_terminus2,
)
from app.adapters.base import UnknownFormat, UnsupportedArtifact
from app.schema import AnnotatedStep, GroundTruth, StageAnnotation, StageRange, Trajectory

NAME = "codetracebench"
SECRET_RE = re.compile(r"(\.jwt_secret|secret|\.pem$|\.key$|id_rsa|id_ed25519|(^|/)\.env$|credentials|\.netrc|\.pgpass)", re.I)
DEFAULT_DIR = Path(os.environ.get("TRAJVIZ_CTB_DIR", Path(__file__).resolve().parents[3] / "data" / "raw" / "codetracebench"))
# (módulo, step_ref_kind, regra confirmada?)
AGENTS = {
    "ctb_openhands_events": (ctb_openhands_events, "run_rank", True),
    "ctb_terminus2": (ctb_terminus2, "episode", True),
    "ctb_sweagent": (ctb_sweagent, "index", True),
    "ctb_miniswe": (ctb_miniswe, "assistant_rank", True),
    "ctb_openhands_swe": (ctb_openhands_swe, "tool_call_rank", False),  # hipótese: sem action_ref para confirmar
}
ORDER = ["ctb_openhands_events", "ctb_terminus2", "ctb_sweagent", "ctb_miniswe", "ctb_openhands_swe"]


def can_parse(obj: Any) -> float:
    if isinstance(obj, Path) and obj.name.endswith(".tar.zst"):
        return 0.9
    return 0.0


# ----------------------------------------------------------------------------- extração segura
def is_secret(name: str) -> bool:
    return bool(SECRET_RE.search(name))


def extract(path: Path, dest: Path) -> Path:
    """Extrai o .tar.zst em `dest` (streaming), pulando segredos. Devolve o diretório."""
    dest.mkdir(parents=True, exist_ok=True)
    with open(path, "rb") as fh, zstandard.ZstdDecompressor().stream_reader(fh) as r, tarfile.open(fileobj=r, mode="r|") as t:
        for m in t:
            if is_secret(m.name):
                continue
            t.extract(m, dest, filter="data")
    return dest


# ----------------------------------------------------------------------------- detecção do agente
def detect_agent(d: Path) -> str:
    for name in ORDER:
        if AGENTS[name][0].can_parse(d) > 0:
            return name
    if next(d.rglob("agent.cast"), None) is not None or next(d.rglob("agent.log"), None) is not None:
        raise UnsupportedArtifact(f"{d.name}: artefato só com logs/asciinema (sem trajetória estruturada)")
    raise UnknownFormat(f"{d.name}: estrutura de CodeTraceBench não reconhecida",
                        sorted(p.name for p in d.iterdir())[:20])


# ----------------------------------------------------------------------------- manifest
_MANIFESTS: dict[str, dict[str, dict]] = {}


def load_manifest(directory: Path | str | None = None) -> dict[str, dict]:
    d = Path(directory) if directory else DEFAULT_DIR
    key = str(d)
    if key not in _MANIFESTS:
        rows: dict[str, dict] = {}
        for f in ("bench_manifest.full.jsonl", "bench_manifest.verified.jsonl"):  # verified por último (prevalece)
            p = d / f
            if p.exists():
                for line in p.read_text().splitlines():
                    r = json.loads(line)
                    rows[r["traj_id"]] = r
        _MANIFESTS[key] = rows
    return _MANIFESTS[key]


def _jl(x: Any) -> Any:
    return json.loads(x) if isinstance(x, str) else x


def origin_of(row: dict) -> str:
    return "SWE-bench" if (row.get("source_relpath") or "").startswith("swe_raw/") else "TerminalBench"


# ----------------------------------------------------------------------------- ground truth
def _ref_native_id(kind: str, ref: dict | None) -> int | None:
    if not ref:
        return None
    if kind == "run_rank":  # content = linha JSON do evento OpenHands: {"id": 59, …}
        m = re.search(r'"id":\s*(\d+)', ref.get("content", "")[:200])
        return int(m.group(1)) if m else None
    if kind == "episode":
        m = re.search(r"episode-(\d+)/", ref.get("path", ""))
        return int(m.group(1)) if m else None
    return None


def resolve_idx(t: Trajectory, kind: str, step_id: int, action_ref: dict | None) -> tuple[int | None, str | None]:
    """Alinha um step_id do benchmark ao idx canônico → (idx, via). `action_ref` manda quando existe.

    OpenHands-TB e Terminus2: a lista do benchmark = unidades "primárias" (ações `run` / 1 por episódio) seguidas de
    uma CAULDA (demais ações / 2º+ comando de cada episódio). step_id ≤ nº de primárias é confirmado (action_ref);
    a cauda é hipótese (nenhum action_ref a confirma). Ver docs/formats.md §4.5."""
    n = len(t.steps)
    nid = _ref_native_id(kind, action_ref)
    if nid is not None:
        for s in t.steps:
            if s.native_id == nid:
                return s.idx, "action_ref"
        return None, None
    if kind == "index" or kind == "assistant_rank":
        return (step_id - 1, "rule") if 1 <= step_id <= n else (None, None)
    if kind == "tool_call_rank":
        return (step_id - 1, "hypothesis") if 1 <= step_id <= n else (None, None)
    if kind == "episode":
        eps = [s for s in t.steps]
        E = len(eps)
        if 1 <= step_id <= E:
            return (eps[step_id - 1].idx, "rule") if eps[step_id - 1].native_id == step_id - 1 else (None, None)
        extras = [s.idx for s in eps for _ in s.action.args.get("commands", [])[1:]]
        j = step_id - E - 1
        return (extras[j], "hypothesis") if 0 <= j < len(extras) else (None, None)
    if kind == "run_rank":
        runs = [s.idx for s in t.steps if s.action.tool_native == "run"]
        if 1 <= step_id <= len(runs):
            return runs[step_id - 1], "rule"
        tail = [s.idx for s in t.steps if s.action.tool_native in ("edit", "read", "run_ipython", "think", "finish")]
        j = step_id - len(runs) - 1
        return (tail[j], "hypothesis") if 0 <= j < len(tail) else (None, None)
    return None, None


def build_ground_truth(t: Trajectory, row: dict, kind: str, confirmed: bool) -> GroundTruth:
    stages = [StageRange(**s) for s in _jl(row.get("stages")) or []]
    anns = []
    for st in _jl(row.get("incorrect_stages")) or []:
        steps = {s["step_id"]: s for s in st.get("steps") or []}
        for sid, lab in [(i, "incorrect") for i in st.get("incorrect_step_ids", [])] + \
                        [(i, "unuseful") for i in st.get("unuseful_step_ids", [])]:
            steps.setdefault(sid, {"step_id": sid, "labels": [lab], "action_ref": None, "observation_ref": None})
        ann_steps = []
        for s in sorted(steps.values(), key=lambda s: s["step_id"]):
            idx, via = resolve_idx(t, kind, s["step_id"], s.get("action_ref"))
            ann_steps.append(AnnotatedStep(step_id=s["step_id"], labels=s.get("labels") or [], action_ref=s.get("action_ref"),
                                           observation_ref=s.get("observation_ref"), resolved_idx=idx, resolved_via=via))
        anns.append(StageAnnotation(stage_id=st["stage_id"], incorrect_step_ids=st.get("incorrect_step_ids", []),
                                    unuseful_step_ids=st.get("unuseful_step_ids", []), steps=ann_steps,
                                    reasoning=st.get("reasoning")))
    return GroundTruth(stages=stages, annotations=anns, step_ref_kind=kind, ref_rule_confirmed=confirmed,
                       manifest_step_count=row.get("step_count"))


def apply_manifest(t: Trajectory, row: dict, kind: str, confirmed: bool) -> Trajectory:
    t.id = row["traj_id"]
    t.agent = row.get("agent") or t.agent
    t.model = row.get("model") or t.model
    t.task_id = row.get("task_name") or t.task_id
    t.resolved = row.get("solved")
    t.meta.update({k: row.get(k) for k in ("difficulty", "category", "tags", "task_slug", "trial_name", "stage_count")})
    t.meta["origin"] = origin_of(row)
    t.ground_truth = build_ground_truth(t, row, kind, confirmed)
    return t


# ----------------------------------------------------------------------------- API
def parse_dir(d: Path, *, row: dict | None = None, manifest_dir: Path | str | None = None) -> Trajectory:
    name = detect_agent(d)
    mod, kind, confirmed = AGENTS[name]
    t = mod.parse(d)
    if row is None:
        row = load_manifest(manifest_dir).get(d.name)
    if row is not None:
        apply_manifest(t, row, kind, confirmed)
    return t


def parse(source: Any, *, row: dict | None = None, manifest_dir: Path | str | None = None) -> Trajectory:
    p = Path(source)
    if p.is_dir():
        return parse_dir(p, row=row, manifest_dir=manifest_dir)
    if p.name.endswith(".tar.zst"):
        traj_id = p.name[: -len(".tar.zst")]
        with tempfile.TemporaryDirectory(prefix="trajviz-ctb-") as tmp:
            d = extract(p, Path(tmp) / traj_id)
            return parse_dir(d, row=row, manifest_dir=manifest_dir)
    raise UnknownFormat(f"{p}: esperado .tar.zst ou diretório do CodeTraceBench")
