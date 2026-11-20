#!/usr/bin/env python
"""Exporta a paleta do front (frontend/src/theme/categories.ts) para results/figures/palette.json (as figuras usam a MESMA paleta)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src" / "theme" / "categories.ts"


def export() -> dict:
    s = SRC.read_text()
    kinds = {}
    for m in re.finditer(r"^\s{2}(\w+): \{ label: '([^']+)', code: '([^']+)', color: '(#[0-9A-Fa-f]{6})', phase: (?:'([^']+)'|null), icon: \w+, special: (true|false) \}", s, re.M):
        k, label, code, color, phase, special = m.groups()
        kinds[k] = {"label": label, "code": code, "color": color, "phase": phase, "special": special == "true"}
    phase = {m.group(1): m.group(2) for m in re.finditer(r"(\w+): '(#[0-9A-Fa-f]{6})'", re.search(r"PHASE_COLOR[^{]*\{([^}]*)\}", s).group(1))}
    out = {"kinds": kinds, "phase_color": phase, "error_color": re.search(r"ERROR_COLOR = '(#[0-9A-Fa-f]{6})'", s).group(1),
           "dark_submit": re.search(r"DARK_SUBMIT = '(#[0-9A-Fa-f]{6})'", s).group(1), "special_fill_light": "#E4E4E7", "source": "frontend/src/theme/categories.ts"}
    assert len(kinds) == 14 and len(phase) == 4, (len(kinds), len(phase))
    p = ROOT / "results" / "figures" / "palette.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    o = export()
    print(f"{len(o['kinds'])} tipos, {len(o['phase_color'])} fases → results/figures/palette.json")
