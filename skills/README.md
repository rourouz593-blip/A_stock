# skills/ — 技能层

## 这一层是什么

**Agent 是"谁"，Skill 是"怎么做"。**

同一个技能可以被多个 agent 引用（比如 `a-share-market-basics` 被 4 个 agent 用）；
同一个 agent 也可以引用多个技能。把方法论从角色定义里抽出来，是为了：

1. **可复用** — 不用在每个 agent 里重复抄一遍 A 股常识
2. **可迭代** — 分析方法改进时只改技能包，不动角色定义
3. **可按需加载** — agent 不必把所有知识都塞进上下文，用到哪个加载哪个

> 教学要点：这就是"上下文工程"。模型的上下文窗口是稀缺资源，
> 技能层的本质是**一个按需检索的知识索引**，而不是一本一次性读完的大百科。

## 技能包结构

```
skills/<skill-name>/
├── SKILL.md          # 必需。frontmatter + 方法论正文
├── reference/        # 可选。查得到就不必背下来的长表格、字段字典
├── templates/        # 可选。输出模板
└── examples/         # 可选。好/坏示例对照
```

`SKILL.md` 的 frontmatter：

```yaml
---
name: sector-ladder
description: 什么时候该加载这个技能（写清触发场景，harness 靠这句做检索）
used_by: [sector-analyst, position-advisor]
status: draft           # skeleton / draft / stable
---
```

## 现有技能包（9 个）

| 技能 | 用途 | 被谁用 | 状态 |
|---|---|---|---|
| `a-share-market-basics` | A 股制度常识、短线术语、数据口径陷阱 | 5 个 agent | draft |
| `market-emotion-cycle` | 冰点/修复/主升/分歧/退潮 五阶段判定 | market, sector | draft |
| `intraday-rhythm` | 日内四段拆解与归因方法 | market | draft |
| `sector-ladder` | 板块梯队、龙头识别、五维强弱判定 | sector, position | draft |
| `position-review` | 持仓卡片口径 + 七条行为自检 | position | draft |
| `risk-discipline` | 仓位、单笔风险、是否停手的计算与判定 | position, report | draft |
| `news-triage` | 信源分层、去重、三分类、次日验证 | news | draft |
| `report-writing` | 九章结构、语言规范、仪表盘约定 | report | draft |
| `positions-import` | 券商截图字段识别、七个陷阱、算术自检 | position, orchestrator | draft |

**状态说明**：`draft` = 框架与方法论已写，但**具体阈值仍是 `TODO(strategy)`**。
比如"炸板率多少算退潮"——这个数需要用历史数据回测确定，或由用户按自己的经验填。
框架是通用的，阈值是个人的，所以框架我写，阈值留给你。

## 阈值集中放在哪

分散在各 SKILL.md 里的 `TODO(strategy)` 是**说明**；
真正被代码读取的数值放在 `config/thresholds.yaml`。
改阈值改那一个文件，不要改 SKILL.md。
