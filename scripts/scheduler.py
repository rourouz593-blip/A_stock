"""调度层：让系统自己决定"该不该跑、跑哪种模式"。

## 定位

在此之前，`astock run` 还是要人去敲一下。这一层把"什么时候跑"也变成系统自己的事，
于是 coding agent 的角色从**执行者**退成**监工**：
它不再一步步做分析，只需要在出问题时介入。

## 为什么不直接写一行 cron

因为 cron 只会"到点就跑"，而这件事需要判断：

- 今天是不是交易日？（周末、节假日不该出复盘）
- 今天这个模式是不是已经跑过了？（笔记本合盖睡过头，14:00 醒来该补跑）
- 上次失败了，现在该重试还是该停？

所以真正的设计是：**cron / launchd 每隔十分钟叫醒一次，由本模块判断该不该动手。**
`astock daemon --once` 就是这个"被叫醒之后想一想"的入口，它是幂等的——
一天之内叫醒多少次，该跑的也只跑一次。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE = REPO_ROOT / "workspace" / "schedule_state.json"
LOG_DIR = REPO_ROOT / "workspace" / "logs"

# 默认时刻表。config/pipeline.yaml 的 modes.<mode>.suggested_time 可以覆盖
DEFAULT_SCHEDULE = {
    "close": {"at": "15:40", "days": "trading", "desc": "收盘复盘"},
    "premarket": {"at": "08:45", "days": "trading", "desc": "盘前更新"},
    "weekly": {"at": "10:00", "days": "sat", "desc": "周复盘"},
}


@dataclass
class Decision:
    should_run: bool
    mode: str | None = None
    as_of: str | None = None
    reason: str = ""

    def __str__(self) -> str:
        head = f"跑 {self.mode}（{self.as_of}）" if self.should_run else "不跑"
        return f"{head}：{self.reason}"


def load_state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"runs": {}}      # {"2026-08-28_close": {"status":..., "at":...}}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_schedule(cfg: dict | None = None) -> dict:
    """从 config/pipeline.yaml 读时刻表，缺的用默认值补。"""
    import yaml

    if cfg is None:
        p = REPO_ROOT / "config" / "pipeline.yaml"
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else {}
    out = {k: dict(v) for k, v in DEFAULT_SCHEDULE.items()}
    for mode, spec in (cfg.get("modes") or {}).items():
        if mode in out and spec.get("suggested_time"):
            t = str(spec["suggested_time"])
            if ":" in t and t[0].isdigit():
                out[mode]["at"] = t
    for mode, spec in (cfg.get("schedule") or {}).items():   # 显式覆盖优先
        out.setdefault(mode, {}).update(spec)
    return {m: v for m, v in out.items() if v.get("enabled", True)}


def is_trading_day(day: date, calendar: list[str] | None = None) -> bool | None:
    """今天是不是交易日。拿不到日历就返回 None——**不猜**。

    周末可以确定不是；工作日是否为节假日必须查日历，
    猜错的代价是产出一份没有数据支撑的"复盘"。
    """
    if day.weekday() >= 5:
        return False
    if calendar is None:
        return None
    return day.isoformat() in set(calendar)


def _recent_calendar() -> list[str] | None:
    """从最近一次 run 的 dataset 里取交易日历，避免为了判断而多打一次网络。"""
    runs = sorted((REPO_ROOT / "workspace" / "runs").glob("*/dataset.json"), reverse=True)
    for f in runs[:5]:
        try:
            cal = (json.loads(f.read_text(encoding="utf-8"))
                   .get("blocks", {}).get("calendar", {}).get("inline") or {})
            if cal.get("recent_20"):
                return cal["recent_20"]
        except Exception:
            continue
    return None


def decide(now: datetime | None = None, *, schedule: dict | None = None,
           state: dict | None = None, calendar: list[str] | None = None,
           grace_minutes: int = 240) -> Decision:
    """被叫醒之后想一想：现在该跑什么。

    grace_minutes：过了预定时刻多久之内还允许补跑。
    默认 4 小时——笔记本合盖到晚上七点才打开，收盘复盘照样补上。
    """
    now = now or datetime.now()
    schedule = schedule if schedule is not None else load_schedule()
    state = state if state is not None else load_state()
    today = now.date()

    for mode, spec in sorted(schedule.items(), key=lambda kv: kv[1].get("at", "23:59")):
        days = spec.get("days", "trading")
        if days == "sat" and today.weekday() != 5:
            continue
        if days == "trading":
            td = is_trading_day(today, calendar)
            if td is False:
                continue
            if td is None and today.weekday() < 5:
                pass      # 日历不可用：工作日就先按交易日试，取数阶段会自己把关

        hh, mm = (int(x) for x in str(spec["at"]).split(":")[:2])
        due = datetime.combine(today, time(hh, mm))
        if now < due:
            continue
        if now - due > timedelta(minutes=grace_minutes):
            continue      # 过期太久就不补了，免得半夜跑出一份没人看的报告

        as_of = _as_of_for(mode, today, calendar)
        key = f"{as_of}_{mode}"
        prev = (state.get("runs") or {}).get(key)
        if prev and prev.get("status") in ("completed", "partial"):
            continue
        if prev and prev.get("attempts", 0) >= int(spec.get("max_attempts", 3)):
            continue      # 连续失败就不再空转，交给 supervise 报给人看

        late = int((now - due).total_seconds() // 60)
        return Decision(True, mode, as_of,
                        f"{spec.get('desc', mode)} 预定 {spec['at']}，现在 {now:%H:%M}"
                        + (f"（迟了 {late} 分钟，补跑）" if late > 5 else ""))

    return Decision(False, reason=f"{now:%Y-%m-%d %H:%M} 没有到期且未完成的任务")


def _as_of_for(mode: str, today: date, calendar: list[str] | None) -> str:
    """盘前模式分析的是**上一个交易日**，其余分析当天。"""
    if mode != "premarket":
        return today.isoformat()
    if calendar:
        past = sorted([d for d in calendar if d < today.isoformat()], reverse=True)
        if past:
            return past[0]
    d = today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def record(key: str, status: str, detail: str = "") -> dict:
    st = load_state()
    runs = st.setdefault("runs", {})
    entry = runs.setdefault(key, {"attempts": 0})
    entry["attempts"] = entry.get("attempts", 0) + 1
    entry["status"] = status
    entry["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if detail:
        entry["detail"] = detail[:300]
    save_state(st)
    return st


def log_path(day: date | None = None) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{(day or date.today()).isoformat()}.log"


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    with log_path().open("a", encoding="utf-8") as f:
        f.write(line + "\n")
