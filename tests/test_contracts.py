"""Repository-level artifact and agent-package contract tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agent_registry import agent_files, read_meta

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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("artifact,schema_file", sorted(ARTIFACTS.items()))
def test_example_artifact_matches_schema(artifact: str, schema_file: str) -> None:
    pytest.importorskip("jsonschema")
    from core.cli import build_validator

    document = _load(EXAMPLE_RUN / f"{artifact}.json")
    schema = _load(REPO / "schemas" / schema_file)
    errors = sorted(build_validator(schema).iter_errors(document), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
    )


def test_all_agents_declared_in_manifest() -> None:
    discovered = {read_meta(path)["name"] for path in agent_files()}
    steps = {step["agent"] for step in _load(EXAMPLE_RUN / "run_manifest.json")["steps"]}
    assert not discovered - steps - {"orchestrator"}


def test_every_agent_writes_a_schema_that_exists() -> None:
    for definition in agent_files():
        metadata = read_meta(definition)
        assert (REPO / metadata["schema"]).is_file()


def test_every_agent_is_a_strict_package_without_ownership_manifests() -> None:
    for definition in agent_files():
        package = definition.parent
        assert (package / "SKILL.md").is_file()
        assert (package / "tools").is_dir()
        assert (package / "scripts").is_dir()
        assert not list(package.rglob("manifest.yaml"))


def test_panel_has_exactly_three_signals() -> None:
    assert len(_load(EXAMPLE_RUN / "report.json")["panel"]["signals"]) == 3


def test_every_position_has_exactly_one_action() -> None:
    review = _load(EXAMPLE_RUN / "positions_review.json")
    report = _load(EXAMPLE_RUN / "report.json")
    allowed = {"持有", "减仓", "退出", "禁止加仓", "确认后可加仓"}
    actions = {card["code"]: card["action"] for card in review["cards"]}
    assert all(card["action"] in allowed for card in review["cards"])
    assert all(actions.get(item["code"]) == item["action"] for item in report["panel"]["actions"])


def test_seven_behavior_checks_all_present() -> None:
    checks = _load(EXAMPLE_RUN / "positions_review.json")["behavior_checks"]
    assert len({item["check"] for item in checks}) == 7
    assert all(item["detail"].strip() for item in checks)


def test_no_trade_advice_in_example_report() -> None:
    text = (EXAMPLE_RUN / "report.md").read_text(encoding="utf-8")
    banned = ["建议买入", "建议卖出", "目标价", "满仓", "抄底", "推荐关注"]
    assert not [word for word in banned if word in text]


def test_data_gap_declared_at_the_top() -> None:
    report = _load(EXAMPLE_RUN / "report.json")
    if report["data_completeness"]["level"] != "complete":
        head = (EXAMPLE_RUN / "report.md").read_text(encoding="utf-8")[:600]
        assert "数据缺口" in head or "缺失" in head
