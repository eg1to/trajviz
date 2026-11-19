#!/usr/bin/env python
"""Exploração dos datasets de trajetórias (Fase 1). NÃO é o adaptador: só mede e amostra.

    cd backend && uv run python scripts/explore_dataset.py swe-rebench|swe-smith|codetracebench

- Parquet é lido sempre em lotes (ParquetFile.iter_batches), nunca inteiro.
- Estatísticas: ~2.000 linhas espalhadas pelo arquivo (primeiras N linhas de cada row group / arquivo).
- Saídas: relatório no terminal, `data/samples/<dataset>/_stats.json` e uma amostra JSON por trajetória.
- CodeTraceBench: extrai (em data/tmp/ctb/) só os .tar.zst das 60 trajetórias da amostra.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import orjson
import pyarrow.parquet as pq
import zstandard
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
SAMPLES = ROOT / "data" / "samples"
TMP = ROOT / "data" / "tmp"
console = Console()
TRUNC_RE = re.compile(
    r"truncat|clipped|too large to display|output too long|abbreviated|\[\.\.\.|\.\.\. ?\(|content has been cut",
    re.I,
)
CLIP = 6000  # limite de caracteres por campo de texto nas amostras salvas


# ----------------------------------------------------------------------------- utilidades
def pct(xs: list[float]) -> dict:
    if not xs:
        return {}
    xs = sorted(xs)
    q = lambda p: xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]  # noqa: E731
    return {"n": len(xs), "min": xs[0], "p50": q(0.5), "p90": q(0.9), "max": xs[-1], "mean": round(sum(xs) / len(xs), 1)}


def clip(x, n=CLIP):
    if isinstance(x, str) and len(x) > n:
        return x[:n] + f"…[+{len(x) - n} chars]"
    if isinstance(x, dict):
        return {k: clip(v, n) for k, v in x.items()}
    if isinstance(x, list):
        return [clip(v, n) for v in x]
    return x


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS))


def show_counter(title: str, c: Counter, n: int = 15) -> None:
    t = Table(title=title, show_header=False)
    for k, v in c.most_common(n):
        t.add_row(str(k)[:90], str(v))
    console.print(t)


def show_pct(title: str, d: dict) -> None:
    console.print(f"[bold]{title}[/bold]: {d}")


def iter_parquet(files, per_group: int, columns=None, batch_size=16, wanted=None):
    """Itera as primeiras `per_group` linhas de cada row group. `wanted` = {(arquivo, rg, off)} p/ releitura."""
    for fp in files:
        pf = pq.ParquetFile(fp)
        for rg in range(pf.metadata.num_row_groups):
            if wanted is not None and not any(w[0] == str(fp) and w[1] == rg for w in wanted):
                continue
            off = 0
            for batch in pf.iter_batches(batch_size=batch_size, row_groups=[rg], columns=columns):
                for row in batch.to_pylist():
                    if off >= per_group:
                        break
                    if wanted is None or (str(fp), rg, off) in wanted:
                        yield str(fp), rg, off, row
                    off += 1
                if off >= per_group:
                    break


# ----------------------------------------------------------------------------- bash: primeiro executável
WRAPPERS = {"sudo", "env", "time", "nohup", "timeout", "command", "builtin", "exec", "nice", "stdbuf"}
NOISE = {"return", "def", "class", "import", "and", "or", "the", "You", "This", "Let", "The", "file", "print", "from", "with"}
HEREDOC_RE = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", re.S)


def split_segments(cmd: str) -> list[str]:
    """Divide em segmentos de topo por ; && || | & e quebra de linha, respeitando aspas e $( )."""
    cmd = HEREDOC_RE.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)
    segs, cur, q, depth, i = [], [], None, 0, 0
    while i < len(cmd):
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q == '"' and i + 1 < len(cmd):
                cur.append(cmd[i + 1]); i += 1
            elif ch == q:
                q = None
        elif ch in "'\"":
            q = ch; cur.append(ch)
        elif ch == "\\" and i + 1 < len(cmd):
            cur.append(ch); cur.append(cmd[i + 1]); i += 1
        elif ch == "(" and cmd[max(0, i - 1)] == "$":
            depth += 1; cur.append(ch)
        elif ch == ")" and depth:
            depth -= 1; cur.append(ch)
        elif ch == "&" and (cmd[i - 1:i] in (">", "<") or cmd[i + 1:i + 2] == ">"):
            cur.append(ch)
        elif depth == 0 and (ch in ";\n|&"):
            segs.append("".join(cur)); cur = []
            if ch in "|&" and i + 1 < len(cmd) and cmd[i + 1] == ch:
                i += 1
        else:
            cur.append(ch)
        i += 1
    segs.append("".join(cur))
    return [s.strip() for s in segs if s.strip()]


def seg_exec(seg: str) -> str | None:
    seg = seg.lstrip("({ !").strip()
    toks = re.findall(r"""(?:[^\s'"]+|'[^']*'|"[^"]*")+""", seg)
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^[A-Za-z_]\w*=", t):  # VAR=val
            i += 1
        elif t in WRAPPERS:
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or re.fullmatch(r"\d+[smh]?", toks[i])):
                i += 1
        else:
            break
    if i >= len(toks):
        return None
    ex = toks[i].strip("'\")}")
    if ex in {"if", "then", "else", "fi", "do", "done", "for", "while", "}", "{", "esac", "case", "EOF"}:
        return None
    if not re.fullmatch(r"[\w./+@-]+", ex) or ex.startswith("..") or ex in NOISE:
        return None  # lixo de parsing (corpo de heredoc/python -c multilinha, prosa, redirecionamentos)
    return os.path.basename(ex) if "/" in ex and not ex.startswith("./") else ex


