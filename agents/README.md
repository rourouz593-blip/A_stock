# agents/ — 角色定义层

## 这一层是什么

一个 agent = **一段角色 prompt + 一份输入输出契约**。它不含业务算法（算法在 `skills/`），
也不含代码（代码在 `scripts/`）。这样拆开的好处是：换模型、换 harness、换数据源时，
这一层几乎不用改。

## 文件格式

每个 agent 是一个 Markdown 文件，顶部是 YAML frontmatter（机器读），下面是正文（模型读）。

```yaml
---
name: technical-analyst          # 唯一标识，与文件名一致
display_name: 技术面分析师
description: 一句话说明何时该派这个 agent 上场   # harness 用它来做路由
model: default                   # default / fast / reasoning，由 harness 映射到具体模型
depends_on: [data-engineer]      # 必须先完成的 agent
reads:                           # 只读这些文件，多一个都不许读
  - workspace/runs/{run_id}/dataset.json
writes:                          # 只写这些文件
  - workspace/runs/{run_id}/technical.json
schema: schemas/technical.schema.json
skills: [technical-indicators]   # 引用的技能包
tools: [compute_indicators]      # 允许调用的工具
---
```

正文统一分五节：**职责 / 输入 / 工作步骤 / 输出 / 边界与禁止事项**。

## 现有 agent

| name | 角色 | 依赖 | 产物 |
|---|---|---|---|
| `orchestrator` | 总控编排 | — | `run_manifest.json` |
| `data-engineer` | 数据工程 | orchestrator | `dataset.json` |
| `fundamental-analyst` | 基本面分析 | data-engineer | `fundamental.json` |
| `technical-analyst` | 技术面分析 | data-engineer | `technical.json` |
| `sentiment-analyst` | 情绪面分析 | data-engineer | `sentiment.json` |
| `report-writer` | 汇总成文 | 上面三个 | `report.json` + `report.md` |

## 新增 agent 的检查清单

- [ ] `agents/<name>.md` 建好，frontmatter 字段齐全
- [ ] `schemas/<name>.schema.json` 定义好产物结构
- [ ] `agents/orchestrator.md` 的调度表加了一行
- [ ] `AGENTS.md` 第 2 节的流程图加了这个节点
- [ ] 如果需要新的方法论 → `skills/` 加一个技能包
- [ ] 如果需要新的动作能力 → `tools/` 加工具并登记 manifest
