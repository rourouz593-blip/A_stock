---
name: technical-indicators
description: 需要计算或解读技术指标、判断趋势与关键价位时加载。提供本项目认可的指标白名单、参数与读法。
used_by: [technical-analyst]
status: skeleton
---

# 技术指标手册

> **白名单原则**：只有登记在本文件里的指标才允许使用。
> 自创指标必须先在这里登记（含公式、参数、适用条件），再由 agent 使用。

## 1. 指标白名单

| 指标 | 类别 | 参数 | 计算实现 | 读法 | 失效条件 |
|---|---|---|---|---|---|
| TODO | 趋势 | TODO | `scripts/...` | TODO | TODO |
| TODO | 动量 | TODO | TODO | TODO | TODO |
| TODO | 波动 | TODO | TODO | TODO | TODO |
| TODO | 量能 | TODO | TODO | TODO | TODO |

<!-- TODO(strategy): 指标集合与参数待确认。确认后同步在 tools/tool_manifest.yaml
     登记 compute_indicators 支持的指标名 -->

## 2. 复权口径

技术分析前**必须**确认 `dataset.json.adjust_mode`：

<!-- TODO: 前复权 / 后复权 / 不复权 各自适用场景与对指标的影响 -->

## 3. A 股特有的失真来源

<!-- TODO: 涨跌停截断信号、一字板无成交、停牌造成的时间不连续、
     除权跳空、次新股样本不足 -->

## 4. 关键位置的定义

<!-- TODO(strategy): 支撑压力如何量化（前高前低 / 密集成交区 / 整数关口 / 均线）
     ——必须是可复现的规则，不能是"看图感觉" -->

## 5. 输出规范

每个指标输出三元组：`value`（数值）+ `reading`（状态描述）+ `caveat`（可信度限制）。
禁止只给状态不给数值。