def bash_execs(cmd: str) -> list[str]:
    return [e for e in (seg_exec(s) for s in split_segments(cmd or "")) if e]


# ----------------------------------------------------------------------------- acumulador de estatísticas
class Acc:
    def __init__(self):
        self.n_traj = 0
        self.n_msgs: list[int] = []
        self.n_steps: list[int] = []
        self.resolved = Counter()
        self.exit_status = Counter()
        self.models = Counter()
        self.agents = Counter()
        self.roles = Counter()
        self.keys_by_type: dict[str, Counter] = defaultdict(Counter)
        self.tools = Counter()
        self.subcmds: dict[str, Counter] = defaultdict(Counter)
        self.execs = Counter()  # todos os executáveis
        self.primary = Counter()  # ignorando cd/export (o que interessa à rotulação)
        self.obs_len: list[int] = []
        self.obs_trunc = 0
        self.obs_n = 0
        self.extra = Counter()

    def step(self, s: dict):
        """s: {tool, sub, command, obs}"""
        self.n_steps_total = getattr(self, "n_steps_total", 0) + 1
        self.tools[s["tool"]] += 1
        if s.get("sub"):
            self.subcmds[s["tool"]][s["sub"]] += 1
        if s.get("command"):
            ex = bash_execs(s["command"])
            self.execs.update(ex)
            prim = [e for e in ex if e not in {"cd", "export", "set", "echo", "true", "source"}] or ex[:1]
            self.primary.update(prim[:1] if len(prim) == 1 else prim)
        obs = s.get("obs")
        if obs is not None:
            self.obs_n += 1
            self.obs_len.append(len(obs))
            if TRUNC_RE.search(obs[:300] + obs[-300:]):
                self.obs_trunc += 1

    def report(self, name: str) -> dict:
        out = {
            "n_trajectories_in_sample": self.n_traj,
            "n_messages": pct(self.n_msgs),
            "n_steps": pct(self.n_steps),
            "resolved": dict(self.resolved),
            "exit_status": dict(self.exit_status),
            "models": dict(self.models),
            "agents": dict(self.agents),
            "roles": dict(self.roles),
            "message_keys": {k: dict(v) for k, v in self.keys_by_type.items()},
            "tools": dict(self.tools.most_common()),
            "subcommands": {k: dict(v.most_common()) for k, v in self.subcmds.items()},
            "top60_exec_all_segments": self.execs.most_common(60),
            "top60_exec_primary": self.primary.most_common(60),
            "obs_chars": pct(self.obs_len),
            "obs_possibly_truncated": f"{self.obs_trunc}/{self.obs_n}",
            "extra": dict(self.extra),
        }
        console.rule(f"[bold]{name}")
        show_pct("nº mensagens/traj", out["n_messages"])
        show_pct("nº passos/traj", out["n_steps"])
        console.print("resolved:", out["resolved"], " exit_status:", out["exit_status"])
        console.print("modelos:", out["models"], " agentes:", out["agents"])
        show_counter("roles", self.roles)
        for k, v in self.keys_by_type.items():
            console.print(f"chaves \\[{k}]:", dict(v))
        show_counter("ferramentas", self.tools, 30)
        for t, c in self.subcmds.items():
            show_counter(f"subcomandos de {t}", c, 12)
        show_counter("top executáveis bash (1º por segmento, sem cd/export)", self.primary, 60)
        show_pct("observação (chars)", out["obs_chars"])
        console.print("observações possivelmente truncadas:", out["obs_possibly_truncated"])
        console.print("extra:", out["extra"])
        return out


