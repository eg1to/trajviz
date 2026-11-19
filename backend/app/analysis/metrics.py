"""Métricas do dashboard (docs/PLAN.md §7). `compute_metrics(traj) -> Metrics` (modelo Pydantic exposto no OpenAPI)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from app.analysis.detectors import ignored
from app.labeling.bash_parser import executables
from app.labeling.taxonomy import PHASE, Category
from app.schema import Step, Trajectory

FLAGS_PROBLEM = ("error", "repeated", "no_new_info", "loop", "truncated")


class IdxCount(BaseModel):
    count: int = 0
    rate: float = 0.0  # % dos passos analisáveis (sem keys/harness)
    idx: list[int] = Field(default_factory=list)  # para o front navegar até o passo


class Outcome(BaseModel):
    resolved: bool | None
    resolved_validated: bool
    exit_status: str | None
    n_steps: int
    ended_with_submit: bool
    patch_files: int = 0
    patch_lines_added: int = 0
    patch_lines_removed: int = 0
    patch_source: str | None = None  # "patch" (confiável) | "steps" (derivado dos passos edit) | None


class CatStat(BaseModel):
    count: int
    pct_total: float  # % sobre todos os passos
    pct_core: float  # % sem message/keys/harness


class PhaseStat(BaseModel):
    phase: str
    count: int
    pct_total: float
    pct_core: float


class Special(BaseModel):
    count: int = 0
    pct_total: float = 0.0
    idx: list[int] = Field(default_factory=list)


class Ranked(BaseModel):
    name: str
    count: int


class Effort(BaseModel):
    n_steps: int
    n_core_steps: int  # sem message / keys / harness_protocol
    by_category: dict[str, CatStat]
    by_phase: list[PhaseStat]
    message: Special  # passos `message` (agente falando sem agir): fora de think
    keys: Special  # teclas de controle: fora de other
    harness_protocol: Special
    tools_ranking: list[Ranked]
    executables_ranking: list[Ranked]


class ThirdPhase(BaseModel):
    third: int
    phase: str | None
    share: float  # fração dos passos do terço na fase dominante


class Dynamics(BaseModel):
    first_edit_idx: int | None
    pct_before_first_edit: float | None
    edit_test_cycles: int
    cycles_passed: int
    cycles_failed: int
    dominant_phase_by_third: list[ThirdPhase]


class Streak(BaseModel):
    length: int = 0
    start_idx: int | None = None
    end_idx: int | None = None


class LoopRange(BaseModel):
    kind: str
    range: list[int]
    detail: str


class Problems(BaseModel):
    error: IdxCount
    repeated: IdxCount
    no_new_info: IdxCount
    loop: IdxCount
    loop_ranges: list[LoopRange]
    truncated: IdxCount
    test_fail: IdxCount
    test_pass: IdxCount
    longest_error_streak: Streak


class FileStat(BaseModel):
    path: str
    reads: int = 0
    edits: int = 0
    runs: int = 0
    first_idx: int
    last_idx: int


class Files(BaseModel):
    table: list[FileStat]
    edited_never_read: list[str]
    read_3plus_no_edit: list[str]


class Context(BaseModel):
    obs_chars: list[int]  # por passo (0 = sem observação)
    n_truncated: int
    total_obs_chars: int
    max_obs_chars: int


class Overlap(BaseModel):
    annotated: int
    flagged: int  # anotados que o detector também marcou
    precision_hint: float | None = None  # flagged / total marcado pelo detector (indicativo, refina na Fase 6)


class GroundTruthMetrics(BaseModel):
    n_incorrect: int
    n_unuseful: int
    unresolved: int
    resolved_via: dict[str, int]
    unuseful_vs_repeated_or_no_new_info: Overlap
    incorrect_vs_error_or_test_fail: Overlap
    incorrect_idx: list[int]
    unuseful_idx: list[int]


class Metrics(BaseModel):
    outcome: Outcome
    effort: Effort
    dynamics: Dynamics
    problems: Problems
    files: Files
    context: Context
    ground_truth: GroundTruthMetrics | None = None


# ----------------------------------------------------------------------------- helpers
def _pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


def _lines(s) -> int:
    return len(s.splitlines()) if isinstance(s, str) and s else 0


def _patch_stats(patch: str) -> tuple[int, int, int]:
    files = len(re.findall(r"^diff --git ", patch, re.M))
    add = sum(1 for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    rem = sum(1 for ln in patch.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    return files, add, rem


def _outcome(t: Trajectory) -> Outcome:
    last = t.steps[-1] if t.steps else None
    o = Outcome(resolved=t.resolved, resolved_validated=t.resolved_validated, exit_status=t.exit_status, n_steps=len(t.steps),
                ended_with_submit=bool(last and last.category == "submit"))
    if t.patch and t.resolved_validated:
        o.patch_files, o.patch_lines_added, o.patch_lines_removed = _patch_stats(t.patch)
        o.patch_source = "patch"
        return o
    paths, add, rem = set(), 0, 0  # patch ausente/não confiável: deriva dos passos edit
    for s in t.steps:
        if s.category != "edit" or ignored(s):
            continue
        paths.update(f.path for f in s.files if f.mode == "edit")
        a = s.action
        if a.tool == "editor":
            if a.command == "create":
                add += _lines(a.args.get("file_text"))
            elif a.command == "str_replace":
                add += _lines(a.args.get("new_str")); rem += _lines(a.args.get("old_str"))
            elif a.command == "insert":
                add += _lines(a.args.get("new_str"))
    if paths or add or rem:
        o.patch_files, o.patch_lines_added, o.patch_lines_removed, o.patch_source = len(paths), add, rem, "steps"
    return o


def _special(steps: list[Step], n: int) -> Special:
    return Special(count=len(steps), pct_total=_pct(len(steps), n), idx=[s.idx for s in steps])


def _effort(t: Trajectory) -> Effort:
    n = len(t.steps)
    msgs = [s for s in t.steps if s.action.tool == "message"]
    keys = [s for s in t.steps if s.subcategory == "keys"]
    harness = [s for s in t.steps if s.subcategory == "harness_protocol"]
    special = {s.idx for s in msgs + keys + harness}
    core = [s for s in t.steps if s.idx not in special]
    by_cat = {c.value: CatStat(count=0, pct_total=0.0, pct_core=0.0) for c in Category}
    cnt = Counter(s.category for s in core)
    for c, k in cnt.items():
        by_cat[c] = CatStat(count=k, pct_total=_pct(k, n), pct_core=_pct(k, len(core)))
    ph = Counter()
    for s in core:
        ph[PHASE[Category(s.category)].value] += 1
    phases = sorted({p.value for p in PHASE.values()}, key=lambda x: ["Entendimento", "Modificação", "Verificação", "Controle"].index(x))
    by_phase = [PhaseStat(phase=p, count=ph[p], pct_total=_pct(ph[p], n), pct_core=_pct(ph[p], len(core))) for p in phases]
    tools = Counter((s.action.tool_native or s.action.tool) for s in core)
    exes: Counter = Counter()
    for s in core:
        if s.action.tool == "keys" and s.action.args.get("commands"):
            for c in s.action.args["commands"]:
                exes.update(executables(c.get("keystrokes", "")))
        elif s.action.tool in ("bash", "ipython") and s.action.command:
            exes.update(executables(s.action.command) if s.action.tool == "bash" else ["python"])
    return Effort(n_steps=n, n_core_steps=len(core), by_category=by_cat, by_phase=by_phase, message=_special(msgs, n),
                  keys=_special(keys, n), harness_protocol=_special(harness, n),
                  tools_ranking=[Ranked(name=k, count=v) for k, v in tools.most_common(10)],
                  executables_ranking=[Ranked(name=k, count=v) for k, v in exes.most_common(10)])


def _dynamics(t: Trajectory) -> Dynamics:
    core = [s for s in t.steps if not ignored(s) and s.action.tool != "message"]
    first = next((s.idx for s in core if s.category == "edit"), None)
    cycles = passed = failed = 0
    pending = False
    for s in core:
        if s.category == "edit":
            pending = True
        elif s.category == "test" and pending:
            cycles += 1
            pending = False
            if "test_pass" in s.flags:
                passed += 1
            elif "test_fail" in s.flags:
                failed += 1
    thirds = []
    if core:
        size = -(-len(core) // 3)
        for i in range(3):
            chunk = core[i * size:(i + 1) * size]
            c = Counter(PHASE[Category(s.category)].value for s in chunk)
            top = c.most_common(1)
            thirds.append(ThirdPhase(third=i + 1, phase=top[0][0] if top else None, share=round(top[0][1] / len(chunk), 2) if top else 0.0))
    n = len(t.steps)
    return Dynamics(first_edit_idx=first, pct_before_first_edit=_pct(first, n) if first is not None else None,
                    edit_test_cycles=cycles, cycles_passed=passed, cycles_failed=failed, dominant_phase_by_third=thirds)


def _problems(t: Trajectory) -> Problems:
    analyz = [s for s in t.steps if not ignored(s)]
    n = len(analyz)

    def ic(flag: str) -> IdxCount:
        idx = [s.idx for s in analyz if flag in s.flags]
        return IdxCount(count=len(idx), rate=_pct(len(idx), n), idx=idx)

    best, cur, start = Streak(), 0, None
    for s in analyz:
        if "error" in s.flags:
            cur += 1
            start = s.idx if cur == 1 else start
            if cur > best.length:
                best = Streak(length=cur, start_idx=start, end_idx=s.idx)
        else:
            cur = 0
    loops = [LoopRange(kind=lp["kind"], range=lp["range"],
                       detail=(f"n={lp['n']} ×{lp['reps']}: {lp['pattern']}" if lp["kind"] == "ngram" else f"{lp['file']} ×{lp['cycles']}"))
             for lp in t.meta.get("loops", [])]
    return Problems(error=ic("error"), repeated=ic("repeated"), no_new_info=ic("no_new_info"), loop=ic("loop"), loop_ranges=loops,
                    truncated=ic("truncated"), test_fail=ic("test_fail"), test_pass=ic("test_pass"), longest_error_streak=best)


def _files(t: Trajectory) -> Files:
    d: dict[str, FileStat] = {}
    for s in t.steps:
        for f in s.files:
            st = d.setdefault(f.path, FileStat(path=f.path, first_idx=s.idx, last_idx=s.idx))
            st.last_idx = s.idx
            if f.mode == "read":
                st.reads += 1
            elif f.mode == "edit":
                st.edits += 1
            else:
                st.runs += 1
    table = sorted(d.values(), key=lambda x: (-(x.reads + x.edits + x.runs), x.first_idx))
    return Files(table=table, edited_never_read=[f.path for f in table if f.edits and not f.reads],
                 read_3plus_no_edit=[f.path for f in table if f.reads >= 3 and not f.edits])


def _context(t: Trajectory) -> Context:
    series = [(s.observation.chars if s.observation else 0) for s in t.steps]
    return Context(obs_chars=series, n_truncated=sum(1 for s in t.steps if s.observation and s.observation.truncated),
                   total_obs_chars=sum(series), max_obs_chars=max(series, default=0))


def _gt(t: Trajectory) -> GroundTruthMetrics | None:
    gt = t.ground_truth
    if gt is None:
        return None
    inc, unu, unres, via = set(), set(), 0, Counter()
    for a in gt.annotations:
        for s in a.steps:
            if s.resolved_idx is None:
                unres += 1
                continue
            via[s.resolved_via or "none"] += 1
            if "incorrect" in s.labels:
                inc.add(s.resolved_idx)
            if "unuseful" in s.labels:
                unu.add(s.resolved_idx)
    by_idx = {s.idx: s for s in t.steps}
    pred_unu = {i for i, s in by_idx.items() if {"repeated", "no_new_info"} & set(s.flags)}
    pred_inc = {i for i, s in by_idx.items() if {"error", "test_fail"} & set(s.flags)}
    ov = lambda ann, pred: Overlap(annotated=len(ann), flagged=len(ann & pred),  # noqa: E731
                                   precision_hint=round(len(ann & pred) / len(pred), 3) if pred else None)
    return GroundTruthMetrics(n_incorrect=len(inc), n_unuseful=len(unu), unresolved=unres, resolved_via=dict(via),
                              unuseful_vs_repeated_or_no_new_info=ov(unu, pred_unu), incorrect_vs_error_or_test_fail=ov(inc, pred_inc),
                              incorrect_idx=sorted(inc), unuseful_idx=sorted(unu))


def compute_metrics(traj: Trajectory) -> Metrics:
    return Metrics(outcome=_outcome(traj), effort=_effort(traj), dynamics=_dynamics(traj), problems=_problems(traj),
                   files=_files(traj), context=_context(traj), ground_truth=_gt(traj))
