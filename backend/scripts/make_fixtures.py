#!/usr/bin/env python
"""Gera backend/tests/fixtures/ a partir de data/samples e data/tmp/ctb (reproduzível; fixtures < 200 KB).
Observações longas são cortadas (cabeça + cauda, preservando o `[The command completed with exit code N.]`).
NUNCA copia segredos (.jwt_secret etc.): só lê events/*.json, .traj, *.traj.json, episode-*/{prompt,response}.txt."""
import glob
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "backend" / "tests" / "fixtures"
TMP = ROOT / "data" / "tmp" / "ctb"
CTB_RAW = ROOT / "data" / "raw" / "codetracebench"

IDS = {
    "openhands_swe": "openhands-OpenAI__GPT-5-sympy__sympy-17630-fbbfeb9e",  # incorrect [19], 21 passos
    "sweagent": "sweagent-OpenAI__GPT-5-keras-team__keras-19636-be8c419a",  # incorrect [30,31,33], unuseful [32]
    "miniswe": "miniswe-OpenAI__GPT-5-keras-team__keras-19636-0123c279",  # incorrect [23]
    "terminus2": "terminus2-Anthropic__Claude-Sonnet-4-20250514-Thinking-chem-rf-2ba0f88d",  # incorrect [7,8,10], unuseful [9]
    "openhands_events": "openhands-Anthropic__Claude-Sonnet-4-20250514-Thinking-leelachess0-pytorch-conversion-46d95888",
}


def clip(x, n=600):
    if isinstance(x, str) and len(x) > n:
        h = int(n * 0.55)
        return x[:h] + "\n…[cortado p/ fixture]…\n" + x[-(n - h):]
    return x


def clip_deep(o, n=600):
    if isinstance(o, str):
        return clip(o, n)
    if isinstance(o, list):
        return [clip_deep(v, n) for v in o]
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k == "arguments" and isinstance(v, str):  # string JSON: cortar os valores, não a string (senão quebra o JSON)
                try:
                    v = json.dumps(clip_deep(json.loads(v), n), ensure_ascii=False)
                except Exception:
                    pass
                out[k] = v
            else:
                out[k] = clip_deep(v, n)
        return out
    return o


def dump(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False))


def first_user_clip(msgs):  # enunciados enormes
    return msgs


