#!/usr/bin/env python3
"""astock —— 本仓库的统一入口。任何 coding agent 只需要记住这一个命令。

    python tools/astock.py doctor                 # 环境自检：能不能跑
    python tools/astock.py demo                   # 离线示例，不联网

    # ① harness 模式：你在 coding agent 里，一步步走。不花 API 钱
    python tools/astock.py review                 # 建 run + 取数
    python tools/astock.py next                   # 我现在该做什么？
    python tools/astock.py done <agent>           # 我做完了，校验并推进

    # ② api 模式：一条命令跑完，无人值守。用 config/models.yaml 里配的模型
    python tools/astock.py run                    # 取数 + 五步分析 + 渲染报告

    python tools/astock.py status                 # 进度到哪了

## 为什么要有这个文件

一个 coding agent 第一次进入本仓库时，面对 7 个 agent、6 个工具、9 个章节，
很容易不知道从哪下手，或者跑到一半忘了下一步是什么。

`astock next` 解决的就是这个问题：它读 `run_manifest.json` 的状态，
    再读对应 agent package 的 frontmatter，**把"下一步该做什么"渲染成一段可执行的指令**——
包括读哪些文件、写哪个文件、按哪份 schema、加载哪些技能、怎么自检。

于是任何 agent 的工作方式都退化成一个死循环：

    next → 干活 → done → next → 干活 → done → …

状态机是 harness-neutral：流程状态在文件中，不依赖任何模型的会话记忆。
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

from core.cli import REPO_ROOT, SCHEMAS, WORKSPACE  # noqa: F401
from agents.orchestrator.scripts.pipeline import artifact_map, automated_agents, mode_steps

MODE_STEPS = mode_steps()

# 这两步是确定性代码，不需要模型思考，由 astock 自动执行
AUTOMATED = automated_agents()

ARTIFACT_OF = artifact_map()

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
    """从可发现 agent package 的 AGENT.md frontmatter 读元信息。

    **单一事实来源**：reads / writes / schema / skills 只在那份文件里定义，
    这里只是读出来渲染，不重复定义。
    """
    from core.agent_registry import agent_file, read_meta

    try:
        p = agent_file(name)
        meta = read_meta(p)
        meta["_path"] = p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)
        return meta
    except (FileNotFoundError, ValueError) as e:
        die(str(e))


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

    ⚠️ 这只是**粗略**推断。真正的交易日校验由 data_engineer 的 calendar fetcher 完成，
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
MIN_PY = (3, 9)        # 硬性下限：低于此跑不起来
NICE_PY = (3, 11)      # 推荐版本：3.9 已 EOL，能跑但建议升


def _python_fix() -> str:
    """给出**当前这台机器上**最短的修复路径。

    常见情况：用 macOS 自带的 python3.9 建了 .venv。
    这时候光装新 Python 没用——venv 是照着旧解释器建的，必须重建。
    """
    in_venv = sys.prefix != sys.base_prefix
    steps = []
    if sys.platform == "darwin":
        steps.append("装新 Python：  brew install python@3.12   "
                     "（没有 brew 就去 python.org 下安装包）")
    else:
        steps.append("装新 Python：  用系统包管理器安装 python3.12")
    if in_venv:
        steps.append("重建虚拟环境：rm -rf .venv && python3.12 -m venv .venv && "
                     "source .venv/bin/activate")
        steps.append("重装依赖：    pip install -r requirements.txt")
    else:
        steps.append("建虚拟环境：  python3.12 -m venv .venv && source .venv/bin/activate")
        steps.append("装依赖：      pip install -r requirements.txt")
    return "\n     ".join(steps)


def cmd_doctor(args) -> None:
    say(_color("astock doctor —— 环境自检", C_B))
    say()
    ok = True
    fails: list[tuple[str, str]] = []

    def check(label: str, passed: bool, detail: str = "", fix: str = "", fatal: bool = True) -> None:
        nonlocal ok
        mark = _color("✓", C_OK) if passed else (_color("✗", C_NO) if fatal else _color("!", C_DIM))
        say(f" {mark} {label:<26} {detail}")
        if not passed:
            if fix:
                say(f"   {_color('→ ' + fix, C_DIM)}")
            if fatal:
                ok = False
                fails.append((label, fix))

    v = sys.version_info
    cur = f"{v.major}.{v.minor}.{v.micro}"
    if v < MIN_PY:
        check(f"Python >= {MIN_PY[0]}.{MIN_PY[1]}", False, f"当前 {cur}，太旧了跑不起来",
              _python_fix())
    elif v < NICE_PY:
        eol = "（3.9 已停止维护）" if v[:2] == (3, 9) else ""
        check("Python 版本", True, f"当前 {cur} —— 能跑{eol}，建议有空升到 3.11+")
        say(f"   {_color('→ 不急，先跑起来看产出；要升的话：', C_DIM)}")
        for line in _python_fix().split("\n     "):
            say(f"     {_color(line, C_DIM)}")
    else:
        check("Python 版本", True, f"当前 {cur}")

    for mod, fatal, fix in [("akshare", True, "pip install -r requirements.txt"),
                            ("baostock", True, "pip install -r requirements.txt"),
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

    # 执行方式：模型配置是可选的 —— 没有它也能用 next/done 模式跑
    try:
        from agents.orchestrator.scripts.llm import load_models_config

        mcfg = load_models_config()
        has_yaml = (REPO_ROOT / "config" / "models.yaml").is_file()
        tiers = mcfg.get("tiers") or {}
        provs = mcfg.get("providers") or {}
        ready = []
        for tier, key in tiers.items():
            raw = provs.get(key) or {}
            env = raw.get("api_key_env")
            if not env or os.getenv(env):
                ready.append(f"{tier}→{key}")
        if has_yaml and ready:
            check("模型配置（api 模式）", True, "、".join(ready))
        elif has_yaml:
            need = sorted({(provs.get(k) or {}).get("api_key_env")
                           for k in tiers.values() if (provs.get(k) or {}).get("api_key_env")})
            check("模型配置（api 模式）", False,
                  f"models.yaml 在，但缺 API key：{'、'.join(filter(None, need))}",
                  "在 .env 里填上对应的 key；或者用 astock next/done 让编码 agent 跑（不花 API 钱）",
                  fatal=False)
        else:
            check("模型配置（api 模式）", False, "未配置 → 只能用 next/done 模式",
                  "想无人值守跑：cp config/models.yaml.example config/models.yaml",
                  fatal=False)
    except Exception as e:
        check("模型配置（api 模式）", False, f"读取失败：{str(e)[:60]}", fatal=False)

    # 代理：这是最常见的"昨天还好好的今天连不上"的原因
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from agents.data_engineer.scripts.ak_client import explain, proxy_summary
    except Exception:
        explain, proxy_summary = (lambda e: str(e)), (lambda: "")
    px = proxy_summary()
    import urllib.request as _u

    sys_px = sorted({v for k, v in _u.getproxies().items()
                     if k in ("http", "https", "all") and v})
    if px or sys_px:
        check("代理设置", True, f"环境变量 {px or '无'}　系统 {len(sys_px)} 项")
        say(f"   {_color('→ 东财、新浪都是境内站点，走代理反而更容易失败', C_DIM)}")
        if sys_px:
            say(f"   {_color('⚠ macOS 上「系统代理」是独立的一套：', C_DIM)}")
            say(f"   {_color('  系统设置 → 网络 → Wi-Fi → 详细信息 → 代理 →「网页代理」「SOCKS 代理」', C_DIM)}")
            say(f"   {_color('  关掉 VPN 客户端不会清掉它，端口失效后所有请求都会卡在这里', C_DIM)}")
    else:
        check("代理设置", True, "未设置代理，直连")

    # 熔断：被限流的域名会进冷却期，这是"今天怎么什么都取不到"的常见原因
    try:
        from agents.data_engineer.scripts.ak_client import cooling_hosts

        cooling = cooling_hosts()
        if cooling:
            check("数据源冷却中", False,
                  "、".join(f"{h}({m:.0f}分钟)" for h, m in list(cooling.items())[:3]),
                  "连续被拒后自动触发，期间不发请求。python tools/astock.py cooldown 看详情",
                  fatal=False)
        else:
            check("数据源冷却中", True, "无")
    except Exception:
        pass

    # 请求计数：仅用于发现重复取数，不做硬拦截
    try:
        from agents.data_engineer.scripts.ak_client import budget_state

        b = budget_state()
        top = max(b["hosts"].items(), key=lambda kv: kv[1], default=None)
        detail = f"今日 {b['total']} 个请求（无上限）"
        if top:
            detail += f"，最多的是 {top[0]}（{top[1]} 个）"
        check("请求计数", True, detail)
    except Exception:
        pass

    # 本地仓库：命中越多，越不需要联网，也就越不容易被封
    try:
        from agents.data_engineer.scripts.store import bars

        rows = bars.stats()
        if rows:
            total = sum(r["n_rows"] for r in rows)
            check("本地仓库", True,
                  f"{len(rows)} 个数据集 / {total} 行 / {bars.db_size_mb()} MB")
        else:
            check("本地仓库", True, "空（跑一次 review 就会开始积累）")
    except Exception as e:
        check("本地仓库", False, str(e)[:60],
              "仓库不可用不影响复盘，只是每次都要重新联网取数", fatal=False)

    # 网络：指数日线只走 Baostock，其余数据仍依赖 AKShare
    bao_ok, bao_detail = False, ""
    try:
        import contextlib
        import io
        import baostock as bs

        with contextlib.redirect_stdout(io.StringIO()):
            login = bs.login()
            if login.error_code == "0":
                bs.logout()
        bao_ok = login.error_code == "0"
        bao_detail = "登录成功" if bao_ok else f"{login.error_code} {login.error_msg}"
    except Exception as e:
        bao_detail = str(e)[:100]
    check("Baostock 网络连通（指数日线）", bao_ok, bao_detail,
          "确认网络允许 Baostock 登录服务；指数日线不会回退其他来源", fatal=False)

    net_ok, net_detail = False, ""
    try:
        import akshare as ak  # noqa: F401
        from agents.data_engineer.scripts.ak_client import call

        df = call("tool_trade_date_hist_sina", cache=False)
        net_ok, net_detail = True, f"交易日历 {len(df)} 条"
    except Exception as e:
        # FetchError 里已经带了 explain() 出的诊断，取"原因："那一段
        msg = str(e)
        net_detail = (msg.split("原因：", 1)[1] if "原因：" in msg else explain(e))
        net_detail = " ".join(net_detail.split())[:100]
    check("AKShare 网络连通", net_ok, net_detail,
          "跑 python tools/net_check.py 逐个域名定位（DNS？代理？IPv6？）；"
          "或先看离线示例 python tools/astock.py demo", fatal=False)

    say()
    if ok and net_ok and bao_ok:
        as_of, note = default_as_of()
        say(_color(f"✓ 一切就绪。下一步：python tools/astock.py review   （将分析 {as_of}{note}）", C_OK))
    elif ok:
        say(_color("! 依赖齐全但至少一个数据源不可达 —— 真实取数会缺块。", C_DIM))
        say(_color("  离线示例照样能看：python tools/astock.py demo", C_DIM))
    else:
        say(_color(f"✗ {len(fails)} 项必需检查未通过：", C_NO))
        for i, (label, fix) in enumerate(fails, 1):
            say(f"  {i}. {label}")
            for line in (fix or "见上面的提示").split("\n     "):
                say(f"     {line}")
        say()
        say(_color("修完再跑一次 python tools/astock.py doctor", C_DIM))
        sys.exit(1)


# ── review：开工 ────────────────────────────────────────────────
def cmd_review(args) -> None:
    quiet = getattr(args, "quiet", False)
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
            [sys.executable, "-m", "agents.data_engineer.scripts.build_dataset", "--run-id", run_id,
             "--as-of", as_of, "--mode", args.mode] + (["--no-cache"] if args.no_cache else []),
            cwd=REPO_ROOT)
        if r.returncode != 0:
            _mark(run_id, "data-engineer", "failed", note="build_dataset 失败")
            die("取数失败", "看上面的报错。连不上网就先跑 python tools/astock.py demo")
        _finish_step(run_id, "data-engineer")

    if not quiet:
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
    from core.agent_registry import agent_file, skill_files
    skills = [p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)
              for p in skill_files(agent_file(name), meta)]
    example = f"workspace/runs/{EXAMPLE_RUN}/{artifact}.json"

    if args.json:
        print(json.dumps({
            "run_id": run_id, "as_of": man["as_of"], "mode": man["mode"], "done": False,
            "next_agent": name, "display_name": meta.get("display_name"),
            "definition": meta["_path"], "reads": reads, "writes": writes,
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
    say(f"│     {meta['_path']}   ← 职责、工作步骤、边界与禁止事项都在里面")
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
    from core.cli import build_validator

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
        text = (idx.read_text(encoding="utf-8") if idx.is_file()
                else "# 运行记忆索引\n")
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


# ── run：无人值守跑完全流程 ─────────────────────────────────────
def cmd_run(args) -> None:
    """一条命令跑完整条流水线，不需要人坐在终端前。

    与 next/done 循环的区别只有一个：**谁来做那五步判断**。
    next/done 交给你所在的 coding agent；run 交给 config/models.yaml 里配的 API。
    角色定义、技能、契约完全共用——这正是把内容与 harness 解耦的回报。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from agents.orchestrator.scripts.agent_runner import run_agent
    from agents.orchestrator.scripts.llm import Budget, BudgetExceeded, LLMError, load_models_config
    from core import repository as store

    cfg = load_models_config()
    if not (cfg.get("providers") and cfg.get("tiers")):
        die("没有可用的模型配置",
            "cp config/models.yaml.example config/models.yaml 并填一个 provider；"
            "或者用 astock next / done 让你所在的 coding agent 来跑（不花 API 钱）")
    b = cfg.get("budget") or {}
    budget = Budget(max_cost=b.get("max_cost_per_run"),
                    max_tokens=b.get("max_tokens_per_run"))

    # ① 取数（确定性代码，不花 API 钱）
    cmd_review(argparse.Namespace(as_of=args.as_of, mode=args.mode, no_fetch=args.no_fetch,
                                  no_cache=args.no_cache, force=args.force, quiet=True))
    run_id, d, man = resolve_run(None if not args.as_of else f"{args.as_of}_{args.mode}")

    # ② 逐步交给模型
    steps = []
    for step in man["steps"]:
        name = step["agent"]
        if name in AUTOMATED or step["status"] in ("ok", "blocked"):
            continue
        say(_color(f"→ {name} …", C_DIM))
        try:
            doc, stat = run_agent(name, d, budget=budget,
                                  max_attempts=int(b.get("max_attempts_per_agent", 2)),
                                  cfg=cfg, log=lambda m: say(_color("  " + m, C_DIM)))
        except BudgetExceeded as e:
            _mark(run_id, name, "failed", note=str(e)[:200])
            die(f"预算用尽，已停在 {name}", str(e))
            return
        except LLMError as e:
            _mark(run_id, name, "failed", note=str(e)[:200])
            say(_color(f"✗ {name} 失败：{e}", C_NO))
            say("  产物没通过 schema。可以改用 astock next 手工完成这一步，再 astock done 继续")
            sys.exit(1)
        store.write_json(d / f"{ARTIFACT_OF[name]}.json", doc)
        steps.append(stat)
        if not _finish_step(run_id, name):
            sys.exit(1)
        if name == "report-writer":
            subprocess.run([sys.executable, "tools/render_report.py", "--run-id", run_id],
                           cwd=REPO_ROOT, check=False)
            _append_memory(run_id)

    # ③ 把花费如实写进 manifest —— 每天跑的东西，成本必须看得见
    rep = budget.report()
    man = read_json(d / "run_manifest.json")
    man["llm_usage"] = {**rep, "steps": steps}
    write_json(d / "run_manifest.json", man)

    say()
    say(_color(f"✓ {run_id} 完成", C_OK))
    say(f"  报告：workspace/runs/{run_id}/report.md")
    say(f"  仪表盘：workspace/runs/{run_id}/report.html")
    say()
    cost = f"　花费 {rep['cost']}" if rep.get("cost") is not None else ""
    say(_color(f"  模型调用 {rep['calls']} 次 · "
               f"输入 {rep['prompt_tokens']:,} + 输出 {rep['completion_tokens']:,} token{cost}",
               C_DIM))
    if rep.get("cost_note"):
        say(_color(f"  （{rep['cost_note']}）", C_DIM))


