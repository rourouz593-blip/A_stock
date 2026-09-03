"""新闻与公告。对应报告章节六。

纪律：本模块只负责"如实取回 + 标注来源与时间"。
利好/中性/利空的判断是 news-analyst 的活，绝不在取数层预先打标签。
"""
from __future__ import annotations

from ..ak_client import now_iso, try_call
from core.contracts import DataBlock, Provenance, QualityFlag, to_ak_date

# 信源分层：交易所公告 > 财联社电报 > 门户新闻
SOURCE_TIER = {
    "stock_notice_report": "T1",
    "stock_info_global_cls": "T2",
    "stock_info_global_em": "T3",
}


def fetch_news(as_of: str, limit: int = 120) -> DataBlock:
    """取当日财经快讯（财联社电报为主，东财全球财经快讯为辅）。"""
    flags, items = [], []

    df, err = try_call("stock_info_global_cls", {"symbol": "全部"}, cache=False)
    if df is not None:
        for _, r in df.iterrows():
            items.append(
                {
                    "time": f"{r.get('发布日期', '')} {r.get('发布时间', '')}".strip(),
                    "title": str(r.get("标题", ""))[:120],
                    "content": str(r.get("内容", ""))[:600],
                    "source": "财联社电报",
                    "source_tier": "T2",
                }
            )
    else:
        flags.append(QualityFlag("news", "warning", f"财联社电报取不到: {err}"))

    df2, err2 = try_call("stock_info_global_em", cache=False)
    if df2 is not None:
        for _, r in df2.iterrows():
            items.append(
                {
                    "time": str(r.get("发布时间", "")),
                    "title": str(r.get("标题", ""))[:120],
                    "content": str(r.get("摘要", ""))[:600],
                    "source": "东方财富快讯",
                    "source_tier": "T3",
                }
            )
    else:
        flags.append(QualityFlag("news", "info", f"东财快讯取不到: {err2}"))

    items = _dedupe(items)[:limit]
    return DataBlock(
        status="ok" if items else "missing",
        rows=len(items),
        inline=items,
        provenance=Provenance(
            source="akshare.stock_info_global_cls + stock_info_global_em",
            fetched_at=now_iso(),
            params={"as_of": as_of, "limit": limit},
        ),
        flags=flags,
    )


def fetch_announcements(as_of: str, limit: int = 200) -> DataBlock:
    """取当日交易所公告（T1 级信源，可信度最高）。"""
    df, err = try_call("stock_notice_report", {"symbol": "全部", "date": to_ak_date(as_of)})
    if df is None:
        return DataBlock(
            status="missing",
            rows=0,
            inline=[],
            provenance=Provenance(source="akshare.stock_notice_report", fetched_at=now_iso()),
            flags=[QualityFlag("announcements", "warning", f"公告取不到: {err}")],
        )
    cols = [c for c in ["代码", "名称", "公告标题", "公告类型", "公告日期", "网址"] if c in df.columns]
    items = df.head(limit)[cols].to_dict("records")
    for it in items:
        it["source_tier"] = "T1"
    return DataBlock(
        status="ok",
        rows=len(items),
        inline=items,
        provenance=Provenance(
            source="akshare.stock_notice_report", fetched_at=now_iso(), params={"date": as_of}
        ),
    )


def _dedupe(items: list[dict]) -> list[dict]:
    """同一事件多家转载只留一条：按标题前 24 字去重。"""
    seen, out = set(), []
    for it in items:
        key = it["title"][:24]
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out
