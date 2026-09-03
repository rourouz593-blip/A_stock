#!/usr/bin/env python3
"""生成一份完整的合成示例 run，用于离线演示与契约验证。

用法:
    python tools/make_demo_run.py --run-id 2026-08-28_example

为什么需要它：
  真实取数依赖 AKShare 的网络接口。开发者首次打开仓库时，
  可能还没配好环境、或者当天不是交易日。
  有了这份离线示例，**五秒钟就能看到系统最终产出长什么样**，
  再回头看每个 agent 怎么把它拼出来。

⚠️ 所有代码、板块、数值均为虚构：
   999001.SZ「示例科技」/ 999002.SH「示例材料」不是真实股票。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from core.cli import REPO_ROOT, emit

DISCLAIMER = ("本报告由自动化系统生成，所有内容基于公开数据的程序化处理，"
              "不构成任何投资建议、要约或承诺。数据可能存在缺失、延迟或错误，"
              "分析方法存在局限性。据此操作，风险自负。")
NOW = "2026-08-28T15:42:00+08:00"


def manifest(run_id, as_of):
    return {
        "run_id": run_id, "created_at": NOW, "as_of": as_of, "mode": "close",
        "trading_day": True, "status": "partial",
        "steps": [
            {"agent": "data-engineer", "status": "ok", "artifact": "dataset.json",
             "attempts": 1, "note": "分时接口失败一次后重试成功；北向资金块缺失"},
            {"agent": "market-analyst", "status": "ok", "artifact": "market.json", "attempts": 1, "note": None},
            {"agent": "sector-analyst", "status": "ok", "artifact": "sectors.json", "attempts": 1, "note": None},
            {"agent": "news-analyst", "status": "ok", "artifact": "news.json", "attempts": 1, "note": None},
            {"agent": "position-advisor", "status": "ok", "artifact": "positions_review.json",
             "attempts": 1, "note": None},
            {"agent": "report-writer", "status": "ok", "artifact": "report.json", "attempts": 1, "note": None},
        ],
        "notes": [
            "本目录为合成契约示例，全部数值为虚构数据",
            "999001.SZ 示例科技 / 999002.SH 示例材料 均非真实股票",
            "刻意保留 northbound 块 missing，演示“缺一块时系统如何诚实降级”",
        ],
    }


def dataset(run_id, as_of):
    def prov(src, **kw):
        return {"source": src, "fetched_at": NOW, "params": kw, "unit": "CNY_yuan", "fallback_from": None}

    idx = [
        {"code": "000001", "name": "上证指数", "date": as_of, "open": 3412.55, "close": 3438.21,
         "high": 3444.90, "low": 3405.12, "pct_chg": 0.74, "amplitude": 1.17,
         "amount": 5.62e11, "prev_close": 3412.98, "amount_chg_pct": 8.4},
        {"code": "399001", "name": "深证成指", "date": as_of, "open": 10820.4, "close": 10902.6,
         "high": 10930.1, "low": 10788.3, "pct_chg": 0.62, "amplitude": 1.31,
         "amount": 6.94e11, "prev_close": 10835.4, "amount_chg_pct": 6.1},
        {"code": "399006", "name": "创业板指", "date": as_of, "open": 2158.9, "close": 2131.7,
         "high": 2166.2, "low": 2126.4, "pct_chg": -1.28, "amplitude": 1.84,
         "amount": 3.01e11, "prev_close": 2159.3, "amount_chg_pct": 3.2},
        {"code": "000688", "name": "科创50", "date": as_of, "open": 1042.3, "close": 1028.8,
         "high": 1046.7, "low": 1025.1, "pct_chg": -1.44, "amplitude": 2.07,
         "amount": 5.80e10, "prev_close": 1043.8, "amount_chg_pct": -2.6},
    ]
    return {
        "run_id": run_id, "as_of": as_of, "mode": "close", "generated_at": NOW,
        "adjust_mode": "qfq", "data_source": "akshare",
        "blocks": {
            "calendar": {"status": "ok", "rows": 6000,
                         "inline": {"as_of": as_of, "is_trading_day": True,
                                    "last_trading_day": as_of, "prev_trading_day": "2026-08-27"},
                         "provenance": prov("akshare.tool_trade_date_hist_sina")},
            "index_spot": {"status": "ok", "rows": 4, "inline": idx,
                           "provenance": prov("akshare.index_zh_a_hist", period="daily")},
            "index_hist": {"status": "ok", "rows": 240, "path": f"data/{run_id}/index_hist.csv",
                           "provenance": prov("akshare.index_zh_a_hist", period="daily")},
            "index_intraday": {"status": "ok", "rows": 964, "path": f"data/{run_id}/index_intraday.csv",
                               "provenance": prov("akshare.index_zh_a_hist_min_em", period="1")},
            "breadth": {"status": "ok", "rows": 143,
                        "inline": {
                            "as_of": as_of,
                            "advance_decline": {"up": 3104, "down": 1892, "flat": 121,
                                                "limit_up_legu": 68, "limit_down_legu": 9, "suspended": 14},
                            "limit_stats": {"limit_up": 68, "broken_board": 31,
                                            "limit_down": 9, "prev_limit_up": 55},
                            "broken_board_rate": 31.3, "promotion_rate": 34.5,
                            "highest_board": 5,
                            "ladder": {"1板": 41, "2板": 15, "3板": 8, "4板": 3, "5板": 1},
                        },
                        "provenance": prov("akshare.stock_market_activity_legu + stock_zt_pool_*")},
            "limit_pool": {"status": "ok", "rows": 163, "path": f"data/{run_id}/pool_*.csv",
                           "provenance": prov("akshare.stock_zt_pool_em")},
            "sectors": {"status": "ok", "rows": 480, "path": f"data/{run_id}/sector_*.csv",
                        "provenance": prov("akshare.stock_board_industry_name_em")},
            "sector_flow": {"status": "ok", "rows": 40, "path": f"data/{run_id}/sector_flow.csv",
                            "provenance": prov("akshare.stock_sector_fund_flow_rank", indicator="今日")},
            "holdings": {"status": "ok", "rows": 180,
                         "inline": [
                             {"code": "999001.SZ", "date": as_of, "open": 13.90, "close": 14.62,
                              "high": 14.71, "low": 13.85, "pct_chg": 5.10, "amplitude": 6.2,
                              "turnover_rate": 18.4, "amount": 9.1e8, "ma5": 13.42, "ma10": 12.88,
                              "ma20": 12.10, "high_20d": 14.71, "low_20d": 11.20,
                              "vol_ratio_5d": 1.62, "stale": False},
                             {"code": "999002.SH", "date": as_of, "open": 25.10, "close": 24.18,
                              "high": 25.22, "low": 24.02, "pct_chg": -3.75, "amplitude": 4.8,
                              "turnover_rate": 6.1, "amount": 3.4e8, "ma5": 25.02, "ma10": 25.44,
                              "ma20": 24.90, "high_20d": 27.30, "low_20d": 23.10,
                              "vol_ratio_5d": 0.74, "stale": False},
                         ],
                         "provenance": prov("akshare.stock_zh_a_hist", adjust="qfq")},
            "news": {"status": "ok", "rows": 118, "path": f"data/{run_id}/news.csv",
                     "provenance": prov("akshare.stock_info_global_cls")},
            "announcements": {"status": "ok", "rows": 421, "path": f"data/{run_id}/announcements.csv",
                              "provenance": prov("akshare.stock_notice_report", date=as_of)},
            "northbound": {"status": "missing", "rows": 0,
                           "provenance": prov("akshare.stock_hsgt_fund_flow_summary_em")},
        },
        "derived": {"two_market_amount": {
            "total": 1.256e12, "total_yi": 12560.0, "prev_total_yi": 11640.0,
            "chg_yi": 920.0, "chg_pct": 7.9,
            "note": "上证 + 深证成指市场成交额之和；创业板/科创板已含其中，未重复计入"}},
        "quality_flags": [
            {"block": "index_intraday", "level": "info",
             "message": "分时接口首次超时，重试后取到完整数据", "affected_range": None},
            {"block": "northbound", "level": "info",
             "message": "北向资金接口无数据（沪深港通披露规则已调整），本块为可选，不阻塞分析",
             "affected_range": None},
        ],
    }


def market(run_id, as_of, ds):
    idx = ds["blocks"]["index_spot"]["inline"]
    br = ds["blocks"]["breadth"]["inline"]
    tm = ds["derived"]["two_market_amount"]
    return {
        "run_id": run_id, "as_of": as_of, "status": "ok", "blocked_reason": None,
        "overview": {
            "indexes": [{"name": i["name"], "code": i["code"], "open": i["open"], "close": i["close"],
                         "high": i["high"], "low": i["low"], "pct_chg": i["pct_chg"],
                         "amount_yi": round(i["amount"] / 1e8, 1)} for i in idx],
            "turnover": {"total_yi": tm["total_yi"], "prev_total_yi": tm["prev_total_yi"],
                         "chg_yi": tm["chg_yi"], "chg_pct": tm["chg_pct"],
                         "reading": "放量 920 亿（+7.9%），但增量集中在沪市权重，创业板成交仅 +3.2%——"
                                    "放量方向与题材方向不一致"},
            "breadth": {"up": br["advance_decline"]["up"], "down": br["advance_decline"]["down"],
                        "limit_up": br["limit_stats"]["limit_up"],
                        "limit_down": br["limit_stats"]["limit_down"],
                        "broken_board_rate": br["broken_board_rate"],
                        "promotion_rate": br["promotion_rate"],
                        "highest_board": br["highest_board"], "ladder": br["ladder"]},
            "market_state": {"value": "震荡",
                             "basis": "上证 +0.74% 而创业板 -1.28%、科创50 -1.44%，指数分化；"
                                      "涨跌家数 3104/1892 偏多，但两市成交额虽放量 7.9%，"
                                      "增量集中在沪市权重"},
            "emotion_phase": {
                "value": "分歧",
                "basis": "晋级率 34.5%（昨日 55 只涨停仅 19 只续板）、炸板率 31.3% 已明显抬升，"
                         "最高板 5 板但 4 板仅 3 只、5 板 1 只，梯队上方开始变薄——"
                         "赚钱效应仍在但接力意愿下降，属典型分歧特征，尚未到退潮",
                "evidence": [
                    {"block": "breadth", "field": "promotion_rate", "value": 34.5, "period": as_of},
                    {"block": "breadth", "field": "broken_board_rate", "value": 31.3, "period": as_of},
                    {"block": "breadth", "field": "ladder", "value": {"4板": 3, "5板": 1}, "period": as_of},
                ],
            },
        },
        "index_review": {
            "sessions": [
                {"session": "早盘", "pct_chg_in_session": 0.52,
                 "narrative": "高开后权重直接拉升，上证 10:00 前完成全天大部分涨幅",
                 "driver": "示例金融、示例电力两个权重板块"},
                {"session": "上午", "pct_chg_in_session": 0.11,
                 "narrative": "权重走平，题材开始分化，示例算力盘中冲高回落",
                 "driver": "无明确带动，成交额环比收缩"},
                {"session": "午后", "pct_chg_in_session": -0.08,
                 "narrative": "创业板加速下行，高位连板股批量炸板，上证靠权重护住",
                 "driver": "示例算力退潮拖累创业板"},
                {"session": "尾盘", "pct_chg_in_session": 0.19,
                 "narrative": "尾盘权重再度拉升，但题材股未跟随——护指数不护情绪",
                 "driver": "示例金融"},
            ],
            "why": "指数上涨完全由沪市权重贡献（示例金融、示例电力合计拉动上证约 0.6 个点），"
                   "而创业板、科创50 下跌源于示例算力板块高位退潮。"
                   "这是一个典型的“指数红、情绪凉”结构。",
            "resonant_sectors": ["示例金融", "示例电力"],
            "independent_sectors": ["示例固态电池"],
            "drag_sectors": ["示例算力", "示例半导体"],
            "key_levels": [
                {"index": "上证指数", "type": "resistance", "level": 3450.0,
                 "basis": "8 月 12 日高点 3449.6，且为整数关口"},
                {"index": "上证指数", "type": "support", "level": 3405.0,
                 "basis": "今日最低 3405.12 + 20 日均线 3402.8 重合"},
                {"index": "创业板指", "type": "support", "level": 2126.0,
                 "basis": "今日最低点，同时是 8 月 19 日缺口下沿"},
            ],
            "day_type": {"value": "震荡",
                         "basis": "上证振幅 1.17% 且全天在早盘区间内运行，"
                                  "但指数内部分化剧烈，不属于单边主升或冲高回落"},
        },
        "confidence": "medium",
        "caveats": ["本文件为合成契约示例，全部数值为虚构数据",
                    "北向资金块缺失，无法交叉验证权重拉升的资金来源"],
    }


def sectors(run_id, as_of):
    def m(code, name, boards=None, pct=None, note=None):
        return {"code": code, "name": name, "boards": boards, "pct_chg": pct, "note": note}

    return {
        "run_id": run_id, "as_of": as_of, "status": "ok", "blocked_reason": None,
        "directions": [
            {"role": "今日主线", "name": "示例固态电池", "phase": "发酵",
             "pct_chg": 4.62, "limit_up_count": 9, "net_inflow_yi": 23.4,
             "members": {
                 "leader": m("999001.SZ", "示例科技", 3, 5.10, "3 板，全天封板未开"),
                 "core": m("999010.SH", "示例电新", None, 3.20, "市值 480 亿，容量票"),
                 "elastic": [m("999011.SZ", "示例锂材", 2, 10.0)],
                 "front": [m("999012.SZ", "示例隔膜", 1, 10.0), m("999013.SZ", "示例电解液", 1, 10.0)],
                 "back": [m("999014.SZ", "示例设备", None, 4.1)]},
             "strength_basis": {
                 "linkage": "板块内 9 只涨停、涨幅>5% 的 17 只，不是单票行为",
                 "leadership": "龙头 9:48 封板后，30 分钟内 4 只跟风涨停，带动性强",
                 "capacity": "有 480 亿市值的示例电新参与，机构资金进得来",
                 "ladder": "1板5 / 2板3 / 3板1，梯队连续无断层",
                 "vs_index": "板块 +4.62%，创业板 -1.28%，超额 5.9 个百分点，逆指数走强"},
             "verify_tomorrow": {
                 "watch": ["龙头示例科技竞价开盘价", "10:00 前板块内第二只涨停是否出现",
                           "示例电新（中军）是否跟涨"],
                 "continuation": "示例科技竞价不低开超 3%，且 10:00 前板块出现第二只涨停",
                 "failure": "示例科技低开破 5 日线 13.42 且 30 分钟内不收回，视为方向失败"},
             "evidence": [{"block": "sectors", "field": "涨跌幅", "value": 4.62, "period": as_of}]},

            {"role": "次主线", "name": "示例电力", "phase": "启动",
             "pct_chg": 2.15, "limit_up_count": 3, "net_inflow_yi": 11.8,
             "members": {"leader": m("999020.SH", "示例电投", 1, 10.0),
                         "core": m("999021.SH", "示例长电", None, 1.8),
                         "elastic": [], "front": [m("999022.SH", "示例皖能", 1, 10.0)], "back": []},
             "strength_basis": {
                 "linkage": "3 只涨停但涨幅>5% 仅 5 只，联动度一般",
                 "leadership": "龙头首板，尚无接力样本",
                 "capacity": "有超千亿市值的示例长电，容量充足",
                 "ladder": "全是首板，无梯队",
                 "vs_index": "板块 +2.15%，上证 +0.74%，超额 1.4 个点"},
             "verify_tomorrow": {
                 "watch": ["示例电投能否连板"],
                 "continuation": "示例电投连板且板块再出 2 只涨停",
                 "failure": "示例电投低开翻绿，视为一日游"}},

            {"role": "指数共振", "name": "示例金融", "phase": "回流",
             "pct_chg": 1.84, "limit_up_count": 0, "net_inflow_yi": 41.2,
             "members": {"leader": None, "core": m("999030.SH", "示例银行", None, 2.1),
                         "elastic": [], "front": [], "back": []},
             "strength_basis": {
                 "linkage": "普涨但无涨停，是资金避险回流而非题材行情",
                 "leadership": "无龙头，权重齐涨",
                 "capacity": "全是大市值",
                 "ladder": "无梯队",
                 "vs_index": "拉动上证约 0.4 个点，是今日指数上涨的主要来源"},
             "verify_tomorrow": {
                 "watch": ["主力净流入是否连续第 3 日为正"],
                 "continuation": "继续净流入且题材未起，说明资金仍在避险",
                 "failure": "净流出转负，说明资金回流题材"}},

            {"role": "逆指数抱团", "name": "示例固态电池", "phase": "发酵",
             "pct_chg": 4.62, "limit_up_count": 9, "net_inflow_yi": 23.4,
             "members": {"leader": m("999001.SZ", "示例科技", 3, 5.10), "core": None,
                         "elastic": [], "front": [], "back": []},
             "strength_basis": {
                 "vs_index": "创业板 -1.28% 而板块 +4.62%，是今日唯一有独立资金的方向"},
             "verify_tomorrow": {
                 "watch": ["与主线同一板块，验证条件同上"],
                 "continuation": "同今日主线",
                 "failure": "同今日主线"}},

            {"role": "退潮风险", "name": "示例算力", "phase": "退潮",
             "pct_chg": -5.31, "limit_up_count": 1, "net_inflow_yi": -38.6,
             "members": {"leader": m("999002.SH", "示例材料", None, -3.75, "昨日 4 板，今日断板"),
                         "core": None, "elastic": [],
                         "front": [m("999040.SZ", "示例光模块", None, -8.2)],
                         "back": [m("999041.SZ", "示例服务器", None, -10.0, "跌停")]},
             "strength_basis": {
                 "linkage": "板块内 6 只昨日涨停股今日全部低开，2 只跌停",
                 "leadership": "前龙头断板，无人接力",
                 "capacity": "容量票率先出货",
                 "ladder": "梯队断裂，昨日 4 板今日无 5 板",
                 "vs_index": "板块 -5.31%，创业板 -1.28%，跑输 4 个百分点"},
             "verify_tomorrow": {
                 "watch": ["前龙头示例材料能否止跌", "板块炸板率"],
                 "continuation": "（对退潮而言）继续下跌属正常演绎",
                 "failure": "若明日板块内出现 3 只以上涨停且龙头反包，则退潮判断被证伪"}},
        ],
        "confidence": "medium",
        "caveats": ["本文件为合成契约示例，全部板块与个股均为虚构",
                    "示例固态电池同时被标记为“今日主线”与“逆指数抱团”——"
                    "这是合理的：一个方向可以同时满足两个角色，报告中会合并说明"],
    }


def positions_review(run_id, as_of):
    return {
        "run_id": run_id, "as_of": as_of, "status": "ok", "blocked_reason": None,
        "cards": [
            {"code": "999001.SZ", "name": "示例科技", "sector": "示例固态电池", "module": "打板",
             "role_in_sector": "龙头", "cost": 12.80, "shares": 2000, "close": 14.62,
             "pnl_pct": 14.22, "weight_pct": 14.6,
             "relative_strength": {"vs_index": 4.36, "vs_sector": 0.48, "vs_leader": 0.0,
                                   "reading": "自身即龙头，相对大盘 +4.36pp、相对板块 +0.48pp，三项均为正"},
             "thesis": "题材启动第二天打板做龙头，看三日内能否走出高度",
             "thesis_still_valid": {"value": "成立",
                                    "reason": "已走到 3 板且全天封板未开，板块梯队完整、有中军跟随，"
                                              "原逻辑（走高度）正在兑现"},
             "scenarios": {
                 "strong": {"trigger": "竞价高开 3% 以上且开盘 10 分钟不破分时均价",
                            "action": "持有不动，不加仓（已是最大单票权重）"},
                 "medium": {"trigger": "竞价平开或小幅低开，盘中在 5 日线上方震荡",
                            "action": "持有，10:00 前若板块无第二只涨停则减半仓"},
                 "weak": {"trigger": "低开破 5 日线 13.42 且 30 分钟不收回",
                          "action": "全部退出，不等反弹"}},
             "levels": {"resistance": 16.08, "support": 13.42, "invalidation": 13.42,
                        "basis": "压力＝3 板后的理论涨停价；支撑与失效位取 5 日均线，与买入时设定一致"},
             "action": "持有", "action_reason": "逻辑成立 + 三项相对强弱为正 + 处于梯队最前排",
             "priority": "优先保留"},

            {"code": "999002.SH", "name": "示例材料", "sector": "示例算力", "module": "打板",
             "role_in_sector": "前排（原龙头，已断板）", "cost": 26.50, "shares": 800, "close": 24.18,
             "pnl_pct": -8.75, "weight_pct": 9.7,
             "relative_strength": {"vs_index": -4.49, "vs_sector": 1.56, "vs_leader": None,
                                   "reading": "相对大盘 -4.49pp；虽相对板块 +1.56pp，"
                                              "但那是因为整个板块在退潮，比烂不算强"},
             "thesis": "算力题材四板龙头，赌五板高度",
             "thesis_still_valid": {"value": "已失效",
                                    "reason": "昨日 4 板今日断板且收绿，板块整体退潮、梯队断裂，"
                                              "“赌高度”的前提已不存在"},
             "scenarios": {
                 "strong": {"trigger": "竞价高开 2% 以上且板块出现新涨停",
                            "action": "反弹至 25.02（5 日线）附近全部卖出，不留仓"},
                 "medium": {"trigger": "平开震荡", "action": "开盘 30 分钟内择机全部卖出"},
                 "weak": {"trigger": "低开 3% 以上", "action": "开盘直接卖出，不等反弹"}},
             "levels": {"resistance": 25.02, "support": 23.10, "invalidation": 24.00,
                        "basis": "压力＝5 日线；支撑＝20 日最低；失效位为买入时设定的 24.00，今日已跌破"},
             "action": "退出", "action_reason": "逻辑已失效且今日收盘 24.18 已逼近失效位 24.00，"
                                                "三种情景下的动作都是卖出，只是节奏不同",
             "priority": "优先处理"},
        ],
        "behavior_checks": [
            {"check": "卖强留弱", "triggered": False,
             "detail": "本次未发生卖出。当前组合中相对强度高的示例科技标为“优先保留”，"
                       "相对强度低的示例材料标为“优先处理”，方向正确",
             "involved_codes": []},
            {"check": "把缩量下跌解释成洗盘", "triggered": True,
             "detail": "示例材料今日 -3.75%、量比 0.74（缩量），且已跌破买入时设定的失效位 24.00。"
                       "板块同步退潮、梯队断裂，这不是洗盘，是没人接。"
                       "如果此刻还在用“缩量洗盘”解释，就是在替已失效的逻辑找台阶",
             "involved_codes": ["999002.SH"]},
            {"check": "亏损补仓", "triggered": False,
             "detail": "示例材料浮亏 -8.75%，持仓数量自 8 月 25 日买入后未变，无补仓记录",
             "involved_codes": []},
            {"check": "卖飞后追回", "triggered": False,
             "detail": "近 10 个交易日无同一代码的卖出后再买入记录",
             "involved_codes": []},
            {"check": "同一题材重复持仓", "triggered": False,
             "detail": "两只持仓分属示例固态电池与示例算力，题材不重叠。"
                       "但注意：示例固态电池单一题材权重已达 14.6%，本身已是集中度风险",
             "involved_codes": []},
            {"check": "板块回流时替弱票找理由", "triggered": True,
             "detail": "示例算力板块今日整体 -5.31%、资金净流出 38.6 亿，属板块级退潮。"
                       "此时若因“相对板块 +1.56pp”而认为示例材料抗跌、值得再拿一天——"
                       "那是在拿“比烂”当持有理由",
             "involved_codes": ["999002.SH"]},
            {"check": "短线失败后临时改成长线", "triggered": False,
             "detail": "positions.yaml 中示例材料的 module 仍为“打板”，本次复盘也按打板逻辑判定退出，"
                       "未出现改口为中长线持有的情况",
             "involved_codes": []},
        ],
        "risk": {
            "account_equity": 200000.0,
            "total_market_value": 48584.0,
            "total_position_pct": 24.3,
            "cash_pct": 75.7,
            "concentration": [
                {"scope": "999001.SZ", "kind": "single_stock", "weight_pct": 14.6, "over_limit": False},
                {"scope": "999002.SH", "kind": "single_stock", "weight_pct": 9.7, "over_limit": False},
                {"scope": "示例固态电池", "kind": "theme", "weight_pct": 14.6, "over_limit": False},
                {"scope": "示例算力", "kind": "theme", "weight_pct": 9.7, "over_limit": False},
            ],
            "per_trade_risk": [
                {"code": "999001.SZ", "invalidation": 13.42, "loss_at_invalidation": 2400.0,
                 "loss_pct_of_equity": 1.2, "over_half_percent": True},
                {"code": "999002.SH", "invalidation": 24.00, "loss_at_invalidation": 144.0,
                 "loss_pct_of_equity": 0.072, "over_half_percent": False},
            ],
            "max_daily_loss": 4000.0,
            "current_drawdown_today": -736.0,
            "stop_trading": {
                "value": True,
                "reason": "触发两条：① 情绪阶段为“分歧”，按纪律不新开仓；"
                          "② 行为自检触发 2 条（缩量下跌当洗盘、替弱票找理由），"
                          "距停手阈值 3 条尚差 1 条，但叠加①已足以停止新增。"
                          "另需注意：示例科技单笔风险 1.2% 已超 0.5% 上限，"
                          "属历史遗留仓位，处理方式是不加仓 + 上移失效位，而非立即砍",
            },
        },
        "confidence": "medium",
        "caveats": [
            "本文件为合成契约示例，全部持仓与数值为虚构",
            "示例科技单笔风险 1.2% 超出 0.5% 纪律线——这是刻意保留的示例，"
            "演示“已经超限的存量仓位该怎么处理”",
            "卖强留弱 / 亏损补仓 / 卖飞追回 三条自检依赖交易流水，"
            "当前仅有静态持仓，判定为近似结果",
        ],
    }


def news(run_id, as_of):
    return {
        "run_id": run_id, "as_of": as_of, "status": "ok", "blocked_reason": None,
        "items": [
            {"time": f"{as_of} 08:42", "title": "示例部委发布固态电池中试线建设指引",
             "source": "示例部委官网", "source_tier": "T1", "url": None, "category": "政策",
             "polarity": "利好", "certainty": "fact",
             "related_sectors": ["示例固态电池"], "related_codes": [],
             "impact": "属产业政策定调，落地节奏未定。短期影响预期而非业绩，"
                       "对应板块今日 +4.62% 已部分反映",
             "horizon": "数日"},
            {"time": f"{as_of} 11:20", "title": "示例科技公告：与示例车企签订固态电池样品供货协议",
             "source": "交易所公告", "source_tier": "T1", "url": None, "category": "公司",
             "polarity": "利好", "certainty": "fact",
             "related_sectors": ["示例固态电池"], "related_codes": ["999001.SZ"],
             "impact": "样品阶段，金额未披露，对当期业绩无实质影响；"
                       "但为龙头地位提供了公告层面的支撑",
             "horizon": "数日"},
            {"time": f"{as_of} 14:05", "title": "市场传闻示例算力龙头订单不及预期",
             "source": "示例财经社群", "source_tier": "T4", "url": None, "category": "产业",
             "polarity": "利空", "certainty": "rumor",
             "related_sectors": ["示例算力"], "related_codes": ["999002.SH"],
             "impact": "传闻，无任何官方来源。板块午后加速下跌与之时间吻合，"
                       "但不能据此认定因果——退潮在传闻出现前已经开始",
             "horizon": "不确定"},
            {"time": f"{as_of} 09:15", "title": "示例统计局公布 7 月工业增加值同比 +4.1%",
             "source": "示例统计局", "source_tier": "T1", "url": None, "category": "政策",
             "polarity": "中性", "certainty": "fact",
             "related_sectors": [], "related_codes": [],
             "impact": "与市场预期基本一致，未见明显交易反应",
             "horizon": "中期"},
            {"time": f"{as_of} 16:30", "title": "示例交易所向示例材料下发关注函",
             "source": "交易所公告", "source_tier": "T1", "url": None, "category": "公司",
             "polarity": "利空", "certainty": "fact",
             "related_sectors": ["示例算力"], "related_codes": ["999002.SH"],
             "impact": "盘后发布，要求说明股价异动原因。历史经验上关注函多导致次日低开，"
                       "需在明日竞价重点观察",
             "horizon": "当日"},
        ],
        "overseas_tech": {
            "summary": "隔夜示例海外科技指数 -1.2%，半导体板块领跌，"
                       "对次日国内算力/半导体开盘情绪偏负面",
            "direction": "negative"},
        "verification_log": [
            {"date": "2026-08-27", "title": "示例算力厂商宣布扩产",
             "expected": "利好，示例算力板块延续", "actual": "板块今日 -5.31%，龙头断板",
             "verdict": "证伪"},
            {"date": "2026-08-27", "title": "固态电池行业会议召开",
             "expected": "利好，关注示例固态电池", "actual": "板块今日 +4.62%，9 只涨停",
             "verdict": "兑现"},
        ],
        "confidence": "medium",
        "caveats": ["本文件为合成契约示例，全部新闻均为虚构",
                    "关注函为盘后信息，其影响需在次日价格中验证，本报告不预判方向"],
    }


def report(run_id, as_of):
    return {
        "run_id": run_id, "as_of": as_of, "mode": "close", "generated_at": NOW,
        "data_completeness": {
            "level": "partial", "missing": ["northbound（北向资金）"],
            "notice": "北向资金数据缺失，无法交叉验证权重拉升的资金来源；其余八章数据完整。"},
        "plan_tomorrow": {
            "scenarios": [
                {"index_case": "强", "trigger": "上证高开并站上 3450，创业板同步翻红",
                 "favored_sectors": ["示例固态电池", "示例电力"],
                 "holding_actions": [{"code": "999001.SZ", "action": "持有不动，不加仓"},
                                     {"code": "999002.SH", "action": "反弹至 25.02 附近全部卖出"}]},
                {"index_case": "中", "trigger": "上证在 3405—3450 区间震荡，创业板小幅波动",
                 "favored_sectors": ["示例固态电池"],
                 "holding_actions": [{"code": "999001.SZ", "action": "10:00 前板块无第二只涨停则减半仓"},
                                     {"code": "999002.SH", "action": "开盘 30 分钟内择机全部卖出"}]},
                {"index_case": "弱", "trigger": "上证低开破 3405，或创业板低开破 2126",
                 "favored_sectors": [],
                 "holding_actions": [{"code": "999001.SZ", "action": "破 13.42 且 30 分钟不收回则清仓"},
                                     {"code": "999002.SH", "action": "开盘直接卖出"}]},
            ],
            "position_cap": {"max_total_pct": 25, "new_open_pct": 0, "new_open_count": 0},
            "forbidden": ["禁止新开任何仓位（情绪处于分歧）",
                          "禁止对示例科技加仓（单笔风险已 1.2%，超 0.5% 线）",
                          "禁止对示例材料补仓或摊薄成本",
                          "禁止把示例材料改为中线持有"],
            "timeline": [
                {"window": "9:15—9:25 竞价观察",
                 "task": "看示例科技与示例材料的竞价开盘价，以及示例算力板块整体高开/低开比例",
                 "decision_rule": "若示例科技竞价低开超 3% → 直接进入弱情景脚本"},
                {"window": "开盘1—3分钟确认",
                 "task": "确认示例科技是否守住分时均价，示例材料是否如预期低开（关注函影响）",
                 "decision_rule": "若示例材料低开 3% 以上 → 立即卖出，不等反弹"},
                {"window": "9:30—10:00 核心执行窗口",
                 "task": "完成示例材料的清仓；观察示例固态电池板块是否出现第二只涨停",
                 "decision_rule": "若 10:00 仍无第二只涨停 → 示例科技减半仓。"
                                  "本窗口之后不再做任何卖出以外的操作"},
                {"window": "午后验证",
                 "task": "验证“示例固态电池仍是主线”这一判断",
                 "decision_rule": "若板块午后翻绿且龙头炸板 → 剩余仓位收盘前处理完"},
                {"window": "14:30 尾盘处理",
                 "task": "确认仓位符合明日上限 25%，确认示例材料已清空",
                 "decision_rule": "若仍持有示例材料 → 无条件市价卖出，不带入下一日"},
            ],
        },
        "panel": {
            "one_liner": "指数红、情绪凉：上证靠权重 +0.74%，创业板 -1.28%，"
                         "晋级率跌到 34.5%、炸板率升到 31.3%，短线进入分歧",
            "tomorrow_main": ["示例固态电池"],
            "tomorrow_risk": ["示例算力", "示例半导体"],
            "keep_first": ["示例科技 999001.SZ"],
            "handle_first": ["示例材料 999002.SH"],
            "actions": [
                {"code": "999001.SZ", "name": "示例科技", "action": "持有"},
                {"code": "999002.SH", "name": "示例材料", "action": "退出"},
            ],
            "signals": [
                "示例科技竞价开盘价：低开超 3% 即进入弱情景",
                "10:00 前示例固态电池板块是否出现第二只涨停",
                "示例材料受关注函影响的开盘表现（低开幅度）",
            ],
            "discipline": "今天不开新仓——情绪在分歧期，只做减法。",
        },
        "sections": {
            "overview": "**震荡，情绪进入分歧。**[market]\n\n"
                        "上证 3438.21（+0.74%）、深成 10902.6（+0.62%）、"
                        "创业板 2131.7（-1.28%）、科创50 1028.8（-1.44%）。\n\n"
                        "两市成交额 12560 亿，较昨日 +920 亿（+7.9%）——但增量集中在沪市权重，"
                        "创业板成交仅 +3.2%，**放量方向与题材方向不一致**。\n\n"
                        "涨跌家数 3104/1892，涨停 68 家、跌停 9 家。"
                        "炸板率 31.3%，连板晋级率 34.5%（昨日 55 只涨停仅 19 只续板），"
                        "最高 5 板但 4 板仅 3 只、5 板 1 只，**梯队上方明显变薄**。\n\n"
                        "→ 赚钱效应仍在但接力意愿下降，属典型分歧特征，尚未到退潮。[market]",
            "index_review": "**今天是震荡日，指数上涨完全由沪市权重贡献。**[market]\n\n"
                            "示例金融、示例电力合计拉动上证约 0.6 个点；"
                            "创业板与科创50 的下跌源于示例算力板块高位退潮。\n\n"
                            "日内四段：早盘 +0.52%（权重直拉）→ 上午 +0.11%（走平分化）"
                            "→ 午后 -0.08%（创业板加速下行、高位股批量炸板）"
                            "→ 尾盘 +0.19%（权重再拉但题材不跟）。\n\n"
                            "**尾盘护指数不护情绪**，是今天最值得注意的一段。\n\n"
                            "关键位：上证压力 3450（8/12 高点 + 整数关口），"
                            "支撑 3405（今日低点与 20 日线重合）；创业板支撑 2126。[market]",
            "sectors": "**主线：示例固态电池（发酵期）。**[sectors]\n\n"
                       "板块 +4.62%、9 只涨停、主力净流入 23.4 亿。"
                       "五维依据全部满足：涨幅>5% 的 17 只（联动）、"
                       "龙头封板后 30 分钟内 4 只跟风涨停（带动性）、"
                       "有 480 亿市值的中军参与（容量）、1板5/2板3/3板1 无断层（梯队）、"
                       "相对创业板超额 5.9pp（逆指数）。\n\n"
                       "它同时是今日的**逆指数抱团方向**——创业板 -1.28% 而它 +4.62%，"
                       "是全场唯一有独立资金的地方。\n\n"
                       "次主线示例电力（启动期）全是首板、无梯队，"
                       "需要明日示例电投连板来确认，否则是一日游。\n\n"
                       "**退潮方向：示例算力。**前龙头示例材料昨日 4 板今日断板，"
                       "板块 -5.31%、资金净流出 38.6 亿、6 只昨日涨停股全部低开、2 只跌停。[sectors]",
            "positions": "两只持仓，方向完全相反。[positions]\n\n"
                         "**示例科技（999001.SZ）**：主线龙头，3 板未开，"
                         "相对大盘 +4.36pp、相对板块 +0.48pp，买入逻辑（走高度）正在兑现。"
                         "→ **持有**，优先保留。\n\n"
                         "**示例材料（999002.SH）**：昨日 4 板今日断板收绿，"
                         "板块整体退潮、梯队断裂，"
                         "买入逻辑（赌五板高度）**已失效**，收盘 24.18 已逼近失效位 24.00。"
                         "→ **退出**，优先处理。\n\n"
                         "行为自检触发 2 条，见下节。[positions]",
            "plan": "见第五章结构化预案。核心是三句话：\n\n"
                    "1. 明日总仓位上限 25%，**新开仓额度为 0**（情绪在分歧期）\n"
                    "2. 9:30—10:00 是唯一执行窗口，之后只做卖出\n"
                    "3. 示例材料无论强中弱情景都要清掉，区别只在节奏[positions][sectors]",
            "news": "五条有效信息，两好一空两中性。[news]\n\n"
                    "**利好**：固态电池中试线建设指引（T1 政策，影响预期非业绩）；"
                    "示例科技样品供货协议（T1 公告，样品阶段无当期业绩影响，"
                    "但为龙头地位提供公告支撑）。\n\n"
                    "**利空**：示例材料收到交易所关注函（T1，盘后发布，"
                    "需在明日竞价重点观察）。另有一条算力订单传闻为 T4 级，"
                    "**标记为 rumor，不作为判断依据**——退潮在传闻出现前已经开始。\n\n"
                    "**昨日回验**：算力扩产消息 → **证伪**（板块今日 -5.31%）；"
                    "固态电池会议 → **兑现**（板块 +4.62%）。[news]",
            "risk": "总仓位 24.3%，现金 75.7%，账户 20 万。[positions]\n\n"
                    "**一处超限**：示例科技单笔风险 1.2%（跌到 13.42 亏 2400 元），"
                    "超出 0.5% 纪律线。这是历史遗留仓位——"
                    "处理方式是**不加仓 + 随股价上移失效位**，而不是立刻砍掉。\n\n"
                    "**结论：停止新增交易。**触发原因：① 情绪阶段为分歧；"
                    "② 行为自检触发 2 条。[positions]",
        },
        "provenance": {
            "data_source": "akshare", "adjust_mode": "qfq", "fetched_at": NOW,
            "quality_flags": [
                {"block": "northbound", "level": "info", "message": "北向资金接口无数据，本块为可选"},
                {"block": "index_intraday", "level": "info", "message": "分时接口首次超时，重试后成功"},
            ]},
        "disclaimer": DISCLAIMER,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="2026-08-28_example")
    ap.add_argument("--as-of", default="2026-08-28")
    args = ap.parse_args()

    import json

    d = REPO_ROOT / "workspace" / "runs" / args.run_id
    (d / "logs").mkdir(parents=True, exist_ok=True)
    ds = dataset(args.run_id, args.as_of)
    files = {
        "run_manifest.json": manifest(args.run_id, args.as_of),
        "dataset.json": ds,
        "market.json": market(args.run_id, args.as_of, ds),
        "sectors.json": sectors(args.run_id, args.as_of),
        "positions_review.json": positions_review(args.run_id, args.as_of),
        "news.json": news(args.run_id, args.as_of),
        "report.json": report(args.run_id, args.as_of),
    }
    for name, payload in files.items():
        (d / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    emit({"ok": True, "run_dir": f"workspace/runs/{args.run_id}", "files": sorted(files),
          "next": f"python tools/render_report.py --run-id {args.run_id}"})


if __name__ == "__main__":
    main()