def cmd_cooldown(args) -> None:
    """看/清 熔断状态。

    一个域名连续被拒之后会进冷却期，期间**一次请求都不发**——
    因为继续硬打只会让对方扩大封禁范围（实测教训）。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from agents.data_engineer.scripts.ak_client import clear_circuit, cooling_hosts

    if args.clear:
        n = clear_circuit()
        say(_color(f"✓ 已清空 {n} 条冷却记录", C_OK))
        say(_color("  提醒：如果对方还在封，清空只会让你更快地再被封一次。"
                   "先确认能连上再清。", C_DIM))
        return
    cooling = cooling_hosts()
    if not cooling:
        say(_color("✓ 没有域名处于冷却期", C_OK))
        return
    say(_color(f"{len(cooling)} 个域名正在冷却（期间不发请求，直接走备用源）：", C_B))
    for host, left in sorted(cooling.items(), key=lambda kv: -kv[1]):
        say(f"  {host:<32} 还剩 {left:.0f} 分钟")
    say()
    say(_color("  想强行试：ASTOCK_IGNORE_COOLDOWN=1 python tools/astock.py review", C_DIM))
    say(_color("  想清空：  python tools/astock.py cooldown --clear", C_DIM))


def cmd_budget(args) -> None:
    """看/清 今日请求预算。

    熔断器管的是"被拒之后别再打"，预算管的是"每个都成功但数量失控"——
    后者才是被封的开始。一次正常复盘约 30–50 个请求，
    数字远超这个量级，说明有地方在重复取数，而不是该调大上限。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from agents.data_engineer.scripts.ak_client import budget_state, reset_budget

    if args.reset:
        n = reset_budget()
        say(_color(f"✓ 已清零今日计数（原本 {n} 个请求）", C_OK))
        say(_color("  提醒：清零只删除本地计数，不会影响对方的限流状态。", C_DIM))
        return

    b = budget_state()
    say(_color(f"今日请求：{b['total']}（无上限）", C_OK))
    say(_color(f"参考：一次正常复盘约 30–50 个请求", C_DIM))
    say()
    if b["hosts"]:
        say(_color("按域名：", C_B))
        for host, n in sorted(b["hosts"].items(), key=lambda kv: -kv[1]):
            say(f"  {host:<32} {n:>4}")
    else:
        say(_color("  今天还没发过请求", C_DIM))
    say()
    say(_color("  清零计数：python tools/astock.py budget --reset", C_DIM))


