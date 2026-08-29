# 01 · 什么是 agentic workflow

## 一、三个阶段

```
阶段一：Prompt
  人 → [一段话] → 模型 → 文本
  模型只会说，不会做。

阶段二：Tool Use（工具调用）
  人 → 模型 ⇄ [工具] → 结果
  模型能查数据、能跑代码了。但仍是一问一答，没有过程。

阶段三：Agentic Workflow
  人 → [Agent 系统] → 产物
        ├─ 自己拆解任务
        ├─ 自己决定调哪个工具
        ├─ 自己检查中间结果
        └─ 出错自己重试或如实上报
  模型有了"过程"，而过程需要被工程化管理。
```

**本项目在阶段三。** 而阶段三的工程量，90% 不在写 prompt，在管理这个"过程"。

看一眼就明白：本仓库 `agents/` 里的七个 prompt 加起来不到 1000 行，
而 `scripts/` + `tools/` + `schemas/` + `tests/` 加起来是它的好几倍。

## 二、Agent 的最小定义

一个 agent 需要四样东西：

1. **目标** —— 我要完成什么（`agents/*.md` 的"职责"节）
2. **上下文** —— 我能看到什么（frontmatter 的 `reads`）
3. **能力** —— 我能做什么（`skills` + `tools`）
4. **终止条件** —— 什么时候算完成（frontmatter 的 `writes` + `schema`）

缺任何一样都会跑飞：
没目标 → 漫游；没上下文边界 → 乱读；没能力 → 空谈；没终止条件 → 停不下来或半途而废。

拿本项目的 `sector-analyst` 对照：

```yaml
name: sector-analyst
reads:  [dataset.json, market.json]     # 上下文边界
writes: [sectors.json]                  # 终止条件
schema: schemas/sectors.schema.json     # 终止条件的验收标准
skills: [sector-ladder, market-emotion-cycle]   # 能力：怎么判断
tools:  [validate_artifact]                     # 能力：怎么动手
```

## 三、为什么"多"agent

**多 agent 的价值不只是分工，更是"制造独立性"。**

本项目里，`sector-analyst` 的 `reads` 里**没有** `positions.yaml`——
它在判断板块强弱时根本不知道你持有什么。

这不是疏忽，是刻意的：
如果板块分析师知道你重仓了某个题材，它会不自觉地为那个题材找强的理由。
**一个替你的持仓找理由的系统，比没有系统更危险**——
它会用看起来很专业的语言，把你已有的偏见包装成结论。

顺序也是为此设计的：先判断市场 → 再判断板块 → 最后才看持仓。
持仓分析引用前面的结论，前面的结论不知道持仓存在。

## 四、Agentic ≠ 全自动

一个常见误解是"agentic 就是让 AI 全权处理"。恰恰相反：

**好的 agent 系统会主动制造"停下来"的时机。**

本项目里有五处刻意的"停"：

| 停在哪 | 触发条件 | 在哪实现 |
|---|---|---|
| 不出复盘 | 当天不是交易日 | `pipeline.yaml: forbid_run_on_non_trading_day` |
| 标 blocked | 某类数据取不到 | `scripts/` 各 fetch 函数 |
| 数字留空 | 没配账户总资产 | `scripts/positions.py` |
| 停止交易 | 情绪退潮 / 行为自检触发 3 条 | `skills/risk-discipline` |
| 不填阈值 | `TODO(strategy)` 是用户的经验参数 | `config/thresholds.yaml` |

> 判断一个 agent 系统成不成熟，不看它能自动做多少，
> 看它**知不知道自己什么时候不该做**。

## 练习

1. 用自己的话说明：为什么 `sector-analyst` 的 `reads` 里不许有 `positions.yaml`？
2. 打开 `agents/report-writer.md`，找出它的"终止条件"是什么。
3. 在本项目里再找一处"刻意停下来"的设计（提示：看 `scripts/ak_client.py` 的失败处理）。
