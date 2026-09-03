"""提示词组装与产物校验测试。

重点在**纪律靠机制而不是靠叮嘱**：
- 板块分析师拿不到持仓数据，是因为代码不给它，不是因为提示词让它别看
- 产物不合 schema 会被打回重来，而不是"模型说它写好了就算好了"
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.orchestrator.scripts import agent_runner as ar
from agents.orchestrator.scripts import llm
from core.agent_registry import agent_file, read_meta

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "workspace" / "runs" / "2026-08-28_example"

CFG = {"providers": {"f": {"protocol": "openai", "base_url": "http://x/v1",
                           "api_key_env": None, "model": "f1"}},
       "tiers": {"default": "f", "reasoning": "f"}}


# ── 提示词组装 ─────────────────────────────────────────────────
def test_system_prompt_includes_role_and_its_skills():
    s = ar.build_system("sector-analyst")
    assert "板块分析师" in s
    assert "五维强弱判定" in s or "板块联动" in s, "引用的技能正文要被带进来"
    assert "绝不编造" in s, "硬性纪律必须在场"


def test_system_prompt_only_loads_declared_skills():
    """技能是按需加载的——上下文窗口是稀缺资源。"""
    s = ar.build_system("news-analyst")
    assert "信源分层" in s                     # news-triage 在它的 skills 里
    assert "连板梯队" not in s                 # sector-ladder 不在


def test_sector_analyst_cannot_see_holdings():
    """最关键的一条：板块强弱必须在不知道用户持仓的前提下判断。

    以前这只是 agent 定义里的一句话；现在是代码层面的事实。
    """
    u = ar.build_user("sector-analyst", EXAMPLE)
    assert "holdings" not in u
    assert "示例科技" not in u or "999001" not in u.split("=====")[1]


def test_each_agent_gets_only_its_blocks():
    import yaml

    for name in ("market-analyst", "sector-analyst", "news-analyst", "position-advisor"):
        fm = read_meta(agent_file(name))
        declared = set(fm["dataset_blocks"])
        doc = json.loads((EXAMPLE / "dataset.json").read_text(encoding="utf-8"))
        got = set(ar.slim_dataset(doc, list(declared))["blocks"])
        assert got == declared, f"{name} 拿到的数据块与 frontmatter 声明不一致"


def test_slim_dataset_keeps_quality_flags():
    """数据质量标记必须始终在场——它决定 agent 该不该写 blocked。"""
    doc = json.loads((EXAMPLE / "dataset.json").read_text(encoding="utf-8"))
    out = ar.slim_dataset(doc, ["breadth"])
    assert out["quality_flags"] and out["adjust_mode"] == "qfq"


def test_user_prompt_carries_schema_and_example():
    u = ar.build_user("market-analyst", EXAMPLE)
    assert "market.schema.json" in u
    assert "虚构假数据" in u, "示例要标明是假数据，免得模型照抄内容"


def test_missing_input_is_flagged_not_hidden(tmp_path):
    """输入文件缺失要明说，并提示 agent 写 blocked——不能装作没事。"""
    (tmp_path / "logs").mkdir(parents=True)
    u = ar.build_user("market-analyst", tmp_path)
    assert "文件缺失" in u and "blocked" in u


# ── 产物校验 ───────────────────────────────────────────────────
def test_validate_accepts_the_example():
    doc = json.loads((EXAMPLE / "market.json").read_text(encoding="utf-8"))
    assert ar.validate("market", doc) == []


def test_validate_rejects_garbage():
    assert ar.validate("market", {"run_id": "x"})


def test_run_agent_retries_with_the_errors(monkeypatch):
    """第一次不合规 → 把具体错误发回去让它改，而不是重新瞎猜一遍。"""
    good = json.loads((EXAMPLE / "market.json").read_text(encoding="utf-8"))
    seen = []

    def fake(prov, system, user, *, json_mode=True, budget=None):
        seen.append(user)
        payload = {"run_id": "x"} if len(seen) == 1 else good
        return json.dumps(payload, ensure_ascii=False), llm.Usage(1, 1, 1)

    monkeypatch.setattr(ar, "complete", fake)
    doc, stat = ar.run_agent("market-analyst", EXAMPLE, cfg=CFG, log=lambda m: None)
    assert stat["attempts"] == 2
    assert "没通过 schema 校验" in seen[1] and "required property" in seen[1]


def test_run_agent_gives_up_instead_of_looping(monkeypatch):
    """空转比失败更糟。重试有上限。"""
    monkeypatch.setattr(ar, "complete",
                        lambda *a, **k: ('{"run_id":"x"}', llm.Usage(1, 1, 1)))
    with pytest.raises(llm.LLMError) as e:
        ar.run_agent("market-analyst", EXAMPLE, cfg=CFG, max_attempts=2, log=lambda m: None)
    assert "2 次" in str(e.value)


def test_budget_is_enforced_across_steps(monkeypatch):
    good = json.loads((EXAMPLE / "market.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(ar, "complete",
                        lambda p, s, u, json_mode=True, budget=None: (
                            budget.charge(p, llm.Usage(10_000, 100, 1)) if budget else None,
                            (json.dumps(good), llm.Usage(10_000, 100, 1)))[1])
    b = llm.Budget(max_tokens=5_000)
    with pytest.raises(llm.BudgetExceeded):
        ar.run_agent("market-analyst", EXAMPLE, budget=b, cfg=CFG, log=lambda m: None)


def test_prompt_size_is_reasonable():
    """一次调用的提示词规模要可控——这是每天都要花的钱。"""
    total = max(len(ar.build_system(n)) + len(ar.build_user(n, EXAMPLE))
                for n in ("market-analyst", "sector-analyst", "position-advisor",
                          "news-analyst", "report-writer"))
    assert total < 60_000, f"最大的一步提示词 {total} 字，太大了，检查 dataset_blocks 裁剪"
