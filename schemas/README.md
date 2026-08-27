# schemas/ — 文件契约层

## 这一层是什么

**Agent 之间不共享内存、不互相调用函数，只交换文件。** 这些 JSON Schema 就是那些文件的合同。

契约层是整个 harness 里最不该随便改的部分：
改一个字段名，下游 agent 就会静默读到 `None`，然后一本正经地基于空数据写出报告。

> 教学要点：多智能体系统里最常见的失败不是"模型不够聪明"，而是**接口错位**。
> 用 schema 把接口钉死，再用 `validate_artifact` 在每一步之后强制校验，
> 才能让错误在发生的那一步暴露，而不是在最终报告里以"看起来很合理的胡说"呈现。

## 契约清单

| 文件 | 产出者 | 消费者 |
|---|---|---|
| `run_manifest.schema.json` | orchestrator | 所有 agent |
| `dataset.schema.json` | data-engineer | 三个分析 agent |
| `fundamental.schema.json` | fundamental-analyst | report-writer |
| `technical.schema.json` | technical-analyst | report-writer |
| `sentiment.schema.json` | sentiment-analyst | report-writer |
| `report.schema.json` | report-writer | 人 / 下游程序 |

## 三条通用约定

1. **每份分析产物都必须有 `status`**：`ok` / `partial` / `blocked`。
   宁可诚实地 `blocked`，不要编造内容。
2. **每条结论都必须有 `evidence`**，evidence 必须指向 `dataset.json` 里的具体字段与数值。
3. **每份产物都必须有 `caveats`**，写明这次分析的已知局限。

## 修改流程

改 schema → 改对应 `agents/*.md` 的输出说明 → 改 `workspace/runs/2026-01-02_example/` 示例
→ 跑 `python tools/validate_artifact.py` 确认示例仍然合法。三步缺一不可。
