"""Utilidades compartilhadas pelos scripts de avaliação (Fase 6): pipeline sem cache, estatística, caminhos."""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import codetracebench as ctb  # noqa: E402
from app.adapters.detect import BY_NAME, detect, load  # noqa: E402
from app.analysis.detectors import run_detectors  # noqa: E402
from app.analysis.metrics import compute_metrics  # noqa: E402
from app.labeling import label_trajectory  # noqa: E402

RESULTS = ROOT / "results"
CTB_DIR = ROOT / "data" / "raw" / "codetracebench"
SEED = 20251119


def run_pipeline(src, row: int = 0):
    """detect → parse → label (só regras) → detectores → métricas, SEM cache. Devolve (traj, metrics, segundos)."""
    t0 = time.perf_counter()
    obj = load(src, row)
    name, _ = detect(obj, row)
    traj = ctb.parse(obj, manifest_dir=CTB_DIR) if isinstance(obj, Path) else BY_NAME[name].parse(obj)
    label_trajectory(traj)
    run_detectors(traj)
    m = compute_metrics(traj)
    return traj, m, time.perf_counter() - t0


def verified_ids() -> list[str]:
    return [json.loads(line)["traj_id"] for line in (CTB_DIR / "bench_manifest.verified.jsonl").read_text().splitlines()]


def artifact(tid: str) -> Path:
    return CTB_DIR / "bench_artifacts" / "full" / f"{tid}.tar.zst"


# ----------------------------------------------------------------------------- estatística
def prf(tp: float, pred: float, pos: float) -> tuple[float, float, float]:
    p = tp / pred if pred else float("nan")
    r = tp / pos if pos else float("nan")
    if p == p and r == r:
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0  # TP=0 com marcados e positivos → F1 = 0 (não indefinido)
    else:
        f = float("nan")
    return p, r, f


def ci95(xs) -> tuple[float, float]:
    a = np.asarray([x for x in xs if x == x], dtype=float)
    return (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))) if len(a) else (float("nan"), float("nan"))


def cliffs_delta(a, b) -> float:
    """δ = P(a > b) − P(a < b); > 0 = a tende a ser maior que b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if not len(a) or not len(b):
        return float("nan")
    from scipy.stats import mannwhitneyu
    u = mannwhitneyu(a, b, alternative="two-sided", method="asymptotic").statistic
    return float(2 * u / (len(a) * len(b)) - 1)


def mann_whitney(a, b) -> tuple[float, float]:
    from scipy.stats import mannwhitneyu
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3 or (np.ptp(np.concatenate([a, b])) == 0):
        return float("nan"), float("nan")
    r = mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
    return float(r.statistic), float(r.pvalue)


def holm(pvals: list[float]) -> list[float]:
    """Correção de Holm-Bonferroni (p ajustados, monotônicos); NaN passa direto."""
    idx = [i for i, p in enumerate(pvals) if p == p]
    order = sorted(idx, key=lambda i: pvals[i])
    m = len(order)
    out = [float("nan")] * len(pvals)
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * pvals[i]))
        out[i] = run
    return out


def fmt(x: float, d: int = 3) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def fmt_ci(x: float, ci: tuple[float, float], d: int = 3) -> str:
    return f"{fmt(x, d)} [{fmt(ci[0], d)}; {fmt(ci[1], d)}]"
