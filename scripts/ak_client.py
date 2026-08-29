"""AKShare 调用封装：统一重试、超时、缓存与"响亮失败"。

为什么要包一层，而不是到处直接 `ak.xxx()`：
  1. akshare 背后是第三方网页接口，会限流、会偶发超时——重试逻辑只写一次
  2. 同一天的数据反复取没意义，本地缓存能让调试快十倍，也少给数据源添麻烦
  3. 取数失败必须"响亮地失败"（抛异常），不能返回空 DataFrame 让上层误以为"今天就是没数据"
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("ASTOCK_CACHE_DIR", REPO_ROOT / "workspace" / "cache"))
MAX_RETRY = int(os.getenv("ASTOCK_MAX_RETRY", "3"))
RETRY_SLEEP = float(os.getenv("ASTOCK_RETRY_SLEEP", "1.5"))


class FetchError(RuntimeError):
    """取数失败。上层应把对应 block 标为 missing，而不是伪造数据。"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _cache_key(name: str, params: dict) -> str:
    raw = name + json.dumps(params, sort_keys=True, ensure_ascii=False)
    return f"{name}_{hashlib.md5(raw.encode()).hexdigest()[:10]}"


def call(name: str, params: dict[str, Any] | None = None, *, cache: bool = True):
    """调用一个 akshare 接口并返回 DataFrame。

    name   : akshare 函数名，如 'stock_zh_index_spot_em'
    params : 关键字参数
    cache  : 是否使用本地 CSV 缓存（默认开，调试时省时间）
    """
    params = params or {}
    try:
        import akshare as ak
    except ImportError as e:  # pragma: no cover
        raise FetchError(
            "未安装 akshare。请先 pip install -r requirements.txt"
        ) from e

    fn: Callable | None = getattr(ak, name, None)
    if fn is None:
        raise FetchError(f"akshare 没有接口 {name}（可能版本太旧，试试 pip install -U akshare）")

    cache_file = CACHE_DIR / f"{_cache_key(name, params)}.csv"
    if cache and cache_file.is_file():
        import pandas as pd

        return pd.read_csv(cache_file, dtype={"代码": str, "板块代码": str})

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            df = fn(**params)
            if df is None or len(df) == 0:
                raise FetchError(f"{name} 返回空数据 params={params}")
            if cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(cache_file, index=False)
            return df
        except FetchError:
            raise
        except Exception as e:  # 网络/限流/接口变更
            last_err = e
            if attempt < MAX_RETRY:
                time.sleep(RETRY_SLEEP * attempt)
    raise FetchError(f"{name} 连续 {MAX_RETRY} 次失败 params={params}: {last_err}")


def try_call(name: str, params: dict[str, Any] | None = None, *, cache: bool = True):
    """同 call()，但失败时返回 (None, 错误信息) 而不是抛异常。

    用于"缺了也能继续"的可选数据块（如北向资金）。
    必需数据块请用 call()，让它响亮地失败。
    """
    try:
        return call(name, params, cache=cache), None
    except Exception as e:
        return None, str(e)
