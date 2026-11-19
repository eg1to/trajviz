"""Camada 3: fallback com Claude Haiku para passos ambíguos. Uma requisição por trajetória (em lotes < ~80K tokens).

- só roda com LABEL_LLM_ENABLED=1 e ANTHROPIC_API_KEY (a chave nunca é impressa/logada/gravada);
- system prompt fixo com cache_control; saída por tool use (`label_steps`), validada com Pydantic;
- cache em disco por hash(modelo + versão do prompt + conteúdo do passo); contador em `.cache/llm_usage.json`;
- trava de orçamento LLM_BUDGET_USD por execução; `estimate()` = dry-run sem rede.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import CACHE_DIR, LLMConfig
from app.labeling.taxonomy import Category, taxonomy_prompt
from app.schema import Step, Trajectory

PROMPT_VERSION = "v1"
# preços do Haiku 5.5 (US$/token): entrada 0,10/MTok · saída 0,50/MTok · cache hit 0,01/MTok · escrita de cache 1,25× entrada
P_IN, P_OUT, P_CACHE_READ, P_CACHE_WRITE = 0.10e-6, 0.50e-6, 0.01e-6, 0.125e-6
MAX_BATCH_TOKENS = 80_000  # teto por requisição (o preço sobe 5× acima de 100K)
CHARS_PER_TOKEN = 3.2  # estimativa conservadora
OUT_TOKENS_PER_STEP = 45
THOUGHT_MAX, ACTION_MAX, OBS_MAX, TASK_MAX = 400, 600, 300, 300
FOOTER_RE = re.compile(r"\n?\[(?:The command completed with exit code[^\]]*|Current working directory:[^\]]*|"
                       r"Python interpreter:[^\]]*|Command finished with exit code[^\]]*)\]", re.I)

SYSTEM_PROMPT = f"""You label steps of a coding agent's trajectory (a software-engineering agent fixing a bug or doing a terminal task).
Assign EXACTLY ONE category to each step, based on what the ACTION does (the thought and the observation are context).

Categories (phase in brackets):
{taxonomy_prompt()}

