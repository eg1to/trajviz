#!/usr/bin/env python
"""Baixa trajetórias do CodeTraceBench (bench_artifacts/full/<traj_id>.tar.zst) de forma lenta e retomável.

Uso (a partir da raiz do projeto):
    python backend/scripts/download_ctb_artifacts.py --sample 60
    python backend/scripts/download_ctb_artifacts.py --all

- Lê data/raw/codetracebench/bench_manifest.verified.jsonl.
- --sample N: amostra estratificada por agente x origem (SWE-bench / TerminalBench).
- Um arquivo por vez; pula os que já existem com o tamanho certo; ~1 s entre downloads;
  em HTTP 429 faz backoff exponencial (60 s, 120 s, ...).
- Progresso em data/raw/codetracebench/_download_log.jsonl.
"""
import argparse
import json
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import HfHubHTTPError
from tqdm import tqdm

REPO = "NJU-LINK/CodeTraceBench"
ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "data" / "raw" / "codetracebench"
MANIFEST = DEST / "bench_manifest.verified.jsonl"
LOG = DEST / "_download_log.jsonl"
SLEEP = 1.0
BACKOFF0 = 60
MAX_RETRIES = 6


def origin(row: dict) -> str:
    src = row.get("source_relpath") or ""
    return "SWE-bench" if src.startswith("swe_raw/") else "TerminalBench"


def load_rows() -> list[dict]:
    rows = [json.loads(line) for line in MANIFEST.open()]
    return [r for r in rows if r.get("artifact_path")]


def stratified(rows: list[dict], n: int, seed: int) -> list[dict]:
    """Distribui n entre os estratos (agente, origem) proporcionalmente, com ao menos 1 por estrato."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["agent"], origin(r))].append(r)
    rng = random.Random(seed)
    for g in groups.values():
        rng.shuffle(g)
    keys = sorted(groups)
    total = sum(len(g) for g in groups.values())
    quota = {k: max(1, round(n * len(groups[k]) / total)) for k in keys}
    # ajusta para somar exatamente n (tira/adiciona nos maiores estratos)
    order = sorted(keys, key=lambda k: -len(groups[k]))
    i = 0
    while sum(quota.values()) != min(n, total):
        k = order[i % len(order)]
        if sum(quota.values()) > n and quota[k] > 1:
            quota[k] -= 1
        elif sum(quota.values()) < n and quota[k] < len(groups[k]):
            quota[k] += 1
        i += 1
        if i > 10000:
            break
    picked = []
    for k in keys:
        picked += groups[k][: quota[k]]
    return picked


def remote_sizes() -> dict[str, int]:
    api = HfApi()
    return {
        f.path: f.size
        for f in api.list_repo_tree(REPO, path_in_repo="bench_artifacts/full", repo_type="dataset", recursive=True)
        if getattr(f, "size", None) is not None
    }


def log(entry: dict) -> None:
    entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def download(path: str) -> None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            hf_hub_download(REPO, path, repo_type="dataset", local_dir=str(DEST))
            return
        except HfHubHTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 429 and attempt < MAX_RETRIES:
                wait = BACKOFF0 * 2**attempt
                tqdm.write(f"429 em {path}; aguardando {wait}s (tentativa {attempt + 1})")
                log({"path": path, "status": "rate_limited", "wait_s": wait})
                time.sleep(wait)
                continue
            raise


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int, metavar="N")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = load_rows()
    picked = rows if args.all else stratified(rows, args.sample, args.seed)
    strata = defaultdict(int)
    for r in picked:
        strata[(r["agent"], origin(r))] += 1
    print(f"{len(picked)} trajetórias selecionadas (de {len(rows)} com artefato):")
    for k, v in sorted(strata.items()):
        print(f"  {k[0]:15s} {k[1]:13s} {v}")

    sizes = remote_sizes()
    stats = defaultdict(int)
    for r in tqdm(picked, desc="download", unit="traj"):
        path = r["artifact_path"]
        local = DEST / path
        expected = sizes.get(path)
        if expected is None:
            stats["not_in_repo"] += 1
            log({"traj_id": r["traj_id"], "path": path, "status": "not_in_repo"})
            continue
        if local.exists() and local.stat().st_size == expected:
            stats["skipped"] += 1
            log({"traj_id": r["traj_id"], "path": path, "status": "skipped", "size": expected})
            continue
        try:
            download(path)
        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            log({"traj_id": r["traj_id"], "path": path, "status": "failed", "error": repr(e)})
            tqdm.write(f"FALHOU {path}: {e!r}")
            continue
        ok = local.exists() and local.stat().st_size == expected
        stats["ok" if ok else "size_mismatch"] += 1
        log({"traj_id": r["traj_id"], "path": path, "status": "ok" if ok else "size_mismatch",
             "size": local.stat().st_size if local.exists() else None, "expected": expected})
        time.sleep(SLEEP)
    print(dict(stats))


if __name__ == "__main__":
    main()
