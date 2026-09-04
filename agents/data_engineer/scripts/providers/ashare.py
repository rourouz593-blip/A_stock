"""AShare-compatible index bars backed by Sina and Tencent, not Eastmoney."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

import pandas as pd

from .tencent import _prefix

SINA = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
TENCENT_DAY = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_MIN = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
UA = "Mozilla/5.0 (compatible; astock-review/1.0)"


def _json(url: str, params: dict, timeout: float):
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return json.loads(response.read().decode("utf-8"))


def _daily_frame(rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    if frame.empty:
        raise RuntimeError("provider returned no daily bars")
    for column in ("open", "close", "high", "low", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    previous = frame["close"].shift(1)
    frame["振幅"] = ((frame["high"] - frame["low"]) / previous * 100).round(2)
    frame["涨跌幅"] = ((frame["close"] / previous - 1) * 100).round(2)
    frame["成交额"] = float("nan")  # These index K-lines do not expose turnover amount.
    return frame.rename(columns={
        "date": "日期", "open": "开盘", "close": "收盘", "high": "最高",
        "low": "最低", "volume": "成交量",
    })[["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅"]]


def _sina_daily(symbol: str, count: int, timeout: float) -> pd.DataFrame:
    payload = _json(SINA, {"symbol": symbol, "scale": 240, "ma": 5, "datalen": count}, timeout)
    rows = [[r.get(k) for k in ("day", "open", "close", "high", "low", "volume")] for r in payload]
    return _daily_frame(rows)


def _tencent_daily(symbol: str, count: int, timeout: float) -> pd.DataFrame:
    payload = _json(TENCENT_DAY, {"param": f"{symbol},day,,,{count},qfq"}, timeout)
    data = payload.get("data", {}).get(symbol) or {}
    rows = data.get("qfqday") or data.get("day") or []
    frame = _daily_frame([row[:6] for row in rows])
    frame["成交量"] *= 100  # Tencent index volume is lots; the pipeline contract is shares.
    return frame


def index_daily(code: str, start_date: str, end_date: str, *, timeout: float = 10.0):
    """Return index daily bars; Sina first, Tencent fallback."""
    symbol = _prefix(code)
    count = max((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 10, 20)
    errors = []
    for fetch in (_sina_daily, _tencent_daily):
        try:
            frame = fetch(symbol, count, timeout)
            frame = frame[(frame["日期"] >= pd.Timestamp(start_date)) &
                          (frame["日期"] <= pd.Timestamp(end_date))].copy()
            if frame.empty:
                raise RuntimeError("requested date range is absent")
            frame["日期"] = frame["日期"].dt.strftime("%Y-%m-%d")
            return frame
        except Exception as exc:
            errors.append(f"{fetch.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def index_intraday(code: str, as_of: str, *, timeout: float = 10.0):
    """Return Tencent 1-minute index OHLCV for one trading day."""
    symbol = _prefix(code)
    payload = _json(TENCENT_MIN, {"param": f"{symbol},m1,,500"}, timeout)
    rows = (payload.get("data", {}).get(symbol) or {}).get("m1") or []
    frame = pd.DataFrame([row[:6] for row in rows],
                         columns=["时间", "开盘", "收盘", "最高", "最低", "成交量"])
    if frame.empty:
        raise RuntimeError(f"Tencent returned no minute bars for {symbol}")
    frame["时间"] = pd.to_datetime(frame["时间"], format="%Y%m%d%H%M", errors="coerce")
    frame = frame[frame["时间"].dt.strftime("%Y-%m-%d") == as_of].copy()
    if frame.empty:
        raise RuntimeError(f"Tencent has no minute bars for {symbol} on {as_of}")
    for column in ("开盘", "收盘", "最高", "最低", "成交量"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["成交量"] *= 100  # Tencent index volume is lots.
    frame["成交额"] = float("nan")
    frame["时间"] = frame["时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return frame


def stock_daily(code: str, start_date: str, end_date: str, *, timeout: float = 10.0):
    """Return Tencent qfq stock bars; never substitute Sina's unadjusted series."""
    symbol = _prefix(code)
    count = max((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 10, 20)
    payload = _json(TENCENT_DAY, {"param": f"{symbol},day,,,{count},qfq"}, timeout)
    data = payload.get("data", {}).get(symbol) or {}
    rows = data.get("qfqday") or []
    if not rows:
        raise RuntimeError(f"Tencent returned no qfq daily bars for {symbol}")
    frame = _daily_frame([row[:6] for row in rows])
    frame["换手率"] = float("nan")

    quote = (data.get("qt") or {}).get(symbol) or []
    if len(quote) > 38 and len(quote[30]) >= 8:
        quote_date = pd.to_datetime(quote[30][:8], format="%Y%m%d", errors="coerce")
        mask = frame["日期"] == quote_date
        try:
            frame.loc[mask, "成交额"] = float(quote[37]) * 1e4
            frame.loc[mask, "换手率"] = float(quote[38])
        except (TypeError, ValueError):
            pass

    frame = frame[(frame["日期"] >= pd.Timestamp(start_date)) &
                  (frame["日期"] <= pd.Timestamp(end_date))].copy()
    if frame.empty:
        raise RuntimeError(f"Tencent has no qfq bars for {symbol} in requested range")
    frame["日期"] = frame["日期"].dt.strftime("%Y-%m-%d")
    return frame
