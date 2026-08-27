"""契约测试：示例 run 的产物必须符合 schemas/ 定义。

这是整个仓库最该先跑通的测试——它保证 agent 之间的接口没有错位。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_RUN = REPO / "workspace" / "runs" / "2026-01-02_example"

ARTIFACTS = {
    "run_manifest": "run_manifest.schema.json",
    "dataset": "dataset.schema.json",
    "fundamental": "fundamental.schema.json",
    "technical": "technical.schema.json",
    "sentiment": "sentiment.schema.json",
    "report": "report.schema.json",
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("artifact,schema_file", sorted(ARTIFACTS.items()))
def test_example_artifact_matches_schema(artifact: str, schema_file: str) -> None:
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(REPO / "tools"))
    from _common import build_validator  # noqa: PLC0415

    doc = _load(EXAMPLE_RUN / f"{artifact}.json")
    schema = _load(REPO / "schemas" / schema_file)

    errors = sorted(build_validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
    )


def test_all_agents_declared_in_manifest() -> None:
    """agents/ 下的每个 agent 都应出现在示例 run_manifest 的 steps 里（orchestrator 除外）。"""
    agent_files = {p.stem for p in (REPO / "agents").glob("*.md")} - {"README"}
    manifest = _load(EXAMPLE_RUN / "run_manifest.json")
    steps = {s["agent"] for s in manifest["steps"]}
    missing = agent_files - steps - {"orchestrator"}
    assert not missing, f"这些 agent 没有出现在 run_manifest.steps 中: {missing}"


def test_no_trade_advice_in_example_report() -> None:
    """硬约束：报告中不得出现买卖建议类措辞。"""
    text = (EXAMPLE_RUN / "report.md").read_text(encoding="utf-8")
    banned = ["建议买入", "建议卖出", "目标价", "满仓", "抄底"]
    hits = [w for w in banned if w in text]
    assert not hits, f"报告中出现了禁止的措辞: {hits}"
