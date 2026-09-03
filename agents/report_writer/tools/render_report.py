#!/usr/bin/env python3
"""把 report.json 渲染成 report.md（存档）与 report.html（仪表盘）。

用法:
    python tools/render_report.py --run-id 2026-08-28_close

设计约定：
  - **纯标准库**，不依赖 jinja2 / echarts / plotly。产出是单文件 HTML，
    离线打开、发微信、存网盘都不会坏。
  - 渲染是确定性代码，不是模型手写 HTML。想改样式改这个文件，
    这样每天的报告长得一样，也能 diff。
  - 颜色遵循 A 股习惯：**红涨绿跌**（与欧美相反）。
  - 深浅色都可读：调色板按 prefers-color-scheme 与 [data-theme] 双轨定义。
"""
from __future__ import annotations

import argparse
import html
import json

from core.cli import emit, read_json, run_dir


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def num(v, digits: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return esc(v)


def signed(v, digits: int = 2, suffix: str = "%") -> str:
    if v is None:
        return "—"
    f = float(v)
    return f"{'+' if f > 0 else ''}{f:,.{digits}f}{suffix}"


def ts(v) -> str:
    """把 ISO 时间戳显示成人读的样子：2026-08-28T15:42:00+08:00 → 2026-08-28 15:42"""
    if not v:
        return "—"
    t = str(v).replace("T", " ")
    return t[:16]


def tone(v) -> str:
    """A 股配色：涨红、跌绿、平灰。"""
    if v is None:
        return "flat"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "flat"
    return "up" if f > 0 else ("down" if f < 0 else "flat")


PHASES = ["冰点", "修复", "主升", "分歧", "退潮"]
ROLE_ORDER = ["今日主线", "次主线", "指数共振", "逆指数抱团", "退潮风险"]
ACTION_CLASS = {"持有": "hold", "减仓": "cut", "退出": "exit",
                "禁止加仓": "cut", "确认后可加仓": "hold"}
PRIO_CLASS = {"优先保留": "keep", "继续观察": "watch", "优先处理": "handle"}

CSS = """
:root{
  color-scheme: light;
  --bg:#f6f6f4; --surface:#ffffff; --surface-2:#fbfbfa; --border:#e3e2dd;
  --ink:#14140f; --ink-2:#57564f; --ink-3:#8a887e;
  --up:#d33a35; --down:#12894f; --flat:#8a887e;
  --accent:#2a78d6; --warn:#8a5300; --warn-bg:#fdf3e2;
  --chip:#f0efeb;
  --shadow:0 1px 2px rgba(0,0,0,.05), 0 8px 24px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#111110; --surface:#1a1a19; --surface-2:#212120; --border:#302f2c;
    --ink:#f5f4ef; --ink-2:#b8b6ac; --ink-3:#87857c;
    --up:#e66767; --down:#2eaa6b; --flat:#87857c;
    --accent:#3987e5; --warn:#e0a44a; --warn-bg:#2a2114;
    --chip:#262624;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#111110; --surface:#1a1a19; --surface-2:#212120; --border:#302f2c;
  --ink:#f5f4ef; --ink-2:#b8b6ac; --ink-3:#87857c;
  --up:#e66767; --down:#2eaa6b; --flat:#87857c;
  --accent:#3987e5; --warn:#e0a44a; --warn-bg:#2a2114;
  --chip:#262624;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 72px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:17px;margin:38px 0 14px;display:flex;align-items:baseline;gap:10px}
h2 .no{font-size:12px;color:var(--ink-3);font-weight:600;letter-spacing:.08em}
h3{font-size:14px;margin:0 0 8px}
.sub{color:var(--ink-2);font-size:13px;margin:0 0 20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:18px;box-shadow:var(--shadow)}
.grid{display:grid;gap:12px}
.g4{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.g2{grid-template-columns:repeat(auto-fit,minmax(400px,1fr))}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}
.kpi .label{font-size:12px;color:var(--ink-2);margin-bottom:6px}
.kpi .value{font-size:26px;font-weight:640;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.kpi .delta{font-size:13px;font-variant-numeric:tabular-nums;margin-top:2px}
.kpi .foot{font-size:12px;color:var(--ink-3);margin-top:6px}
.banner{border:1px solid var(--warn);background:var(--warn-bg);color:var(--warn);
  border-radius:12px;padding:12px 16px;font-size:13px;margin:0 0 20px}
.panel{background:var(--surface);border:2px solid var(--accent);border-radius:16px;
  padding:22px;box-shadow:var(--shadow)}
.panel .one-liner{font-size:20px;font-weight:640;line-height:1.5;margin:0 0 16px;letter-spacing:-.01em}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--chip);border:1px solid var(--border);border-radius:999px;
  padding:3px 11px;font-size:12.5px;color:var(--ink-2)}
.chip.up{color:var(--up)} .chip.down{color:var(--down)}
.stepper{display:flex;gap:6px;margin:6px 0 2px}
.step{flex:1;text-align:center;font-size:12.5px;padding:8px 4px;border-radius:9px;
  background:var(--surface-2);border:1px solid var(--border);color:var(--ink-3)}
.step.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.bar-row{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:13px}
.bar-row .k{width:46px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.bar-row .b{height:16px;border-radius:4px;background:var(--up);min-width:3px}
.bar-row .v{color:var(--ink-2);font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{font-size:12px;color:var(--ink-3);font-weight:600;letter-spacing:.03em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;
  border:1px solid var(--border);background:var(--surface-2)}
.tag.hold{color:var(--accent);border-color:var(--accent)}
.tag.cut{color:var(--warn);border-color:var(--warn)}
.tag.exit{color:var(--up);border-color:var(--up)}
.pos{border-left:3px solid var(--border)}
.pos.keep{border-left-color:var(--down)}
.pos.watch{border-left-color:var(--accent)}
.pos.handle{border-left-color:var(--up)}
.kv{display:grid;grid-template-columns:88px 1fr;gap:4px 12px;font-size:13px;margin-top:10px}
.kv dt{color:var(--ink-3)} .kv dd{margin:0}
.chk{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);font-size:13.5px}
.chk .dot{flex:none;width:8px;height:8px;border-radius:50%;margin-top:7px;background:var(--down)}
.chk.hit .dot{background:var(--up)}
.chk.hit .name{color:var(--up);font-weight:600}
.chk .name{width:200px;flex:none}
.tl{position:relative;padding-left:20px}
.tl li{list-style:none;position:relative;padding:0 0 14px 0}
.tl li::before{content:"";position:absolute;left:-20px;top:7px;width:9px;height:9px;
  border-radius:50%;background:var(--accent)}
.tl li::after{content:"";position:absolute;left:-16px;top:16px;bottom:-4px;width:1px;background:var(--border)}
.tl li:last-child::after{display:none}
.tl .w{font-weight:600;font-size:13.5px}
.tl .t{font-size:13px;color:var(--ink-2)}
.muted{color:var(--ink-3);font-size:12.5px}
.news li{margin-bottom:7px;font-size:13.5px}
.foot{margin-top:48px;padding-top:18px;border-top:1px solid var(--border);
  font-size:12px;color:var(--ink-3);line-height:1.7}
.toggle{position:fixed;right:16px;top:16px;background:var(--surface);border:1px solid var(--border);
  border-radius:999px;padding:6px 14px;font-size:12px;color:var(--ink-2);cursor:pointer}
@media print{.toggle{display:none}}
@media (max-width:600px){.wrap{padding:18px 12px 48px}h1{font-size:21px}.chk .name{width:120px}}
"""


def _chips(items, cls: str = "") -> str:
    if not items:
        return "<span class='muted'>—</span>"
    return "".join(f"<span class='chip {cls}'>{esc(i)}</span>" for i in items)


def h_panel(p: dict) -> str:
    """章节八：最终执行面板。放在页面最上面——这是第二天早上唯一要看的东西。"""
    if not p:
        return "<div class='card muted'>执行面板缺失</div>"
    rows = "".join(
        f"<tr><td>{esc(a.get('name') or a.get('code'))}"
        f"<span class='muted'> {esc(a.get('code'))}</span></td>"
        f"<td><span class='tag {ACTION_CLASS.get(a.get('action'), '')}'>{esc(a.get('action'))}</span></td></tr>"
        for a in p.get("actions", [])
    ) or "<tr><td class='muted'>无持仓</td><td></td></tr>"
    sig = "".join(f"<li>{esc(s)}</li>" for s in p.get("signals", []))
    return (
        "<div class='panel'>"
        "<div class='muted'>今日定性</div>"
        f"<p class='one-liner'>{esc(p.get('one_liner'))}</p>"
        "<div class='grid g2'>"
        f"<div><h3>明日主线</h3><div class='chips'>{_chips(p.get('tomorrow_main'), 'up')}</div></div>"
        f"<div><h3>明日风险</h3><div class='chips'>{_chips(p.get('tomorrow_risk'), 'down')}</div></div>"
        f"<div><h3>优先保留</h3><div class='chips'>{_chips(p.get('keep_first'))}</div></div>"
        f"<div><h3>优先处理</h3><div class='chips'>{_chips(p.get('handle_first'))}</div></div>"
        "</div>"
        "<h3 style='margin-top:18px'>每只持仓唯一动作</h3>"
        f"<table><tbody>{rows}</tbody></table>"
        "<div class='grid g2' style='margin-top:16px'>"
        f"<div><h3>明天三个关键信号</h3><ol style='margin:0;padding-left:18px;font-size:13.5px'>{sig}</ol></div>"
        f"<div><h3>明天唯一纪律</h3><p style='margin:0;font-size:15px;font-weight:600'>{esc(p.get('discipline'))}</p></div>"
        "</div></div>"
    )


def h_ladder(ladder) -> str:
    if not ladder:
        return ""
    try:
        items = sorted(ladder.items(), key=lambda kv: int(str(kv[0]).replace("板", "")))
    except ValueError:
        items = list(ladder.items())
    mx = max([v for _, v in items] or [1])
    rows = "".join(
        f"<div class='bar-row'><span class='k'>{esc(k)}</span>"
        f"<span class='b' style='width:{max(3, int(v / mx * 170))}px'></span>"
        f"<span class='v'>{v}</span></div>"
        for k, v in items
    )
    return f"<h3 style='margin-top:16px'>连板梯队</h3>{rows}"


def h_overview(ov) -> str:
    """章节一：市场总览。"""
    if not ov:
        return "<div class='card muted'>章节一数据缺失</div>"
    kpis = []
    for i in ov.get("indexes", []):
        t = tone(i.get("pct_chg"))
        kpis.append(
            f"<div class='card kpi'><div class='label'>{esc(i.get('name'))}</div>"
            f"<div class='value {t}'>{num(i.get('close'), 2)}</div>"
            f"<div class='delta {t}'>{signed(i.get('pct_chg'))}</div>"
            f"<div class='foot'>开 {num(i.get('open'))} · 高 {num(i.get('high'))} · 低 {num(i.get('low'))}</div></div>"
        )
    tv = ov.get("turnover") or {}
    br = ov.get("breadth") or {}
    kpis.append(
        "<div class='card kpi'><div class='label'>两市成交额</div>"
        f"<div class='value'>{num(tv.get('total_yi'), 0)}<span class='muted' style='font-size:14px'> 亿</span></div>"
        f"<div class='delta {tone(tv.get('chg_yi'))}'>{signed(tv.get('chg_yi'), 0, ' 亿')} · {signed(tv.get('chg_pct'))}</div>"
        f"<div class='foot'>{esc(tv.get('reading'))}</div></div>"
    )
    kpis.append(
        "<div class='card kpi'><div class='label'>涨 / 跌 家数</div>"
        f"<div class='value'><span class='up'>{num(br.get('up'), 0)}</span>"
        f"<span class='muted' style='font-size:18px'> / </span>"
        f"<span class='down'>{num(br.get('down'), 0)}</span></div>"
        f"<div class='foot'>涨停 {num(br.get('limit_up'), 0)} · 跌停 {num(br.get('limit_down'), 0)}</div></div>"
    )
    kpis.append(
        "<div class='card kpi'><div class='label'>炸板率 / 晋级率</div>"
        f"<div class='value'>{num(br.get('broken_board_rate'), 1, '%')}"
        f"<span class='muted' style='font-size:18px'> / </span>{num(br.get('promotion_rate'), 1, '%')}</div>"
        f"<div class='foot'>最高板 {num(br.get('highest_board'), 0)} 板</div></div>"
    )

    ep = ov.get("emotion_phase") or {}
    steps = "".join(f"<div class='step{' on' if p == ep.get('value') else ''}'>{p}</div>" for p in PHASES)
    st = ov.get("market_state") or {}
    st_cls = "up" if st.get("value") == "强势" else ("down" if st.get("value") == "弱势" else "")
    return (
        f"<div class='grid g4'>{''.join(kpis)}</div>"
        "<div class='card' style='margin-top:12px'><div class='grid g2'>"
        f"<div><h3>情绪阶段</h3><div class='stepper'>{steps}</div>"
        f"<p class='muted' style='margin:8px 0 0'>{esc(ep.get('basis'))}</p></div>"
        f"<div><h3>大盘状态 · <span class='{st_cls}'>{esc(st.get('value'))}</span></h3>"
        f"<p class='muted' style='margin:8px 0 0'>{esc(st.get('basis'))}</p>"
        f"{h_ladder(br.get('ladder'))}</div>"
        "</div></div>"
    )


def h_index_review(ir) -> str:
    """章节二：指数复盘。"""
    if not ir:
        return "<div class='card muted'>章节二数据缺失</div>"
    seg = "".join(
        f"<li><div class='w'>{esc(s.get('session'))} "
        f"<span class='{tone(s.get('pct_chg_in_session'))}'>{signed(s.get('pct_chg_in_session'))}</span></div>"
        f"<div class='t'>{esc(s.get('narrative'))}"
        + (f"<br><span class='muted'>带动：{esc(s.get('driver'))}</span>" if s.get("driver") else "")
        + "</div></li>"
        for s in ir.get("sessions", [])
    )
    lv = "".join(
        f"<tr><td>{esc(k.get('index'))}</td>"
        f"<td>{'压力' if k.get('type') == 'resistance' else '支撑'}</td>"
        f"<td class='n'>{num(k.get('level'))}</td><td class='muted'>{esc(k.get('basis'))}</td></tr>"
        for k in ir.get("key_levels", [])
    )
    dt = ir.get("day_type") or {}
    return (
        "<div class='card'>"
        f"<p style='margin:0 0 14px'><b>{esc(dt.get('value'))}</b> — {esc(ir.get('why'))}</p>"
        "<div class='grid g2'>"
        "<div><h3>日内四段</h3><ul class='tl' style='margin:0;padding-left:20px'>"
        + (seg or "<li class='muted'>分时数据缺失，无法拆解</li>")
        + "</ul></div><div><h3>板块与指数的关系</h3><div style='font-size:13.5px'>"
        f"<div style='margin-bottom:6px'>正向共振<div class='chips'>{_chips(ir.get('resonant_sectors'), 'up')}</div></div>"
        f"<div style='margin-bottom:6px'>逆指数走强<div class='chips'>{_chips(ir.get('independent_sectors'), 'up')}</div></div>"
        f"<div>拖累权重<div class='chips'>{_chips(ir.get('drag_sectors'), 'down')}</div></div></div>"
        "<h3 style='margin-top:16px'>关键位置</h3><table><tbody>"
        + (lv or "<tr><td class='muted'>—</td></tr>")
        + "</tbody></table></div></div></div>"
    )


def _member_chips(m: dict) -> str:
    out = []
    for label, key in [("龙头", "leader"), ("中军", "core")]:
        v = m.get(key)
        if v:
            b = f" {v['boards']}板" if v.get("boards") else ""
            out.append(f"<span class='chip up'>{label} {esc(v.get('name'))}{b}</span>")
    for label, key in [("弹性", "elastic"), ("前排", "front"), ("后排", "back")]:
        for v in (m.get(key) or [])[:4]:
            out.append(f"<span class='chip'>{label} {esc(v.get('name'))}</span>")
    return "".join(out) or "<span class='muted'>—</span>"


def h_sectors(directions) -> str:
    """章节三：板块与题材。"""
    if not directions:
        return "<div class='card muted'>章节三数据缺失</div>"
    order = {r: i for i, r in enumerate(ROLE_ORDER)}
    cards = []
    for d in sorted(directions, key=lambda x: order.get(x.get("role"), 99)):
        sb = d.get("strength_basis") or {}
        vt = d.get("verify_tomorrow") or {}
        basis = "".join(
            f"<dt>{k}</dt><dd>{esc(v)}</dd>"
            for k, v in [("联动", sb.get("linkage")), ("带动性", sb.get("leadership")),
                         ("容量票", sb.get("capacity")), ("梯队", sb.get("ladder")),
                         ("相对指数", sb.get("vs_index"))] if v
        )
        extra = ""
        if d.get("limit_up_count") is not None:
            extra += f"<span class='chip'>涨停 {d['limit_up_count']} 只</span>"
        if d.get("net_inflow_yi") is not None:
            extra += (f"<span class='chip {tone(d.get('net_inflow_yi'))}'>"
                      f"主力 {signed(d.get('net_inflow_yi'), 1, ' 亿')}</span>")
        watch = "".join(f"<li>{esc(w)}</li>" for w in (vt.get("watch") or []))
        cards.append(
            "<div class='card'>"
            "<div style='display:flex;justify-content:space-between;align-items:baseline;gap:8px'>"
            f"<h3 style='margin:0'>{esc(d.get('name'))}</h3>"
            f"<span class='chip'>{esc(d.get('role'))}</span></div>"
            f"<div class='chips' style='margin:8px 0 4px'><span class='chip'>阶段：{esc(d.get('phase'))}</span>"
            f"<span class='chip {tone(d.get('pct_chg'))}'>{signed(d.get('pct_chg'))}</span>{extra}</div>"
            "<div class='muted' style='margin-top:8px'>梯队</div>"
            f"<div class='chips'>{_member_chips(d.get('members') or {})}</div>"
            f"<dl class='kv'>{basis}</dl>"
            + (f"<div class='muted' style='margin-top:10px'>明日验证</div>"
               f"<ul style='margin:4px 0 0;padding-left:18px;font-size:13px'>{watch}</ul>" if watch else "")
            + "<div class='kv' style='margin-top:8px'>"
            f"<dt>延续</dt><dd class='up'>{esc(vt.get('continuation'))}</dd>"
            f"<dt>失败</dt><dd class='down'>{esc(vt.get('failure'))}</dd></div></div>"
        )
    return f"<div class='grid g2'>{''.join(cards)}</div>"


def h_positions(cards) -> str:
    """章节四：持仓卡片。"""
    if not cards:
        return "<div class='card muted'>无持仓，或持仓数据缺失</div>"
    out = []
    for c in cards:
        rs = c.get("relative_strength") or {}
        lv = c.get("levels") or {}
        sc = c.get("scenarios") or {}
        tv = c.get("thesis_still_valid") or {}
        out.append(
            f"<div class='card pos {PRIO_CLASS.get(c.get('priority'), '')}'>"
            "<div style='display:flex;justify-content:space-between;align-items:baseline;gap:8px'>"
            f"<h3 style='margin:0'>{esc(c.get('name'))} <span class='muted'>{esc(c.get('code'))}</span></h3>"
            f"<span class='tag {ACTION_CLASS.get(c.get('action'), '')}'>{esc(c.get('action'))}</span></div>"
            "<div class='chips' style='margin:8px 0'>"
            f"<span class='chip'>{esc(c.get('sector'))}</span>"
            f"<span class='chip'>{esc(c.get('module'))}</span>"
            f"<span class='chip'>地位 {esc(c.get('role_in_sector'))}</span>"
            f"<span class='chip'>{esc(c.get('priority'))}</span></div>"
            "<div class='grid g4' style='gap:8px'>"
            f"<div><div class='muted'>现价</div><div style='font-weight:600'>{num(c.get('close'))}</div></div>"
            f"<div><div class='muted'>盈亏</div><div class='{tone(c.get('pnl_pct'))}' style='font-weight:600'>{signed(c.get('pnl_pct'))}</div></div>"
            f"<div><div class='muted'>仓位</div><div style='font-weight:600'>{num(c.get('weight_pct'), 1, '%')}</div></div>"
            f"<div><div class='muted'>失效位</div><div style='font-weight:600'>{num(lv.get('invalidation'))}</div></div>"
            "</div><dl class='kv'>"
            f"<dt>相对强弱</dt><dd>大盘 <span class='{tone(rs.get('vs_index'))}'>{signed(rs.get('vs_index'), 2, 'pp')}</span>"
            f" · 板块 <span class='{tone(rs.get('vs_sector'))}'>{signed(rs.get('vs_sector'), 2, 'pp')}</span>"
            f" · 核心 <span class='{tone(rs.get('vs_leader'))}'>{signed(rs.get('vs_leader'), 2, 'pp')}</span></dd>"
            f"<dt>买入逻辑</dt><dd>{esc(c.get('thesis'))}</dd>"
            f"<dt>是否成立</dt><dd><b>{esc(tv.get('value'))}</b> — {esc(tv.get('reason'))}</dd>"
            f"<dt>压力/支撑</dt><dd>{num(lv.get('resistance'))} / {num(lv.get('support'))} "
            f"<span class='muted'>{esc(lv.get('basis'))}</span></dd>"
            f"<dt>明日·强</dt><dd>{esc((sc.get('strong') or {}).get('trigger'))} → {esc((sc.get('strong') or {}).get('action'))}</dd>"
            f"<dt>明日·中</dt><dd>{esc((sc.get('medium') or {}).get('trigger'))} → {esc((sc.get('medium') or {}).get('action'))}</dd>"
            f"<dt>明日·弱</dt><dd>{esc((sc.get('weak') or {}).get('trigger'))} → {esc((sc.get('weak') or {}).get('action'))}</dd>"
            f"<dt>动作理由</dt><dd>{esc(c.get('action_reason'))}</dd></dl></div>"
        )
    return f"<div class='grid g2'>{''.join(out)}</div>"


def h_checks(checks) -> str:
    """章节四的七条行为自检。触发的用红点标出。"""
    if not checks:
        return ""
    rows = "".join(
        f"<div class='chk{' hit' if c.get('triggered') else ''}'>"
        f"<span class='dot'></span><span class='name'>{esc(c.get('check'))}"
        + ("&nbsp;⚠" if c.get("triggered") else "")
        + f"</span><span>{esc(c.get('detail'))}</span></div>"
        for c in checks
    )
    hit = sum(1 for c in checks if c.get("triggered"))
    return f"<div class='card'><h3>行为自检 · 触发 {hit}/{len(checks)} 条</h3>{rows}</div>"


def h_risk(risk) -> str:
    """章节七：风险与纪律。"""
    if not risk:
        return "<div class='card muted'>章节七数据缺失</div>"
    pt = "".join(
        f"<tr><td>{esc(r.get('code'))}</td><td class='n'>{num(r.get('invalidation'))}</td>"
        f"<td class='n'>{num(r.get('loss_at_invalidation'), 0)}</td>"
        f"<td class='n'>{num(r.get('loss_pct_of_equity'), 3, '%')}</td>"
        + ("<td><span class='up'>超限</span></td>" if r.get("over_half_percent")
           else "<td><span class='down'>合规</span></td>")
        + "</tr>"
        for r in risk.get("per_trade_risk", [])
    )
    conc = "".join(
        f"<span class='chip {'up' if c.get('over_limit') else ''}'>"
        f"{esc(c.get('scope'))} {num(c.get('weight_pct'), 1, '%')}</span>"
        for c in risk.get("concentration", [])
    )
    st = risk.get("stop_trading") or {}
    return (
        "<div class='card'><div class='grid g4'>"
        f"<div class='kpi'><div class='label'>总仓位</div><div class='value'>{num(risk.get('total_position_pct'), 1, '%')}</div></div>"
        f"<div class='kpi'><div class='label'>现金</div><div class='value'>{num(risk.get('cash_pct'), 1, '%')}</div></div>"
        f"<div class='kpi'><div class='label'>当日最大允许亏损</div><div class='value'>{num(risk.get('max_daily_loss'), 0)}</div></div>"
        f"<div class='kpi'><div class='label'>是否停止新增交易</div>"
        f"<div class='value {'up' if st.get('value') else 'down'}'>{'停手' if st.get('value') else '可交易'}</div>"
        f"<div class='foot'>{esc(st.get('reason'))}</div></div></div>"
        f"<h3 style='margin-top:16px'>集中度（单票 + 同题材）</h3><div class='chips'>{conc or '—'}</div>"
        "<h3 style='margin-top:16px'>单笔风险（跌到失效位）</h3>"
        "<table><thead><tr><th>代码</th><th class='n'>失效位</th><th class='n'>亏损额</th>"
        "<th class='n'>占账户</th><th>0.5% 线</th></tr></thead><tbody>"
        + (pt or "<tr><td class='muted'>—</td></tr>")
        + "</tbody></table></div>"
    )


def h_plan(plan) -> str:
    """章节五：明日预案。"""
    if not plan:
        return "<div class='card muted'>章节五数据缺失</div>"
    sc = "".join(
        f"<div class='card'><h3>指数 · {esc(s.get('index_case'))}</h3>"
        f"<p class='muted' style='margin:0 0 8px'>{esc(s.get('trigger'))}</p>"
        f"<div class='chips'>{_chips(s.get('favored_sectors'))}</div><dl class='kv'>"
        + "".join(f"<dt>{esc(a.get('code'))}</dt><dd>{esc(a.get('action'))}</dd>"
                  for a in s.get("holding_actions", []))
        + "</dl></div>"
        for s in plan.get("scenarios", [])
    )
    cap = plan.get("position_cap") or {}
    tl = "".join(
        f"<li><div class='w'>{esc(t.get('window'))}</div><div class='t'>{esc(t.get('task'))}"
        + (f"<br><span class='muted'>规则：{esc(t.get('decision_rule'))}</span>" if t.get("decision_rule") else "")
        + "</div></li>"
        for t in plan.get("timeline", [])
    )
    return (
        f"<div class='grid g3'>{sc}</div>"
        "<div class='card' style='margin-top:12px'><div class='grid g3'>"
        f"<div class='kpi'><div class='label'>明日总仓位上限</div><div class='value'>{num(cap.get('max_total_pct'), 0, '%')}</div></div>"
        f"<div class='kpi'><div class='label'>允许新开仓位</div><div class='value'>{num(cap.get('new_open_pct'), 0, '%')}</div></div>"
        f"<div class='kpi'><div class='label'>允许新开数量</div><div class='value'>{num(cap.get('new_open_count'), 0, ' 只')}</div></div>"
        "</div><h3 style='margin-top:16px'>明确禁止</h3>"
        f"<div class='chips'>{_chips(plan.get('forbidden'), 'down')}</div>"
        f"<h3 style='margin-top:18px'>时间轴</h3><ul class='tl' style='margin:0;padding-left:20px'>{tl}</ul></div>"
    )


def h_news(news) -> str:
    """章节六：新闻与公告，三分类 + 次日验证。"""
    if not news:
        return "<div class='card muted'>章节六数据缺失</div>"
    items = news.get("items", [])
    cols = []
    for pol, cls in [("利好", "up"), ("中性", ""), ("利空", "down")]:
        sub = [i for i in items if i.get("polarity") == pol]
        lis = "".join(
            f"<li><span class='chip {cls}'>{esc(i.get('source_tier'))}</span> "
            f"<b>{esc(i.get('title'))}</b>"
            f"<div class='muted'>{esc(i.get('time'))} · {esc(i.get('source'))}"
            + (f" · {esc('/'.join(i.get('related_sectors') or []))}" if i.get("related_sectors") else "")
            + (f" · <i>{esc(i.get('certainty'))}</i>" if i.get("certainty") else "")
            + f"</div><div class='muted'>{esc(i.get('impact'))}</div></li>"
            for i in sub
        )
        cols.append(
            f"<div class='card'><h3 class='{cls}'>{pol} · {len(sub)}</h3>"
            f"<ul class='news' style='margin:0;padding-left:16px'>{lis or '<li class=muted>—</li>'}</ul></div>"
        )
    ver = "".join(
        f"<tr><td>{esc(v.get('date'))}</td><td>{esc(v.get('title'))}</td>"
        f"<td>{esc(v.get('expected'))}</td><td>{esc(v.get('actual'))}</td>"
        f"<td><b>{esc(v.get('verdict'))}</b></td></tr>"
        for v in news.get("verification_log", [])
    )
    vblock = ""
    if ver:
        vblock = ("<div class='card' style='margin-top:12px'><h3>昨日新闻的次日验证</h3>"
                  "<table><thead><tr><th>日期</th><th>事件</th><th>预期</th><th>实际</th><th>结论</th></tr></thead>"
                  f"<tbody>{ver}</tbody></table></div>")
    ot = news.get("overseas_tech") or {}
    oblock = ""
    if ot:
        oblock = (f"<div class='card' style='margin-top:12px'><h3>外围科技 · "
                  f"<span class='{ {'positive': 'up', 'negative': 'down'}.get(ot.get('direction'), '') }'>"
                  f"{esc(ot.get('direction'))}</span></h3>"
                  f"<p style='margin:0;font-size:13.5px'>{esc(ot.get('summary'))}</p></div>")
    return f"<div class='grid g3'>{''.join(cols)}</div>{oblock}{vblock}"


def render_html(rep: dict, extra: dict) -> str:
    dc = rep.get("data_completeness") or {}
    banner = ""
    if dc.get("level") != "complete":
        banner = ("<div class='banner'><b>数据缺口</b> · 缺失："
                  f"{esc('、'.join(dc.get('missing') or []) or '—')}　{esc(dc.get('notice'))}</div>")
    market = extra.get("market") or {}
    sectors = extra.get("sectors") or {}
    pr = extra.get("positions_review") or {}
    news = extra.get("news") or {}
    prov = rep.get("provenance") or {}

    body = (
        "<div class='wrap'>"
        f"<h1>A 股每日复盘 · {esc(rep.get('as_of'))}</h1>"
        f"<p class='sub'>运行模式 {esc(rep.get('mode'))} · run_id {esc(rep.get('run_id'))}"
        f" · 生成于 {esc(ts(rep.get('generated_at')))}</p>"
        f"{banner}"
        "<h2><span class='no'>08</span>最终执行面板</h2>" + h_panel(rep.get("panel")) +
        "<h2><span class='no'>01</span>市场总览</h2>" + h_overview(market.get("overview")) +
        "<h2><span class='no'>02</span>指数复盘</h2>" + h_index_review(market.get("index_review")) +
        "<h2><span class='no'>03</span>板块与题材</h2>" + h_sectors(sectors.get("directions")) +
        "<h2><span class='no'>04</span>我的持仓计划</h2>" + h_positions(pr.get("cards")) +
        "<div style='margin-top:12px'>" + h_checks(pr.get("behavior_checks")) + "</div>" +
        "<h2><span class='no'>05</span>明日预案</h2>" + h_plan(rep.get("plan_tomorrow")) +
        "<h2><span class='no'>06</span>新闻与公告</h2>" + h_news(news) +
        "<h2><span class='no'>07</span>风险与纪律</h2>" + h_risk(pr.get("risk")) +
        "<div class='foot'>"
        f"<div>数据源 {esc(prov.get('data_source'))} · 复权 {esc(prov.get('adjust_mode'))}"
        f" · 取数时间 {esc(ts(prov.get('fetched_at')))}</div>"
        f"<div style='margin-top:8px'>{esc(rep.get('disclaimer'))}</div></div></div>"
        "<div class='toggle' onclick=\"var r=document.documentElement;"
        "r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'\">切换深浅色</div>"
    )
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>A股复盘 {esc(rep.get("as_of"))}</title><style>{CSS}</style></head>'
            f'<body>{body}</body></html>')


