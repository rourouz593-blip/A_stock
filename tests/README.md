# tests/ — 测试层

## 测什么

优先级从高到低：

1. **契约测试**（`test_contracts.py`）—— 示例 run 的产物是否符合 `schemas/`，
   agent 声明的 schema 与 tool 是否真的存在，
   以及那些**硬约束**是否被守住：三个信号不多不少、每只持仓唯一动作、
   七条行为自检一条不少、报告里没有荐股措辞、数据缺口写在开头。
2. **派生指标测试**（`test_derive.py`）—— 两市成交额不重复计算、相对强弱、均线位置。
   这些是"唯一答案"型计算，错了整份报告都跟着错。
3. **涨停生态测试**（`test_breadth.py`）—— 炸板率、连板晋级率、梯队统计，
   以及"取不到数据时是否诚实地返回 None + flag"。

所有 akshare 调用都用 mock，**测试不访问网络**。

## 不测什么

**不测模型输出的"分析质量"。** 这不是单测能覆盖的。
分析质量靠 `news.json` 的次日验证与 `memory/runs/` 的历史复盘来检验。

## 运行

```bash
pytest tests/ -v
```

契约测试依赖 `workspace/runs/2026-08-28_example/`。如果那份示例被删了，先重建：

```bash
python tools/make_demo_run.py
python tools/render_report.py --run-id 2026-08-28_example
```
