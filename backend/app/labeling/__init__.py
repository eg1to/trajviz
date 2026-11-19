"""Rotulação: regras (camada 1+2) → LLM (camada 3). `label_trajectory(traj)` só altera rótulos, nunca os passos."""
from __future__ import annotations

from app.labeling.bash_parser import Ctx
from app.labeling.llm import LLMLabeler
from app.labeling.rules import Label, label_step_rules
from app.labeling.taxonomy import Category
from app.schema import FileRef, Trajectory

RULE_MIN_CONF = 0.6


def _dedupe(files: list[FileRef]) -> list[FileRef]:
    seen, out = set(), []
    for f in files:
        k = (f.path, f.mode)
        if k not in seen:
            seen.add(k); out.append(f)
    return out


def label_trajectory(traj: Trajectory, llm: LLMLabeler | None = None) -> Trajectory:
    """Camada 1 → 2 (regras) → 3 (LLM só p/ confiança < 0.6, se `llm` ativo). Sem LLM: melhor palpite com label_source=fallback."""
    ctx = Ctx()
    pending = []
    for s in traj.steps:
        lab: Label = label_step_rules(s, ctx)
        for w in lab.writes:
            ctx.add(w)
        s.category = lab.category.value  # type: ignore[assignment]
        s.subcategory = lab.subcategory
        s.confidence = lab.confidence
        s.files = _dedupe(lab.files)
        if lab.final or lab.confidence >= RULE_MIN_CONF:
            s.label_source = "rule"
        else:
            s.label_source = "fallback"
            pending.append(s)
    if llm is not None and llm.enabled and pending:
        res = llm.label_steps(traj, pending)
        for s in pending:
            r = res.get(s.idx)
            if r is not None:
                s.category = r.category  # type: ignore[assignment]
                s.subcategory = r.subcategory or s.subcategory
                s.confidence = r.confidence
                s.label_source = "llm"
    return traj
