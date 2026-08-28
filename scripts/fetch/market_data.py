"""行情数据取数。

当前只接入 AKShare 的 A 股历史行情接口。其他行情能力仍保持为空实现，避免把
“采用 AKShare 获取 OHLCV”误解成“AKShare 已获准提供所有数据”。
"""
from __future__ import annotations

import math
import re
from contextlib import redirect_stderr
from datetime import date, datetime, timezone
from io import StringIO
from typing import Any

from ..contracts import AdjustMode, DataBlock, FetchRequest

CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
FREQUENCIES = {"daily", "weekly", "monthly"}
FIELD_MAPPING = {
    "日期": "date",
    "股票代码": "code",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume_lots",
    "成交额": "amount_cny",
    "振幅": "amplitude_pct",
    "涨跌幅": "change_pct",
    "涨跌额": "change_cny",
    "换手率": "turnover_rate_pct",
}
REQUIRED_COLUMNS = {"日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"}
TX_FIELD_MAPPING = {
    "date": "date",
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume_lots",
    "turnover": "turnover_rate_pct",
    "amount": "amount_cny",
}
TX_REQUIRED_COLUMNS = {"date", "open", "close", "high", "low", "volume", "amount"}


def _load_akshare():
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("缺少 AKShare；请先执行 pip install -r requirements.txt") from exc
    return ak


def _date_param(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} 不能为空")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是 YYYY-MM-DD: {value}") from exc
    return parsed.strftime("%Y%m%d")


def _json_value(value: Any) -> Any:
    """把 pandas/numpy 标量变为严格 JSON 可序列化的 Python 值。"""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _normalize_frame(frame: Any, code: str) -> list[dict[str, Any]]:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"AKShare 返回缺列: {sorted(missing)}")

    normalized = frame.rename(columns=FIELD_MAPPING)
    output_columns = [
        mapped for source, mapped in FIELD_MAPPING.items() if source in frame.columns
    ]
    # `股票代码` 在旧版 AKShare 响应中不存在，因此 code 始终以请求值为准。
    output_columns = [column for column in output_columns if column != "code"]
    records: list[dict[str, Any]] = []
    for raw in normalized.to_dict(orient="records"):
        record = {"code": code}
        for column in output_columns:
            if column in raw:
                record[column] = _json_value(raw[column])
        record["date"] = str(record["date"])[:10]
        records.append(record)
    return records


def _normalize_tx_frame(frame: Any, code: str) -> list[dict[str, Any]]:
    missing = TX_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"AKShare 腾讯响应缺列: {sorted(missing)}")

    normalized = frame.rename(columns=TX_FIELD_MAPPING)
    output_columns = [
        mapped for source, mapped in TX_FIELD_MAPPING.items() if source in frame.columns
    ]
    records: list[dict[str, Any]] = []
    for raw in normalized.to_dict(orient="records"):
        record = {"code": code}
        for column in output_columns:
            if column in raw:
                record[column] = _json_value(raw[column])
        record["date"] = str(record["date"])[:10]
        # 腾讯成交量为股、换手率为小数；项目统一为手和百分比。
        if record.get("volume_lots") is not None:
            record["volume_lots"] = round(record["volume_lots"] / 100, 2)
        if record.get("turnover_rate_pct") is not None:
            record["turnover_rate_pct"] = round(
                record["turnover_rate_pct"] * 100, 10
            )
        if record.get("amount_cny") is not None:
            record["amount_cny"] = round(record["amount_cny"], 2)
        records.append(record)
    return records


