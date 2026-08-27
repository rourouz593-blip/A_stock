"""数据层骨架测试：确认空实现是"响亮地失败"，而不是静默返回假数据。

TODO(datasource): 实现 scripts/ 后，把这些测试替换成真正的行为测试。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.contracts import BLOCK_NAMES, FetchRequest, Provenance  # noqa: E402


def test_block_names_match_schema() -> None:
    import json

    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "dataset.schema.json").read_text(
            encoding="utf-8"
        )
    )
    allowed = set(schema["properties"]["blocks"]["propertyNames"]["enum"])
    assert set(BLOCK_NAMES) == allowed, "contracts.BLOCK_NAMES 与 dataset.schema.json 不一致"


def test_provenance_requires_source_and_time() -> None:
    p = Provenance(source="X", fetched_at="2026-01-02T00:00:00+00:00")
    assert p.source and p.fetched_at
    assert p.fallback_from is None


@pytest.mark.parametrize(
    "module,func",
    [
        ("scripts.fetch.market_data", "fetch_ohlcv"),
        ("scripts.fetch.financials", "fetch_statements"),
        ("scripts.fetch.news", "fetch_news"),
        ("scripts.clean.normalize", "align_to_calendar"),
        ("scripts.store.repository", "build_dataset_json"),
    ],
)
def test_stubs_raise_not_implemented(module: str, func: str) -> None:
    import importlib

    m = importlib.import_module(module)
    with pytest.raises(NotImplementedError):
        getattr(m, func)(FetchRequest(codes=["000000.SZ"]))
