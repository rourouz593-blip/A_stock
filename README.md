# A-Stock Agent Factory · A 股多智能体分析工厂

一个**教学导向**的多智能体（multi-agent）分析系统骨架，面向中国大陆 A 股市场。

它的目标有两个：

1. **工程目标** —— 做成一个 harness factory：任何 coding agent（Claude Code、opencode、
   Cursor、Codex……）在**对本项目零了解**的情况下进来，读完 `AGENTS.md` 就知道该怎么干活。
2. **教学目标** —— 让学生看清一个 agentic workflow 是由哪些零件组成的、
   零件之间怎么咬合、以及为什么要这样拆。

> ⚠️ **当前状态：骨架完成，业务内容为空。**
> 数据源 API 与投资策略尚未确定，所有涉及"具体怎么算""从哪拿数据"的地方都是
> `TODO(datasource)` / `TODO(strategy)` 占位。**这是设计，不是未完成。**
> 骨架先立住，内容后填——填内容正是学生的作业。

---

## 目录

- [一、为什么要拆成多个 agent](#一为什么要拆成多个-agent)
- [二、系统架构](#二系统架构)
- [三、六个组件：一个健康的 agentic workflow 有什么](#三六个组件一个健康的-agentic-workflow-有什么)
- [四、目录结构](#四目录结构)
- [五、数据流：一次完整运行发生了什么](#五数据流一次完整运行发生了什么)
- [六、快速开始](#六快速开始)
- [七、给学生的扩展任务](#七给学生的扩展任务)
- [八、设计原则与硬约束](#八设计原则与硬约束)
- [九、当前留白清单](#九当前留白清单)
- [十、免责声明](#十免责声明)

---

## 一、为什么要拆成多个 agent

一个很自然的疑问是：为什么不写一个超长 prompt，让一个模型把基本面、技术面、
情绪面一次全分析完？

因为会遇到四个问题：

| 问题 | 单 agent 的表现 | 多 agent 的解法 |
|---|---|---|
| **上下文稀释** | 财报、K 线、新闻全塞进一个窗口，模型注意力被摊薄，哪一路都做不深 | 每个 agent 只拿自己需要的那部分数据 |
| **无法定位错误** | 报告写错了，不知道是数据错、还是财务理解错、还是行文时编的 | 每一步产物单独落盘，逐步校验，错在哪一步一目了然 |
| **结论互相污染** | 模型看完"股价大涨"再去读财报，会不自觉地为涨幅找理由（确认偏误） | 三路分析**并行且互相隔离**，只在最后一步汇总 |
| **无法复用与迭代** | 改一处 prompt，全盘行为都变 | 改一个 agent 只影响那一路，其他不动 |

第三条尤其重要，也是本项目的核心设计动机：
**基本面、技术面、情绪面必须互不知情地各自得出结论，它们之间的分歧才有信息量。**
如果让一个模型顺序地看完三类数据，它给出的"三方共振"往往只是自我说服。

---

## 二、系统架构

```
                          用户请求
                             │
                             ▼
                  ┌────────────────────┐
                  │    orchestrator    │  总控：拆解任务、调度、校验产物
                  │      总控编排       │  ← 唯一有权决定"下一步"的角色
                  └─────────┬──────────┘
                            │ ① 建 run 目录 + run_manifest.json
                            ▼
                  ┌────────────────────┐
                  │   data-engineer    │  调 tools → scripts：取数、清洗、落盘
                  │     数据工程师      │  ← 本次 run 唯一的"事实来源"
                  └─────────┬──────────┘
                            │ ② dataset.json
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ fundamental-  │  │  technical-   │  │  sentiment-   │   ③ 三路并行
│   analyst     │  │   analyst     │  │   analyst     │     互相隔离
│  基本面分析师   │  │  技术面分析师   │  │  情绪面分析师   │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │fundamental.json  │technical.json    │sentiment.json
        └──────────────────┼──────────────────┘
                           ▼
                  ┌────────────────────┐
                  │   report-writer    │  ④ 综合，重点是找出三路的**分歧**
                  │     报告撰写        │
                  └─────────┬──────────┘
                            ▼
                   report.md + report.json
```

### 六个 agent

| Agent | 中文 | 一句话职责 | 产物 |
|---|---|---|---|
| `orchestrator` | 总控编排 | 拆解请求、按依赖调度、校验产物、决定重试或中止 | `run_manifest.json` |
| `data-engineer` | 数据工程师 | 取数、清洗、口径统一、如实标注质量问题 | `dataset.json` |
| `fundamental-analyst` | 基本面分析师 | 生意好不好、价格贵不贵 | `fundamental.json` |
| `technical-analyst` | 技术面分析师 | 价格处在什么状态、关键位在哪 | `technical.json` |
| `sentiment-analyst` | 情绪面分析师 | 市场在关注什么、有无事件催化 | `sentiment.json` |
| `report-writer` | 报告撰写 | 综合三路、突出分歧、成文 | `report.md` / `report.json` |

详细定义见 `agents/` 下各文件。

---

## 三、六个组件：一个健康的 agentic workflow 有什么

这是本项目最想让学生带走的一张表。**一个能长期跑下去的 agent 系统，
不是只有 prompt，而是由六层组成的：**

```
┌─────────────────────────────────────────────────────────────┐
│  ①  Agent 角色定义        agents/     "我是谁，我读什么，我写什么"  │
├─────────────────────────────────────────────────────────────┤
│  ②  Skill 技能            skills/     "这类事情的正确做法是什么"    │
├─────────────────────────────────────────────────────────────┤
│  ③  Tool 工具             tools/      "我怎么真的动手做，而不是空谈" │
├─────────────────────────────────────────────────────────────┤
│  ④  Contract 契约         schemas/    "我们之间传的东西长什么样"     │
├─────────────────────────────────────────────────────────────┤
│  ⑤  Memory 记忆           memory/     "上次踩的坑这次别再踩"        │
├─────────────────────────────────────────────────────────────┤
│  ⑥  Workspace 工作区      workspace/  "过程和产物都看得见、可复现"   │
└─────────────────────────────────────────────────────────────┘
                        ↑
                 scripts/ 数据层：唯一接触外部世界的代码
```

### ① Agent 角色定义（`agents/`）

一个 agent = **一段角色 prompt + 一份输入输出契约**。
它不含算法（算法在 skills），不含代码（代码在 scripts）。

```yaml
---
name: technical-analyst
depends_on: [data-engineer]
reads:  [workspace/runs/{run_id}/dataset.json]      # 只读这个，多一个都不许读
writes: [workspace/runs/{run_id}/technical.json]    # 只写这个
schema: schemas/technical.schema.json
skills: [technical-indicators]
tools:  [compute_indicators]
---
```

**为什么要写死 reads/writes？** 因为不写死，模型就会去读它"觉得有用"的东西，
于是技术面分析师看到了新闻，情绪面分析师看到了财报——三路隔离当场失效。
**约束不是限制模型，而是保护设计。**

### ② Skill 技能（`skills/`）

技能是**可复用的方法论**："读财报要看哪六个维度""情绪信源怎么分层加权"。

- 一个技能可被多个 agent 引用（`a-share-market-basics` 被四个 agent 用）
- 方法论改进时只改技能包，不动角色定义
- **按需加载**：agent 用到哪个技能才把它读进上下文

> 这就是所谓的**上下文工程**。上下文窗口是稀缺资源，技能层的本质是
> *一个按需检索的知识索引*，而不是一本一次性读完的百科全书。

### ③ Tool 工具（`tools/`）

Skill 让 agent "知道怎么做"，Tool 让 agent "真的能做"。

**判断标准：这件事是否需要可复现的精确结果？**

- "MA20 是多少" → **Tool**（模型心算的数字不可信、不可复现）
- "这个趋势结构说明什么" → **Prompt**（需要判断，不需要精确）

本项目的工具都是**独立 CLI，JSON 进 JSON 出**，因此任何 harness 都能调用：

```bash
python tools/validate_artifact.py --run-id 2026-01-02_example --artifact dataset
```

工具只做 `scripts/` 的薄封装，业务逻辑在 scripts 里，方便写单测。
所有工具必须在 `tools/tool_manifest.yaml` 登记，**没登记的不许调用**。

### ④ Contract 契约（`schemas/`）

Agent 之间**不共享内存、不互相调用函数，只交换文件**。JSON Schema 就是这些文件的合同。

> **多智能体系统最常见的失败不是"模型不够聪明"，而是接口错位。**
> 上游改了个字段名，下游读到 `None`，然后一本正经地基于空数据写出一份
> 看起来非常合理的报告——这是最危险的失败模式，因为它不报错。

解法：schema 钉死接口 + 每一步之后强制校验，让错误在发生的那一步就暴露。

### ⑤ Memory 记忆（`memory/`）

Agent 的上下文是一次性的，run 结束就忘光。记忆层负责跨 run 保留。

**记忆的核心是筛选，不是存档。** 分三类：

- `knowledge/` — 稳定知识与踩坑记录（"某数据源财报单位是万元"）
- `decisions/` — 决策记录 ADR（"为什么用文件契约而不是内存传参"）
- `runs/` — 运行摘要（"这只票上周分析过，结论是什么"）

`MEMORY.md` 是**索引**：agent 先读索引，再决定展开读哪个文件，避免撑爆上下文。

**记忆 vs 技能怎么分？** 通用方法论进 skills，本项目的具体经验进 memory。

### ⑥ Workspace 工作区（`workspace/`）

Agent 之间传消息的"信箱"。一次分析 = 一个 run 目录。

用文件而不是内存，换来四件事：**可观察、可复现、可断点续跑、harness 无关**。

> 消息藏在内存里的系统，出了问题只能重跑；
> 消息落在磁盘上的系统，出了问题可以**验尸**。

---

## 四、目录结构

```
A-stock/
├── AGENTS.md                    ★ 任何 coding agent 进来读的第一份文件
├── README.md                    ★ 你正在读的这份（面向人）
├── CLAUDE.md                      Claude Code 入口指针 → 指向 AGENTS.md
├── .claude/README.md              harness 适配说明（如何软链成原生 subagent）
│
├── agents/                      ① 角色定义
│   ├── orchestrator.md
│   ├── data-engineer.md
│   ├── fundamental-analyst.md
│   ├── technical-analyst.md
│   ├── sentiment-analyst.md
│   └── report-writer.md
│
├── skills/                      ② 技能（全部为 skeleton，内容待填）
│   ├── a-share-market-basics/       A 股制度常识与陷阱清单
│   ├── financial-statement-reading/ 财报阅读方法
│   ├── technical-indicators/        指标白名单与读法
│   ├── sentiment-scoring/           情绪量化口径
│   └── report-writing/              报告结构与模板
│
├── tools/                       ③ 工具（CLI，JSON 进 JSON 出）
│   ├── tool_manifest.yaml           工具注册表
│   ├── init_run.py                  ✅ 已实现
│   ├── validate_artifact.py         ✅ 已实现
│   └── fetch_*.py / compute_*.py    ⬜ 空壳，等数据源与策略确定
│
├── schemas/                     ④ 文件契约（JSON Schema）
│   ├── run_manifest.schema.json
│   ├── dataset.schema.json
│   ├── fundamental|technical|sentiment.schema.json
│   └── report.schema.json
│
├── memory/                      ⑤ 记忆
│   ├── MEMORY.md                    索引（agent 先读这个）
│   ├── knowledge/                   知识与踩坑
│   ├── decisions/                   ADR 决策记录
│   └── runs/                        运行摘要
│
├── workspace/                   ⑥ 运行时产物
│   └── runs/2026-01-02_example/     ★ 一份完整的假数据示例 run
│
├── scripts/                     数据层（唯一接触外部世界的代码）
│   ├── contracts.py                 数据契约
│   ├── fetch/ clean/ store/         ⬜ 全部为 NotImplementedError
│   └── run_pipeline.py              不经过 agent 直接跑数据流水线（调试用）
│
├── config/                      配置：股票池、数据源、流水线开关
├── docs/                        教学文档（五篇，见下）
└── tests/                       契约测试与数据层单测
```

---

## 五、数据流：一次完整运行发生了什么

以 `workspace/runs/2026-01-02_example/` 这份示例为例：

```
① orchestrator
   输入：「分析一下示例科技」
   动作：解析成 targets=["000000.SZ"], as_of="2026-01-02"
        → python tools/init_run.py 建目录
   产出：run_manifest.json（5 个步骤全部 pending）

② data-engineer
   读：  run_manifest.json + config/datasources.yaml
   动作：调 fetch_* 工具取行情/财报/新闻/资金流 → 清洗 → 落盘
        主新闻源挂了 → 降级到备用源，记录 fallback_from
        社交舆情源未配置 → 标 status=missing，不编造
   产出：dataset.json（含 provenance 与 quality_flags）

③ 三路并行，只读 dataset.json
   fundamental-analyst → fundamental.json   status=ok（低置信度）
   technical-analyst   → technical.json     status=ok（低置信度）
   sentiment-analyst   → sentiment.json     status=blocked ← 数据缺失，诚实退出

④ report-writer
   读：  三份产物 + manifest
   动作：对照三路结论，识别印证与分歧；情绪面缺失 → 在摘要第一句声明
   产出：report.md（给人看）+ report.json（给程序看）
```

**这个示例刻意保留了一路 `blocked`**，用来演示本系统最重要的一条纪律：

> 数据缺失时，agent 必须输出 `blocked` 并说明原因，
> **绝不用常识、记忆或推测把空缺填上。**
> 一份诚实标注"情绪面缺失"的报告，比一份三路齐全但有一路是编的报告，价值高一个数量级。

打开 `workspace/runs/2026-01-02_example/` 里的六个文件对照着看，
比读十页架构文档更快理解这套系统。

---

## 六、快速开始

### 环境

```bash
git clone <repo> && cd A-stock
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # 数据源确定后再填
cp config/universe.example.yaml    config/universe.yaml
cp config/datasources.example.yaml config/datasources.yaml
```

Python >= 3.10，所有命令从仓库根目录执行。

### 看懂骨架（不需要任何数据源）

```bash
# 1. 读示例 run，看清 agent 之间传的是什么
ls workspace/runs/2026-01-02_example/
cat workspace/runs/2026-01-02_example/report.md

# 2. 校验示例产物是否符合契约（这是唯一能立刻跑通的完整闭环）
python tools/validate_artifact.py --run-id 2026-01-02_example --artifact dataset
python tools/validate_artifact.py --run-id 2026-01-02_example --artifact report

# 3. 新建一个自己的 run 目录
python tools/init_run.py --targets 600519.SH --as-of 2026-01-02 --slug myfirst

# 4. 看数据流水线骨架（会如实告诉你每一步都还没实现）
python scripts/run_pipeline.py --run-id myfirst --codes 600519.SH

# 5. 跑测试
pytest tests/ -v
```

### 让 coding agent 接手

把仓库交给任何 coding agent，只需一句话：

> 读 `AGENTS.md`，然后 <你的任务>

`AGENTS.md` 会告诉它：这是什么、有哪些角色、数据怎么流、该改哪里、不许做什么。

---

## 七、给学生的扩展任务

按难度排序，每一项都对应上面某一层组件。教学文档见 `docs/`。

| # | 任务 | 练的是哪一层 | 难度 |
|---|---|---|---|
| 1 | 读懂示例 run，画出六个文件之间的依赖关系 | ⑥ Workspace + ④ Contract | ★ |
| 2 | 给 `technical.json` 加一个字段，并同步改 schema、agent 定义、示例 | ④ Contract | ★ |
| 3 | 填 `skills/a-share-market-basics/SKILL.md` 的涨跌停与 T+1 小节 | ② Skill | ★★ |
| 4 | 实现 `scripts/fetch/market_data.py:fetch_trading_calendar` | scripts 数据层 | ★★ |
| 5 | 实现 `clean/normalize.py:unify_units` 并补单测 | scripts + tests | ★★ |
| 6 | 把 `compute_indicators.py` 从空壳填成真实实现 | ③ Tool | ★★★ |
| 7 | 新增一个 `moneyflow-analyst`（资金流分析师）agent，走完五步清单 | 全链路 | ★★★ |
| 8 | 设计"三路结论加权成总分"的方案，并论证为什么现在**不**做 | 系统设计判断 | ★★★★ |

第 8 题没有标准答案。提示：加权会把分歧抹平，而分歧恰恰是这套系统最有价值的产出。

---

## 八、设计原则与硬约束

这些不是建议，是**跑起来之后不许为了"让流程跑通"而放宽的红线**
（对应 `config/pipeline.yaml` 的 `policy` 段）：

1. **禁止编造数据。** 数据缺失 → `blocked` + 说明原因。
2. **每条结论必须有 evidence**，evidence 必须指向 `dataset.json` 的具体字段与数值。
3. **三路隔离。** 分析 agent 只读 `dataset.json`，不读彼此的产物，不自己取数。
4. **report-writer 不引入新信息。** 它只做综合，不做分析。
5. **禁止输出买卖建议、目标价、仓位建议。** 本系统输出的是分析，不是投资建议。
6. **改产物结构必须先改 schema。** 顺序反了会造成静默失败。
7. **占位就是占位。** 看到 `TODO(strategy)` / `TODO(datasource)` 不要自作主张填内容，
   这些必须由人确认——这正是本仓库现在留白的原因。

---

## 九、当前留白清单

| 留白项 | 标记 | 卡在哪 | 影响 |
|---|---|---|---|
| 数据源选型（akshare / tushare / 自建） | `TODO(datasource)` | 未决 | `scripts/fetch/*` 全部空实现 |
| 复权口径（前复权 / 后复权） | `TODO(strategy)` | 未决 | 技术面所有指标 |
| 行业分类标准（申万 / 中证 / 证监会） | `TODO(strategy)` | 未决 | 基本面同业对比 |
| 财务指标口径、阈值、打分体系 | `TODO(strategy)` | 未决 | `fundamental.json` 的 score 全为 null |
| 技术指标白名单与参数 | `TODO(strategy)` | 未决 | `technical.json` 只有占位指标 |
| 情绪打分口径、信源权重、时间衰减 | `TODO(strategy)` | 未决 | `sentiment.json` 的分值为 null |
| 三路结论是否加权成总分 | `TODO(strategy)` | 未决 | 当前只做对照展示 |

全仓库搜索留白位置：

```bash
grep -rn "TODO(strategy)\|TODO(datasource)" --include="*.md" --include="*.py" --include="*.yaml" --include="*.json" .
```

---

## 十、免责声明

本项目为**教学示例**，用于演示 agentic workflow 的工程结构。
它不构成任何投资建议、要约或承诺，也不保证任何数据或分析的准确性。
`workspace/runs/2026-01-02_example/` 中的标的「示例科技 000000.SZ」为虚构公司，
全部数值为占位假数据。据本项目产出的任何内容进行投资操作，风险自负。