def new_step(tool, sub=None, command=None, obs=None, thought=None, args=None):
    return {"tool": tool, "sub": sub, "command": command, "obs": obs, "thought": thought, "args": args}


# ----------------------------------------------------------------------------- SWE-rebench
def rebench_steps(msgs: list[dict], acc: Acc | None = None) -> list[dict]:
    """Um passo por tool_call. Observação = mensagem `tool` com o mesmo tool_call_id."""
    by_id, pending, steps = {}, {}, []
    seen_calls = set()
    for i, m in enumerate(msgs):
        if m["role"] == "assistant":
            seen_calls.update(tc["id"] for tc in (m.get("tool_calls") or []))
        if m["role"] == "tool":
            by_id[m["tool_call_id"]] = m
            if acc is not None and m["tool_call_id"] not in seen_calls:
                acc.extra["tool_msg_sem_tool_call_anterior"] += 1
    for i, m in enumerate(msgs):
        if m["role"] != "assistant":
            continue
        tcs = m.get("tool_calls") or []
        if acc is not None:
            acc.extra["assistant_msgs"] += 1
            if len(tcs) > 1:
                acc.extra["assistant_com_varios_tool_calls"] += 1
            if not tcs:
                acc.extra["assistant_sem_tool_call"] += 1
            if m.get("content") in (None, ""):
                acc.extra["assistant_content_vazio"] += 1
        for tc in tcs:
            pending[tc["id"]] = i
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
                if acc is not None:
                    acc.extra["arguments_json_ok"] += 1
            except Exception:
                args = {"_raw": fn["arguments"]}
                if acc is not None:
                    acc.extra["arguments_json_invalido"] += 1
            name = fn["name"]
            obs_m = by_id.get(tc["id"])
            if acc is not None and obs_m is None:
                acc.extra["tool_call_sem_resposta"] += 1
            if acc is not None and obs_m is not None and obs_m.get("name") != name:
                acc.extra["tool_name_diferente_do_call"] += 1
            steps.append(new_step(
                name,
                sub=args.get("command") if name == "str_replace_editor" else None,
                command=args.get("command") if name in ("execute_bash", "bash") else None,
                obs=(obs_m or {}).get("content"),
                thought=m.get("content") or args.get("thought"),
                args=args,
            ))
    return steps