def fetch_ohlcv(req: FetchRequest, freq: str = "daily", adjust: AdjustMode = "qfq") -> DataBlock:
    """取日线/周线/月线行情。

    复权口径、字段映射和单位全部写进 Provenance。接口不会给缺失日期补 0、前值
    或插值；完整的交易日历对齐仍由尚未实现的 clean 层负责。

    Returns: DataBlock(status, rows, coverage, inline, provenance, flags)

    `inline` 中是一组已统一英文字段名的记录。CLI tool 负责把它写入本次 run 的
    工作区，并将最终相对路径回填到 DataBlock.path。
    """
    from ..contracts import Provenance, QualityFlag

    if not req.codes:
        raise ValueError("codes 不能为空")
    bad_codes = [code for code in req.codes if not CODE_RE.fullmatch(code)]
    if bad_codes:
        raise ValueError(f"股票代码格式不合法: {bad_codes}")
    if freq not in FREQUENCIES:
        raise ValueError(f"freq 必须是 {sorted(FREQUENCIES)} 之一: {freq}")
    if adjust not in {"qfq", "hfq", "none"}:
        raise ValueError(f"adjust 必须是 qfq/hfq/none: {adjust}")

    start = _date_param(req.start, "start")
    end = _date_param(req.end, "end")
    if start > end:
        raise ValueError("start 不得晚于 end")

    ak = _load_akshare()
    records: list[dict[str, Any]] = []
    flags: list[QualityFlag] = []
    timeout = float(req.extra.get("timeout", 15))
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    source_adjust = "" if adjust == "none" else adjust
    source_by_code: dict[str, str] = {}
    fallback_codes: list[str] = []

    for code in req.codes:
        try:
            frame = ak.stock_zh_a_hist(
                symbol=code[:6],
                period=freq,
                start_date=start,
                end_date=end,
                adjust=source_adjust,
                timeout=timeout,
            )
            if frame is None or frame.empty:
                raise ValueError("接口返回空数据")
            records.extend(_normalize_frame(frame, code))
            source_by_code[code] = "Eastmoney"
            continue
        except Exception as primary_exc:
            if freq == "daily":
                try:
                    # AKShare 的腾讯实现会输出 tqdm；tool 成功时 stdout/stderr 应保持结构化。
                    with redirect_stderr(StringIO()):
                        frame = ak.stock_zh_a_hist_tx(
                            symbol={"SH": "sh", "SZ": "sz", "BJ": "bj"}[
                                code[-2:]
                            ]
                            + code[:6],
                            start_date=start,
                            end_date=end,
                            adjust=source_adjust,
                            timeout=timeout,
                        )
                    if frame is None or frame.empty:
                        raise ValueError("接口返回空数据")
                    records.extend(_normalize_tx_frame(frame, code))
                    source_by_code[code] = "Tencent"
                    fallback_codes.append(code)
                    flags.append(
                        QualityFlag(
                            block="ohlcv",
                            level="warning",
                            message=(
                                f"{code} 东财主源失败，已降级到腾讯: "
                                f"{type(primary_exc).__name__}: {primary_exc}"
                            ),
                            affected_range=f"{req.start}..{req.end}",
                        )
                    )
                    continue
                except Exception as fallback_exc:
                    error_message = (
                        f"{code} 获取失败；东财={type(primary_exc).__name__}: {primary_exc}; "
                        f"腾讯={type(fallback_exc).__name__}: {fallback_exc}"
                    )
            else:
                error_message = (
                    f"{code} 获取失败: {type(primary_exc).__name__}: {primary_exc}; "
                    "腾讯备用源只支持 daily"
                )

            # 每个标的独立失败，允许保留其余可用数据。
            flags.append(
                QualityFlag(
                    block="ohlcv",
                    level="error",
                    message=error_message,
                    affected_range=f"{req.start}..{req.end}",
                )
            )

    records.sort(key=lambda row: (row["code"], row["date"]))
    dates = [row["date"] for row in records]
    if dates and max(dates) < req.end:
        flags.append(
            QualityFlag(
                block="ohlcv",
                level="info",
                message=(
                    f"数据覆盖截至 {max(dates)}，早于请求终点 {req.end}；"
                    "可能是非交易日或备用源尚未更新，未做补值"
                ),
                affected_range=f"{max(dates)}..{req.end}",
            )
        )
    status = (
        "missing"
        if not records
        else (
            "degraded"
            if any(flag.level in {"warning", "error"} for flag in flags)
            else "ok"
        )
    )
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if fallback_codes and len(fallback_codes) == len(source_by_code):
        actual_source = "AKShare.stock_zh_a_hist_tx (Tencent)"
    elif fallback_codes:
        actual_source = "AKShare mixed (Eastmoney/Tencent)"
    else:
        actual_source = "AKShare.stock_zh_a_hist (Eastmoney)"
    if fallback_codes and len(fallback_codes) == len(source_by_code):
        provenance_mapping = TX_FIELD_MAPPING
    elif fallback_codes:
        provenance_mapping = {
            **{f"Eastmoney:{key}": value for key, value in FIELD_MAPPING.items()},
            **{f"Tencent:{key}": value for key, value in TX_FIELD_MAPPING.items()},
        }
    else:
        provenance_mapping = FIELD_MAPPING
    provenance = Provenance(
        source=actual_source,
        fetched_at=fetched_at,
        fallback_from=(
            "AKShare.stock_zh_a_hist (Eastmoney)" if fallback_codes else None
        ),
        field_mapping=provenance_mapping,
        unit="price/amount=CNY_yuan; volume=lot; rates=percent",
        params={
            "codes": req.codes,
            "start": req.start,
            "end": req.end,
            "freq": freq,
            "adjust": adjust,
            "timeout": timeout,
            "source_by_code": source_by_code,
        },
    )
    return DataBlock(
        status=status,
        provenance=provenance,
        rows=len(records),
        coverage={"start": min(dates), "end": max(dates)} if dates else None,
        inline=records,
        flags=flags,
    )


def fetch_trading_calendar(start: str, end: str) -> DataBlock:
    """取交易日历。所有时间序列对齐都依赖它，务必先实现这个。"""
    raise NotImplementedError("TODO(datasource): 实现交易日历取数")


def fetch_adjust_factor(req: FetchRequest) -> DataBlock:
    """取复权因子。自行复权时需要；若数据源直接给复权价可跳过。"""
    raise NotImplementedError("TODO(datasource): 实现复权因子取数")
