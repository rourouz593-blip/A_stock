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
name: technical-indicators
description: 什么时候该加载这个技能（写清触发场景，harness 靠这句做检索）
used_by: [technical-analyst]
status: skeleton        # skeleton / draft / stable
---
```

## 现有技能包

| 技能 | 用途 | 被谁用 | 状态 |
|---|---|---|---|
| `a-share-market-basics` | A 股市场的制度性常识与陷阱清单 | orchestrator, data-engineer, fundamental, sentiment | skeleton |
| `financial-statement-reading` | 财报阅读与拆解方法 | fundamental-analyst | skeleton |
| `technical-indicators` | 指标定义、参数、读法 | technical-analyst | skeleton |
| `sentiment-scoring` | 情绪量化口径与信源权重 | sentiment-analyst | skeleton |
| `report-writing` | 报告结构与写作规范 | report-writer | skeleton |

**全部为 skeleton：只有骨架和 TODO，没有实际方法论内容。**
这是刻意的——具体策略需要人来确定，填内容就是学生的作业。
