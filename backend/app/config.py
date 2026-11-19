"""Configuração por ambiente (.env via python-dotenv). A chave NUNCA é impressa, logada ou gravada em cache/relatório."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / ".env")  # não sobrescreve variáveis já definidas no ambiente


@dataclass
class LLMConfig:
    enabled: bool = False
    model: str = "claude-haiku-5-5"
    budget_usd: float = 0.50
    api_key: str = field(default="", repr=False)  # repr=False: nunca aparece em logs/tracebacks

    @property
    def usable(self) -> bool:
        return self.enabled and bool(self.api_key)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        def f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name) or default)
            except ValueError:
                return default
        return cls(enabled=(os.getenv("LABEL_LLM_ENABLED") or "0").strip().lower() in ("1", "true", "yes", "on"),
                   model=os.getenv("LLM_MODEL") or "claude-haiku-5-5",
                   budget_usd=f("LLM_BUDGET_USD", 0.50), api_key=os.getenv("ANTHROPIC_API_KEY") or "")

    def __str__(self) -> str:
        return f"LLMConfig(enabled={self.enabled}, model={self.model}, budget_usd={self.budget_usd}, api_key={'set' if self.api_key else 'unset'})"


CACHE_DIR = BACKEND / ".cache"
