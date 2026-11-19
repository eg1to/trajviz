import json
from pathlib import Path

import pytest

FX = Path(__file__).parent / "fixtures"
CTB = FX / "ctb"


def jload(name: str):
    return json.loads((FX / name).read_text())


@pytest.fixture(scope="session")
def ctb_dir():
    return CTB


def ctb_path(prefix: str) -> Path:
    return next(p for p in CTB.iterdir() if p.is_dir() and p.name.startswith(prefix) and "mlflow" not in p.name)


def manifest_row(traj_id: str) -> dict:
    for line in (CTB / "bench_manifest.verified.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["traj_id"] == traj_id:
            return r
    raise KeyError(traj_id)
