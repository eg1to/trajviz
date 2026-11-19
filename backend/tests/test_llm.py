"""Camada 3 com cliente falso (sem rede): lote, cache, orçamento, saída inválida, chave nunca exposta."""
import json
from types import SimpleNamespace as NS

import pytest

from app.config import LLMConfig
from app.labeling import label_trajectory
from app.labeling import llm as llm_mod
from app.labeling.llm import LLMLabeler, clean_obs, render_step, step_hash
from app.schema import Action, Observation, Step, Trajectory

SECRET = "sk-ant-TEST-SECRET-123"


def mk_traj(n=3, tool_cmd="dvc repro"):
    steps = [Step(idx=i, thought="thinking " * 80, action=Action(tool="bash", tool_native="bash", command=f"{tool_cmd} {i}",
                                                                  args={"command": f"{tool_cmd} {i}"}, raw=f"{tool_cmd} {i}"),
                  observation=Observation(content="out\n[The command completed with exit code 0.]\n[Current working directory: /x]\n"
                                                  "[Python interpreter: /opt/py]\n[Command finished with exit code 0]", chars=10))
             for i in range(n)]
    return Trajectory(id="t", source_format="x", agent="OpenHands", problem_statement="fix the bug " * 50, steps=steps)


class FakeClient:
    def __init__(self, replies=None, usage=None):
        self.calls, self.replies, self.messages = [], replies, NS(create=self.create)
        self.usage = usage or NS(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)

    def create(self, **kw):
        self.calls.append(kw)
        text = kw["messages"][0]["content"]
        idxs = [int(x) for x in __import__("re").findall(r"\[idx=(\d+)\]", text)]
        labels = self.replies if self.replies is not None else [{"idx": i, "category": "test", "subcategory": "dvc", "confidence": 0.8, "rationale": "r"} for i in idxs]
        return NS(content=[NS(type="tool_use", name="label_steps", input={"labels": labels})], usage=self.usage)


def labeler(tmp_path, client=None, budget=0.5, enabled=True):
    return LLMLabeler(LLMConfig(enabled=enabled, model="claude-haiku-5-5", budget_usd=budget, api_key=SECRET), client=client, cache_dir=tmp_path)


def test_batch_one_request_per_trajectory_with_cached_system_prompt(tmp_path):
    fake = FakeClient()
    t = label_trajectory(mk_traj(5), labeler(tmp_path, fake))
    assert len(fake.calls) == 1
    kw = fake.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["tool_choice"] == {"type": "tool", "name": "label_steps"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and "explore" in kw["system"][0]["text"]
    assert all(s.label_source == "llm" and s.category == "test" and s.confidence == 0.8 for s in t.steps)
    assert all(s.subcategory == "dvc" for s in t.steps)


def test_prompt_content_limits_and_footer_removed(tmp_path):
    fake = FakeClient()
    label_trajectory(mk_traj(1), labeler(tmp_path, fake))
    text = fake.calls[0]["messages"][0]["content"]
    assert "[The command completed" not in text and "[Current working directory" not in text and "[Python interpreter" not in text
    th = next(ln for ln in text.splitlines() if ln.startswith("THOUGHT:"))
    assert len(th) - len("THOUGHT: ") <= 400
    assert clean_obs("a\n[The command completed with exit code 1.]\n[Current working directory: /x]") == "a"


def test_splits_into_multiple_requests_over_token_ceiling(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_mod, "MAX_BATCH_TOKENS", 1500)
    fake = FakeClient()
    label_trajectory(mk_traj(8), labeler(tmp_path, fake))
    assert len(fake.calls) > 1
    seen = [int(x) for c in fake.calls for x in __import__("re").findall(r"\[idx=(\d+)\]", c["messages"][0]["content"])]
    assert sorted(seen) == list(range(8))


def test_cache_never_repeats_a_call(tmp_path):
    fake = FakeClient()
    label_trajectory(mk_traj(3), labeler(tmp_path, fake))
    assert len(fake.calls) == 1
    fake2 = FakeClient()
    t = label_trajectory(mk_traj(3), labeler(tmp_path, fake2))  # novo labeler, mesmo diretório de cache
    assert fake2.calls == [] and all(s.label_source == "llm" for s in t.steps)
    assert step_hash("m1", mk_traj(1).steps[0]) != step_hash("m2", mk_traj(1).steps[0])  # modelo entra no hash


def test_budget_stops_and_leaves_fallback(tmp_path):
    fake = FakeClient()
    lab = labeler(tmp_path, fake, budget=0.0000001)
    t = label_trajectory(mk_traj(3), lab)
    assert fake.calls == [] and lab.budget_exhausted
    assert all(s.label_source == "fallback" for s in t.steps)


def test_budget_accumulates_cost_and_halts_later_trajectories(tmp_path):
    usage = NS(input_tokens=2_000_000, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)  # US$ 0,20 por chamada
    fake = FakeClient(usage=usage)
    lab = labeler(tmp_path, fake, budget=0.15)
    label_trajectory(mk_traj(2, "aa"), lab)
    label_trajectory(mk_traj(2, "bb"), lab)  # 2ª excederia o orçamento → não chama
    assert len(fake.calls) == 1 and lab.budget_exhausted and abs(lab.run.cost_usd - 0.20) < 1e-9


def test_usage_file_has_tokens_and_cost(tmp_path):
    usage = NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=500, cache_creation_input_tokens=300)
    lab = labeler(tmp_path, FakeClient(usage=usage))
    label_trajectory(mk_traj(2), lab)
    u = json.loads((tmp_path / "llm_usage.json").read_text())
    assert (u["input_tokens"], u["output_tokens"], u["cache_read_tokens"], u["cache_write_tokens"]) == (1000, 200, 500, 300)
    exp = 1000 * 0.10e-6 + 200 * 0.50e-6 + 500 * 0.01e-6 + 300 * 0.125e-6
    assert abs(u["cost_usd"] - exp) < 1e-12 and u["requests"] == 1


