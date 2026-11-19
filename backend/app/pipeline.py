"""Pipeline: detect → parse → label → detectores → métricas, com cache em disco (chave = hash do conteúdo + versão do pipeline)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app import config
from app.adapters import codetracebench
from app.adapters.base import UnknownFormat, UnsupportedArtifact
from app.adapters.detect import BY_NAME, detect, load
from app.analysis.detectors import run_detectors
from app.analysis.metrics import Metrics, compute_metrics
from app.config import LLMConfig
from app.labeling import label_trajectory
from app.labeling.llm import LLMLabeler
from app.schema import Trajectory

APP_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_EXTRACT_BYTES = 1024 * 1024 * 1024
SUFFIXES = (".tar.zst", ".zip", ".parquet", ".jsonl", ".json", ".traj")


def _version() -> str:
    """Hash do código que define o resultado: mudar regras/adaptadores/detectores/schema invalida o cache."""
    h = hashlib.sha256()
    for sub in ("schema.py", "adapters", "labeling", "analysis", "pipeline.py"):
        p = APP_DIR / sub
        for f in sorted([p] if p.is_file() else p.rglob("*.py")):
            h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:12]


PIPELINE_VERSION = _version()


def cache_dir() -> Path:
    d = config.CACHE_DIR / "trajectories"
    d.mkdir(parents=True, exist_ok=True)
    return d


class PipelineError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


class SourceInfo(BaseModel):
    filename: str
    sha256: str
    row: int = 0
    format_hint: str | None = None
    sample_id: str | None = None


class ProcessedTrajectory(BaseModel):
    id: str
    format_detected: str
    confidence: float
    source: SourceInfo
    trajectory: Trajectory
    metrics: Metrics
    warnings: list[str] = Field(default_factory=list)
    llm_used: bool = False
    pipeline_version: str = PIPELINE_VERSION


def sanitize_name(name: str) -> str:
    base = Path(name or "upload").name
    return re.sub(r"[^\w.\-]", "_", base)[:200] or "upload"


def file_suffix(name: str) -> str | None:
    low = name.lower()
    return next((s for s in SUFFIXES if low.endswith(s)), None)


def effective_llm(use_llm: bool | None) -> tuple[bool, str | None]:
    cfg = LLMConfig.from_env()
    if use_llm is None:
        return cfg.usable, None
    if use_llm and not cfg.usable:
        return False, "use_llm pedido, mas o LLM está desligado ou sem ANTHROPIC_API_KEY: usando só regras"
    return use_llm, None


def cache_key(content_sha: str, filename: str, row: int, fmt: str | None, llm: bool) -> str:
    model = LLMConfig.from_env().model if llm else ""
    return hashlib.sha256(f"{content_sha}|{sanitize_name(filename)}|{row}|{fmt}|{llm}|{model}|{PIPELINE_VERSION}".encode()).hexdigest()


def load_cached(pid: str) -> ProcessedTrajectory | None:
    for p in cache_dir().glob(f"{pid}*.json"):
        if not p.name.endswith(".meta.json"):
            return ProcessedTrajectory.model_validate_json(p.read_text())
    return None


def save_cached(pt: ProcessedTrajectory, key: str) -> None:
    d = cache_dir()
    (d / f"{key}.json").write_text(pt.model_dump_json())
    (d / f"{key}.meta.json").write_text(json.dumps({
        "id": pt.id, "n_steps": len(pt.trajectory.steps), "resolved": pt.trajectory.resolved, "format": pt.format_detected,
        "agent": pt.trajectory.agent, "model": pt.trajectory.model, "task": pt.trajectory.task_id}))


# ----------------------------------------------------------------------------- extração segura
def extract_zip(path: Path, dest: Path) -> Path:
    """Extrai .zip sem path traversal, sem symlinks e sem segredos (.jwt_secret, *.pem, .env, id_rsa*…)."""
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise PipelineError("invalid_file", f"{path.name}: não é um .zip válido") from e
    with zf:
        for info in zf.infolist():
            name = info.filename
            parts = Path(name).parts
            if info.is_dir() or name.startswith("/") or ".." in parts:
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:  # symlink
                continue
            if codetracebench.is_secret(name):
                continue
            total += info.file_size
            if total > MAX_EXTRACT_BYTES:
                raise PipelineError("too_large", "conteúdo do .zip descompactado excede 1 GB")
            out = dest / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return dest


# ----------------------------------------------------------------------------- processamento
def _read(path_or_bytes: Any) -> bytes:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes)
    return Path(path_or_bytes).read_bytes()


def process(path_or_bytes: Any, filename: str, *, format_hint: str | None = None, row: int = 0, use_llm: bool | None = None,
            sample_id: str | None = None) -> ProcessedTrajectory:
    content = _read(path_or_bytes)
    if len(content) > MAX_UPLOAD_BYTES:
        raise PipelineError("too_large", f"arquivo excede o limite de {MAX_UPLOAD_BYTES // 2**20} MB")
    name = sanitize_name(filename)
    suffix = file_suffix(name)
    if suffix is None:
        raise PipelineError("unsupported_extension", f"extensão não suportada: {name!r}. Aceitos: {', '.join(SUFFIXES)}")
    if format_hint is not None and format_hint not in BY_NAME and format_hint != "codetracebench":
        raise PipelineError("invalid_format_hint", f"format={format_hint!r} desconhecido. Opções: {sorted(BY_NAME)}")
    llm_on, llm_warn = effective_llm(use_llm)
    sha = hashlib.sha256(content).hexdigest()
    key = cache_key(sha, name, row, format_hint, llm_on)
    hit = load_cached(key)
    if hit is not None:
        return hit
    warnings = [llm_warn] if llm_warn else []
    with tempfile.TemporaryDirectory(prefix="trajviz-") as tmp:
        tmpd = Path(tmp)
        f = tmpd / name
        f.write_bytes(content)
        try:
            src: Any = extract_zip(f, tmpd / "zip" / name[: -len(".zip")]) if suffix == ".zip" else f
            if suffix == ".zip":  # um único diretório raiz dentro do zip
                kids = [p for p in src.iterdir()]
                src = kids[0] if len(kids) == 1 and kids[0].is_dir() else src
            obj = load(src, row)
            name_det, conf = detect(obj, row)
            if format_hint and isinstance(obj, Path):
                if format_hint != "codetracebench" and format_hint != name_det:
                    raise PipelineError("format_mismatch", f"format={format_hint!r} não confere com o artefato (detectado: {name_det})")
            elif format_hint and format_hint != "codetracebench":
                name_det, conf = format_hint, 1.0
            if isinstance(obj, Path):
                traj = codetracebench.parse(obj)
            else:
                traj = BY_NAME[name_det].parse(obj)
        except PipelineError:
            raise
        except UnknownFormat as e:
            raise PipelineError("unknown_format", f"formato não reconhecido: {e}", top_keys=getattr(e, "top_keys", [])) from e
        except UnsupportedArtifact as e:
            raise PipelineError("unsupported_artifact", str(e)) from e
        except (json.JSONDecodeError, UnicodeDecodeError, IndexError, KeyError, ValueError, TypeError) as e:
            raise PipelineError("invalid_file", f"{name}: arquivo inválido ou corrompido ({type(e).__name__}: {str(e)[:200]})") from e
    if not traj.steps:
        raise PipelineError("empty_trajectory", f"{name}: nenhuma ação/passo encontrada na trajetória")
    llm = LLMLabeler(LLMConfig.from_env()) if llm_on else None
    if llm is not None:
        llm.cfg.enabled = True
    label_trajectory(traj, llm)
    run_detectors(traj)
    if traj.resolved is None:
        warnings.append("resolved ausente na fonte (null)")
    if not traj.resolved_validated:
        warnings.append("resolved/patch não são confiáveis neste formato (SWE-smith): o patch foi ignorado")
    gt = traj.ground_truth
    if gt is not None:
        unresolved = sum(1 for a in gt.annotations for s in a.steps if s.resolved_idx is None)
        hyp = sum(1 for a in gt.annotations for s in a.steps if s.resolved_via == "hypothesis")
        if unresolved:
            warnings.append(f"{unresolved} anotações do CodeTraceBench não puderam ser alinhadas a passos")
        if hyp:
            warnings.append(f"{hyp} anotações alinhadas por hipótese (cauda do step_id; ver docs/formats.md §4.5)")
        if gt.manifest_step_count and gt.manifest_step_count != len(traj.steps):
            warnings.append(f"step_count do manifest ({gt.manifest_step_count}) ≠ passos extraídos ({len(traj.steps)}): unidades diferentes")
    elif codetracebench.can_parse(Path(name)) > 0:
        warnings.append("trajetória do CodeTraceBench sem entrada no manifest: sem ground truth")
    if llm is not None and llm.errors:
        warnings.append(f"LLM: {'; '.join(sorted(set(llm.errors)))}")
    metrics = compute_metrics(traj)
    pt = ProcessedTrajectory(id=key[:16], format_detected=name_det, confidence=conf,
                             source=SourceInfo(filename=name, sha256=sha, row=row, format_hint=format_hint, sample_id=sample_id),
                             trajectory=traj, metrics=metrics, warnings=warnings, llm_used=llm_on)
    save_cached(pt, key)
    return pt


def recompute(pt: ProcessedTrajectory) -> ProcessedTrajectory:
    """Reaplica detectores + métricas (usado depois de corrigir um rótulo) e regrava o cache."""
    run_detectors(pt.trajectory)
    pt.metrics = compute_metrics(pt.trajectory)
    for p in cache_dir().glob(f"{pt.id}*.json"):
        if not p.name.endswith(".meta.json"):
            p.write_text(pt.model_dump_json())
    return pt
