"""Detecção automática de formato (assinaturas do docs/formats.md §5) + carga de arquivos.

    detect(path_or_obj, row=0) -> (adapter_name, confidence)
    parse_any(path_or_obj, row=0, manifest_dir=None) -> Trajectory
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import zstandard

from app.adapters import (
    codetracebench, ctb_miniswe, ctb_openhands_events, ctb_openhands_swe, ctb_sweagent, ctb_terminus2,
    generic_chat, openhands_chat, sweagent_smith,
)
from app.adapters.base import UnknownFormat, UnsupportedArtifact
from app.schema import Trajectory

# ordem = ordem das assinaturas do §5 (desempate); generic_chat por último
ADAPTERS = [openhands_chat, sweagent_smith, ctb_sweagent, ctb_miniswe, ctb_openhands_swe, ctb_openhands_events,
            ctb_terminus2, generic_chat]
BY_NAME = {m.NAME: m for m in ADAPTERS}
MIN_CONF = 0.3


def tar_names(path: Path) -> list[str]:
    names = []
    with open(path, "rb") as fh, zstandard.ZstdDecompressor().stream_reader(fh) as r, tarfile.open(fileobj=r, mode="r|") as t:
        for m in t:
            names.append(m.name)
    return names


def classify_names(names: list[str]) -> str | None:
    """Agente do CodeTraceBench a partir dos nomes de arquivo do .tar.zst (sem extrair)."""
    j = "\n".join(names)
    if "/events/" in j and any(n.endswith(".json") and "/events/" in n for n in names):
        return "ctb_openhands_events"
    if "agent-logs/episode-" in j and "response.txt" in j:
        return "ctb_terminus2"
    if any(n.endswith(".traj") for n in names):
        return "ctb_sweagent"
    if any(n.endswith(".traj.json") for n in names):
        return "ctb_miniswe"
    if any("swe_raw/openhands" in n and n.endswith(".json") and not n.endswith(("report.json", "_result.json", "_metrics.json"))
           for n in names):
        return "ctb_openhands_swe"
    return None


def read_parquet_row(path: Path, row: int = 0) -> dict:
    pf = pq.ParquetFile(path)
    cols = [c for c in pf.schema_arrow.names if c != "tools"]  # `tools` é enorme e idêntico em toda linha
    seen = 0
    for batch in pf.iter_batches(batch_size=16, columns=cols):
        if seen + batch.num_rows > row:
            return batch.to_pylist()[row - seen]
        seen += batch.num_rows
    raise IndexError(f"row={row} fora do arquivo ({seen} linhas)")


def load(src: Any, row: int = 0) -> Any:
    """Caminho → objeto Python (dict/list) ou Path (diretório / .tar.zst). Objetos passam direto."""
    if not isinstance(src, (str, Path)):
        return src
    p = Path(src)
    if p.is_dir() or p.name.endswith(".tar.zst"):
        return p
    suf = p.suffix.lower()
    if suf == ".parquet":
        return read_parquet_row(p, row)
    if suf == ".jsonl":
        with open(p) as fh:
            for i, line in enumerate(fh):
                if i == row:
                    return json.loads(line)
        raise IndexError(f"row={row} fora do .jsonl")
    if suf in (".json", ".traj"):
        return json.loads(p.read_text())
    raise UnknownFormat(f"extensão não suportada: {p.name}")


def _top_keys(obj: Any) -> list[str]:
    if isinstance(obj, dict):
        return sorted(obj)
    if isinstance(obj, list):
        return sorted({k for m in obj[:20] if isinstance(m, dict) for k in m}) or [f"<lista de {type(obj[0]).__name__ if obj else 'vazio'}>"]
    if isinstance(obj, Path) and obj.is_dir():
        return sorted(p.name for p in obj.iterdir())[:30]
    return [type(obj).__name__]


def detect(src: Any, row: int = 0) -> tuple[str, float]:
    obj = load(src, row)
    if isinstance(obj, Path) and obj.name.endswith(".tar.zst"):
        name = classify_names(tar_names(obj))
        if name:
            return name, 0.95
        names = tar_names(obj)
        if any(n.endswith(("agent.cast", "agent.log")) for n in names) or \
                {n.split("/")[0] for n in names} & {"terminus2", "openhands", "miniswe", "swe_raw"}:
            raise UnsupportedArtifact(f"{obj.name}: artefato de agente conhecido, mas sem trajetória estruturada (sem episódios/eventos/JSON)")
        raise UnknownFormat(f"{obj.name}: .tar.zst sem estrutura conhecida do CodeTraceBench", sorted({n.split('/')[0] for n in names})[:20])
    best_name, best = None, 0.0
    for m in ADAPTERS:
        c = m.can_parse(obj)
        if c > best:
            best_name, best = m.NAME, c
    if (best_name is None or best < MIN_CONF) and isinstance(obj, Path) and obj.is_dir() \
            and (next(obj.rglob("agent.cast"), None) or next(obj.rglob("agent.log"), None) or next(obj.rglob("agent-logs"), None)):
        raise UnsupportedArtifact(f"{obj.name}: artefato só com logs/asciinema (sem trajetória estruturada)")
    if best_name is None or best < MIN_CONF:
        raise UnknownFormat("nenhuma assinatura de formato casou", _top_keys(obj))
    return best_name, best


def parse_any(src: Any, row: int = 0, manifest_dir: Path | str | None = None) -> Trajectory:
    """Detecta e converte. CTB (.tar.zst/diretório) usa `codetracebench.parse` (anexa ground_truth do manifest)."""
    obj = load(src, row)
    name, _ = detect(obj, row)
    if isinstance(obj, Path):
        return codetracebench.parse(obj, manifest_dir=manifest_dir)
    return BY_NAME[name].parse(obj)
