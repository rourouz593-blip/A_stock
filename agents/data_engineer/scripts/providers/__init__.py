"""数据 provider：同一类数据，多个来源，按优先级挑一个。

# 为什么要有这一层

在这之前，取数代码直接写死了"用 akshare 的哪个函数"。
于是"换一个源"意味着改取数逻辑，而不是改配置——8-31 被封那天，
我们没有任何一个开关可以说"这块数据改走别处"。

provider 把这件事拆成两半：

    做什么（fetch_holdings_quotes 要一份持仓快照）
    ↕                                    ← 这条线就是 provider 的意义
    谁来做（腾讯批量 / 东财逐个 / 仓库读回）

优先级写在 `config/datasources.yaml` 里，不写在代码里。

# 挑选原则（来自 ADR-0004 §3.5）

> 能用通达信/腾讯，就别用东财；东财只留给它独有、别处拿不到的数据。

不是因为东财数据差，是因为**东财会封 IP，腾讯不会**。
把高频、批量、每天都要跑的那些请求挪走，等于把风险最高的那部分请求量清零。
"""
from __future__ import annotations

import os
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from core.paths import REPO_ROOT

CONFIG = REPO_ROOT / "config" / "datasources.yaml"

# dataset → [provider 名字，按优先级]。读不到配置时的兜底，与 datasources.yaml 保持一致。
DEFAULT_CHAIN = {
    "spot": ["tencent"],
    "index_daily": ["baostock"],
    "index_daily_000688": ["ashare"],
    "index_intraday": ["ashare"],
    "stock_daily": ["ashare"],
    "sectors": ["sina"],
    "sector_flow": [],
}


def chain(dataset: str) -> list[str]:
    """这类数据按什么顺序试。环境变量可以临时改，方便排障。

    ASTOCK_PROVIDER_SPOT=eastmoney python tools/astock.py review
    """
    override = os.getenv(f"ASTOCK_PROVIDER_{dataset.upper()}")
    if override:
        return [p.strip() for p in override.split(",") if p.strip()]
    try:
        import yaml

        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
        got = (cfg.get("datasets") or {}).get(dataset)
        if got:
            return list(got)
    except Exception:
        pass          # 配置坏了不该让取数停摆，用兜底顺序继续
    return list(DEFAULT_CHAIN.get(dataset, []))


def get(dataset: str, capability: str) -> list[tuple[str, Callable[..., Any]]]:
    """按优先级返回 [(provider 名, 可调用对象)]。

    返回列表而不是单个：调用方要能在第一个失败时接着试第二个，
    并且**把实际命中的那个记进 provenance**——报告里"这个数从哪来"必须能查。
    """
    out = []
    for name in chain(dataset):
        mod = _provider(name)
        if mod is None:
            continue
        fn = getattr(mod, capability, None)
        if fn is not None:
            out.append((name, fn))
    return out


def _extension_paths() -> list[Path]:
    paths: list[str] = []
    try:
        import yaml

        cfg = yaml.safe_load((REPO_ROOT / "config" / "extensions.yaml")
                             .read_text(encoding="utf-8")) or {}
        paths += (cfg.get("paths") or {}).get("providers") or []
    except (FileNotFoundError, OSError, ValueError):
        pass
    paths += [p for p in os.getenv("ASTOCK_PROVIDER_PATHS", "").split(os.pathsep) if p]
    return [p if (p := Path(raw)).is_absolute() else REPO_ROOT / p for raw in paths]


@lru_cache(maxsize=None)
def _provider(name: str) -> ModuleType | None:
    """Load a configured external provider first, then a built-in provider."""
    for root in _extension_paths():
        for path in (root / f"{name}.py", root / name / "__init__.py"):
            if not path.is_file():
                continue
            module_name = f"astock_provider_{name}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                return module
    try:
        return __import__(f"agents.data_engineer.scripts.providers.{name}", fromlist=["x"])
    except ImportError:
        return None