def test_invalid_outputs_fall_back(tmp_path):
    # bloco sem tool_use / estrutura inválida / categoria inexistente
    bad_cat = FakeClient(replies=[{"idx": 0, "category": "dance", "confidence": 2.5}])
    t = label_trajectory(mk_traj(1), labeler(tmp_path / "a", bad_cat))
    assert t.steps[0].category == "other" and t.steps[0].label_source == "llm" and t.steps[0].confidence == 1.0
    broken = FakeClient(replies=[{"nope": 1}])
    lab = labeler(tmp_path / "b", broken)
    t = label_trajectory(mk_traj(1), lab)
    assert t.steps[0].label_source == "fallback" and lab.errors
    unknown_idx = FakeClient(replies=[{"idx": 99, "category": "test", "confidence": 0.9}])
    t = label_trajectory(mk_traj(1), labeler(tmp_path / "c", unknown_idx))
    assert t.steps[0].label_source == "fallback"


def test_disabled_or_no_key_means_fallback_and_no_calls(tmp_path):
    fake = FakeClient()
    t = label_trajectory(mk_traj(2), LLMLabeler(LLMConfig(enabled=False, api_key=SECRET), client=None, cache_dir=tmp_path))
    assert all(s.label_source == "fallback" for s in t.steps)
    lab = LLMLabeler(LLMConfig(enabled=True, api_key=""), client=None, cache_dir=tmp_path / "x")
    assert not lab.enabled
    t = label_trajectory(mk_traj(2), lab)
    assert all(s.label_source == "fallback" and s.category == "other" for s in t.steps)
    assert fake.calls == []


def test_api_exception_does_not_crash_or_leak(tmp_path):
    class Boom:
        messages = NS(create=lambda **kw: (_ for _ in ()).throw(RuntimeError(f"401 {SECRET}")))
    lab = labeler(tmp_path, Boom())
    t = label_trajectory(mk_traj(1), lab)
    assert t.steps[0].label_source == "fallback"
    assert SECRET not in json.dumps(lab.errors)  # só o nome da exceção é guardado


def test_key_never_in_repr_or_files(tmp_path):
    lab = labeler(tmp_path, FakeClient())
    label_trajectory(mk_traj(2), lab)
    assert SECRET not in repr(lab.cfg) and SECRET not in str(lab.cfg)
    for p in tmp_path.iterdir():
        assert SECRET not in p.read_text()


def test_dry_run_estimate_without_network(tmp_path):
    lab = labeler(tmp_path, client=None, enabled=False)
    e = lab.estimate([(mk_traj(4), mk_traj(4).steps), (mk_traj(4, 'zz'), mk_traj(4, 'zz').steps)])
    assert e["steps"] == 8 and e["requests"] == 2 and e["input_tokens"] > 0 and 0 < e["cost_usd_with_cache"] <= e["cost_usd_no_cache"] * 1.5


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("LABEL_LLM_ENABLED", "1"); monkeypatch.setenv("LLM_MODEL", "m"); monkeypatch.setenv("LLM_BUDGET_USD", "0.07")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    c = LLMConfig.from_env()
    assert c.usable and c.model == "m" and c.budget_usd == 0.07 and SECRET not in repr(c)
    monkeypatch.delenv("LABEL_LLM_ENABLED")
    assert not LLMConfig.from_env().usable


def test_render_step_shape():
    s = mk_traj(1).steps[0]
    r = render_step(s)
    assert r.startswith("[idx=0] tool=bash") and "ACTION: dvc repro 0" in r