def explore_rebench():
    files = [RAW / "swe-rebench" / "trajectories.parquet"]
    pf = pq.ParquetFile(files[0])
    console.print(pf.schema_arrow.names, f"linhas={pf.metadata.num_rows} row_groups={pf.metadata.num_row_groups}")
    cols = ["trajectory_id", "instance_id", "repo", "trajectory", "model_patch", "exit_status", "resolved",
            "gen_tests_correct", "pred_passes_gen_tests"]  # sem `tools` (enorme e idêntico em todas as linhas)
    acc, cand = Acc(), []
    for fp, rg, off, row in iter_parquet(files, per_group=120, columns=cols):
        msgs = row["trajectory"]
        acc.n_traj += 1
        acc.n_msgs.append(len(msgs))
        acc.resolved[row["resolved"]] += 1
        acc.exit_status[row["exit_status"]] += 1
        acc.models["Qwen3-Coder-480B (por README)"] += 1
        acc.agents["OpenHands"] += 1
        for m in msgs:
            acc.roles[m["role"]] += 1
            acc.keys_by_type[m["role"]].update(k for k, v in m.items() if v not in (None, [], ""))
        steps = rebench_steps(msgs, acc)
        acc.n_steps.append(len(steps))
        for s in steps:
            acc.step(s)
        if msgs and msgs[-1]["role"] != "assistant":
            acc.extra["ultima_msg_nao_assistant"] += 1
        if not row["model_patch"]:
            acc.extra["model_patch_vazio"] += 1
        cand.append((fp, rg, off, row["resolved"], len(steps)))
    stats = acc.report("SWE-rebench")
    # amostra: 25 resolvidas + 25 não, espalhadas por nº de passos
    pick = set()
    for flag in (1, 0):
        pool = sorted((c for c in cand if c[3] == flag), key=lambda c: c[4])
        k = min(25, len(pool))
        pick |= {pool[int(i * (len(pool) - 1) / max(1, k - 1))][:3] for i in range(k)}
    out = SAMPLES / "swe-rebench"
    n = 0
    for fp, rg, off, row in iter_parquet(files, per_group=120, columns=cols, wanted=pick):
        dump(out / f"{row['trajectory_id']}.json", {**row, "n_steps": len(rebench_steps(row["trajectory"]))})
        n += 1
    stats["amostra_salva"] = n
    dump(out / "_stats.json", stats)
    console.print(f"[green]{n} trajetórias salvas em {out}")


# ----------------------------------------------------------------------------- SWE-smith
XML_FN = re.compile(r"<function=([\w\-]+)>(.*?)</function>", re.S)
XML_PARAM = re.compile(r"<parameter=([\w\-]+)>(.*?)</parameter>", re.S)
TICKS = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return "" if content is None else str(content)


def strip_obs(t: str) -> str:
    return re.sub(r"^OBSERVATION:\n", "", t)


def smith_format(m: dict, split: str) -> str:
    """Formato da AÇÃO de uma mensagem assistant — decidido por mensagem, não pelo nome do split."""
    if m.get("tool_calls") is not None or m.get("message_type") == "action":
        return "native"
    return "xml" if "<function=" in text_of(m.get("content")) else ("ticks" if split == "ticks" else "none")


