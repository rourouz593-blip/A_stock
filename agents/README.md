# agents/ — 角色定义层

## 这一层是什么

一个 agent = **一段角色 prompt + 一份输入输出契约**。它不含业务算法（算法在 `skills/`），
也不含代码（代码在 `scripts/`）。这样拆开的好处是：换模型、换 harness、换数据源时，
这一层几乎不用改。

## 文件格式

每个 agent 是一个 Markdown 文件，顶部是 YAML frontmatter（机器读），下面是正文（模型读）。

```yaml
---
name: sector-analyst             # 唯一标识，与文件名一致
display_name: 板块分析师
description: 一句话说明何时该派这个 agent 上场   # harness 用它来做路由
model: reasoning                 # default / fast / reasoning，由 harness 映射到具体模型
depends_on: [data-engineer, market-analyst]      # 必须先完成的 agent
reads:                           # 只读这些文件，多一个都不许读
  - workspace/runs/{run_id}/dataset.json
  - workspace/runs/{run_id}/market.json
writes:                          # 只写这些文件
  - workspace/runs/{run_id}/sectors.json
schema: schemas/sectors.schema.json
skills: [sector-ladder, market-emotion-cycle]    # 引用的技能包
tools: [validate_artifact]       # 允许调用的工具
---
```

正文统一分五节：**职责 / 输入 / 工作步骤 / 输出 / 边界与禁止事项**。

## 现有 agent（7 个）

| name | 角色 | 覆盖报告章节 | 依赖 | 产物 |
|---|---|---|---|---|
| `orchestrator` | 总控编排 | — | — | `run_manifest.json` |
| `data-engineer` | 数据工程 | 全部章节的数据底座 | orchestrator | `dataset.json` |
| `market-analyst` | 市场分析 | ① 市场总览 ② 指数复盘 | data-engineer | `market.json` |
| `sector-analyst` | 板块分析 | ③ 板块与题材 | market-analyst | `sectors.json` |
| `news-analyst` | 新闻分析 | ⑥ 新闻与公告 | data-engineer | `news.json` |
| `position-advisor` | 持仓顾问 | ④ 持仓计划 ⑦ 风险纪律 | market + sectors | `positions_review.json` |
| `report-writer` | 报告撰写 | ⑤ 明日预案 ⑧ 执行面板 + 全文 | 上面四个分析 agent | `report.json/.md/.html` |

章节⑨（运行方式）不属于某个 agent，它是 `orchestrator` 的四种运行模式，见 `config/pipeline.yaml`。

## 新增 agent 的检查清单


- [ ] `agents/<name>.md` 建好，frontmatter 字段齐全
- [ ] `schemas/<name>.schema.json` 定义好产物结构
- [ ] `agents/orchestrator.md` 的调度表加了一行
- [ ] `AGENTS.md` 第 2 节的流程图加了这个节点
- [ ] 如果需要新的方法论 → `skills/` 加一个技能包
- [ ] 如果需要新的动作能力 → `tools/` 加工具并登记 manifest
