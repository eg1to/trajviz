"""API FastAPI (Fase 4). `cd backend && uv run uvicorn app.main:app --reload` → http://localhost:8000/docs"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import library, pipeline
from app.analysis.metrics import Metrics
from app.config import LLMConfig
from app.labeling.taxonomy import DESCRIPTIONS, PHASE, Category
from app.pipeline import PIPELINE_VERSION, PipelineError, ProcessedTrajectory
from app.schema import Step, Trajectory

OBS_CUT = 2000
ROOT = Path(__file__).resolve().parents[2]
LABELS_PT = {"explore": "Explorar", "search": "Buscar", "read": "Ler", "edit": "Editar", "reproduce": "Reproduzir", "test": "Testar",
             "setup": "Preparar", "vcs": "Versionar", "think": "Pensar", "submit": "Entregar", "other": "Outro"}
DISPLAY_ORDER = ["explore", "search", "read", "edit", "reproduce", "test", "vcs", "setup", "think", "submit", "other"]
FLAGS_DOC = {"error": "o comando falhou (exit code ≠ 0 ou padrão de erro; grep/diff com exit 1 não conta)",
             "test_fail": "teste/linter falhou", "test_pass": "teste passou", "repeated": "ação idêntica a uma anterior (sem edição no meio)",
             "no_new_info": "leitura/busca/exploração sem informação nova", "loop": "faz parte de um ciclo repetido",
             "truncated": "observação truncada pela ferramenta"}

app = FastAPI(title="trajviz API", version="0.4.0",
              description="Visualizador de trajetórias de agentes de código: upload → formato canônico + rótulos + flags + métricas.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def results_dir() -> Path:
    return Path(os.environ.get("TRAJVIZ_RESULTS_DIR", ROOT / "results"))


# ----------------------------------------------------------------------------- modelos de resposta
class ErrorDetail(BaseModel):
    code: str
    message: str
    top_keys: list[str] | None = None


class UploadResponse(BaseModel):
    id: str
    format_detected: str
    confidence: float
    n_steps: int
    warnings: list[str]


class TrajectoryResponse(BaseModel):
    id: str
    format_detected: str
    confidence: float
    warnings: list[str]
    llm_used: bool
    source_filename: str
    trajectory: Trajectory  # observações cortadas em 2.000 chars (Observation.chars = tamanho original; content_cut = true)


class StepResponse(BaseModel):
    id: str
    step: Step  # observação inteira


class CorrectionBody(BaseModel):
    category: Category
    note: str | None = Field(default=None, max_length=500)


class CorrectionResponse(BaseModel):
    step: Step
    metrics: Metrics


class CategoryInfo(BaseModel):
    id: str
    label: str
    phase: str
    description: str
    examples: list[str]
    order: int


class FlagInfo(BaseModel):
    id: str
    description: str


class TaxonomyResponse(BaseModel):
    categories: list[CategoryInfo]
    phases: list[str]
    display_order: list[str]
    flags: list[FlagInfo]


class Health(BaseModel):
    status: str
    pipeline_version: str
    llm_enabled: bool


def http_error(e: PipelineError) -> HTTPException:
    status = 413 if e.code == "too_large" else 422
    return HTTPException(status, detail=ErrorDetail(code=e.code, message=e.message, top_keys=e.extra.get("top_keys")).model_dump(exclude_none=True))


def get_processed(tid: str) -> ProcessedTrajectory:
    pt = pipeline.load_cached(tid) if tid.isalnum() else None
    if pt is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"trajetória {tid!r} não encontrada — reabra pela biblioteca (ou reenvie o arquivo)"})
    return pt


def cut_view(traj: Trajectory) -> Trajectory:
    v = traj.model_copy(deep=True)
    for s in v.steps:
        o = s.observation
        if o is not None and len(o.content) > OBS_CUT:
            o.content, o.content_cut = o.content[:OBS_CUT], True
    return v


def upload_response(pt: ProcessedTrajectory) -> UploadResponse:
    return UploadResponse(id=pt.id, format_detected=pt.format_detected, confidence=pt.confidence, n_steps=len(pt.trajectory.steps), warnings=pt.warnings)


# ----------------------------------------------------------------------------- endpoints
@app.get("/api/health", response_model=Health, tags=["meta"])
def health():
    return Health(status="ok", pipeline_version=PIPELINE_VERSION, llm_enabled=LLMConfig.from_env().usable)


@app.get("/api/taxonomy", response_model=TaxonomyResponse, tags=["meta"])
def taxonomy():
    cats = [CategoryInfo(id=c.value, label=LABELS_PT[c.value], phase=PHASE[c].value, description=DESCRIPTIONS[c][0],
                         examples=list(DESCRIPTIONS[c][1]), order=DISPLAY_ORDER.index(c.value)) for c in Category]
    cats.sort(key=lambda c: c.order)
    return TaxonomyResponse(categories=cats, phases=["Entendimento", "Modificação", "Verificação", "Controle"], display_order=DISPLAY_ORDER,
                            flags=[FlagInfo(id=k, description=v) for k, v in FLAGS_DOC.items()])


@app.post("/api/trajectories", response_model=UploadResponse, tags=["trajectories"],
          responses={413: {"model": ErrorDetail}, 422: {"model": ErrorDetail}})
async def upload(file: UploadFile = File(...), format: str | None = Form(None), row: int = Form(0), use_llm: bool | None = Form(None)):
    """Aceita .json, .jsonl, .traj, .parquet, .tar.zst e .zip (diretório). Limite: 200 MB.

    `use_llm` (padrão: falso) liga o fallback Haiku para passos ambíguos; exige LABEL_LLM_ENABLED=1 e ANTHROPIC_API_KEY no servidor."""
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > pipeline.MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail={"code": "too_large", "message": f"arquivo excede o limite de {pipeline.MAX_UPLOAD_BYTES // 2**20} MB"})
        chunks.append(chunk)
    return _process(b"".join(chunks), file.filename or "upload", format=format, row=row, use_llm=use_llm)


log = logging.getLogger("uvicorn.error")


def _process(content: Any, filename: str, **kw: Any) -> UploadResponse:
    t0 = time.perf_counter()
    try:
        pt = pipeline.process(content, filename, format_hint=kw.get("format"), row=kw.get("row", 0), use_llm=bool(kw.get("use_llm")),  # LLM só sob pedido
                              sample_id=kw.get("sample_id"))
    except PipelineError as e:
        raise http_error(e) from e
    log.info("processado %s: formato=%s passos=%d tempo=%.0f ms (inclui cache)", filename, pt.format_detected, len(pt.trajectory.steps), (time.perf_counter() - t0) * 1000)
    return upload_response(pt)


@app.get("/api/trajectories/{tid}", response_model=TrajectoryResponse, tags=["trajectories"])
def get_trajectory(tid: str):
    pt = get_processed(tid)
    return TrajectoryResponse(id=pt.id, format_detected=pt.format_detected, confidence=pt.confidence, warnings=pt.warnings,
                              llm_used=pt.llm_used, source_filename=pt.source.filename, trajectory=cut_view(pt.trajectory))


@app.get("/api/trajectories/{tid}/steps/{idx}", response_model=StepResponse, tags=["trajectories"])
def get_step(tid: str, idx: int):
    pt = get_processed(tid)
    if not 0 <= idx < len(pt.trajectory.steps):
        raise HTTPException(404, detail={"code": "step_not_found", "message": f"passo {idx} fora do intervalo 0..{len(pt.trajectory.steps) - 1}"})
    return StepResponse(id=pt.id, step=pt.trajectory.steps[idx])


@app.get("/api/trajectories/{tid}/metrics", response_model=Metrics, tags=["trajectories"])
def get_metrics(tid: str):
    return get_processed(tid).metrics


@app.patch("/api/trajectories/{tid}/steps/{idx}", response_model=CorrectionResponse, tags=["trajectories"])
def correct_step(tid: str, idx: int, body: CorrectionBody):
    """Corrige a categoria de um passo (label_source=\"user\") e registra em results/gold/corrections.jsonl."""
    pt = get_processed(tid)
    if not 0 <= idx < len(pt.trajectory.steps):
        raise HTTPException(404, detail={"code": "step_not_found", "message": f"passo {idx} fora do intervalo"})
    s = pt.trajectory.steps[idx]
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "traj_id": pt.id, "trajectory": pt.trajectory.id,
           "source": pt.source.sample_id or pt.source.filename, "idx": idx, "previous_category": s.category,
           "previous_label_source": s.label_source, "previous_confidence": s.confidence, "new_category": body.category.value,
           "note": body.note}
    s.category, s.label_source, s.confidence = body.category.value, "user", 1.0  # type: ignore[assignment]
    pipeline.recompute(pt)
    out = results_dir() / "gold" / "corrections.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return CorrectionResponse(step=pt.trajectory.steps[idx], metrics=pt.metrics)


@app.get("/api/library", response_model=list[library.LibraryItem], tags=["library"])
def get_library(dataset: str | None = None, agent: str | None = None, resolved: bool | None = None, q: str | None = Query(None)):
    return library.list_items(dataset=dataset, agent=agent, resolved=resolved, q=q)


@app.post("/api/library/{sample_id:path}/open", response_model=UploadResponse, tags=["library"],
          responses={404: {"model": ErrorDetail}, 422: {"model": ErrorDetail}})
def open_sample(sample_id: str, use_llm: bool | None = None):
    hit = library.find(sample_id)
    if hit is None:
        raise HTTPException(404, detail={"code": "sample_not_found", "message": f"amostra {sample_id!r} não existe na biblioteca"})
    item, path = hit
    return _process(path, path.name, use_llm=use_llm, sample_id=item.id)
