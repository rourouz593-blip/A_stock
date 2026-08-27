# tests/ — 测试层

## 测什么

优先级从高到低：

1. **契约测试** — `workspace/runs/*/` 的产物是否符合 `schemas/`。这是最重要的一类，
   因为契约破了会让下游 agent 静默失败。
2. **数据层单测** — `scripts/` 的清洗函数：单位换算、日历对齐、披露日对齐。
3. **工具测试** — `tools/` 的 CLI 输入输出约定。

## 不测什么

**不测模型输出的"分析质量"。** 这不是单测能覆盖的，
应该用 `workspace/` 里的历史 run 做人工复盘，结论沉淀到 `memory/knowledge/`。

## 运行

```bash
pytest tests/ -v
```
