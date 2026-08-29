# 03 · 动手：加一个新 agent

目标：新增 **`moneyflow-analyst`（资金流分析师）**，分析北向资金、龙虎榜、两融余额，
在报告里加一节"资金面"。

完整走一遍，你就理解了这套 harness 的全部咬合关系。

## Step 0 · 先想清楚边界

新 agent 的第一个问题不是"它做什么"，而是"**它和谁抢活**"。

资金流数据目前分散在两处：`sector-analyst` 用 `sector_flow` 判断板块真假，
`news-analyst` 用 `moneyflow` 做舆情背离检测。

拆出来之后要决定：那两个 agent 还能不能读资金流？

- 全部移走 → `sector-analyst` 失去"资金印证"这个判断维度，会退化成看涨幅榜
- 都保留 → 三个 agent 对同一份数据给出三个可能矛盾的结论

**推荐做法**：资金流的**原始数据**大家都能读，但"资金面结论"只有新 agent 出，
其他 agent 引用它而不是自己重新判断。这需要把 `moneyflow-analyst` 排在
`sector-analyst` 之前。

这个取舍没有标准答案，但**必须在动手前想清楚**，否则改到一半会推倒重来。

## Step 1 · 定契约（先做这一步，不要先写 prompt）

新建 `schemas/moneyflow.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "moneyflow.schema.json",
  "title": "资金面结论",
  "type": "object",
  "required": ["run_id", "as_of", "status", "direction", "evidence", "confidence", "caveats"],
  "properties": {
    "run_id": {"type": "string"},
    "as_of": {"type": "string"},
    "status": {"$ref": "_common.defs.json#/$defs/status"},
    "direction": {"enum": ["净流入", "净流出", "均衡", "unknown"]},
    "northbound_yi": {"type": ["number", "null"]},
    "margin_balance_chg_yi": {"type": ["number", "null"]},
    "lhb_highlights": {"type": "array", "items": {"type": "object"}},
    "divergences": {"type": "array", "items": {"type": "object"},
                    "description": "资金方向与价格/舆情方向不一致之处"},
    "evidence": {"type": "array", "items": {"$ref": "_common.defs.json#/$defs/evidence"}},
    "confidence": {"$ref": "_common.defs.json#/$defs/confidence"},
    "caveats": {"$ref": "_common.defs.json#/$defs/caveats"}
  }
}
```

**为什么先定契约？** 契约定了，下游 `report-writer` 就知道该期待什么。
先写 prompt 的话，你会不自觉地按 prompt 的输出反推结构，结构就会长歪。

## Step 2 · 补数据块

资金流已有 `sector_flow` 与 `northbound`，但龙虎榜和两融还没有。

1. `scripts/fetch/moneyflow.py` 新增：
   ```python
   def fetch_lhb(as_of): ...      # akshare.stock_lhb_detail_em
   def fetch_margin(as_of): ...   # akshare.stock_margin_sse / _szse
   ```
   每个函数返回 `DataBlock`，**必须带 `Provenance`**。
2. `scripts/build_dataset.py` 里挂上这两块
3. `schemas/dataset.schema.json` 的 `blocks.propertyNames.enum` 加 `"lhb"`, `"margin"`
4. `scripts/contracts.py` 的 `BLOCK_NAMES` 加同样两个

第 3、4 步必须同步——`tests/test_derive.py` 里有测试守着两边一致。

## Step 3 · 写角色定义

新建 `agents/moneyflow-analyst.md`：

```yaml
---
name: moneyflow-analyst
display_name: 资金流分析师
description: 从北向、龙虎榜、两融判断资金进出方向与主力行为，并检测资金与价格的背离。
model: default
depends_on: [data-engineer]
reads:  [workspace/runs/{run_id}/dataset.json]
writes: [workspace/runs/{run_id}/moneyflow.json]
schema: schemas/moneyflow.schema.json
skills: [a-share-market-basics]
tools:  [validate_artifact]
---
```

正文五节：职责 / 输入 / 工作步骤 / 输出 / **边界与禁止事项**。

边界那节最重要。至少要写清：
- 不判断板块强弱（那是 sector-analyst）
- 不推荐个股（龙虎榜上榜 ≠ 该买）
- 北向数据缺失时标 blocked，不用"市场传闻"替代

## Step 4 · 挂进编排

1. `agents/orchestrator.md` 的调度表，插在 `sector-analyst` **之前**：
   ```
   | 3 | `moneyflow-analyst` | 是 | dataset 校验通过 |
   ```
2. `config/pipeline.yaml`：
   ```yaml
   modes:
     close:
       steps: [..., moneyflow-analyst, sector-analyst, ...]
   steps:
     moneyflow-analyst: {enabled: true, required: false, retry: 1, timeout_seconds: 300}
   ```
3. `sector-analyst.md` 的 `depends_on` 与 `reads` 加上 `moneyflow.json`

## Step 5 · 让下游知道

- `agents/report-writer.md`：`depends_on` / `reads` 加上，正文加一节"资金面"
- `schemas/report.schema.json`：`sections` 加 `moneyflow` 字段
- `tools/render_report.py`：加一个 `h_moneyflow()` 并挂进 `render_html`
- `skills/report-writing/SKILL.md` 的九章表加一行

## Step 6 · 示例与测试

1. `tools/make_demo_run.py` 加一个 `moneyflow()` 函数，产出示例数据
2. `tests/test_contracts.py` 的 `ARTIFACTS` 字典加 `"moneyflow"`
3. `AGENTS.md` 第 2 节的流程图加上这个节点

```bash
python tools/make_demo_run.py
python tools/validate_artifact.py --run-id 2026-08-28_example --artifact moneyflow
python tools/render_report.py --run-id 2026-08-28_example
pytest tests/ -q
```

## 检查清单

- [ ] Step 0 的边界问题想清楚了，写进了 `agents/moneyflow-analyst.md` 的边界节
- [ ] schema 建好且能校验通过示例
- [ ] 数据块四处同步（fetch / build / schema enum / BLOCK_NAMES）
- [ ] agent 定义的 reads/writes 写死了
- [ ] orchestrator 调度表 + pipeline.yaml 都加了
- [ ] report-writer 知道有这个新输入，渲染器有对应区块
- [ ] AGENTS.md 流程图更新
- [ ] 示例 run 有对应产物，测试通过

**七步里只有一步在写 prompt。** 这就是 agentic workflow 的真实工作量分布。
