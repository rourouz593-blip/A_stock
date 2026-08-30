#!/usr/bin/env python3
"""从 agents/ 与 AGENTS.md 生成各家 coding agent 的适配文件。

用法:
    python tools/sync_harness.py            # 生成/更新
    python tools/sync_harness.py --check    # 只检查是否同步（CI / 测试用）

## 为什么需要它

Claude Code、opencode、Codex、Cursor 各有各的"发现约定"：
斜杠命令放哪、技能放哪、子 agent 放哪，四家都不一样。

如果给每家手写一份，很快就会分叉——改了 `agents/market-analyst.md`，
忘了改 `.claude/agents/market-analyst.md`，于是同一个角色在两个 harness 里行为不同。

所以本项目的做法是：

    agents/*.md + AGENTS.md   ← 唯一事实来源（harness 无关）
              ↓ sync_harness.py
    .claude/  .opencode/  .cursor/  .codex/   ← 生成的薄适配层

**生成的文件不要手改。** 要改内容改源头，然后重新跑本脚本。
`tests/test_harness_sync.py` 会检查两边是否同步。

> 教学要点：这就是"harness 工厂"的含义——
> 内容与发现机制解耦之后，支持一个新 harness 的成本从"重写一遍"降到"加十行生成代码"。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import REPO_ROOT

GEN_MARK = "<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agents/ 或 AGENTS.md 后重新生成 -->"

# 用户可能怎么说 → 触发本系统。写全一点，harness 靠这句做路由
TRIGGER_ZH = (
    "帮我做今日股市复盘、复盘一下今天大盘、今天 A 股怎么样、盘后复盘、"
    "跑一下复盘、看看我的持仓、明日预案、今天什么板块最强、生成复盘报告、"
    "股市日报、收盘总结、A股复盘"
)

SKILL_BODY = """# A 股每日复盘

用户想要一份 A 股复盘时，**不要自己去查行情、不要凭印象分析**。
本仓库是一条已经建好的流水线，你要做的是驱动它。

## 三条命令，一个循环

```bash
python tools/astock.py doctor    # 第一次跑，先自检环境
python tools/astock.py review    # 开始：建 run + 用 AKShare 取数
python tools/astock.py next      # 我现在该做什么（它会告诉你一切）
#   ↑ 按提示完成那一步、写出产物 ↓
python tools/astock.py done <agent>
#   ↑ 校验通过后自动打印下一步，回到 next
```

`next` 的输出里包含：读哪些文件、加载哪些技能、写哪个产物、按哪份 schema、
照哪份示例抄、以及完成后的校验命令。**照着做即可，不需要你记流程。**

## 你要亲自完成的是"判断"，不是"取数"

- 取数、算炸板率、算风险金额、渲染报告 → 都是确定性代码，`astock` 会跑
- 判断情绪阶段、认主线龙头、给持仓定动作 → 这是你的活，方法论在 `skills/`

## 开工前必读

- `AGENTS.md` —— 本仓库的完整操作手册（角色、契约、纪律）
- 每一步 `next` 指给你的那份 `agents/<name>.md`

## 四条铁律

1. 数据缺了写 `blocked` + 原因，**绝不编造**
2. 每条结论都要能追溯到 `dataset.json` 的具体字段
3. 每只持仓只能给**一个**动作，不许"可以持有也可以减半"
4. 不给目标价、不荐股。本系统输出分析与纪律检查，不是投资建议

## 环境不通怎么办

