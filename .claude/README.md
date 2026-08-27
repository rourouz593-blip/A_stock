# .claude/ — Claude Code 兼容层

本项目的角色定义**不放在这里**，而是放在仓库根目录的 `agents/`（通用 AGENTS.md 规范），
这样 opencode / Cursor / Codex 等其他 harness 也能直接读。

如果你需要把它们注册成 Claude Code 的原生 subagent，
在本目录下建 `agents/` 并做软链即可：

```bash
mkdir -p .claude/agents
for f in agents/*.md; do
  [ "$(basename "$f")" = "README.md" ] && continue
  ln -sf "../../$f" ".claude/agents/$(basename "$f")"
done
```

> 教学要点：**同一套内容适配不同 harness**。
> 角色定义、技能、契约都是与 harness 无关的纯文本，
> 各家 harness 的差异只在"从哪个目录发现它们"。
> 把内容和发现机制解耦，换 harness 的成本就从"重写"降到"建软链"。