def cmd_check(args) -> None:
    """逐块体检。和 doctor 的分工：doctor 查环境，check 查数据。"""
    cmd = [sys.executable, "tools/fetch_check.py"]
    if args.as_of:
        cmd += ["--as-of", args.as_of]
    if args.only:
        cmd += ["--only"] + list(args.only)
    if args.json:
        cmd += ["--json"]
    raise SystemExit(subprocess.run(cmd, cwd=REPO_ROOT).returncode)


def cmd_store(args) -> None:
    """看/清 本地行情仓库。

    仓库存的是**已收盘的交易日**——那些数据永远不会再变，
    所以没有 TTL，只取一次。缓存省的是这一次请求，仓库省的是以后所有次。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from agents.data_engineer.scripts.store import bars

    if args.purge is not None:
        n = bars.purge(args.purge or None)
        what = f"数据集 {args.purge}" if args.purge else "整个仓库"
        say(_color(f"✓ 已清空{what}（{n} 行）", C_OK))
        say(_color("  删了也没关系，下次复盘会重新取，只是多花几个请求。", C_DIM))
        return

    try:
        rows = bars.stats()
    except Exception as e:
        say(_color(f"✗ 仓库打不开：{str(e)[:120]}", C_NO))
        say(_color(f"  位置：{bars.DB_PATH}", C_DIM))
        say(_color("  常见原因：仓库落在了网络盘 / 同步盘 / 只读目录上——"
                   "SQLite 在这些文件系统上会报 disk I/O error。", C_DIM))
        say(_color("  换个位置：ASTOCK_HISTORY_DB=~/astock-history.sqlite", C_DIM))
        say(_color("  仓库不可用不影响复盘，只是每次都要重新联网取数。", C_DIM))
        return
    if not rows:
        say(_color("仓库还是空的——跑一次 review 就会开始积累。", C_DIM))
        say(_color(f"  位置：{bars.DB_PATH}", C_DIM))
        return
    say(_color(f"本地行情仓库（{bars.db_size_mb()} MB）", C_B))
    say(_color(f"  {bars.DB_PATH}", C_DIM))
    say()
    say(f"  {'数据集':<18}{'标的':>6}{'行数':>8}   覆盖区间")
    for r in rows:
        say(f"  {r['dataset']:<18}{r['symbols']:>6}{r['n_rows']:>8}   "
            f"{r['first']} → {r['last']}")
    say()
    say(_color("  这些日子已经存下来了，之后的复盘不会再为它们发请求。", C_DIM))
    say(_color("  清空：python tools/astock.py store --purge", C_DIM))


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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
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

    ru = sub.add_parser("run", help="无人值守跑完全流程（用 config/models.yaml 里配的模型）")
    ru.add_argument("--as-of", help="分析日 YYYY-MM-DD，默认自动推断")
    ru.add_argument("--mode", default="close", choices=sorted(MODE_STEPS))
    ru.add_argument("--no-fetch", action="store_true")
    ru.add_argument("--no-cache", action="store_true")
    ru.add_argument("--force", action="store_true")
    ru.set_defaults(func=cmd_run)

    cd = sub.add_parser("cooldown", help="看/清 被限流域名的冷却状态")
    cd.add_argument("--clear", action="store_true", help="清空冷却记录")
    cd.set_defaults(func=cmd_cooldown)

    ck = sub.add_parser("check", help="逐块体检：哪些数据能取到、哪些不能")
    ck.add_argument("--as-of", default=None)
    ck.add_argument("--only", nargs="*")
    ck.add_argument("--json", action="store_true")
    ck.set_defaults(func=cmd_check)

    st = sub.add_parser("store", help="看/清 本地行情仓库（已收盘的日子只取一次）")
    st.add_argument("--purge", nargs="?", const="", default=None,
                    metavar="数据集", help="清空仓库；给数据集名则只清那一个")
    st.set_defaults(func=cmd_store)

    bg = sub.add_parser("budget", help="看/清今日请求计数（无上限）")
    bg.add_argument("--reset", action="store_true", help="清零今日计数")
    bg.set_defaults(func=cmd_budget)

    m = sub.add_parser("demo", help="生成离线示例（不联网）")
    m.set_defaults(func=cmd_demo)

    args = p.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        say()
        say(_color("⌁ 已中断。进度都在 run_manifest.json 里，"
                   "下次 astock next 会从断的地方接着来。", C_DIM))
        sys.exit(130)


if __name__ == "__main__":
    main()
