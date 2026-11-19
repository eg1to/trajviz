"""Modelo canônico de trajetória (TAR). Este arquivo é o contrato do projeto.

Mudou aqui → regenerar os tipos TS (`npm run gen:api`). Ver docs/formats.md §7 para a origem de cada campo.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["explore", "search", "read", "edit", "reproduce", "test", "setup", "vcs", "think", "submit", "other"]
LabelSource = Literal["rule", "llm", "fallback", "user"]
ThoughtSource = Literal["content", "think_tool", "field", "analysis_plan"]
StepRefKind = Literal["index", "assistant_rank", "episode", "run_rank", "tool_call_rank"]
Flag = Literal["error", "repeated", "loop", "no_new_info", "truncated", "test_fail", "test_pass"]

# Nomes normalizados de ferramenta (Action.tool). O nome original fica em Action.tool_native.
TOOLS = ("bash", "editor", "think", "submit", "task_tracker", "message", "keys", "ipython", "swe_cmd", "other")


class Action(BaseModel):
    tool: str  # normalizado (ver TOOLS; ferramentas desconhecidas mantêm o nome nativo)
    tool_native: str | None = None
    # bash → o comando; editor → subcomando (view|create|str_replace|insert|undo_edit|read|edit);
    # keys → teclas concatenadas; swe_cmd → nome do comando (open, scroll_down…)
    command: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)  # keys: args["commands"] = [{keystrokes, duration}]
    raw: str = ""  # texto original da ação (JSON dos arguments, bloco ```, string `action`, keystrokes…)


class Observation(BaseModel):
    content: str = ""
    exit_code: int | None = None
    is_error: bool | None = None  # preenchido só quando há evidência (exit_code); detectores vêm na Fase 4
    chars: int = 0  # tamanho ORIGINAL (a API pode devolver `content` cortado; ver content_cut)
    truncated: bool = False  # a própria ferramenta/agente cortou a saída
    content_cut: bool = False  # só a API: `content` foi cortado ao responder


class FileRef(BaseModel):
    path: str  # normalizado (sem /workspace/<repo>/, /testbed/, /app/)
    mode: Literal["read", "edit", "run"]


class Step(BaseModel):
    idx: int  # 0-based, ordem canônica
    native_id: str | int | None = None  # id da mensagem/tool_call/evento/episódio original
    thought: str | None = None
    thought_source: ThoughtSource | None = None
    action: Action
    observation: Observation | None = None  # None = ação sem resposta (finish/submit, trajetória cortada)
    category: Category = "other"
    subcategory: str | None = None
    label_source: LabelSource = "fallback"
    confidence: float = 0.0
    flags: list[Flag] = Field(default_factory=list)
    flag_refs: dict[str, int] = Field(default_factory=dict)  # passo relacionado (idx): repeated/no_new_info → passo original
    flag_details: dict[str, Any] = Field(default_factory=dict)  # motivo curto por flag, ex.: {"repeated": "igual ao passo 12"}
    files: list[FileRef] = Field(default_factory=list)  # arquivos tocados (Fase 3 refina a partir da ação)


class StageRange(BaseModel):
    stage_id: int
    start_step_id: int
    end_step_id: int


class AnnotatedStep(BaseModel):
    step_id: int  # numeração do benchmark (semântica depende de step_ref_kind)
    labels: list[str] = Field(default_factory=list)
    action_ref: dict[str, Any] | None = None
    observation_ref: dict[str, Any] | None = None
    resolved_idx: int | None = None  # idx canônico do Step, ou None se não foi possível alinhar
    # como foi resolvido: action_ref (id nativo confirmado) | rule (regra do step_ref_kind, confirmada) |
    # hypothesis (regra não confirmada: cauda de OpenHands-TB/Terminus2 e OpenHands-SWE) | None
    resolved_via: Literal["action_ref", "rule", "hypothesis"] | None = None


class StageAnnotation(BaseModel):
    stage_id: int
    incorrect_step_ids: list[int] = Field(default_factory=list)
    unuseful_step_ids: list[int] = Field(default_factory=list)
    steps: list[AnnotatedStep] = Field(default_factory=list)
    reasoning: str | None = None


class GroundTruth(BaseModel):
    stages: list[StageRange] = Field(default_factory=list)
    annotations: list[StageAnnotation] = Field(default_factory=list)
    step_ref_kind: StepRefKind = "index"
    ref_rule_confirmed: bool = True  # False = regra de mapeamento é hipótese (OpenHands/SWE-bench)
    manifest_step_count: int | None = None

    def resolved_idx(self, step_id: int) -> int | None:
        for a in self.annotations:
            for s in a.steps:
                if s.step_id == step_id:
                    return s.resolved_idx
        return None


class Trajectory(BaseModel):
    id: str
    source_format: str
    agent: str | None = None
    model: str | None = None
    task_id: str | None = None
    repo: str | None = None
    problem_statement: str | None = None
    resolved: bool | None = None
    resolved_validated: bool = True  # False no SWE-smith (resolved/patch não alinham com a trajetória)
    exit_status: str | None = None
    patch: str | None = None
    steps: list[Step] = Field(default_factory=list)
    ground_truth: GroundTruth | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