def smith_steps(split: str, msgs: list[dict], acc: Acc | None = None) -> list[dict]:
    steps = []
    for i, m in enumerate(msgs):
        r = m["role"]
        if r == "assistant":
            c = text_of(m.get("content"))
            fmt = smith_format(m, split)
            if acc is not None:
                acc.extra[f"acao_formato={fmt}"] += 1
            if fmt == "native":
                tcs = m.get("tool_calls") or []
                if acc is not None and len(tcs) != 1:
                    acc.extra[f"native_com_{len(tcs)}_tool_calls"] += 1
                for tc in tcs:
                    fn = tc["function"]
                    try:
                        args = json.loads(fn["arguments"])
                    except Exception:
                        args = {"_raw": fn["arguments"]}
                    name = fn["name"]
                    steps.append(new_step(name, sub=args.get("command") if name == "str_replace_editor" else None,
                                          command=args.get("command") if name == "bash" else None,
                                          thought=m.get("thought"), args=args))
                if not tcs:
                    steps.append(new_step("(sem_acao)", thought=c))
            elif fmt == "xml":
                fns = XML_FN.findall(c)
                if acc is not None:
                    acc.extra[f"xml_com_{len(fns)}_function_blocks"] += 1
                thought = c.split("<function=")[0].strip()
                for name, body in fns[:1]:
                    p = dict(XML_PARAM.findall(body))
                    steps.append(new_step(name, sub=p.get("command") if name == "str_replace_editor" else None,
                                          command=p.get("command") if name == "bash" else None, thought=thought, args=p))
                if not fns:
                    steps.append(new_step("(sem_acao)", thought=c))
            elif fmt == "ticks":
                # a ação é o ÚLTIMO bloco ``` sem linguagem; blocos ```python no texto fazem parte do pensamento
                parts = c.split("```")
                inner = parts[1::2] if len(parts) % 2 == 1 else parts[1:-1:2]  # trechos entre pares de ```
                blocks = [b[1:] for b in inner if b.startswith("\n")]  # sem linguagem na 1ª linha
                if blocks:
                    act = blocks[-1].strip()
                    toks = act.split()
                    first = toks[0] if toks else ""
                    thought = c[: c.rindex("```", 0, c.rindex("```"))].strip() if c.count("```") >= 2 else c
                    if first == "str_replace_editor":
                        steps.append(new_step("str_replace_editor", sub=toks[1] if len(toks) > 1 else None,
                                              thought=thought, args={"raw": act}))
                    elif first == "submit":
                        steps.append(new_step("submit", thought=thought, args={"raw": act}))
                    else:
                        steps.append(new_step("bash", command=act, thought=thought, args={"raw": act}))
                else:
                    steps.append(new_step("(sem_acao)", thought=c))
            else:
                steps.append(new_step("(sem_acao)", thought=c))
        elif r in ("tool", "user") and i > 1 and steps:
            for s in reversed(steps):  # 1ª user/tool depois de uma ação sem observação (user[1] é o enunciado)
                if s["tool"] != "(sem_acao)" and s.get("obs") is None:
                    s["obs"] = strip_obs(text_of(m.get("content")))
                break
    return steps


def explore_smith():
    base = RAW / "swe-smith" / "data"
    out = SAMPLES / "swe-smith"
    allstats = {}
    for split in ("tool", "xml", "ticks"):
        files = sorted(base.glob(f"{split}-*.parquet"))
        n_rows = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
        console.print(f"[bold]{split}[/bold]: {len(files)} arquivos, {n_rows} linhas; schema:",
                      pq.ParquetFile(files[0]).schema_arrow.names)
        acc, cand = Acc(), []
        for fp, rg, off, row in iter_parquet(files, per_group=250, batch_size=8):
            msgs = json.loads(row["messages"])
            acc.n_traj += 1
            acc.n_msgs.append(len(msgs))
            acc.resolved[row["resolved"]] += 1
            acc.models[row["model"]] += 1
            acc.agents["SWE-agent"] += 1
            for m in msgs:
                key = f"{m['role']}/{m.get('message_type')}"
                acc.roles[key] += 1
                acc.keys_by_type[key].update(k for k, v in m.items() if v not in (None, [], ""))
                if m.get("agent") is not None:
                    acc.extra[f"agent={m['agent']}"] += 1
            steps = smith_steps(split, msgs, acc)
            acc.n_steps.append(len(steps))
            for s in steps:
                acc.step(s)
            last = steps[-1] if steps else None
            acc.exit_status["termina_com_submit" if last and last["tool"] == "submit" else "sem_submit_no_fim"] += 1
            if not row["patch"]:
                acc.extra["patch_vazio"] += 1
            else:  # algum arquivo do patch é citado na trajetória? (teste de alinhamento patch↔trajetória)
                files_ = re.findall(r"^diff --git a/(\S+)", row["patch"], re.M)
                txt_ = " ".join(text_of(m.get("content")) + str(m.get("action", "")) for m in msgs)
                acc.extra["patch_alinhado_com_trajetoria" if any(f_ in txt_ for f_ in files_) else "patch_SEM_relacao_com_trajetoria"] += 1
            if row["traj_id"] != row["instance_id"]:
                acc.extra["traj_id!=instance_id"] += 1
            cand.append((fp, rg, off, row["resolved"], len(msgs)))
        allstats[split] = acc.report(f"SWE-smith [{split}] (linhas totais: {n_rows})")
        allstats[split]["rows_total"] = n_rows
        random.seed(7)
        pick = set()
        for flag in (True, False):
            pool = [c for c in cand if c[3] == flag]
            pick |= {c[:3] for c in random.sample(pool, min(10, len(pool)))}
        n = 0
        for fp, rg, off, row in iter_parquet(files, per_group=250, batch_size=8, wanted=pick):
            row["messages"] = json.loads(row["messages"])
            dump(out / split / f"{row['traj_id']}.json", row)
            n += 1
        console.print(f"[green]{n} salvas em {out / split}")
    dump(out / "_stats.json", allstats)


