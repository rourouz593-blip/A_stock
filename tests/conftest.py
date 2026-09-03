import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))


# 预算和熔断都是**落盘**状态。测试里不隔离的话，读到的是这台机器的真实状态——
# 于是「今天被限流过没有」会决定测试过不过，而且失败信息看起来像代码坏了。
#
# 这个坑真的踩到过：test_browser_ua_is_injected 因为 push2his 正在冷却而失败，
# 和它要测的 UA 注入毫无关系。
#
# 规则：任何落盘状态都必须在 conftest 里改指到 tmp_path。
@pytest.fixture(autouse=True)
def _isolate_persistent_state(tmp_path, monkeypatch):
    from scripts import ak_client

    monkeypatch.setattr(ak_client, "BUDGET_FILE", tmp_path / "budget.json")
    monkeypatch.setattr(ak_client, "CIRCUIT_FILE", tmp_path / "circuit.json")
    # 限流是给真实网络用的；测试里 sleep 只是让跑一次要多花半分钟。
    # 想测限流本身的用例自己把它调回来。
    monkeypatch.setattr(ak_client, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(ak_client, "EM_MIN_INTERVAL", 0.0)
