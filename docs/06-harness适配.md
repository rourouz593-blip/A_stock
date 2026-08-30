# 06 · 一套内容，适配所有 coding agent

## 一、问题

同一套角色定义、技能、契约，要在 Claude Code、opencode、Codex、Cursor 里都能用。
但四家的"发现约定"完全不同：

| Harness | 斜杠命令 | 技能 | 子 agent | 自动读的文件 |
|---|---|---|---|---|
| Claude Code | `.claude/commands/` | `.claude/skills/` | `.claude/agents/` | `CLAUDE.md` |
| opencode | `.opencode/command/` | — | `.opencode/agent/` | `AGENTS.md` |
| Cursor | — | — | — | `.cursor/rules/*.mdc` |
| Codex | `~/.codex/prompts/` | — | — | `AGENTS.md` |

**朴素做法**：给每家手写一份。
**结果**：三个月后你改了 `agents/market-analyst.md`，忘了改 `.claude/agents/market-analyst.md`，
于是同一个角色在两个 harness 里行为不同。
这种 bug 极难发现——两边看起来都"有内容"，只是内容不一样。

## 二、解法：内容与发现机制解耦

```
agents/*.md + AGENTS.md          ← 唯一事实来源，harness 无关的纯文本
        ↓ tools/sync_harness.py
.claude/  .opencode/  .cursor/  .codex/    ← 薄适配层，全部生成
```

适配层里**不放内容**，只放两样东西：

1. **路由信息** —— 用户说什么时该触发（Claude Code 的 `description`、Cursor 的 rule）
2. **指针** —— "完整定义在 `agents/market-analyst.md`，先读那份"

所以适配文件都很短，十几行。真正的内容一份都不重复。

```bash
python tools/sync_harness.py          # 生成
python tools/sync_harness.py --check  # 检查是否同步
```

`tests/test_harness.py::test_harness_adapters_are_in_sync` 会跑 `--check`，
有人手改了生成物，测试就红。

## 三、加一个新 harness 要做什么

打开 `tools/sync_harness.py` 的 `build()`，加几行：

```python
files[".newharness/commands/astock-review.md"] = (
    "---\ndescription: 跑一次 A 股每日复盘\n---\n\n" + GEN_MARK + "\n\n"
    "读 AGENTS.md，然后 python tools/astock.py review\n"
)
for a in ags:                       # ags 是从 agents/*.md 读出来的
    files[f".newharness/agents/{a['name']}.md"] = ...
```

**不需要重写任何内容。** 成本从"重写一遍"降到"加十行生成代码"。

## 四、路由：用户说一句话，agent 怎么知道该干嘛

这是"harness factory"里最容易被低估的一环。
系统建得再好，如果用户说「帮我做今日股市复盘」时 agent 开始自己上网查行情，
那前面所有工程都白费。

本项目有三道保险：

### ① `AGENTS.md` 第 0 节的意图路由表

```
| 用户说 | 你做 |
| 「帮我做今日股市复盘」「今天 A 股怎么样」… | python tools/astock.py review |
| 「看看我的持仓」 | ... --mode positions |
```

Codex 和 opencode 会自动读 `AGENTS.md`，所以这张表对它们直接生效。

### ② Claude Code 技能的 `description`

Claude Code 靠技能的 description 做路由，所以那句话要**把用户可能的说法写全**：

```yaml
description: A 股每日复盘。当用户说「帮我做今日股市复盘、复盘一下今天大盘、
  今天 A 股怎么样、盘后复盘、看看我的持仓、明日预案…」等类似意图时使用。
  禁止绕过流水线自行查行情或凭印象分析。
```

最后那句"禁止绕过"很关键——**路由不只是告诉它该做什么，也要告诉它不该做什么。**

### ③ Cursor 的 `alwaysApply: true` 规则

Cursor 没有技能机制，所以用一条常驻规则兜底。