# ----------------------------------------------------------------------------- CodeTraceBench
def jl(x):
    return json.loads(x) if isinstance(x, str) else x


def ctb_origin(row) -> str:
    return "SWE-bench" if (row.get("source_relpath") or "").startswith("swe_raw/") else "TerminalBench"


def ctb_sample_ids() -> list[str]:
    p = SAMPLES / "codetracebench" / "_sample_ids.json"
    if p.exists():
        return json.loads(p.read_text())
    ids, seen = [], set()
    for line in (RAW / "codetracebench" / "_download_log.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e.get("status") in ("ok", "skipped") and e["traj_id"] not in seen:
            seen.add(e["traj_id"]); ids.append(e["traj_id"])
        if len(ids) == 60:  # as 60 primeiras linhas do log são o `--sample 60`; o `--all` vem depois
            break
    dump(p, ids)
    return ids


def ctb_extract(row) -> Path:
    out = TMP / "ctb" / row["traj_id"]
    if not out.exists():
        out.mkdir(parents=True)
        with open(RAW / "codetracebench" / row["artifact_path"], "rb") as fh:
            with zstandard.ZstdDecompressor().stream_reader(fh) as r:
                with tarfile.open(fileobj=r, mode="r|") as t:
                    t.extractall(out, filter="data")
    return out


def ctb_steps(agent: str, origin: str, d: Path) -> tuple[list[dict], dict]:
    """Passos normalizados + metadados do que foi lido. Cada passo traz `ref` (índice/ids de origem)."""
    steps, meta = [], {}
    if agent == "mini-SWE-agent":
        f = next(d.rglob("*.traj.json"), None)
        if f is None:  # alguns artefatos TerminalBench do mini-SWE-agent só têm logs/asciinema (agent.cast)
            return [], {"sem_trajetoria_estruturada": True, "arquivos": sorted(x.name for x in d.rglob("*") if x.is_file())}
        j = json.loads(f.read_text())
        meta = {"file": str(f.relative_to(d)), "top_keys": list(j), "exit_status": j["info"].get("exit_status")}
        ms, k = j["messages"], 0
        for i, m in enumerate(ms):
            if m["role"] == "assistant":
                k += 1
                c = m["content"]
                blk = re.search(r"```(?:bash)?\n(.*?)```", c, re.S)
                obs = ms[i + 1]["content"] if i + 1 < len(ms) and ms[i + 1]["role"] == "user" else None
                s = new_step("bash", command=blk.group(1).strip() if blk else None, obs=obs, thought=c.split("```")[0])
                s["ref"] = {"assistant_rank": k, "message_index": i}
                steps.append(s)
    elif agent == "SWE-agent":
        f = next(d.rglob("*.traj"))
        j = json.loads(f.read_text())
        meta = {"file": str(f.relative_to(d)), "top_keys": list(j), "exit_status": j["info"].get("exit_status"),
                "step_keys": list(j["trajectory"][0])}
        for i, t in enumerate(j["trajectory"]):
            act = (t.get("action") or "").strip()
            toks = act.split()
            tool = toks[0] if toks else "(vazio)"
            if tool == "str_replace_editor":
                s = new_step(tool, sub=toks[1] if len(toks) > 1 else None, obs=t.get("observation"), thought=t.get("thought"), args={"raw": act})
            elif tool in ("submit", "exit_cost", "exit_format"):
                s = new_step(tool, obs=t.get("observation"), thought=t.get("thought"), args={"raw": act})
            else:
                s = new_step("bash", command=act, obs=t.get("observation"), thought=t.get("thought"))
            s["ref"] = {"trajectory_index": i}
            steps.append(s)
    elif agent == "OpenHands" and origin == "SWE-bench":
        fs = sorted(x for x in d.rglob("*.json") if x.name not in ("report.json",))
        best, bn = None, -1
        for x in fs:  # cada arquivo = uma chamada ao LLM (messages cumulativas + response)
            try:
                j = json.loads(x.read_text())
            except Exception:
                continue
            if isinstance(j, dict) and "messages" in j and len(j["messages"]) > bn:
                best, bn = j, len(j["messages"])
        meta = {"n_llm_call_files": len(fs), "file_keys": list(best) if best else None}
        msgs = list(best["messages"]) + [best["response"]["choices"][0]["message"]]
        obs = {m.get("tool_call_id"): text_of(m.get("content")) for m in msgs if m["role"] == "tool"}
        k = 0
        for m in msgs:
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    k += 1
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    name = tc["function"]["name"]
                    s = new_step(name, sub=args.get("command") if name == "str_replace_editor" else None,
                                 command=args.get("command") if name == "execute_bash" else None,
                                 obs=obs.get(tc["id"]), thought=text_of(m.get("content")), args=args)
                    s["ref"] = {"tool_call_rank": k}
                    steps.append(s)
    elif agent == "OpenHands":
        ed = next(d.rglob("events"))
        evs = {}
        for x in ed.glob("*.json"):
            e = json.loads(x.read_text()); evs[e["id"]] = e
        by_cause = {e["cause"]: e for e in evs.values() if e.get("cause") is not None}
        meta = {"n_event_files": len(evs), "event_keys": sorted({k for e in evs.values() for k in e})}
        runk = 0
        for i in sorted(evs):
            e = evs[i]
            if e.get("source") != "agent" or not e.get("action") or e["action"] == "system":
                continue
            a = e["action"]
            args = e.get("args") or {}
            if a == "run":
                runk += 1
            o = by_cause.get(i)
            s = new_step(a, command=args.get("command") if a == "run" else None,
                         sub=args.get("command") if a in ("edit", "run_ipython") else None,
                         obs=text_of((o or {}).get("content")) if o else None, thought=args.get("thought"),
                         args={k: v for k, v in args.items() if k != "thought"})
            s["ref"] = {"event_id": i, "run_rank": runk if a == "run" else None}
            steps.append(s)
    else:  # Terminus2
        ad = next(d.rglob("agent-logs"))
        eps = sorted((int(p.name.split("-")[1]), p) for p in ad.glob("episode-*"))
        meta = {"n_episodes": len(eps), "episode_files": sorted({x.name for _, p in eps for x in p.iterdir()})}
        for n, (idx, p) in enumerate(eps):
            resp = (p / "response.txt").read_text() if (p / "response.txt").exists() else ""
            try:
                j = json.loads(resp)
            except Exception:
                j = {"_raw": resp}
            cmds = j.get("commands") or []
            nxt = eps[n + 1][1] / "prompt.txt" if n + 1 < len(eps) else None
            obs = nxt.read_text() if nxt and nxt.exists() else None
            s = new_step("keystrokes", command="".join(c.get("keystrokes", "") for c in cmds) or None, obs=obs,
                         thought=(j.get("analysis") or "") + "\n" + (j.get("plan") or ""),
                         args={"n_commands": len(cmds), "task_complete": j.get("task_complete"),
                               "keys": list(j)})
            s["ref"] = {"episode": idx}
            steps.append(s)
    return steps, meta


def explore_ctb():
    base = RAW / "codetracebench"
    out = SAMPLES / "codetracebench"
    stats = {}
    for split in ("verified", "full"):
        pf = pq.ParquetFile(base / f"bench_manifest.{split}.parquet")
        console.print(f"[bold]{split}[/bold] linhas={pf.metadata.num_rows}", pf.schema_arrow.names)
        rows = [r for b in pf.iter_batches(batch_size=500) for r in b.to_pylist()]
        c = Counter((r["agent"], ctb_origin(r)) for r in rows)
        show_counter(f"{split}: (agente, origem)", c)
        s = {
            "rows": len(rows), "agent_x_origin": {f"{a}|{o}": n for (a, o), n in c.items()},
            "agents": dict(Counter(r["agent"] for r in rows)), "models": dict(Counter(r["model"] for r in rows)),
            "origin": dict(Counter(ctb_origin(r) for r in rows)), "difficulty": dict(Counter(r["difficulty"] for r in rows)),
            "solved": dict(Counter(r["solved"] for r in rows)), "step_count": pct([r["step_count"] for r in rows]),
            "stage_count": pct([r["stage_count"] for r in rows]),
            "sem_artifact_path": sum(1 for r in rows if not r.get("artifact_path")),
            "sem_source_relpath": sum(1 for r in rows if not r.get("source_relpath")),
            "com_incorrect_stages": sum(1 for r in rows if jl(r["incorrect_stages"])),
        }
        stats[split] = s
        console.print({k: v for k, v in s.items() if k not in ("agent_x_origin",)})
    ver = {json.loads(l)["traj_id"]: json.loads(l) for l in (base / "bench_manifest.verified.jsonl").read_text().splitlines()}
    ids = ctb_sample_ids()
    acc_by_agent: dict[str, Acc] = defaultdict(Acc)
    structure, examples, mapping_notes = {}, {"incorrect": None, "unuseful": None}, {}
    for tid in ids:
        row = ver[tid]
        agent, origin = row["agent"], ctb_origin(row)
        d = ctb_extract(row)
        files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
        steps, meta = ctb_steps(agent, origin, d)
        acc = acc_by_agent[f"{agent}|{origin}"]
        acc.n_traj += 1
        acc.n_steps.append(len(steps))
        acc.resolved[row["solved"]] += 1
        acc.models[row["model"]] += 1
        acc.agents[agent] += 1
        for s in steps:
            acc.step(s)
        acc.extra["step_count_manifest==passos_extraidos"] += int(row["step_count"] == len(steps))
        structure.setdefault(f"{agent}|{origin}", {"exemplo": tid, "n_arquivos": len(files), "arquivos_amostra": files[:12], **meta})
        # exemplos de anotação
        for st in jl(row["incorrect_stages"]):
            for lab, key in (("incorrect", "incorrect_step_ids"), ("unuseful", "unuseful_step_ids")):
                for sid in st[key]:
                    ok = (agent == "SWE-agent" and sid - 1 < len(steps)) or (agent == "mini-SWE-agent" and sid - 1 < len(steps)) \
                        or (agent == "Terminus2" and sid - 1 < len(steps))
                    if ok and examples[lab] is None:
                        s = steps[sid - 1]
                        examples[lab] = {"traj_id": tid, "agent": agent, "step_id": sid, "stage_id": st["stage_id"],
                                         "rule": "step_id-1 = índice 0-based do passo extraído", "reasoning": st.get("reasoning"),
                                         "thought": clip(s.get("thought"), 700), "action": clip(s.get("command") or s.get("args"), 700),
                                         "observation": clip(s.get("obs"), 700)}
        sample = {
            "meta": {k: v for k, v in row.items() if k not in ("stages", "incorrect_stages")},
            "origin": origin,
            "stages": row["stages"], "incorrect_stages": row["incorrect_stages"],
            "artifact_files": files, "artifact_meta": meta,
            "steps": [clip(s) for s in steps],
        }
        dump(out / f"{tid}.json", sample)
    rep = {k: a.report(f"CodeTraceBench amostra [{k}]") for k, a in acc_by_agent.items()}
    stats["sample_by_agent_origin"] = rep
    stats["artifact_structure"] = structure
    stats["annotation_examples"] = examples
    dump(out / "_stats.json", stats)
    console.print(f"[green]{len(ids)} trajetórias salvas em {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["swe-rebench", "swe-smith", "codetracebench"])
    a = ap.parse_args()
    {"swe-rebench": explore_rebench, "swe-smith": explore_smith, "codetracebench": explore_ctb}[a.dataset]()


if __name__ == "__main__":
    main()
