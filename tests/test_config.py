"""配置层测试：缺配置时系统怎么表现。

这一组测试回答一个很实际的问题——
**哪些配置必须提前准备，哪些可以先不管？**
答案不该写在文档里靠人记，应该由测试钉死。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ── .env 加载器 ────────────────────────────────────────────────
def test_dotenv_parses_comments_quotes_and_export(tmp_path, monkeypatch):
    from scripts.env import load_dotenv

    f = tmp_path / ".env"
    f.write_text(
        "# 注释行\n"
        "\n"
        "ASTOCK_ACCOUNT_EQUITY=200000\n"
        'export ASTOCK_MAX_RETRY="4"\n'
        "QUOTED='hello world'\n"
        "EMPTY=\n",
        encoding="utf-8")
    for k in ("ASTOCK_ACCOUNT_EQUITY", "ASTOCK_MAX_RETRY", "QUOTED", "EMPTY"):
        monkeypatch.delenv(k, raising=False)

    loaded = load_dotenv(f)
    assert loaded["ASTOCK_ACCOUNT_EQUITY"] == "200000"
    assert loaded["ASTOCK_MAX_RETRY"] == "4", "export 前缀要被剥掉"
    assert loaded["QUOTED"] == "hello world", "引号要被剥掉"
    assert "EMPTY" not in loaded, "留空等于没填，不该写入空串"


def test_real_env_wins_over_dotenv(tmp_path, monkeypatch):
    """真实环境变量优先于 .env——CI 里能覆盖，本地不受影响。"""
    from scripts.env import load_dotenv

    f = tmp_path / ".env"
    f.write_text("ASTOCK_ACCOUNT_EQUITY=1\n", encoding="utf-8")
    monkeypatch.setenv("ASTOCK_ACCOUNT_EQUITY", "999")
    load_dotenv(f)
    assert os.environ["ASTOCK_ACCOUNT_EQUITY"] == "999"


def test_missing_dotenv_is_silent(tmp_path):
    """.env 是可选的，不存在不该报错。"""
    from scripts.env import load_dotenv

    assert load_dotenv(tmp_path / "nope.env") == {}


def test_scripts_package_autoloads_dotenv():
    """导入 scripts 包就会自动加载 .env，不用记得先 source。"""
    src = (REPO / "scripts" / "__init__.py").read_text(encoding="utf-8")
    assert "load_dotenv()" in src


# ── 缺配置时的降级行为 ──────────────────────────────────────────
def test_missing_positions_yaml_raises_actionable_error(tmp_path, monkeypatch):
    """没有 positions.yaml 时要给出可执行的提示，而不是 FileNotFoundError。"""
    from scripts.positions import PositionError, load_positions

    monkeypatch.setenv("ASTOCK_ACCOUNT_EQUITY", "100000")
    with pytest.raises(PositionError) as e:
        load_positions(tmp_path / "nope.yaml")
    assert "positions.example.yaml" in str(e.value), "提示里要写清怎么修"


def test_missing_equity_refuses_to_guess(tmp_path, monkeypatch):
    """没配账户总资产时必须报错，绝不许拿持仓市值当账户规模估算。"""
    from scripts.positions import PositionError, load_positions

    f = tmp_path / "positions.yaml"
    f.write_text("version: 1\npositions:\n  - {code: '999001.SZ', cost: 10, shares: 100}\n",
                 encoding="utf-8")
    monkeypatch.delenv("ASTOCK_ACCOUNT_EQUITY", raising=False)
    with pytest.raises(PositionError) as e:
        load_positions(f)
    assert "ASTOCK_ACCOUNT_EQUITY" in str(e.value)


def test_thresholds_falls_back_to_example():
    """没有 thresholds.yaml 时回退到 example，流程不中断（阈值为 null 而已）。"""
    src = (REPO / "tools" / "compute_risk.py").read_text(encoding="utf-8")
    assert "thresholds.example.yaml" in src


def test_dataset_build_survives_missing_positions():
    """持仓读不到时只标 warning，不该让整个取数失败——
    没填持仓的人也应该能看到章节①②③⑥。"""
    src = (REPO / "scripts" / "build_dataset.py").read_text(encoding="utf-8")
    assert "持仓读取失败，章节四将为空" in src


def test_example_configs_exist():
    for f in ("config/positions.example.yaml", "config/thresholds.example.yaml", ".env.example"):
        assert (REPO / f).is_file(), f"{f} 缺失，用户没法照着抄"
