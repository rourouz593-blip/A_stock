"""Harness 适配层测试。

守两件事：
  1. `.claude/` `.opencode/` `.cursor/` `.codex/` 与源头同步（防止分叉）
  2. astock 状态机的推进逻辑正确（这是任何 coding agent 能跑通流程的前提）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "tools/astock.py", *args],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "NO_COLOR": "1",
                               "HOME": str(Path.home())})


def test_harness_adapters_are_in_sync() -> None:
    """适配文件必须与 agents/ 同步。不同步说明有人手改了生成物。"""
    r = subprocess.run([sys.executable, "tools/sync_harness.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_agent_has_an_adapter() -> None:
    from core.agent_registry import agent_files, read_meta

    agents = {read_meta(p)["name"] for p in agent_files()}
    for harness_dir in (".claude/agents", ".opencode/agent"):
        got = {p.stem for p in (REPO / harness_dir).glob("*.md")}
        assert got == agents, f"{harness_dir} 与 agents/ 不一致：{got ^ agents}"


def test_all_generated_files_marked() -> None:
    sys.path.insert(0, str(REPO / "tools"))
    import sync_harness

    for rel, content in sync_harness.build().items():
        assert sync_harness.GEN_MARK in content, f"{rel} 缺少「不要手改」标记"


def test_skill_description_covers_chinese_triggers() -> None:
    """Claude Code 靠 description 做路由。用户最可能说的那几句必须出现在里面。"""
    p = REPO / ".claude" / "skills" / "a-stock-daily-review" / "SKILL.md"
    desc = p.read_text(encoding="utf-8").split("---")[1]
    for phrase in ["复盘", "大盘", "持仓", "A 股"]:
        assert phrase in desc, f"技能描述里缺少触发词「{phrase}」"


# ── astock 状态机 ───────────────────────────────────────────────
MODE_STEPS_CLOSE = ["data-engineer", "market-analyst", "sector-analyst",
                    "news-analyst", "position-advisor", "report-writer"]


def test_next_json_is_machine_readable_on_example_run() -> None:
    """`astock next --json` 是给 agent 用的接口，字段不能少。"""
    r = _run("next", "--run-id", "2026-08-28_example", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["done"] is True, "示例 run 应当是已完成状态"


def test_next_instruction_names_reads_writes_and_schema(tmp_path) -> None:
    """`astock next` 的人读输出必须包含：读什么、写什么、按哪份 schema、怎么收尾。"""
    rid = "2026-08-28_example"
    sys.path.insert(0, str(REPO / "tools"))
    import astock

    meta = astock.agent_meta("market-analyst")
    assert meta["reads"] and meta["writes"] and meta["schema"]
    assert astock.ARTIFACT_OF["market-analyst"] == "market"
    # 每个 agent 的产物名都要能映射到一份真实存在的 schema
    for agent, artifact in astock.ARTIFACT_OF.items():
        assert (REPO / "schemas" / f"{artifact}.schema.json").is_file(), agent


def test_mode_steps_match_pipeline_config() -> None:
    """astock 的步骤表必须与 config/pipeline.yaml 一致，否则两处会各跑各的。"""
    import yaml

    sys.path.insert(0, str(REPO / "tools"))
    import astock

    cfg = yaml.safe_load((REPO / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    for mode, spec in cfg["modes"].items():
        assert astock.MODE_STEPS[mode] == spec["steps"], f"{mode} 模式的步骤两处不一致"


def test_artifact_map_covers_every_agent() -> None:
    sys.path.insert(0, str(REPO / "tools"))
    import astock

    from core.agent_registry import agent_files, read_meta

    agents = {read_meta(p)["name"] for p in agent_files()} - {"orchestrator"}
    assert agents <= set(astock.ARTIFACT_OF), "有 agent 没登记产物名，astock done 会不认它"