def render_md(rep: dict, extra: dict) -> str:
    """Markdown 版本：用于存档与 git diff，内容与 HTML 同源。"""
    dc = rep.get("data_completeness") or {}
    p = rep.get("panel") or {}
    sec = rep.get("sections") or {}
    L = [
        f"# A 股每日复盘 · {rep.get('as_of')}",
        "",
        f"- 运行模式：{rep.get('mode')}　run_id：{rep.get('run_id')}　生成时间：{ts(rep.get('generated_at'))}",
        f"- 数据完整性：**{dc.get('level')}**"
        + (f"　缺失：{'、'.join(dc.get('missing') or [])}" if dc.get("missing") else ""),
    ]
    if dc.get("level") != "complete":
        L += ["", f"> ⚠️ **数据缺口**：{dc.get('notice')}"]
    L += ["", "## 八、最终执行面板", "",
          f"**今日定性**：{p.get('one_liner')}", "",
          f"- 明日主线：{'、'.join(p.get('tomorrow_main') or []) or '—'}",
          f"- 明日风险：{'、'.join(p.get('tomorrow_risk') or []) or '—'}",
          f"- 优先保留：{'、'.join(p.get('keep_first') or []) or '—'}",
          f"- 优先处理：{'、'.join(p.get('handle_first') or []) or '—'}",
          "", "| 持仓 | 唯一动作 |", "|---|---|"]
    for a in p.get("actions", []):
        L.append(f"| {a.get('name')}（{a.get('code')}） | {a.get('action')} |")
    L += ["", "**明天三个关键信号**", ""]
    L += [f"{i}. {s}" for i, s in enumerate(p.get("signals", []), 1)]
    L += ["", f"**明天唯一纪律**：{p.get('discipline')}", ""]

    for no, title, key in [("一", "市场总览", "overview"), ("二", "指数复盘", "index_review"),
                           ("三", "板块与题材", "sectors"), ("四", "我的持仓计划", "positions"),
                           ("五", "明日预案", "plan"), ("六", "新闻与公告", "news"),
                           ("七", "风险与纪律", "risk")]:
        L += [f"## {no}、{title}", "", sec.get(key) or "_（本章正文由 report-writer 填写）_", ""]

    prov = rep.get("provenance") or {}
    L += ["## 九、运行说明", "",
          f"- 数据源：{prov.get('data_source')}　复权口径：{prov.get('adjust_mode')}"
          f"　取数时间：{ts(prov.get('fetched_at'))}",
          "", "---", "", rep.get("disclaimer", "")]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    d = run_dir(args.run_id)
    rep = read_json(d / "report.json")
    extra = {}
    for name in ("market", "sectors", "positions_review", "news"):
        f = d / f"{name}.json"
        if f.is_file():
            extra[name] = json.loads(f.read_text(encoding="utf-8"))

    (d / "report.md").write_text(render_md(rep, extra), encoding="utf-8")
    (d / "report.html").write_text(render_html(rep, extra), encoding="utf-8")
    emit({"ok": True, "md": "report.md", "html": "report.html", "sources_used": sorted(extra)})


if __name__ == "__main__":
    main()