def main():
    if FX.exists():
        shutil.rmtree(FX)
    FX.mkdir(parents=True)
    # ---- SWE-rebench: 1 trajetória resolvida, cortada em fronteira de par assistant/tool
    f = sorted(glob.glob(str(ROOT / "data/samples/swe-rebench/chat*.json")))
    for p in f:
        j = json.load(open(p))
        if j["resolved"] == 1 and j["exit_status"] == "submit" and j["n_steps"] < 45:
            msgs = j["trajectory"]
            head = msgs[:2 + 20]  # system, user, 10 passos (assistant+tool)
            if head[-1]["role"] == "assistant":
                head = head[:-1]
            tail = msgs[-2:] if msgs[-1]["role"] == "assistant" else msgs[-3:]
            small = {**{k: v for k, v in j.items() if k != "trajectory"}, "trajectory": clip_deep(head + tail)}
            dump(FX / "swe_rebench_row.json", small)
            dump(FX / "swe_rebench_messages.json", small["trajectory"])  # JSON avulso (lista de mensagens)
            break
    # ---- SWE-smith: nativo, tool-xml, xml, ticks
    want = {"smith_native": ("tool", lambda m: bool(m[0].get("message_type"))),
            "smith_tool_xml": ("tool", lambda m: not m[0].get("message_type")),
            "smith_xml": ("xml", lambda m: True), "smith_ticks": ("ticks", lambda m: True)}
    for name, (split, ok) in want.items():
        for p in sorted(glob.glob(str(ROOT / f"data/samples/swe-smith/{split}/*.json"))):
            j = json.load(open(p))
            m = j["messages"]
            if not ok(m) or j["resolved"] is not True or len(m) > 90:
                continue
            small_msgs = clip_deep(m[:14] + m[-3:])
            if name != "smith_native":  # um dos formatos testa a `messages` como string JSON
                pass
            row = {**j, "messages": json.dumps(small_msgs) if name == "smith_ticks" else small_msgs, "patch": ""}
            dump(FX / f"{name}.json", row)
            break
    # ---- CodeTraceBench: diretórios mínimos
    man = {}
    for l in open(CTB_RAW / "bench_manifest.verified.jsonl"):
        r = json.loads(l)
        man[r["traj_id"]] = r
    rows = []
    for key, tid in IDS.items():
        rows.append(man[tid])
        src, dst = TMP / tid, FX / "ctb" / tid
        if key == "openhands_swe":
            d = next((src / "swe_raw").glob("*/*"))
            best = None
            for p in d.glob("*.json"):
                try:
                    j = json.load(open(p))
                except Exception:
                    continue
                if isinstance(j, dict) and "messages" in j and (best is None or len(j["messages"]) > len(best["messages"])):
                    best = j
            slim = {"messages": clip_deep(best["messages"], 500), "response": clip_deep(best["response"], 500),
                    "kwargs": {"tools": []}, "cost": best.get("cost"), "args": []}
            dump(dst / "swe_raw" / "openhands__verified" / d.name / "tensorblock__gpt-5-1.json", slim)
        elif key == "sweagent":
            p = next(src.rglob("*.traj"))
            j = json.load(open(p))
            hist = [h for h in j["history"] if h.get("role") == "user"][:1]
            slim = {"trajectory": [{"action": t["action"], "observation": clip(t["observation"]), "thought": clip(t.get("thought", ""), 700),
                                    "response": ""} for t in j["trajectory"]],
                    "history": clip_deep(hist, 800), "info": {"exit_status": j["info"].get("exit_status"),
                                                              "submission": clip(j["info"].get("submission"), 800),
                                                              "swe_agent_version": j["info"].get("swe_agent_version")}}
            dump(dst / "swe_raw" / "swe_agent__poly" / "inst" / "inst.traj", slim)
        elif key == "miniswe":
            p = next(src.rglob("*.traj.json"))
            j = json.load(open(p))
            slim = {"info": {"exit_status": j["info"].get("exit_status"), "submission": clip(j["info"].get("submission"), 800)},
                    "messages": clip_deep(j["messages"], 700), "trajectory_format": j["trajectory_format"],
                    "instance_id": j.get("instance_id")}
            dump(dst / "swe_raw" / "mini_swe_agent__poly" / "inst" / "inst.traj.json", slim)
        elif key == "terminus2":
            ad = next(src.rglob("agent-logs"))
            for e in ad.glob("episode-*"):
                out = dst / "terminus2" / "m" / "r" / "task" / "task.1-of-1.ts" / "agent-logs" / e.name
                out.mkdir(parents=True, exist_ok=True)
                (out / "response.txt").write_text(clip((e / "response.txt").read_text(errors="replace"), 3000))
                (out / "prompt.txt").write_text(clip((e / "prompt.txt").read_text(errors="replace"), 800))
        elif key == "openhands_events":
            ed = next(src.rglob("events"))
            out = dst / "openhands" / "m" / "r" / "task" / "task.1-of-1.ts" / "sessions" / "sessions" / "uuid" / "events"
            out.mkdir(parents=True, exist_ok=True)
            for p in ed.glob("*.json"):
                e = json.load(open(p))
                tcm = e.get("tool_call_metadata")
                if tcm:  # só o texto do assistant, sem o payload inteiro do LLM
                    try:
                        c = tcm["model_response"]["choices"][0]["message"].get("content")
                    except Exception:
                        c = None
                    e["tool_call_metadata"] = {"function_name": tcm.get("function_name"), "tool_call_id": tcm.get("tool_call_id"),
                                               "model_response": {"choices": [{"message": {"content": clip(c, 500)}}]}}
                e.pop("llm_metrics", None)
                dump(out / p.name, clip_deep(e, 700))
    # só logs/asciinema → UnsupportedArtifact
    only_cast = FX / "ctb" / "miniswe-Anthropic__Claude-Sonnet-4-20250514-Thinking-mlflow-register-60a717c0"
    (only_cast / "miniswe" / "m" / "r" / "mlflow-register" / "run" / "sessions").mkdir(parents=True)
    (only_cast / "miniswe" / "m" / "r" / "mlflow-register" / "run" / "sessions" / "agent.cast").write_text('{"version": 2}\n')
    (FX / "ctb" / "bench_manifest.verified.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    total = sum(p.stat().st_size for p in FX.rglob("*") if p.is_file())
    print("fixtures:", total // 1024, "KB;", max((p.stat().st_size, p.name) for p in FX.rglob("*") if p.is_file()))
    for sub in sorted(FX.iterdir()):
        sz = sum(p.stat().st_size for p in sub.rglob("*") if p.is_file()) if sub.is_dir() else sub.stat().st_size
        print(f"  {sub.name}: {sz // 1024} KB")


if __name__ == "__main__":
    main()