连不上 AKShare 时跑 `python tools/astock.py demo`，
它会生成一份**全虚构数据**的完整示例，用来演示产出长什么样。
**不要拿示例数据当真实复盘交给用户。**
"""


def agents() -> list[dict]:
    import yaml

    out = []
    for p in sorted((REPO_ROOT / "agents").glob("*.md")):
        if p.stem == "README":
            continue
        fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])
        fm["_path"] = f"agents/{p.name}"
        out.append(fm)
    return out


def build() -> dict[str, str]:
    """返回 {相对路径: 内容}。加一个新 harness 就在这里多加几行。"""
    files: dict[str, str] = {}
    ags = agents()

    # ── Claude Code ────────────────────────────────────────────
    files[".claude/skills/a-stock-daily-review/SKILL.md"] = (
        "---\n"
        "name: a-stock-daily-review\n"
        f"description: A 股每日复盘。当用户说「{TRIGGER_ZH}」等类似意图时使用。"
        "驱动本仓库的多智能体流水线，产出九章复盘报告与 HTML 仪表盘。"
        "禁止绕过流水线自行查行情或凭印象分析。\n"
        "---\n\n" + GEN_MARK + "\n\n" + SKILL_BODY
    )
    files[".claude/commands/astock-review.md"] = (
        "---\n"
        "description: 跑一次 A 股每日复盘（建 run + 取数 + 进入分析循环）\n"
        "argument-hint: \"[YYYY-MM-DD] [close|premarket|positions|weekly]\"\n"
        "---\n\n" + GEN_MARK + "\n\n"
        "先读 `AGENTS.md`，然后：\n\n"
        "```bash\n"
        "python tools/astock.py review $ARGUMENTS\n"
        "```\n\n"
        "之后进入循环：`astock next` → 完成那一步 → `astock done <agent>` → 回到 `next`，\n"
        "直到它输出「全部完成」。每一步的输入、产物、schema、技能都由 `next` 告诉你。\n\n"
        "纪律：数据缺了写 blocked，不编造；每只持仓只给一个动作；不荐股、不给目标价。\n"
    )
    files[".claude/commands/astock-next.md"] = (
        "---\ndescription: 查看当前复盘进行到哪一步，并按提示继续\n---\n\n" + GEN_MARK + "\n\n"
        "```bash\npython tools/astock.py status\npython tools/astock.py next\n```\n\n"
        "按 `next` 的输出完成那一步，然后 `python tools/astock.py done <agent>`。\n"
    )
    for a in ags:
        files[f".claude/agents/{a['name']}.md"] = (
            "---\n"
            f"name: {a['name']}\n"
            f"description: {a['description']}\n"
            "---\n\n" + GEN_MARK + "\n\n"
            f"# {a['display_name']}\n\n"
            f"**完整职责定义在 `{a['_path']}`，先读那份文件再动手。**\n\n"
            f"- 只读：{'、'.join(a.get('reads') or []) or '（无）'}\n"
            f"- 只写：{'、'.join(a.get('writes') or []) or '（无）'}\n"
            f"- 结构：`{a.get('schema')}`\n"
            f"- 技能：{'、'.join(f'`skills/{s}/SKILL.md`' for s in (a.get('skills') or [])) or '（无）'}\n"
            f"- 完成后：`python tools/astock.py done {a['name']}`\n\n"
            "写完必须过 schema 校验。数据缺了写 blocked + 原因，不许编造。\n"
        )

    # ── opencode ───────────────────────────────────────────────
    files[".opencode/command/astock-review.md"] = (
        "---\n"
        "description: 跑一次 A 股每日复盘\n"
        "---\n\n" + GEN_MARK + "\n\n"
        "读 `AGENTS.md`，然后跑 `python tools/astock.py review $ARGUMENTS`，\n"
        "之后按 `astock next` / `astock done <agent>` 的循环走到底。\n"
    )
    for a in ags:
        files[f".opencode/agent/{a['name']}.md"] = (
            "---\n"
            f"description: {a['description']}\n"
            "mode: subagent\n"
            "---\n\n" + GEN_MARK + "\n\n"
            f"完整职责定义在 `{a['_path']}`，先读那份文件。\n"
            f"只读 {'、'.join(a.get('reads') or [])}；只写 {'、'.join(a.get('writes') or [])}；\n"
            f"结构见 `{a.get('schema')}`；完成后跑 `python tools/astock.py done {a['name']}`。\n"
        )

    # ── Cursor ─────────────────────────────────────────────────
    files[".cursor/rules/a-stock.mdc"] = (
        "---\n"
        "description: A 股每日复盘流水线的使用方式\n"
        "alwaysApply: true\n"
        "---\n\n" + GEN_MARK + "\n\n"
        "本仓库是一条 A 股每日复盘流水线。用户说「复盘 / 今天大盘 / 看看我的持仓」时，\n"
        "**不要自己查行情或凭印象分析**，驱动流水线：\n\n"
        "1. `python tools/astock.py doctor`（首次）\n"
        "2. `python tools/astock.py review`\n"
        "3. 循环：`astock next` → 完成那一步 → `astock done <agent>`\n\n"
        "完整手册见 `AGENTS.md`。铁律：数据缺了写 blocked 不编造；\n"
        "每只持仓只给一个动作；不荐股、不给目标价。\n"
    )

    # ── Codex ──────────────────────────────────────────────────
    files[".codex/prompts/astock-review.md"] = (
        GEN_MARK + "\n\n"
        "# 跑一次 A 股每日复盘\n\n"
        "Codex 会自动读仓库根目录的 `AGENTS.md`，所以直接照它做即可。\n\n"
        "```bash\n"
        "python tools/astock.py review\n"
        "```\n\n"
        "然后循环 `astock next` → 完成 → `astock done <agent>`。\n\n"
        "（若你的 Codex 版本只从 `~/.codex/prompts` 读自定义提示词，把本文件复制过去即可。）\n"
    )
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="只检查是否同步，不写文件")
    args = ap.parse_args()

    files = build()
    drift = []
    for rel, content in files.items():
        p = REPO_ROOT / rel
        current = p.read_text(encoding="utf-8") if p.is_file() else None
        if current != content:
            drift.append(rel)
            if not args.check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")

    if args.check:
        if drift:
            print("适配层与源头不同步，以下文件需要重新生成：")
            for f in drift:
                print(f"  {f}")
            print("\n跑 python tools/sync_harness.py 修复")
            sys.exit(1)
        print(f"✓ {len(files)} 个适配文件全部同步")
        return

    print(f"✓ 已生成 {len(files)} 个适配文件"
          + (f"，其中 {len(drift)} 个有更新" if drift else "（无变化）"))
    for f in drift:
        print(f"  {f}")


if __name__ == "__main__":
    main()
