"""落盘序列化测试。

背景（实测）：取数跑完三分钟，最后一步 `json.dumps` 抛
`TypeError: Object of type date is not JSON serializable`，整轮数据全丢。

罪魁是取数层拿回来的 DataFrame 原生对象——`datetime.date`、`numpy.int64`、`NaN`。
它们在内存里都正常，`json` 一个都不认。
"""
from __future__ import annotations

import datetime
import json

import numpy as np
import pandas as pd

from core import repository as R


def _dumps(payload):
    return json.dumps(R._sanitize(payload), ensure_ascii=False, allow_nan=False)


def test_date_and_datetime_become_iso_strings():
    out = R._sanitize({"d": datetime.date(2026, 8, 28),
                       "dt": datetime.datetime(2026, 8, 28, 15, 0)})
    assert out["d"] == "2026-08-28"
    assert out["dt"].startswith("2026-08-28T15:00")


def test_pandas_timestamp_is_serializable():
    assert _dumps({"ts": pd.Timestamp("2026-08-28 15:00")})


def test_numpy_scalars_become_python_types():
    out = R._sanitize({"i": np.int64(42), "f": np.float64(1.5), "b": np.bool_(True)})
    assert out == {"i": 42, "f": 1.5, "b": True}
    assert isinstance(out["i"], int)


def test_missing_values_all_become_null():
    """NaN / NaT / NA 全都是"缺失"，必须是 null。

    尤其 NaT：它是 datetime 的子类，顺序写反就会变成字符串 "NaT"——
    那比 null 糟糕得多，因为下游会把它当成一个有效值。
    """
    out = R._sanitize({"nan": float("nan"), "nat": pd.NaT, "na": pd.NA,
                       "inf": float("inf")})
    assert out == {"nan": None, "nat": None, "na": None, "inf": None}


def test_nan_never_becomes_zero():
    """缺失就是缺失。用 0 代替会让"没有成交额"变成"成交额为零"。"""
    out = R._sanitize({"amount": float("nan")})
    assert out["amount"] is None and out["amount"] != 0


def test_nested_structures_are_walked():
    out = R._sanitize({"blocks": {"a": [{"d": datetime.date(2026, 1, 1)},
                                        {"v": np.int64(3)}]}})
    assert out["blocks"]["a"][0]["d"] == "2026-01-01"
    assert out["blocks"]["a"][1]["v"] == 3


def test_output_is_strict_json():
    """allow_nan=False：NaN 不是合法 JSON，别的语言的解析器会报错。"""
    text = _dumps({"x": float("nan"), "y": [np.float64(1.0)]})
    assert "NaN" not in text


def test_unknown_types_are_coerced_and_recorded():
    """认不出来的类型转成字符串并**记下来**，不要静默吞掉。"""
    R.COERCED.clear()

    class Weird:
        def __repr__(self):
            return "weird"

    out = R._sanitize({"w": Weird()})
    assert out["w"] == "weird"
    assert R.COERCED and "Weird" in R.COERCED[0]


def test_write_json_roundtrip(tmp_path):
    f = tmp_path / "x.json"
    R.write_json(f, {"d": datetime.date(2026, 8, 28), "n": np.int64(7),
                     "missing": float("nan")})
    got = json.loads(f.read_text(encoding="utf-8"))
    assert got == {"d": "2026-08-28", "n": 7, "missing": None}


def test_real_akshare_shaped_payload(tmp_path):
    """模拟公告块：akshare 的 stock_notice_report 返回的日期是 datetime.date。"""
    df = pd.DataFrame({"代码": ["600519"], "公告日期": [datetime.date(2026, 8, 28)],
                       "序号": [np.int64(1)]})
    payload = {"blocks": {"announcements": {"inline": df.to_dict("records")}}}
    R.write_json(tmp_path / "d.json", payload)
    got = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert got["blocks"]["announcements"]["inline"][0]["公告日期"] == "2026-08-28"
