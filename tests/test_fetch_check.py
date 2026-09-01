"""体检表不能和流水线脱节。

这个文件只守一件事：`fetch_check` 检查的数据块，和 `build_dataset` 实际会取的
数据块，必须是同一份清单。否则会出现最坏的情况——**体检全绿，复盘照样缺章**。
"""
import re
from pathlib import Path

import fetch_check

REPO = Path(__file__).resolve().parent.parent


def _pipeline_blocks() -> set:
    src = (REPO / "scripts" / "build_dataset.py").read_text(encoding="utf-8")
    return set(re.findall(r'blocks\["([a-z_]+)"\]', src))


def test_check_covers_every_pipeline_block():
    checked = {name for name, *_ in fetch_check.BLOCKS}
    missing = _pipeline_blocks() - checked
    assert not missing, (
        f"这些块流水线会取、体检却不查：{sorted(missing)}。"
        f"体检全绿但复盘缺章，是最坏的一种失败。")


def test_check_does_not_invent_blocks():
    checked = {name for name, *_ in fetch_check.BLOCKS}
    extra = checked - _pipeline_blocks()
    assert not extra, f"体检查了流水线不取的块：{sorted(extra)}"


def test_required_blocks_match_the_nine_chapters():
    """必需块的定义：缺了就整章 blocked 的那些。

    可选块（分时/资金流/新闻/公告/北向）缺失时复盘照常出，
    所以它们不该让体检返回非 0——否则学生会以为系统坏了。
    """
    required = {n for n, _c, req, _d in fetch_check.BLOCKS if req}
    assert {"calendar", "index_hist", "index_spot", "breadth", "limit_pool",
            "sectors", "holdings"} == required
    optional = {n for n, _c, req, _d in fetch_check.BLOCKS if not req}
    assert "index_intraday" in optional, "分时只留最近几天，历史日期取不到是正常的"
    assert "northbound" in optional, "北向披露规则多次调整，取不到不该阻塞"
