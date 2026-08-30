# .claude/ 与其他适配目录

**本目录下除了这份 README，全部是生成的，不要手改。**

```bash
python tools/sync_harness.py          # 重新生成
python tools/sync_harness.py --check  # 检查是否与源头同步
```

## 为什么是生成的

各家 coding agent 的"发现约定"都不一样：

| Harness | 斜杠命令 | 技能 | 子 agent | 自动读 |
|---|---|---|---|---|
| Claude Code | `.claude/commands/` | `.claude/skills/` | `.claude/agents/` | `CLAUDE.md` |
| opencode | `.opencode/command/` | — | `.opencode/agent/` | `AGENTS.md` |
| Cursor | — | — | — | `.cursor/rules/*.mdc` |
| Codex | `~/.codex/prompts/` | — | — | `AGENTS.md` |

如果给每家手写一份，很快就会分叉——改了 `agents/market-analyst.md`，
忘了改 `.claude/agents/market-analyst.md`，同一个角色在两个 harness 里行为就不同了。
这种 bug 极难发现，因为两边看起来都"有内容"。

所以本项目：

```
agents/*.md + AGENTS.md        ← 唯一事实来源（harness 无关的纯文本）
        ↓ tools/sync_harness.py
.claude/  .opencode/  .cursor/  .codex/     ← 薄适配层，全部生成
```

`tests/test_harness_sync.py` 会检查两边同步，不同步就测试失败。

## 加一个新 harness

在 `tools/sync_harness.py` 的 `build()` 里加几行，指明它的目录约定即可。
**不需要重写任何内容**——内容早就与 harness 解耦了。

> 教学要点：这就是"harness 工厂"的含义。
> 支持一个新 harness 的成本，从"重写一遍"降到"加十行生成代码"。