## 五、状态机：让 agent 不需要记流程

路由解决了"从哪开始"，但一条六步流水线，agent 跑到第四步很可能已经忘了第五步是什么。

解法是 `tools/astock.py` 的 `next` / `done`：

```bash
python tools/astock.py next            # 我现在该做什么
python tools/astock.py done market-analyst   # 我做完了，校验并推进
```

`next` 读 `run_manifest.json` 的状态 + 对应 `agents/*.md` 的 frontmatter，
渲染出一段可执行指令：读哪些文件、加载哪些技能、写哪个产物、按哪份 schema、
照哪份示例抄、完成后跑什么命令。

**关键在于：流程状态存在文件里，不在 agent 的上下文里。**

这带来三个好处：

1. 上下文被截断了也不影响——重新问一次 `next` 就行
2. 换一个 agent 接手能无缝续上
3. 今天跑一半明天继续，状态还在

> 教学要点：Agent 的"记性"是不可靠的。
> 不要让它记流程，把流程放进文件，让它每一步都来问"我在哪、下一步是什么"。

## 五点五、第三种执行者：直接调 API

前面讲的都是"让各家 coding agent 能接手"。但还有一个更根本的问题：
**凭什么假设一定有一个 coding agent 在场？**

章节九写着"每个交易日收盘后自动运行"——没人坐在终端前的时候，谁去做那五步判断？
而且每天把五次推理压在按会话计费的编码 agent 上，对学生是一笔不小的开销。

所以加了第三种执行者：`scripts/agent_runner.py` 直接读同一批
`agents/*.md` + `skills/*/SKILL.md` + `schemas/*.json`，组装成提示词发给 API。

```
        agents/*.md + skills/ + schemas/        ← 同一套内容
                     ↓
      ┌──────────────┴──────────────┐
   coding agent 读它              agent_runner 读它
   （next / done 循环）            （astock run，可无人值守）
```

**一个字都不用改。** 这是前面几轮把内容与执行机制解耦的直接回报——
当初为了"支持 opencode"做的解耦，顺手也支持了"根本没有 coding agent"这种情况。

值得注意的是：解耦之后，纪律反而更强了。
`agents/*.md` 里那句"只读 dataset.json"以前只是给模型看的一句话；
现在 `dataset_blocks` 声明被 `agent_runner` 用来**真的裁剪输入**——
板块分析师拿不到持仓数据，不是因为提示词让它别看，是因为代码不给它。

> 教学要点：**能写成机制的纪律，不要只写成提示词。**
> 提示词里的约束是"希望模型遵守"，代码里的裁剪是"模型没有机会违反"。

## 六、这套模式能迁移到别的项目吗

能，而且这是本仓库最通用的部分。任何多步骤的 agent 系统都可以照搬：

1. **角色定义放中性目录**（`agents/*.md` + frontmatter 声明 reads/writes/schema）
2. **写一个 `next` / `done` 状态机**，从 frontmatter 渲染指令
3. **写一个 sync 脚本**生成各 harness 的适配层
4. **入口手册第一节放意图路由表**
5. **写一个 provider 无关的 runner**，让同一套内容也能脱离 coding agent 跑
6. **测试守住同步、状态机与输入裁剪**

换成"论文写作流水线""代码审查流水线"，这五步一步都不用改。

## 练习

1. 打开 `.claude/agents/market-analyst.md` 与 `agents/market-analyst.md`，
   说清楚哪些信息在前者、哪些在后者，以及为什么这样分。
2. 手动改一下 `.claude/agents/market-analyst.md`，跑 `pytest tests/test_harness.py -q`，
   看它怎么报错。
3. 如果要支持 Windsurf（假设它读 `.windsurf/rules/`），你需要改哪几个文件？
4. `astock next` 的输出里，哪一部分是从 `agents/*.md` 读的、哪一部分是从
   `run_manifest.json` 读的？为什么要拆成两个来源？
