"""SWE-rebench (OpenHands v0.54 + Qwen3-Coder): uma linha Parquet por trajetória; `trajectory` = lista de mensagens."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.adapters.base import UnknownFormat
from app.adapters.chat_core import chat_steps, is_openai_msgs, oh_signature
from app.schema import Trajectory

NAME = "openhands_chat"
ROW_COLUMNS = ["trajectory_id", "instance_id", "repo", "trajectory", "model_patch", "exit_status", "resolved",
               "gen_tests_correct", "pred_passes_gen_tests"]  # sem `tools` (enorme e repetido)


def can_parse(obj: Any) -> float:
    if isinstance(obj, dict) and isinstance(obj.get("trajectory"), list) and obj["trajectory"] \
            and isinstance(obj["trajectory"][0], dict) and "role" in obj["trajectory"][0]:
        return 0.97 if "instance_id" in obj or "trajectory_id" in obj else 0.9
    if is_openai_msgs(obj) and oh_signature(obj):
        return 0.9
    return 0.0


def read_row(path: str | Path, row: int = 0) -> dict:
    """Lê UMA linha do Parquet sem carregar o arquivo (iter_batches, sem a coluna `tools`)."""
    pf = pq.ParquetFile(path)
    cols = [c for c in ROW_COLUMNS if c in pf.schema_arrow.names]
    seen = 0
    for batch in pf.iter_batches(batch_size=16, columns=cols):
        if seen + batch.num_rows > row:
            return batch.to_pylist()[row - seen]
        seen += batch.num_rows
    raise IndexError(f"row={row} fora do arquivo ({seen} linhas)")


def parse(source: Any, *, meta: dict | None = None, source_format: str = NAME) -> Trajectory:
    if isinstance(source, dict):
        msgs, row = source["trajectory"], source
    elif isinstance(source, list):
        msgs, row = source, {}
    else:
        raise UnknownFormat("openhands_chat espera dict (linha) ou lista de mensagens")
    steps, problem = chat_steps(msgs)
    resolved = row.get("resolved")
    t = Trajectory(
        id=str(row.get("trajectory_id") or row.get("id") or "unknown"),
        source_format=source_format, agent="OpenHands", model="Qwen3-Coder-480B" if row else None,
        task_id=row.get("instance_id"), repo=row.get("repo"), problem_statement=problem,
        resolved=None if resolved is None else bool(resolved), exit_status=row.get("exit_status"),
        patch=row.get("model_patch") or None, steps=steps,
        meta={k: row[k] for k in ("gen_tests_correct", "pred_passes_gen_tests") if k in row},
    )
    if meta:
        t.meta.update(meta)
    return t
