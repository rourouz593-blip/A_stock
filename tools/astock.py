#!/usr/bin/env python3
"""astock —— 本仓库的统一入口。任何 coding agent 只需要记住这一个命令。

    python tools/astock.py doctor                 # 环境自检：能不能跑
    python tools/astock.py review                 # 开始今日复盘（建 run + 取数）
    python tools/astock.py next                   # 我现在该做什么？（最重要）
    python tools/astock.py done <agent>           # 我做完了，校验并推进
    python tools/astock.py status                 # 进度到哪了
    python tools/astock.py demo                   # 离线示例，不联网

## 为什么要有这个文件

一个 coding agent 第一次进入本仓库时，面对 7 个 agent、6 个工具、9 个章节，
很容易不知道从哪下手，或者跑到一半忘了下一步是什么。

`astock next` 解决的就是这个问题：它读 `run_manifest.json` 的状态，
再读对应 `agents/*.md` 的 frontmatter，**把"下一步该做什么"渲染成一段可执行的指令**——
包括读哪些文件、写哪个文件、按哪份 schema、加载哪些技能、怎么自检。

于是任何 agent 的工作方式都退化成一个死循环：

    next → 干活 → done → next → 干活 → done → …

> 教学要点：这是 harness 设计里最容易被忽略的一层——**状态机**。
> Agent 的"记性"是不可靠的，所以不要让它记流程；
> 把流程放进文件，让它每一步都来问"我现在在哪、下一步是什么"。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _common import REPO_ROOT, SCHEMAS, WORKSPACE

MODE_STEPS = {
    "close":     ["data-engineer", "market-analyst", "sector-analyst", "news-analyst",
                  "position-advisor", "report-writer"],
    "premarket": ["data-engineer", "news-analyst", "position-advisor", "report-writer"],
    "positions": ["data-engineer", "position-advisor", "report-writer"],
    "weekly":    ["data-engineer", "market-analyst", "sector-analyst",
                  "position-advisor", "report-writer"],
}

# 这两步是确定性代码，不需要模型思考，由 astock 自动执行
AUTOMATED = {"data-engineer"}

ARTIFACT_OF = {
    "data-engineer": "dataset",
    "market-analyst": "market",
    "sector-analyst": "sectors",
    "news-analyst": "news",
    "position-advisor": "positions_review",
    "report-writer": "report",
}

EXAMPLE_RUN = "2026-08-28_example"
C_OK, C_NO, C_DIM, C_B, C_END = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def _color(s: str, c: str) -> str:
    return s if os.getenv("NO_COLOR") else f"{c}{s}{C_END}"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def die(msg: str, hint: str = "") -> "NoReturn":  # type: ignore[valid-type]
    say(_color(f"✗ {msg}", C_NO))
    if hint:
        say(f"  → {hint}")
    sys.exit(1)


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def agent_meta(name: str) -> dict:
    """从 agents/<name>.md 的 frontmatter 读元信息。

    **单一事实来源**：reads / writes / schema / skills 只在那份文件里定义，
    这里只是读出来渲染，不重复定义。
    """
    import yaml

    p = REPO_ROOT / "agents" / f"{name}.md"
    if not p.is_file():
        die(f"找不到 agent 定义 {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])


# ── run 定位 ────────────────────────────────────────────────────
def latest_run() -> str | None:
    runs = WORKSPACE / "runs"
    if not runs.is_dir():
        return None
    cands = [d.name for d in runs.iterdir()
             if d.is_dir() and (d / "run_manifest.json").is_file() and d.name != EXAMPLE_RUN]
    return sorted(cands)[-1] if cands else None


def resolve_run(run_id: str | None) -> tuple[str, Path, dict]:
    rid = run_id or latest_run()
    if not rid:
        die("找不到任何 run", "先跑 python tools/astock.py review")
    d = WORKSPACE / "runs" / rid
    if not (d / "run_manifest.json").is_file():
        die(f"{rid} 没有 run_manifest.json", "先跑 python tools/astock.py review")
    return rid, d, read_json(d / "run_manifest.json")


def default_as_of() -> tuple[str, str]:
    """默认分析日：收盘后(15:30)算今天，否则算上一个工作日；周末回退到周五。

    ⚠️ 这只是**粗略**推断。真正的交易日校验在 scripts/fetch/calendar.py 里，
    用的是交易日历——遇到节假日 build_dataset 会报 error 并停下，不会硬跑。
    """
    now = datetime.now()
    d = now.date() if now.hour * 60 + now.minute >= 15 * 60 + 30 else (now - timedelta(days=1)).date()
    note = ""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
        note = "（当前是周末，已回退到最近的工作日）"
    return d.isoformat(), note


# ── doctor ─────────────────────────────────────────────────────
def cmd_doctor(args) -> None:
    say(_color("astock doctor —— 环境自检", C_B))
    say()
    ok = True

    def check(label: str, passed: bool, detail: str = "", fix: str = "", fatal: bool = True) -> None:
        nonlocal ok
        mark = _color("✓", C_OK) if passed else (_color("✗", C_NO) if fatal else _color("!", C_DIM))
        say(f" {mark} {label:<26} {detail}")
        if not passed:
            if fix:
                say(f"   {_color('→ ' + fix, C_DIM)}")
            if fatal:
                ok = False

    v = sys.version_info
    check("Python >= 3.10", v >= (3, 10), f"当前 {v.major}.{v.minor}.{v.micro}")

    for mod, fatal, fix in [("akshare", True, "pip install -r requirements.txt"),
                            ("pandas", True, "pip install -r requirements.txt"),
                            ("yaml", True, "pip install pyyaml"),
                            ("jsonschema", True, "pip install jsonschema"),
                            ("pytest", False, "pip install pytest（只影响跑测试）")]:
        try:
            __import__(mod)
            check(f"依赖 {mod}", True)
        except ImportError:
            check(f"依赖 {mod}", False, "未安装", fix, fatal)

    check("config/positions.yaml", (REPO_ROOT / "config" / "positions.yaml").is_file(),
          fix="cp config/positions.example.yaml config/positions.yaml 并填入持仓",
          detail="缺了章节④⑦会为空", fatal=False)
    check("config/thresholds.yaml", (REPO_ROOT / "config" / "thresholds.yaml").is_file(),
          fix="cp config/thresholds.example.yaml config/thresholds.yaml",
          detail="缺了会回退到 example 的空阈值", fatal=False)
    env_file = REPO_ROOT / ".env"
    check(".env", env_file.is_file(),
          detail="已加载" if env_file.is_file() else "不存在（可选，但章节⑦要用）",
          fix="cp .env.example .env", fatal=False)
    eq = os.getenv("ASTOCK_ACCOUNT_EQUITY")
    check("ASTOCK_ACCOUNT_EQUITY", bool(eq),
          detail=f"{float(eq):,.0f} 元" if eq else "未设置 → 章节⑦只能给比例、给不出金额",
          fix="在 .env 里填账户总资产（本项目会自动读 .env，不用 source）", fatal=False)

    # 网络：只有真正连得上 AKShare 才能跑真实复盘
    net_ok, net_detail = False, ""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import akshare as ak  # noqa: F401
        from scripts.ak_client import call

        df = call("tool_trade_date_hist_sina", cache=False)
        net_ok, net_detail = True, f"交易日历 {len(df)} 条"
    except Exception as e:
        net_detail = f"{type(e).__name__}: {str(e)[:70]}"
    check("AKShare 网络连通", net_ok, net_detail,
          "检查代理/防火墙；连不上就只能跑 astock demo（离线示例）", fatal=False)

    say()
    if ok and net_ok:
        as_of, note = default_as_of()
        say(_color(f"✓ 一切就绪。下一步：python tools/astock.py review   （将分析 {as_of}{note}）", C_OK))
    elif ok:
        say(_color("! 依赖齐全但连不上 AKShare。可以跑离线示例：python tools/astock.py demo", C_DIM))
    else:
        say(_color("✗ 有必需项未通过，先按上面的提示修复", C_NO))
        sys.exit(1)


# ── review：开工 ────────────────────────────────────────────────
def cmd_review(args) -> None:
    as_of, note = (args.as_of, "") if args.as_of else default_as_of()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", as_of):
        die(f"日期格式不合法: {as_of}", "用 YYYY-MM-DD")

    run_id = f"{as_of}_{args.mode}"
    d = WORKSPACE / "runs" / run_id
    if d.is_dir() and not args.force:
        say(_color(f"! {run_id} 已存在，直接续跑（要重来加 --force）", C_DIM))
    else:
        (d / "logs").mkdir(parents=True, exist_ok=True)
        write_json(d / "run_manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": as_of, "mode": args.mode, "trading_day": None, "status": "running",
            "steps": [{"agent": a, "status": "pending", "artifact": None, "note": None}
                      for a in MODE_STEPS[args.mode]],
            "notes": [f"由 astock review 创建{note}"] if note else [],
        })
        say(_color(f"✓ 建好 run: {run_id}", C_OK) + (f"  {note}" if note else ""))

    if not args.no_fetch:
        say(_color("→ 取数中（AKShare，视网络约 1-3 分钟）…", C_DIM))
        r = subprocess.run(
            [sys.executable, "-m", "scripts.build_dataset", "--run-id", run_id,
             "--as-of", as_of, "--mode", args.mode] + (["--no-cache"] if args.no_cache else []),
            cwd=REPO_ROOT)
        if r.returncode != 0:
            _mark(run_id, "data-engineer", "failed", note="build_dataset 失败")
            die("取数失败", "看上面的报错。连不上网就先跑 python tools/astock.py demo")
        _finish_step(run_id, "data-engineer")

    say()
    cmd_next(argparse.Namespace(run_id=run_id, json=False))


# ── next：我现在该做什么 ────────────────────────────────────────
def _pending_step(manifest: dict) -> dict | None:
    for s in manifest["steps"]:
        if s["status"] in ("pending", "running", "failed"):
            return s
    return None


def cmd_next(args) -> None:
    run_id, d, man = resolve_run(args.run_id)
    step = _pending_step(man)

    if step is None:
        rep = d / "report.html"
        payload = {"run_id": run_id, "done": True,
                   "report_md": str((d / "report.md").relative_to(REPO_ROOT)),
                   "report_html": str(rep.relative_to(REPO_ROOT)) if rep.is_file() else None}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        say(_color(f"✓ {run_id} 全部完成", C_OK))
        say(f"  报告：{payload['report_md']}")
        if payload["report_html"]:
            say(f"  仪表盘：{payload['report_html']}   （浏览器直接打开）")
        return

    name = step["agent"]
    meta = agent_meta(name)
    artifact = ARTIFACT_OF[name]
    reads = [r.replace("{run_id}", run_id) for r in meta.get("reads", [])]
    writes = [w.replace("{run_id}", run_id) for w in meta.get("writes", [])]
    skills = [f"skills/{s}/SKILL.md" for s in (meta.get("skills") or [])]
    example = f"workspace/runs/{EXAMPLE_RUN}/{artifact}.json"

    if args.json:
        print(json.dumps({
            "run_id": run_id, "as_of": man["as_of"], "mode": man["mode"], "done": False,
            "next_agent": name, "display_name": meta.get("display_name"),
            "definition": f"agents/{name}.md", "reads": reads, "writes": writes,
            "schema": meta.get("schema"), "skills": skills, "example": example,
            "automated": name in AUTOMATED,
            "finish_command": f"python tools/astock.py done {name} --run-id {run_id}",
        }, ensure_ascii=False, indent=2))
        return

    idx = [s["agent"] for s in man["steps"]].index(name) + 1
    total = len(man["steps"])
    say(_color(f"┌─ 第 {idx}/{total} 步 · {name}（{meta.get('display_name')}）", C_B))
    say(f"│  run {run_id} · 分析日 {man['as_of']} · 模式 {man['mode']}")
    say("│")

    if name in AUTOMATED:
        say("│  这一步是确定性代码，不需要你思考，直接跑：")
        say(_color(f"│    python tools/astock.py review --as-of {man['as_of']} "
                   f"--mode {man['mode']}", C_B))
        say("└─")
        return

    say(f"│  {_color('①  先读角色定义', C_B)}")
    say(f"│     agents/{name}.md   ← 职责、工作步骤、边界与禁止事项都在里面")
    say("│")
    say(f"│  {_color('②  加载技能（方法论在这里，不要自己发明判断标准）', C_B)}")
    for s in skills or ["（无）"]:
        say(f"│     {s}")
    say("│")
    say(f"│  {_color('③  只读这些输入（多一个都不许读）', C_B)}")
    for r in reads:
        p = REPO_ROOT / r
        mark = _color("✓", C_OK) if p.exists() else _color("✗ 缺失", C_NO)
        say(f"│     {mark} {r}")
    say("│")
    say(f"│  {_color('④  只写这个产物', C_B)}")
    for w in writes:
        say(f"│     {w}")
    say(f"│     结构见 {meta.get('schema')}")
    say(f"│     照着抄 {example}（虚构示例，字段齐全）")
    say("│")
    say(f"│  {_color('⑤  写完自检并推进', C_B)}")
    say(_color(f"│     python tools/astock.py done {name} --run-id {run_id}", C_B))
    say("│")
    say(f"│  {_color('纪律', C_B)}：数据缺了就写 blocked + 原因，不许编；")
    say("│        每条结论都要能追溯到 dataset.json 的具体字段。")
    say("└─")


# ── done：校验并推进 ────────────────────────────────────────────
_KEEP = object()   # note 的哨兵：不传就保留原值，传 None 就清空（重试成功后要清掉旧报错）


def _mark(run_id: str, agent: str, status: str, note=_KEEP,
          artifact: str | None = None) -> dict:
    d = WORKSPACE / "runs" / run_id
    man = read_json(d / "run_manifest.json")
    for s in man["steps"]:
        if s["agent"] == agent:
            s["status"] = status
            if note is not _KEEP:
                s["note"] = note
            if artifact:
                s["artifact"] = artifact
    states = [s["status"] for s in man["steps"]]
    man["status"] = ("completed" if all(x == "ok" for x in states)
                     else "failed" if "failed" in states
                     else "partial" if "blocked" in states and "pending" not in states
                     else "running")
    write_json(d / "run_manifest.json", man)
    return man


def _validate(run_id: str, artifact: str) -> tuple[bool, list[str]]:
    from _common import build_validator

    d = WORKSPACE / "runs" / run_id
    f = d / f"{artifact}.json"
    if not f.is_file():
        return False, [f"产物不存在：workspace/runs/{run_id}/{artifact}.json"]
    schema_file = {"dataset": "dataset", "market": "market", "sectors": "sectors",
                   "news": "news", "positions_review": "positions_review",
                   "report": "report", "run_manifest": "run_manifest"}[artifact]
    validator = build_validator(read_json(SCHEMAS / f"{schema_file}.schema.json"))
    errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(read_json(f)), key=lambda e: list(e.path))]
    return not errs, errs


def _finish_step(run_id: str, agent: str) -> bool:
    """校验某一步的产物；通过则标 ok（或 blocked），不通过则标 failed 并打印错误。"""
    artifact = ARTIFACT_OF[agent]
    valid, errs = _validate(run_id, artifact)
    if not valid:
        _mark(run_id, agent, "failed", note=errs[0][:200])
        say(_color(f"✗ {agent} 的产物没通过 {artifact}.schema.json：", C_NO))
        for e in errs[:8]:
            say(f"    {e}")
        if len(errs) > 8:
            say(f"    …… 还有 {len(errs) - 8} 条")
        say()
        say(f"  → 对照 workspace/runs/{EXAMPLE_RUN}/{artifact}.json 改完，再跑一次本命令")
        return False

    doc = read_json(WORKSPACE / "runs" / run_id / f"{artifact}.json")
    blocked = doc.get("status") == "blocked" or (
        artifact == "dataset" and any(f["level"] == "error" for f in doc.get("quality_flags", [])))
    _mark(run_id, agent, "blocked" if blocked else "ok",
          note=doc.get("blocked_reason"), artifact=f"{artifact}.json")
    say(_color(f"✓ {agent} → {artifact}.json 校验通过"
               + ("（状态 blocked，已如实记录）" if blocked else ""), C_OK))
    return True


def cmd_done(args) -> None:
    run_id, d, man = resolve_run(args.run_id)
    agent = args.agent
    if agent not in ARTIFACT_OF:
        die(f"未知的 agent: {agent}", f"可选：{', '.join(ARTIFACT_OF)}")
    if agent not in [s["agent"] for s in man["steps"]]:
        die(f"{man['mode']} 模式不包含 {agent}",
            f"本模式的步骤：{' → '.join(s['agent'] for s in man['steps'])}")

    if not _finish_step(run_id, agent):
        sys.exit(1)

    # report-writer 完成后自动渲染，省掉一步人肉操作
    if agent == "report-writer":
        say(_color("→ 渲染报告…", C_DIM))
        r = subprocess.run([sys.executable, "tools/render_report.py", "--run-id", run_id],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            die("渲染失败", r.stderr[-500:])
        say(_color("✓ report.md / report.html 已生成", C_OK))
        _append_memory(run_id)

    say()
    cmd_next(argparse.Namespace(run_id=run_id, json=False))


def _append_memory(run_id: str) -> None:
    """把这次运行的摘要写进 memory/runs/ 并在 MEMORY.md 加一行索引。

    news-analyst 明天做"昨日新闻次日验证"时要读它——
    记忆层不是摆设，是下一次运行的输入。
    """
    d = WORKSPACE / "runs" / run_id
    try:
        man = read_json(d / "run_manifest.json")
        rep = read_json(d / "report.json")
        panel = rep.get("panel", {})
        summary = {
            "run_id": run_id, "as_of": man["as_of"], "mode": man["mode"],
            "status": man["status"],
            "one_liner": panel.get("one_liner"),
            "tomorrow_main": panel.get("tomorrow_main"),
            "tomorrow_risk": panel.get("tomorrow_risk"),
            "actions": {a["code"]: a["action"] for a in panel.get("actions", [])},
            "discipline": panel.get("discipline"),
            "data_gaps": (rep.get("data_completeness") or {}).get("missing", []),
        }
        mem = REPO_ROOT / "memory" / "runs" / f"{run_id}.json"
        write_json(mem, summary)
        idx = REPO_ROOT / "memory" / "MEMORY.md"
        line = (f"- {run_id} | {summary['as_of']} | {(summary['one_liner'] or '')[:40]} "
                f"| [记录](runs/{run_id}.json)\n")
        text = idx.read_text(encoding="utf-8")
        if f"runs/{run_id}.json" not in text:
            idx.write_text(text.rstrip("\n") + "\n" + line, encoding="utf-8")
        say(_color(f"✓ 已写入记忆 memory/runs/{run_id}.json", C_OK))
    except Exception as e:
        say(_color(f"! 记忆写入失败（不影响报告）: {e}", C_DIM))


# ── status ─────────────────────────────────────────────────────
ICON = {"ok": _color("●", C_OK), "blocked": _color("◐", C_DIM), "failed": _color("✗", C_NO),
        "pending": "○", "running": "◌", "skipped": _color("－", C_DIM)}


def cmd_status(args) -> None:
    run_id, d, man = resolve_run(args.run_id)
    say(_color(f"{run_id}", C_B) + f"  ·  分析日 {man['as_of']}  ·  模式 {man['mode']}"
        f"  ·  总状态 {man['status']}")
    say()
    for s in man["steps"]:
        note = f"  {_color(s['note'][:60], C_DIM)}" if s.get("note") else ""
        say(f"  {ICON.get(s['status'], '?')} {s['agent']:<20}{s['status']:<9}{note}")
    say()
    for n in man.get("notes", []):
        say(_color(f"  · {n}", C_DIM))
    nxt = _pending_step(man)
    say()
    say("下一步：" + (_color(f"python tools/astock.py next --run-id {run_id}", C_B)
                    if nxt else _color("已全部完成", C_OK)))


def cmd_demo(args) -> None:
    for cmd in (["tools/make_demo_run.py"], ["tools/render_report.py", "--run-id", EXAMPLE_RUN]):
        r = subprocess.run([sys.executable] + cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            die("示例生成失败", r.stderr[-400:])
    say(_color("✓ 离线示例已生成（全部为虚构数据，不联网）", C_OK))
    say(f"  报告：workspace/runs/{EXAMPLE_RUN}/report.md")
    say(f"  仪表盘：workspace/runs/{EXAMPLE_RUN}/report.html   ← 浏览器打开看效果")
    say()
    say("这份示例刻意保留了：一块数据缺失、两条行为自检被触发、一笔风险超限，")
    say("用来演示系统在不完美情况下如何诚实降级。")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="astock", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="环境自检：依赖、配置、网络")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("review", help="开始复盘：建 run + 取数 + 告诉你下一步")
    r.add_argument("--as-of", help="分析日 YYYY-MM-DD，默认自动推断")
    r.add_argument("--mode", default="close", choices=sorted(MODE_STEPS))
    r.add_argument("--no-fetch", action="store_true", help="只建 run 不取数")
    r.add_argument("--no-cache", action="store_true", help="忽略缓存强制重取")
    r.add_argument("--force", action="store_true", help="已存在时重建")
    r.set_defaults(func=cmd_review)

    n = sub.add_parser("next", help="我现在该做什么（最常用）")
    n.add_argument("--run-id", help="默认取最近一个 run")
    n.add_argument("--json", action="store_true", help="机器可读输出")
    n.set_defaults(func=cmd_next)

    o = sub.add_parser("done", help="我做完了：校验产物并推进到下一步")
    o.add_argument("agent", help=f"可选：{', '.join(ARTIFACT_OF)}")
    o.add_argument("--run-id")
    o.set_defaults(func=cmd_done)

    s = sub.add_parser("status", help="进度到哪了")
    s.add_argument("--run-id")
    s.set_defaults(func=cmd_status)

    m = sub.add_parser("demo", help="生成离线示例（不联网）")
    m.set_defaults(func=cmd_demo)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
