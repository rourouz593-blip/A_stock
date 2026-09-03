"""持仓截图导入测试。

这条链路的风险不在"读不出来"，而在"读错了却照样往下跑"——
成本价错一位，章节⑦的单笔风险与 0.5% 判断全错，报告还长得很专业。
所以测试的重点全在**它会不会把错数字挡住**。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _payload(**over) -> dict:
    p = {"code": "600519", "name": "示例", "shares": 100, "cost": 12.80,
         "price": 14.62, "market_value": 1462.0, "pnl": 182.0}
    p.update(over)
    return {"positions": [p]}


def _run(payload: dict, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/import_positions.py", "--json", json.dumps(payload), *extra],
        cwd=REPO, capture_output=True, text=True)


# ── 算术自检 ───────────────────────────────────────────────────
def test_consistent_numbers_pass():
    r = _run(_payload())
    assert r.returncode == 0, r.stderr
    assert "预览" in r.stdout


def test_wrong_cost_is_caught():
    """成本价读错一位 → 盈亏恒等式不成立，必须拦下。"""
    r = _run(_payload(cost=1.28))
    assert r.returncode == 1
    assert "成本价读错" in r.stderr


def test_wrong_shares_is_caught():
    """数量读错一位 → 市值恒等式不成立。"""
    r = _run(_payload(shares=10))
    assert r.returncode == 1
    assert "数量或现价读错" in r.stderr


def test_missing_verification_fields_is_caught():
    """没读现价/市值/盈亏 → 没有任何东西能验证成本与数量，也要拦。"""
    r = _run({"positions": [{"code": "600519", "shares": 100, "cost": 12.80}]})
    assert r.returncode == 1
    assert "无法做算术自检" in r.stderr


def test_allow_unverified_escape_hatch():
    """确实拿不到校验字段时才允许绕过——但这是显式的、要写在命令里的。"""
    r = _run({"positions": [{"code": "600519", "shares": 100, "cost": 12.80}]},
             "--allow-unverified")
    assert r.returncode == 0


def test_bad_code_rejected():
    r = _run(_payload(code="60051"))
    assert r.returncode != 0


def test_zero_shares_rejected():
    r = _run(_payload(shares=0, market_value=0, pnl=0))
    assert r.returncode != 0


# ── 合并逻辑 ───────────────────────────────────────────────────
def test_human_fields_are_preserved(tmp_path, monkeypatch):
    """thesis / stop_level 是截图里没有的，必须从旧文件保留下来。"""
    import import_positions as ip

    old = {"version": 1, "positions": [{
        "code": "600519.SH", "name": "示例", "cost": 12.80, "shares": 2000,
        "module": "打板", "sector": "示例题材",
        "thesis": "题材启动第二天打板做龙头", "stop_level": 11.5,
        "buy_date": "2026-08-25"}]}
    new = [{"code": "600519.SH", "name": "示例", "cost": 13.10, "shares": 3000}]
    merged, delta = ip.merge(new, old)

    got = merged[0]
    assert got["thesis"] == "题材启动第二天打板做龙头", "买入逻辑被截图冲掉了"
    assert got["stop_level"] == 11.5
    assert got["module"] == "打板"
    assert got["cost"] == 13.10 and got["shares"] == 3000, "成本与数量应当被截图更新"
    assert delta["changed"] and not delta["added"]


def test_bare_code_matches_existing_suffix():
    """截图只有六位码，推断的后缀可能与旧文件不同——
    这时必须以旧文件为准，否则 thesis 会被当成新标的丢掉。"""
    import import_positions as ip

    old = {"version": 1, "positions": [
        {"code": "999001.SZ", "cost": 12.8, "shares": 100, "thesis": "别丢我"}]}
    merged, delta = ip.merge([{"code": ip.suffixed("999001"), "name": None,
                               "cost": 13.0, "shares": 100}], old)
    assert merged[0]["code"] == "999001.SZ", "应当沿用旧文件里的后缀"
    assert merged[0]["thesis"] == "别丢我"
    assert not delta["added"] and not delta["removed"]


def test_new_position_is_flagged_for_thesis():
    import import_positions as ip

    merged, delta = ip.merge([{"code": "600519.SH", "name": "新", "cost": 10, "shares": 100}],
                             {"version": 1, "positions": []})
    assert delta["added"] == ["600519.SH"]
    assert merged[0]["thesis"] is None, "新标的的买入逻辑必须留空，交给用户填"


def test_preview_does_not_write(tmp_path):
    """不加 --apply 时绝不能碰 positions.yaml。"""
    target = REPO / "config" / "positions.yaml"
    before = target.read_text(encoding="utf-8") if target.is_file() else None
    _run(_payload())
    after = target.read_text(encoding="utf-8") if target.is_file() else None
    assert before == after


def test_dump_yaml_roundtrips():
    """生成的 yaml 必须能被 position_advisor 的 positions.py 读回去。"""
    import yaml

    import import_positions as ip

    text = ip.dump_yaml([{"code": "600519.SH", "name": "示例", "cost": 12.8, "shares": 100,
                          "module": "打板", "sector": "题材", "thesis": "理由",
                          "stop_level": 11.5, "buy_date": "2026-08-25"}])
    doc = yaml.safe_load(text)
    assert doc["positions"][0]["thesis"] == "理由"
    assert doc["positions"][0]["stop_level"] == 11.5


def test_skill_exists_and_warns_against_guessing_thesis():
    p = REPO / "agents" / "position_advisor" / "skills" / "positions-import" / "SKILL.md"
    assert p.is_file()
    body = p.read_text(encoding="utf-8")
    assert "不要猜" in body and "thesis" in body
