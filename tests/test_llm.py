"""LLM 层测试：provider 解析、预算闸门、JSON 抠取、协议差异。

这一层的存在意义是**不把系统绑死在某一个编码 agent 上**：
同一套角色定义与契约，既能由你所在的 coding agent 执行（不花 API 钱），
也能由任意 OpenAI 兼容的服务执行（无人值守）。
"""
from __future__ import annotations

import json

import pytest

from agents.orchestrator.scripts import llm


CFG = {
    "providers": {
        "cheap": {"protocol": "openai", "base_url": "https://x/v1/",
                  "api_key_env": "FAKE_KEY", "model": "cheap-1",
                  "price_per_1m_input": 1.0, "price_per_1m_output": 2.0},
        "smart": {"protocol": "anthropic", "base_url": "https://y",
                  "api_key_env": "FAKE_KEY", "model": "smart-1"},
        "local": {"protocol": "openai", "base_url": "http://localhost:11434/v1",
                  "api_key_env": None, "model": "qwen"},
    },
    "tiers": {"default": "cheap", "reasoning": "smart"},
}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FAKE_KEY", "sk-test")


# ── 档位解析 ───────────────────────────────────────────────────
def test_tier_maps_to_provider():
    assert llm.resolve_provider("default", CFG).model == "cheap-1"
    assert llm.resolve_provider("reasoning", CFG).model == "smart-1"


def test_unknown_tier_falls_back_to_default():
    assert llm.resolve_provider("nope", CFG).name == "cheap"


def test_trailing_slash_in_base_url_is_normalized():
    assert llm.resolve_provider("default", CFG).base_url == "https://x/v1"


def test_missing_api_key_says_which_env_var(monkeypatch):
    monkeypatch.delenv("FAKE_KEY", raising=False)
    with pytest.raises(llm.LLMError) as e:
        llm.resolve_provider("default", CFG)
    assert "FAKE_KEY" in str(e.value)


def test_local_provider_needs_no_key(monkeypatch):
    monkeypatch.delenv("FAKE_KEY", raising=False)
    cfg = {**CFG, "tiers": {"default": "local"}}
    assert llm.resolve_provider("default", cfg).api_key is None


def test_empty_config_gives_actionable_error():
    with pytest.raises(llm.LLMError) as e:
        llm.resolve_provider("default", {})
    assert "models.yaml" in str(e.value)


# ── 预算闸门 ───────────────────────────────────────────────────
def test_budget_stops_on_token_cap():
    b = llm.Budget(max_tokens=100)
    prov = llm.resolve_provider("default", CFG)
    with pytest.raises(llm.BudgetExceeded):
        b.charge(prov, llm.Usage(prompt_tokens=200, completion_tokens=0, calls=1))


def test_budget_stops_on_cost_cap():
    b = llm.Budget(max_cost=0.001)
    prov = llm.resolve_provider("default", CFG)
    with pytest.raises(llm.BudgetExceeded):
        b.charge(prov, llm.Usage(prompt_tokens=1_000_000, completion_tokens=0, calls=1))


def test_cost_is_none_when_price_not_configured():
    """价格随时在变，写死的价格半年后就是错的。没填就只报用量。"""
    prov = llm.resolve_provider("reasoning", CFG)      # smart 没配价格
    assert prov.cost(llm.Usage(1000, 1000, 1)) is None
    b = llm.Budget()
    b.charge(prov, llm.Usage(1000, 1000, 1))
    rep = b.report()
    assert rep["cost"] is None and rep["total_tokens"] == 2000
    assert "价格" in rep["cost_note"]


def test_cost_math():
    prov = llm.resolve_provider("default", CFG)   # 1 元/M 输入，2 元/M 输出
    assert prov.cost(llm.Usage(1_000_000, 500_000, 1)) == pytest.approx(2.0)


# ── 从模型输出里抠 JSON ────────────────────────────────────────
@pytest.mark.parametrize("raw,expect", [
    ('{"a":1}', {"a": 1}),
    ('```json\n{"a":1}\n```', {"a": 1}),
    ('```\n{"a":1}\n```', {"a": 1}),
    ('好的，结果如下：\n{"a":1}\n以上。', {"a": 1}),
    ('[1,2,3]', [1, 2, 3]),
])
def test_parse_json_survives_model_chatter(raw, expect):
    """模型爱在 JSON 外面裹代码块、写解释。提示词管不住的事，代码管得住。"""
    assert llm.parse_json(raw) == expect


def test_parse_json_reports_clearly_when_hopeless():
    with pytest.raises(llm.LLMError) as e:
        llm.parse_json("我拒绝回答")
    assert "找不到 JSON" in str(e.value)


# ── 两种协议的请求体 ───────────────────────────────────────────
def test_openai_protocol_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers, payload, timeout, retries=3):
        seen.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": '{"ok":1}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    monkeypatch.setattr(llm, "_post", fake_post)
    text, u = llm.complete(llm.resolve_provider("default", CFG), "sys", "usr")
    assert seen["url"].endswith("/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["payload"]["messages"][0]["role"] == "system"
    assert u.prompt_tokens == 10 and json.loads(text) == {"ok": 1}


def test_anthropic_protocol_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers, payload, timeout, retries=3):
        seen.update(url=url, headers=headers, payload=payload)
        return {"content": [{"text": '{"ok":1}'}],
                "usage": {"input_tokens": 7, "output_tokens": 3}}

    monkeypatch.setattr(llm, "_post", fake_post)
    _, u = llm.complete(llm.resolve_provider("reasoning", CFG), "sys", "usr")
    assert seen["url"].endswith("/v1/messages")
    assert seen["headers"]["x-api-key"] == "sk-test"
    assert seen["payload"]["system"] == "sys"      # anthropic 的 system 是独立字段
    assert u.prompt_tokens == 7


def test_response_format_is_dropped_when_unsupported(monkeypatch):
    """有些兼容服务不认 response_format，去掉再试一次，而不是直接失败。"""
    calls = []

    def fake_post(url, headers, payload, timeout, retries=3):
        calls.append(payload.copy())
        if "response_format" in payload:
            raise llm.LLMError("HTTP 400: unknown field response_format")
        return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.complete(llm.resolve_provider("default", CFG), "s", "u")
    assert len(calls) == 2 and "response_format" not in calls[1]
