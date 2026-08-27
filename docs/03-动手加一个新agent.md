# 03 · 动手：加一个新 agent

目标：新增一个 **`moneyflow-analyst`（资金流分析师）**，分析北向资金、龙虎榜、两融数据。

完整走一遍，你就理解了这套 harness 的全部咬合关系。

## Step 1 · 定契约（先做这一步，不要先写 prompt）

新建 `schemas/moneyflow.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "moneyflow.schema.json",
  "title": "资金流分析结论",
  "type": "object",
  "required": ["run_id", "target", "status", "flow_direction", "evidence", "confidence", "caveats"],
  "properties": {
    "run_id": {"type": "string"},
    "target": {"type": "string"},
    "status": {"$ref": "_common.defs.json#/$defs/status"},
    "flow_direction": {"enum": ["inflow", "outflow", "balanced", "unknown"]},
    "evidence": {"type": "array", "items": {"$ref": "_common.defs.json#/$defs/evidence"}},
    "confidence": {"$ref": "_common.defs.json#/$defs/confidence"},
    "caveats": {"$ref": "_common.defs.json#/$defs/caveats"}
  }
}
```

**为什么先定契约？** 因为契约定了，下游 `report-writer` 就知道该期待什么；
先写 prompt 的话，你会不自觉地按 prompt 的输出反推结构，结构就会长歪。

## Step 2 · 写角色定义

新建 `agents/moneyflow-analyst.md`，照抄现有 frontmatter 字段：

```yaml
---
name: moneyflow-analyst
display_name: 资金流分析师
description: 从北向资金、龙虎榜、两融余额判断资金进出方向与主力行为。
model: default
depends_on: [data-engineer]
reads:  [workspace/runs/{run_id}/dataset.json]
writes: [workspace/runs/{run_id}/moneyflow.json]
schema: schemas/moneyflow.schema.json
skills: [a-share-market-basics]
tools: []
---
```

正文五节：职责 / 输入 / 工作步骤 / 输出 / 边界与禁止事项。

**边界那节最重要**，想清楚：它和 `sentiment-analyst` 的界线在哪？
（资金流数据目前在 sentiment 的 `moneyflow` 块里 —— 拆出来后要不要从 sentiment 移走？
移走的话 sentiment 就失去了"背离检测"的能力。这是个真实的设计权衡，没有标准答案。）

## Step 3 · 登记到编排

改 `agents/orchestrator.md` 的调度表，在第 2 层（并行组）加一行：

```
| 2 | `moneyflow-analyst` | 是 | dataset.json 存在且校验通过 |
```

改 `config/pipeline.yaml` 的 `steps`：

```yaml
  moneyflow-analyst: {enabled: true, required: false, retry: 1, timeout_seconds: 300}
```

## Step 4 · 让下游知道

改 `agents/report-writer.md`：
- frontmatter 的 `depends_on` 和 `reads` 加上 moneyflow
- 正文的报告章节加一节「资金流」
- `schemas/report.schema.json` 的 `verdicts` 加一个 `moneyflow` 字段
- `skills/report-writing/templates/report_template.md` 加对应章节

## Step 5 · 更新文档与示例

- `AGENTS.md` 第 2 节的流程图加上这个节点
- `agents/README.md` 的表格加一行
- `workspace/runs/2026-01-02_example/` 加一份 `moneyflow.json` 占位
- `tests/test_contracts.py` 的 `ARTIFACTS` 字典加一项

## Step 6 · 验证

```bash
python tools/validate_artifact.py --run-id 2026-01-02_example --artifact moneyflow
pytest tests/ -v
```

## 检查清单

- [ ] schema 建好且能校验通过示例
- [ ] agent 定义的 reads/writes 写死了
- [ ] orchestrator 调度表加了行
- [ ] pipeline.yaml 加了配置
- [ ] report-writer 知道有这个新输入
- [ ] AGENTS.md 流程图更新
- [ ] 示例 run 有对应产物
- [ ] 测试通过

**六步里只有一步在写 prompt。** 这就是 agentic workflow 的真实工作量分布。