Rules:
- Judge the action's purpose. `python -c "..."` or running a script the agent just wrote to observe behavior = reproduce; running the project's test suite or a linter = test; writing/modifying files (including `cat > f <<EOF`, sed -i, python that writes a file) = edit.
- A compound command takes the highest-precedence category: edit > test > reproduce > search > read > explore > vcs > setup > other.
- Use `other` only when nothing fits (and say why in the rationale).
- subcategory: a short free-form tag (e.g. the main executable), may be null. confidence is your certainty in [0,1].
- Answer ONLY by calling the tool `label_steps` with one entry per step idx given; keep rationales under 15 words."""

TOOL = {
    "name": "label_steps",
    "description": "Return one label per step.",
    "input_schema": {
        "type": "object",
        "properties": {"labels": {"type": "array", "items": {
            "type": "object",
            "properties": {"idx": {"type": "integer"}, "category": {"type": "string", "enum": [c.value for c in Category]},
                           "subcategory": {"type": ["string", "null"]}, "confidence": {"type": "number"},
                           "rationale": {"type": "string"}},
            "required": ["idx", "category", "confidence"]}}},
        "required": ["labels"],
    },
}


class StepLabel(BaseModel):
    idx: int
    category: str = "other"
    subcategory: str | None = None
    confidence: float = 0.7
    rationale: str | None = None


class LabelBatch(BaseModel):
    labels: list[StepLabel]


def clean_obs(text: str) -> str:
    return FOOTER_RE.sub("", text or "").strip()


def render_step(s: Step) -> str:
    th = (s.thought or "").strip()[:THOUGHT_MAX]
    cmd = s.action.raw or s.action.command or ""
    if s.action.tool == "keys" and s.action.args.get("commands"):
        cmd = " ⏎ ".join(c.get("keystrokes", "").strip() for c in s.action.args["commands"])
    cmd = cmd.strip()[:ACTION_MAX]
    ob = clean_obs(s.observation.content if s.observation else "")[:OBS_MAX]
    head = f"[idx={s.idx}] tool={s.action.tool_native or s.action.tool}" + (f" cmd={s.action.command}" if s.action.tool == "editor" and s.action.command else "")
    return f"{head}\nTHOUGHT: {th}\nACTION: {cmd}\nOBS: {ob}"


def step_hash(model: str, s: Step) -> str:
    return hashlib.sha256(f"{model}|{PROMPT_VERSION}|{render_step(s).split(chr(10), 1)[1]}|{s.action.tool}".encode()).hexdigest()[:32]


def est_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    requests: int = 0
    cache_hits_steps: int = 0

    def add(self, u: Any) -> float:
        i, o = getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0
        cr, cw = getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0
        c = i * P_IN + o * P_OUT + cr * P_CACHE_READ + cw * P_CACHE_WRITE
        self.input_tokens += i; self.output_tokens += o; self.cache_read_tokens += cr; self.cache_write_tokens += cw
        self.cost_usd += c; self.requests += 1
        return c


class LLMLabeler:
    def __init__(self, cfg: LLMConfig | None = None, client: Any = None, cache_dir: Path | None = None):
        self.cfg = cfg or LLMConfig.from_env()
        self._client = client
        self.dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cache_path, self.usage_path = self.dir / "llm_labels.json", self.dir / "llm_usage.json"
        self.cache: dict[str, dict] = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.run = Usage()  # gasto desta execução (a trava vale por execução)
        self.total = self._load_usage()
        self.budget_exhausted = False
        self.errors: list[str] = []

    def _load_usage(self) -> Usage:
        if not self.usage_path.exists():
            return Usage()
        d = json.loads(self.usage_path.read_text())
        return Usage(**{k: v for k, v in d.items() if k in Usage.__dataclass_fields__})

    # ------------------------------------------------------------------ estado
    @property
    def enabled(self) -> bool:
        return bool(self._client) or self.cfg.usable

    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.cfg.api_key)
        return self._client

    def _save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache))
        self.usage_path.write_text(json.dumps({**self.total.__dict__, "model": self.cfg.model, "budget_usd_per_run": self.cfg.budget_usd}))

    # ------------------------------------------------------------------ lotes
    def batches(self, rendered: list[tuple[Step, str]], header: str) -> list[list[tuple[Step, str]]]:
        out, cur, tok = [], [], est_tokens(SYSTEM_PROMPT) + est_tokens(header) + 200
        for item in rendered:
            t = est_tokens(item[1])
            if cur and tok + t > MAX_BATCH_TOKENS:
                out.append(cur); cur, tok = [], est_tokens(SYSTEM_PROMPT) + est_tokens(header) + 200
            cur.append(item); tok += t
        if cur:
            out.append(cur)
        return out

    @staticmethod
    def header(traj: Trajectory) -> str:
        return f"Task (excerpt): {(traj.problem_statement or '')[:TASK_MAX]!r}\nAgent: {traj.agent}\n\nLabel these steps:\n"

    def estimate(self, trajs: list[tuple[Trajectory, list[Step]]]) -> dict:
        """Dry-run: tokens e custo estimados, sem rede (descontando o que já está no cache)."""
        n_steps = n_req = in_tok = 0
        for traj, steps in trajs:
            todo = [s for s in steps if step_hash(self.cfg.model, s) not in self.cache]
            if not todo:
                continue
            h = self.header(traj)
            for b in self.batches([(s, render_step(s)) for s in todo], h):
                n_req += 1; n_steps += len(b)
                in_tok += est_tokens(h) + sum(est_tokens(r) for _, r in b)
        sys_tok = est_tokens(SYSTEM_PROMPT) + est_tokens(json.dumps(TOOL))
        out_tok = n_steps * OUT_TOKENS_PER_STEP
        cost_nocache = (in_tok + n_req * sys_tok) * P_IN + out_tok * P_OUT
        cost_cache = in_tok * P_IN + (sys_tok * P_CACHE_WRITE if n_req else 0) + max(n_req - 1, 0) * sys_tok * P_CACHE_READ + out_tok * P_OUT
        return {"steps": n_steps, "requests": n_req, "input_tokens": in_tok + n_req * sys_tok, "output_tokens": out_tok,
                "cost_usd_no_cache": round(cost_nocache, 5), "cost_usd_with_cache": round(cost_cache, 5)}

    # ------------------------------------------------------------------ rotulagem
    def label_steps(self, traj: Trajectory, steps: list[Step]) -> dict[int, StepLabel]:
        """→ {idx: StepLabel} para os passos resolvidos (cache + chamadas). Os demais ficam de fora (fallback)."""
        out: dict[int, StepLabel] = {}
        todo: list[Step] = []
        for s in steps:
            hit = self.cache.get(step_hash(self.cfg.model, s))
            if hit:
                out[s.idx] = StepLabel(idx=s.idx, **hit); self.total.cache_hits_steps += 1
            else:
                todo.append(s)
        if not todo or not self.enabled:
            return out
        h = self.header(traj)
        for batch in self.batches([(s, render_step(s)) for s in todo], h):
            if self.budget_exhausted:
                break
            est = (est_tokens(SYSTEM_PROMPT) + est_tokens(h) + sum(est_tokens(r) for _, r in batch)) * P_IN \
                + len(batch) * OUT_TOKENS_PER_STEP * P_OUT
            if self.run.cost_usd >= self.cfg.budget_usd or self.run.cost_usd + est > self.cfg.budget_usd:
                self.budget_exhausted = True
                self.errors.append(f"orçamento LLM_BUDGET_USD={self.cfg.budget_usd} atingido; passos restantes ficam como fallback")
                break
            self._request(batch, h, out)
        self._save()
        return out

    def _request(self, batch: list[tuple[Step, str]], header: str, out: dict[int, StepLabel]) -> None:
        text = header + "\n---\n".join(r for _, r in batch)
        try:
            resp = self.client().messages.create(
                model=self.cfg.model, max_tokens=min(8192, 120 + OUT_TOKENS_PER_STEP * len(batch) * 2),
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=[TOOL], tool_choice={"type": "tool", "name": "label_steps"},
                messages=[{"role": "user", "content": text}])
        except Exception as e:  # noqa: BLE001 — nunca propagar nem logar cabeçalhos/chave
            self.errors.append(f"{type(e).__name__}")
            return
        for u in (getattr(resp, "usage", None),):
            if u is not None:
                self.run.add(u); self.total.add(u)
        try:
            block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
            parsed = LabelBatch.model_validate(block.input)
        except (StopIteration, ValidationError, AttributeError, TypeError) as e:
            self.errors.append(f"saída inválida ({type(e).__name__})")
            return
        by_idx = {s.idx: s for s, _ in batch}
        valid = {c.value for c in Category}
        for lab in parsed.labels:
            s = by_idx.get(lab.idx)
            if s is None:
                continue
            if lab.category not in valid:
                lab.category = "other"
            lab.confidence = max(0.0, min(1.0, lab.confidence))
            out[lab.idx] = lab
            self.cache[step_hash(self.cfg.model, s)] = {"category": lab.category, "subcategory": lab.subcategory,
                                                         "confidence": lab.confidence, "rationale": lab.rationale}
