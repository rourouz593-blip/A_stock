"""契约测试：示例 run 的产物必须符合 schemas/ 定义。

这是整个仓库最该先跑通的测试——它保证 agent 之间的接口没有错位。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_RUN = REPO / "workspace" / "runs" / "2026-08-28_example"

ARTIFACTS = {
    "run_manifest": "run_manifest.schema.json",
    "dataset": "dataset.schema.json",
    "market": "market.schema.json",
    "sectors": "sectors.schema.json",
    "positions_review": "positions_review.schema.json",
    "news": "news.schema.json",
    "report": "report.schema.json",
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("artifact,schema_file", sorted(ARTIFACTS.items()))
def test_example_artifact_matches_schema(artifact: str, schema_file: str) -> None:
    pytest.importorskip("jsonschema")
    from _common import build_validator

    doc = _load(EXAMPLE_RUN / f"{artifact}.json")
    schema = _load(REPO / "schemas" / schema_file)
    errors = sorted(build_validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
    )


def test_all_agents_declared_in_manifest() -> None:
    """agents/ 下的每个 agent 都应出现在示例 run_manifest 的 steps 里（orchestrator 除外）。"""
    agent_files = {p.stem for p in (REPO / "agents").glob("*.md")} - {"README"}
    steps = {s["agent"] for s in _load(EXAMPLE_RUN / "run_manifest.json")["steps"]}
    missing = agent_files - steps - {"orchestrator"}
    assert not missing, f"这些 agent 没有出现在 run_manifest.steps 中: {missing}"


def test_every_agent_writes_a_schema_that_exists() -> None:
    """agent frontmatter 里声明的 schema 必须真的存在——防止契约与角色定义脱节。"""
    import yaml

    for p in (REPO / "agents").glob("*.md"):
        if p.stem == "README":
            continue
        fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])
        assert (REPO / fm["schema"]).is_file(), f"{p.name} 声明的 {fm['schema']} 不存在"


def test_every_tool_in_manifest_exists() -> None:
    """tool_manifest.yaml 登记的工具必须真的存在，且 agent 引用的工具必须已登记。"""
    import yaml

    manifest = yaml.safe_load((REPO / "tools" / "tool_manifest.yaml").read_text(encoding="utf-8"))
    registered = set()
    for t in manifest["tools"]:
        assert (REPO / t["entry"]).is_file(), f"{t['name']} 的 entry {t['entry']} 不存在"
        registered.add(t["name"])

    for p in (REPO / "agents").glob("*.md"):
        if p.stem == "README":
            continue
        fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])
        for tool in fm.get("tools") or []:
            assert tool in registered, f"{p.name} 引用了未登记的工具 {tool}"


def test_panel_has_exactly_three_signals() -> None:
    """章节八硬要求：明天三个关键观察信号，不多不少。"""
    rep = _load(EXAMPLE_RUN / "report.json")
    assert len(rep["panel"]["signals"]) == 3


def test_every_position_has_exactly_one_action() -> None:
    """每只持仓只能有一个动作——这是 pipeline.yaml 的硬约束。"""
    pr = _load(EXAMPLE_RUN / "positions_review.json")
    rep = _load(EXAMPLE_RUN / "report.json")
    allowed = {"持有", "减仓", "退出", "禁止加仓", "确认后可加仓"}
    card_actions = {c["code"]: c["action"] for c in pr["cards"]}
    for c in pr["cards"]:
        assert c["action"] in allowed
    for a in rep["panel"]["actions"]:
        assert card_actions.get(a["code"]) == a["action"], \
            f"{a['code']} 在执行面板与持仓卡片里的动作不一致"


def test_seven_behavior_checks_all_present() -> None:
    """七条行为自检一条都不能少，触发与否都要有结论。"""
    pr = _load(EXAMPLE_RUN / "positions_review.json")
    names = {c["check"] for c in pr["behavior_checks"]}
    assert len(names) == 7, f"行为自检缺失: {names}"
    for c in pr["behavior_checks"]:
        assert c["detail"].strip(), f"{c['check']} 没有给出依据"


def test_no_trade_advice_in_example_report() -> None:
    """硬约束：报告中不得出现荐股与目标价类措辞。"""
    text = (EXAMPLE_RUN / "report.md").read_text(encoding="utf-8")
    banned = ["建议买入", "建议卖出", "目标价", "满仓", "抄底", "推荐关注"]
    hits = [w for w in banned if w in text]
    assert not hits, f"报告中出现了禁止的措辞: {hits}"


def test_data_gap_declared_at_the_top() -> None:
    """数据缺口必须在报告开头声明，不许藏在末尾。"""
    rep = _load(EXAMPLE_RUN / "report.json")
    if rep["data_completeness"]["level"] != "complete":
        head = (EXAMPLE_RUN / "report.md").read_text(encoding="utf-8")[:600]
        assert "数据缺口" in head or "缺失" in head
