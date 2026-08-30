# A-Stock Daily Review · A 股每日复盘多智能体系统

每个交易日收盘后自动跑一遍，产出一份**九章复盘报告**和一个**单文件 HTML 仪表盘**。

数据源是 [AKShare](https://akshare.akfamily.xyz/)（免费、无需 token），
七个 agent 分工协作，彼此**只通过文件交换结果**。

它同时是一个**教学项目**：让学生看清一个 agentic workflow 由哪些零件组成、
零件之间怎么咬合、以及为什么要这样拆。

```bash
# 五秒钟看到最终产出长什么样（不联网）
python tools/astock.py demo
open workspace/runs/2026-08-28_example/report.html
```

对着任何 coding agent（Claude Code / opencode / Codex / Cursor）说一句
「**帮我做今日股市复盘**」，它读完 `AGENTS.md` 就知道该跑什么——
这是本项目的另一半目标：做一个**零背景可接手**的 harness。

---

## 目录

- [A-Stock Daily Review · A 股每日复盘多智能体系统](#a-stock-daily-review--a-股每日复盘多智能体系统)
  - [目录](#目录)
  - [一、报告长什么样：九个章节](#一报告长什么样九个章节)
    - [两种输出](#两种输出)
  - [二、系统架构：七个 Agent](#二系统架构七个-agent)
    - [为什么要拆成七个，而不是写一个超长 prompt](#为什么要拆成七个而不是写一个超长-prompt)
  - [三、六个组件：一个健康的 agentic workflow 有什么](#三六个组件一个健康的-agentic-workflow-有什么)
    - [① Agent 角色定义（`agents/`）](#-agent-角色定义agents)
    - [② Skill 技能（`skills/`）](#-skill-技能skills)
    - [③ Tool 工具（`tools/`）](#-tool-工具tools)
    - [④ Contract 契约（`schemas/`）](#-contract-契约schemas)
    - [⑤ Memory 记忆（`memory/`）](#-memory-记忆memory)
    - [⑥ Workspace 工作区（`workspace/`）](#-workspace-工作区workspace)
  - [四、目录结构](#四目录结构)
  - [五、数据层：AKShare 取回来的十二个块](#五数据层akshare-取回来的十二个块)
    - [三个必须盯住的口径](#三个必须盯住的口径)
    - [AKShare 的已知限制](#akshare-的已知限制)
  - [六、快速开始](#六快速开始)
    - [三份配置，什么时候需要](#三份配置什么时候需要)
    - [持仓每天都在变：用截图更新](#持仓每天都在变用截图更新)
    - [那 positions.yaml 还需要吗？需要，但它不是配置](#那-positionsyaml-还需要吗需要但它不是配置)
    - [还有一份只增不改的持仓流水](#还有一份只增不改的持仓流水)
    - [学生环境的常见坑](#学生环境的常见坑)
    - [先自检 + 看示例（不联网）](#先自检--看示例不联网)
    - [跑真实数据](#跑真实数据)
    - [跑测试](#跑测试)
  - [六点五、任何 coding agent 怎么接手](#六点五任何-coding-agent-怎么接手)
- [六点六、两种执行方式：谁来做那五步判断](#六点六两种执行方式谁来做那五步判断)
    - [一句话就能启动](#一句话就能启动)
    - [唯一需要记住的循环](#唯一需要记住的循环)
    - [为什么要做成状态机](#为什么要做成状态机)
    - [多 harness 适配是生成的](#多-harness-适配是生成的)
  - [七、四种运行方式](#七四种运行方式)
  - [八、设计原则与硬约束](#八设计原则与硬约束)
  - [九、当前留白：需要你填的阈值](#九当前留白需要你填的阈值)
  - [十、给学生的扩展任务](#十给学生的扩展任务)
  - [十一、免责声明](#十一免责声明)

---

## 一、报告长什么样：九个章节

| # | 章节 | 回答什么 | 产出者 |
|---|---|---|---|
| ① | **市场总览** | 四大指数开收高低、两市成交额增减、涨跌家数、涨停跌停、炸板率、连板晋级率、大盘状态、情绪阶段 | `market-analyst` |
| ② | **指数复盘** | 早盘/上午/午后/尾盘四段拆解、指数为什么涨跌、谁在共振、谁在逆指数走强、谁在拖累、关键支撑压力 | `market-analyst` |
| ③ | **板块与题材** | 主线/次主线/指数共振/逆指数抱团/退潮风险五类方向，每类的阶段、龙头中军梯队、强弱依据、明日验证条件 | `sector-analyst` |
| ④ | **我的持仓计划** | 每只票一张卡片：地位、三重相对强弱、买入逻辑是否仍成立、明日强中弱三情景、压力支撑失效位、唯一动作、优先级 + **七条行为自检** | `position-advisor` |
| ⑤ | **明日预案** | 指数强中弱三套脚本、仓位上限、禁止事项、按五个时间窗口拆的 if-then 执行清单 | `report-writer` |
| ⑥ | **新闻与公告** | 去重分层后的利好/中性/利空，外围科技表现，**昨日新闻的次日价格验证** | `news-analyst` |
| ⑦ | **风险与纪律** | 总仓位、单票与同题材集中度、单笔风险是否超账户 0.5%、当日最大允许亏损、是否停止新增交易 | `position-advisor` |
| ⑧ | **最终执行面板** | 一屏八项：今日定性、明日主线与风险、优先保留谁、优先处理谁、每只持仓唯一动作、三个观察信号、一句纪律 | `report-writer` |
| ⑨ | **运行说明** | 模式、日期、数据源与口径、质量标记 | `orchestrator` |

**章节八放在报告最上面。** 因为第二天早上 9:25，你只有时间看那一屏。

### 两种输出

- `report.md` —— 存档、可 diff、可发给别人看
- `report.html` —— 单文件深色/浅色自适应仪表盘：KPI 卡、情绪阶段步进条、连板梯队条形图、
  板块方向卡、持仓卡、行为自检清单、风险表。**不依赖任何 CDN**，双击就能打开。

---

## 二、系统架构：七个 Agent

```
                      ┌──────────────────┐
                      │  orchestrator    │  总控：定模式与日期、派发、校验产物
                      └────────┬─────────┘
                               │ run_manifest.json
                               ▼
                      ┌──────────────────┐
                      │  data-engineer   │  AKShare 取数 → 清洗 → 落盘
                      └────────┬─────────┘
                               │ dataset.json  ← 本次运行唯一的"事实来源"
                               ▼
                      ┌──────────────────┐
                      │  market-analyst  │  ① 市场总览　② 指数复盘
                      └────────┬─────────┘
                               │ market.json
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌──────────────────┐        ┌──────────────────┐
        │  sector-analyst  │        │   news-analyst   │   ← 可并行
        │  ③ 板块与题材     │        │   ⑥ 新闻与公告    │
        └────────┬─────────┘        └────────┬─────────┘
                 └─────────────┬─────────────┘
                               ▼
                      ┌──────────────────┐
                      │ position-advisor │  ④ 持仓计划　⑦ 风险纪律
                      └────────┬─────────┘
                               ▼
                      ┌──────────────────┐
                      │  report-writer   │  ⑤ 明日预案　⑧ 执行面板　+ 成文与渲染
                      └────────┬─────────┘
                               ▼
                report.json / report.md / report.html
```

### 为什么要拆成七个，而不是写一个超长 prompt

| 问题 | 单 agent 的表现 | 多 agent 的解法 |
|---|---|---|
| **上下文稀释** | 指数、涨停池、板块、持仓、新闻全塞进一个窗口，哪一路都做不深 | 每个 agent 只拿自己需要的那部分 |
| **无法定位错误** | 报告写错了，不知道是数据错、判断错、还是行文时编的 | 每步产物单独落盘并校验，错在哪一步一目了然 |
| **判断互相污染** | 看到"某板块涨停 9 只"再去看持仓，会不自觉替持仓找理由 | 板块判断先独立完成，持仓分析才引用它 |
| **无法迭代** | 改一处 prompt，全盘行为都变 | 改一个 agent 只影响那一章 |

其中第三条是本系统最关键的设计：
**板块强弱要在不知道"我持有什么"的前提下判断出来。**
顺序反了，系统就会变成一个替你的持仓找理由的机器——那比没有系统更危险。

---

## 三、六个组件：一个健康的 agentic workflow 有什么

这是本项目最想让学生带走的一张表。
**一个能长期跑下去的 agent 系统，不是只有 prompt，而是由六层组成：**

```
┌─────────────────────────────────────────────────────────────┐
│  ①  Agent 角色定义     agents/     "我是谁，我读什么，我写什么"   │
├─────────────────────────────────────────────────────────────┤
│  ②  Skill 技能         skills/     "这类事情的正确做法是什么"     │
├─────────────────────────────────────────────────────────────┤
│  ③  Tool 工具          tools/      "我怎么真的动手，而不是空谈"   │
├─────────────────────────────────────────────────────────────┤
│  ④  Contract 契约      schemas/    "我们之间传的东西长什么样"     │
├─────────────────────────────────────────────────────────────┤
│  ⑤  Memory 记忆        memory/     "上次踩的坑这次别再踩"        │
├─────────────────────────────────────────────────────────────┤
│  ⑥  Workspace 工作区   workspace/  "过程和产物都看得见、可复现"   │
└─────────────────────────────────────────────────────────────┘
                        ↑
              scripts/ 数据层：唯一接触外部世界的代码
```

### ① Agent 角色定义（`agents/`）

一个 agent = **一段角色 prompt + 一份输入输出契约**。不含算法，不含代码。

```yaml
---
name: sector-analyst
depends_on: [data-engineer, market-analyst]
reads:  [dataset.json, market.json]          # 只读这些，多一个都不许读
writes: [sectors.json]                       # 只写这个
schema: schemas/sectors.schema.json
skills: [sector-ladder, market-emotion-cycle]
tools:  [validate_artifact]
---
```

**为什么要写死 reads/writes？** 不写死，模型就会去读它"觉得有用"的东西，
于是板块分析师看到了你的持仓，然后开始替你的票说话。
**约束不是限制模型，是保护设计。**

### ② Skill 技能（`skills/`）

技能是可复用的方法论。本项目的九个技能，是把"短线复盘该怎么做"拆开写成的：

| 技能 | 解决什么问题 |
|---|---|
| `market-emotion-cycle` | 冰点/修复/主升/分歧/退潮怎么判、五个常见误判 |
| `intraday-rhythm` | 日内四段各自的含义、六种常见形态、归因方法 |
| `sector-ladder` | **不看涨幅榜**怎么判板块强弱（五维法）、梯队角色、验证条件怎么写才可证伪 |
| `position-review` | 持仓卡片各字段的口径、七条行为自检的判定方法 |
| `risk-discipline` | 仓位与单笔风险的计算顺序、同题材是隐形杠杆、什么情况该停手 |
| `news-triage` | 信源分层、去重、三分类、**次日验证** |
| `report-writing` | 九章结构、语言规范、预案要写成 if-then |
| `positions-import` | 券商截图字段识别、七个陷阱、算术自检 |
| `a-share-market-basics` | 涨跌停、T+1、短线术语、数据口径陷阱 |

> 教学要点：这就是**上下文工程**。上下文窗口是稀缺资源，
> 技能层的本质是一个*按需检索的知识索引*，不是一本一次性读完的百科。

### ③ Tool 工具（`tools/`）

Skill 让 agent"知道怎么做"，Tool 让 agent"真的能做"。

**判断标准：这件事是否需要可复现的精确结果？**

- "炸板率是多少" → **Tool**（模型口算的数字每次都不一样，报告就不可复现了）
- "这个炸板率说明情绪到哪一步了" → **Prompt**（需要判断）

九个工具都是独立 CLI，因此任何 harness 都能调用。
其中 **`astock` 是统一入口**，它把其余几个串成一条带状态的流水线：

```bash
python tools/astock.py doctor | review | next | done <agent> | status | demo
```

底层工具（一般不用直接调）：

```bash
python tools/fetch_dataset.py     --run-id ... --as-of ...    # AKShare 取数
python tools/import_positions.py  --json '...' [--apply]       # 截图 → positions.yaml
python tools/compute_risk.py      --run-id ...                # 仓位与单笔风险
python tools/render_report.py     --run-id ...                # md + html
python tools/validate_artifact.py --run-id ... --artifact ... # schema 校验
python tools/sync_harness.py                                  # 生成 harness 适配层
```

### ④ Contract 契约（`schemas/`）

> **多智能体系统最常见的失败不是"模型不够聪明"，而是接口错位。**
> 上游改了个字段名，下游读到 `None`，然后一本正经地基于空数据写出一份
> 看起来非常合理的报告——这是最危险的失败模式，因为它不报错。

解法：JSON Schema 钉死接口，每一步之后强制校验（`validate_after_each_step: true`）。

契约里还编码了一些**硬约束**，测试会守着：
三个观察信号不多不少、每只持仓唯一动作、七条行为自检一条不少。

### ⑤ Memory 记忆（`memory/`）

Agent 的上下文是一次性的，run 结束就忘光。记忆层负责跨 run 保留：

- `knowledge/akshare-gotchas.md` —— AKShare 的接口限制与踩坑
- `knowledge/conventions.md` —— 全项目统一口径（复权、单位、成交额算法…）
- `decisions/` —— ADR：为什么用文件契约、为什么选 AKShare
- `runs/` —— 每次运行的摘要（news-analyst 做次日验证时要读昨天的）

`MEMORY.md` 是**索引**：agent 先读索引，再决定展开哪个文件，避免撑爆上下文。

### ⑥ Workspace 工作区（`workspace/`）

Agent 之间传消息的"信箱"。用文件而不是内存，换来四件事：
**可观察、可复现、可断点续跑、harness 无关**。

> 消息藏在内存里的系统，出了问题只能重跑；
> 消息落在磁盘上的系统，出了问题可以**验尸**。

---

## 四、目录结构

```
A-stock/
├── AGENTS.md                    ★ 任何 coding agent 进来读的第一份文件（第 0 节是意图路由表）
├── README.md                    ★ 你正在读的这份（面向人）
├── CLAUDE.md                    Claude Code 入口指针 → AGENTS.md
├── Makefile                     给人用的快捷方式：make doctor / review / demo / test
│
├── .claude/ .opencode/          ← 各 harness 的适配层，**全部由 sync_harness.py 生成**
├── .cursor/  .codex/               里面只有路由信息和指针，不放内容
│
├── agents/                      ① 七个角色定义
│   ├── orchestrator.md              总控 + 四种运行模式
│   ├── data-engineer.md             AKShare 取数
│   ├── market-analyst.md            章节①②
│   ├── sector-analyst.md            章节③
│   ├── news-analyst.md              章节⑥
│   ├── position-advisor.md          章节④⑦
│   └── report-writer.md             章节⑤⑧ + 成文
│
├── skills/                      ② 九个技能包
├── tools/                       ③ 九个 CLI 工具（全部已实现）
│   ├── astock.py                    ★ 统一入口 + 状态机 + api 模式执行器
│   ├── sync_harness.py              生成各 harness 的适配层
│   ├── fetch_dataset.py             AKShare 取数
│   ├── import_positions.py          截图 → positions.yaml（带算术自检）
│   ├── compute_risk.py              仓位与单笔风险
│   ├── render_report.py             report.json → md + html 仪表盘
│   ├── validate_artifact.py         schema 校验
│   ├── init_run.py / make_demo_run.py
├── schemas/                     ④ 七份 JSON Schema
├── memory/                      ⑤ 知识 / ADR / 运行流水
├── workspace/runs/              ⑥ 运行产物
│   └── 2026-08-28_example/          ★ 一份完整的虚构示例（含渲染好的 HTML）
│
├── scripts/                     数据层（AKShare）
│   ├── ak_client.py                 重试 + 缓存 + 响亮失败
│   ├── llm.py                       provider 无关的模型调用（OpenAI 兼容 + Anthropic）
│   ├── agent_runner.py              提示词组装 + schema 校验 + 重试
│   ├── fetch/                       calendar / market / breadth / sectors / stocks / news
│   ├── clean/derive.py              派生指标与交付前自检
│   ├── positions.py                 读取校验持仓 + 按收盘价估值
│   └── build_dataset.py             主入口
│
├── config/
│   ├── pipeline.yaml                四种运行模式、并行分组、硬约束
│   ├── models.yaml.example          ★ 模型 provider 与档位（api 模式用）
│   ├── positions.example.yaml       持仓模板
│   └── thresholds.example.yaml      ★ 判定阈值，唯一需要你反复调的文件
│
├── docs/                        教学文档五篇
└── tests/                       契约测试 + 派生指标测试（全 mock，不联网）
```

---

## 五、数据层：AKShare 取回来的十二个块

| block | AKShare 接口 | 服务章节 |
|---|---|---|
| `calendar` | `tool_trade_date_hist_sina` | 全部（判断是否交易日） |
| `index_spot` / `index_hist` | `index_zh_a_hist` | ①② |
| `index_intraday` | `index_zh_a_hist_min_em` | ②（日内四段） |
| `breadth` | `stock_market_activity_legu` + `stock_zt_pool_*` | ① |
| `limit_pool` | `stock_zt_pool_em` / `_zbgc_` / `_dtgc_` / `_previous_` | ①③ |
| `sectors` | `stock_board_industry_name_em` + `stock_board_concept_name_em` | ③ |
| `sector_flow` | `stock_sector_fund_flow_rank` | ③ |
| `holdings` | `stock_zh_a_hist`（qfq） | ④⑦ |
| `news` | `stock_info_global_cls` + `stock_info_global_em` | ⑥ |
| `announcements` | `stock_notice_report` | ⑥ |
| `northbound` | `stock_hsgt_fund_flow_summary_em` | ①③（可选） |

### 三个必须盯住的口径

1. **两市成交额不能把四个指数的成交额相加。**
   创业板指、科创50 的成交额已包含在深市、沪市里，相加会重复计算约 30%。
   算法在 `scripts/clean/derive.py:two_market_amount`，有测试守着。
2. **复权固定 `qfq`（前复权）**，与看盘软件一致。
3. **炸板率与晋级率必须由明细算出**：
   炸板率 = 炸板 /（涨停 + 炸板）；晋级率 = 昨日涨停股中今日仍涨停的比例。

### AKShare 的已知限制

- 分时接口**只保留最近几个交易日** → 历史日期拿不到日内四段（此时章节②的四段标 blocked，
  **绝不许用全天涨跌幅倒推**）
- 炸板池/跌停池**只有最近 30 个交易日**
- 涨跌家数是**实时快照** → 只在收盘后跑 `close` 模式

完整清单见 `memory/knowledge/akshare-gotchas.md`。

---

## 六、快速开始

```bash
git clone <repo> && cd A-stock
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 或者一条 make setup 全做了
cp config/positions.example.yaml  config/positions.yaml   # 填你的持仓
cp config/thresholds.example.yaml config/thresholds.yaml  # 填判定阈值
cp .env.example .env                                      # 填 ASTOCK_ACCOUNT_EQUITY
```

### 三份配置，什么时候需要

| 文件 | 不配会怎样 | 什么时候必须配 |
|---|---|---|
| `config/positions.yaml` | 章节④⑦为空，**①②③⑥⑤⑧ 照常出** | 想看持仓分析与风险纪律时 |
| `.env` 的 `ASTOCK_ACCOUNT_EQUITY` | 风险章节只能给**比例**，给不出**金额**（不许拿持仓市值当账户规模估算） | 想看"跌到失效位亏多少钱""是否超 0.5%"时 |
| `config/thresholds.yaml` | 自动回退到 `thresholds.example.yaml`，阈值全是 `null`，判断由模型自己拿捏 | 想让情绪阶段与板块强弱的判定**可复现**时 |

**三份都不配也能跑通全流程**——但那份报告只有"市场层"是完整的。
先跑一次 `python tools/astock.py demo` 看产出，再决定要不要配，是更省事的顺序。

`.env` 会被**自动加载**（`scripts/env.py`，纯标准库），不需要 `source .env`。
真实环境变量优先于 `.env`，所以 CI 里可以直接用环境变量覆盖。


### 持仓每天都在变：用截图更新

不用手改 yaml。截一张券商 App 的持仓页发给 coding agent：

```
（上传截图）帮我更新持仓，然后跑复盘
```

agent 会读图 → 调 `tools/import_positions.py` 预览 → 你确认 → `--apply` → 跑 `--mode positions`。

**它不会盲信自己读出来的数字。** 工具用券商已经算好的市值与盈亏反验：

```
shares × price          ≈ market_value
(price − cost) × shares ≈ pnl
```

成本价读错一位，第二条立刻不成立，工具会指出"多半是成本价读错了"并拒绝落盘。
——因为成本读错的后果不是报错，而是章节⑦的单笔风险与 0.5% 判断**全错但看起来很专业**。

**截图给不了的东西不会被编出来。** `thesis`（买入逻辑）与 `stop_level`（失效位）
不在截图里，工具按代码匹配保留旧文件里的；新标的会被列出来，
由 agent **回头问你**——章节④的第一个问题就是"买入逻辑是否仍成立"，
这个字段一旦是编的，整份持仓分析就失去意义了。

方法与七个陷阱（可用≠持仓、摊薄成本≠持仓成本、金额被隐藏、混进可转债…）
见 [`skills/positions-import/SKILL.md`](skills/positions-import/SKILL.md)。
截图含真实账户信息，`.gitignore` 已挡掉常见图片格式。

### 那 positions.yaml 还需要吗？需要，但它不是配置

**截图只能给出四个字段**：代码、名称、成本、数量。
而 `positions.yaml` 里真正值钱的是截图里**永远不会有**的两个：

```yaml
thesis: "题材启动第二天打板做龙头，看三日内能否走出高度"   # 当初为什么买
stop_level: 11.50                                        # 破了就承认判断错了
```

章节④要回答的第一个问题就是"**买入逻辑是否仍成立**"。
没有 `thesis`，这个问题无从谈起；而如果让 AI 替你编一个，
它会编一个**恰好还成立**的理由——那正是你花钱买这套系统要避免的事。

所以分工是：**截图管数字，文件管你的判断。**
导入工具按代码匹配，只更新成本与数量，人写的字段原样保留。

### 还有一份只增不改的持仓流水

`memory/positions_history.jsonl`：每次导入持仓或跑复盘都追加一条快照
（成本、数量、当时的浮亏、thesis、失效位、交易模块）。

它把三条最难自查的行为检查，从"靠回忆"变成"有证据"：

| 信号 | 对应自检 | 证据 |
|---|---|---|
| `加仓` | 亏损补仓 | 加仓前是不是已经浮亏、亏多少 |
| `清仓后买回` | 卖飞后追回 | 当时卖在什么价、现在买在什么价 |
| `买入逻辑被改写` | 短线失败后改成长线 | 原文 → 现文，以及改写时是否浮亏 |
| `失效位下移` | （止损被悄悄取消） | 11.50 → 10.00 |

**人恰恰会在这三件事上骗自己**——改完 thesis 之后，昨天写的是什么就没人记得了。
所以这份流水只追加、不修改、不删除：**改过的历史就不是历史了。**

信号只陈述"发生了什么"，**定性仍然由分析 agent 做**——
同样是加仓，主升期加在强势票上和浮亏时摊成本是两回事，代码分不出来。

### 学生环境的常见坑

| 症状 | 原因 | 怎么修 |
|---|---|---|
| `doctor` 说 Python 版本旧 | macOS 自带 python 是 3.9，`.venv` 是照它建的 | **光装新 Python 没用**，venv 必须重建：`rm -rf .venv && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| `pip install` 报 `jsonpath` 编译失败 | pip 太旧 | `pip install --upgrade pip setuptools wheel` 后重装 |
| 装完依赖 `import akshare` 还是失败 | 装到系统 python 去了，不在 venv 里 | 确认提示符前面有 `(.venv)`，再 `which python3` 看路径 |
| `ProxyError ... 127.0.0.1:xxxx Connection refused` | **开着代理但代理客户端没运行**（VPN 关了、代理设置还在） | 三选一：开代理客户端 / `unset http_proxy https_proxy all_proxy` / `ASTOCK_DIRECT=1` |
| 上面三招都试了还是报代理错 | macOS 的**系统代理**独立于环境变量，VPN 退出时不会清掉 | 系统设置 → 网络 → Wi-Fi → 详细信息 → 代理 → 关掉「网页代理」和「SOCKS 代理」 |
| 第一步交易日历秒过、第二步却连不上 | 日历命中了本地缓存，看起来"网络是好的" | 缓存已加 30 分钟 TTL；`--no-cache` 可强制重取 |
| `AKShare 网络连通` 失败，直连也不行 | 可能是 DNS、系统代理、或 **IPv6 出口坏掉** | **先跑 `python tools/net_check.py`**——它逐个域名测 DNS(A/AAAA) / 当前设置 / 强制直连 / 仅 IPv4，直接告诉你是哪一类 |
| 新浪能连、东财连不上 | 典型的 IPv6 出口故障：有 AAAA 记录的站点超时 | `ASTOCK_IPV4_ONLY=1 python tools/astock.py review`（系统也会自动降级重试） |
| `ConnectTimeout` 在 `80.push2.eastmoney.com` | akshare 取指数 K 线前会先向这台机器拉一张**多余的**对照表，而东财各分片主机可达性差别很大 | 已绕开（市场号写死在 `INDEX_MARKET_ID`）；东财整体不通时退到新浪，但成交额会缺失 |
| `RemoteDisconnected` / `Connection aborted` | **连上了但被服务器掐掉**。akshare 有些接口裸调用不带 UA，东财会断开；也可能是代理线路把境内站绕到了境外 | 已自动补浏览器请求头 + 被掐时自动绕代理重试；仍不行跑 `net_check.py` 看「裸UA」那一列 |
| 填了 `.env` 但读不到 | —— | 本项目会自动加载 `.env`，**不用 `source`**；检查是不是写成了 `ASTOCK_ACCOUNT_EQUITY = 200000`（等号两边不能有空格） |

**Python 3.9 能跑**——本项目刻意没用 `match` 语句和运行时联合类型，
`tests/test_py_compat.py` 会守住这条。所以学生卡在版本上时，
先让他跑起来、看到产出，再谈升级。

### 先自检 + 看示例（不联网）

```bash
python tools/astock.py doctor    # 依赖、配置、网络逐项检查，缺什么直接告诉你怎么修
python tools/astock.py demo      # 生成全虚构示例并渲染
open workspace/runs/2026-08-28_example/report.html
```

这份示例刻意做了三件事，值得对照着看：

1. **保留一块数据缺失**（北向资金）→ 演示"缺了一块时系统如何诚实降级"
2. **触发两条行为自检** → 演示这个系统会说不爱听的话
3. **有一笔风险超限** → 演示"已经超出纪律线的存量仓位该怎么处理"

### 跑真实数据

```bash
python tools/astock.py review          # 日期自动推断（收盘后算今天，否则算上一个工作日）
python tools/astock.py review --as-of 2026-08-26 --mode close   # 指定
```

然后按 `next` / `done` 的循环走完。或者直接把仓库交给任何 coding agent，一句话：

> 帮我做今日股市复盘

也可以用 `make`：`make doctor` / `make review` / `make next` / `make demo` / `make test`。

### 跑测试

```bash
pytest tests/ -q      # 143 项，全部 mock，不访问网络
```

---

## 六点五、任何 coding agent 怎么接手

### 一句话就能启动

用户说「帮我做今日股市复盘」，agent 读 `AGENTS.md` 第 0 节的意图路由表，
就知道该跑 `python tools/astock.py review`。

`AGENTS.md` 被 Codex、opencode 自动读取；Claude Code 走 `CLAUDE.md` 指过去；
Cursor 有一条 `alwaysApply` 的常驻规则。四家都能收到同一句指令。

### 唯一需要记住的循环

```bash
python tools/astock.py doctor     # 首次：依赖、配置、网络逐项自检
python tools/astock.py review     # 开始：建 run + AKShare 取数
python tools/astock.py next       # ← 我现在该做什么
#     照着它说的做，写出那一份产物
python tools/astock.py done <agent>   # 校验产物，通过则自动打印下一步
#     回到 next，直到「全部完成」
```

`next` 的输出长这样：

```
┌─ 第 2/6 步 · market-analyst（市场分析师）
│  run 2026-08-28_close · 分析日 2026-08-28 · 模式 close
│
│  ①  先读角色定义
│     agents/market-analyst.md   ← 职责、工作步骤、边界与禁止事项都在里面
│
│  ②  加载技能（方法论在这里，不要自己发明判断标准）
│     skills/market-emotion-cycle/SKILL.md
│     skills/intraday-rhythm/SKILL.md
│     skills/a-share-market-basics/SKILL.md
│
│  ③  只读这些输入（多一个都不许读）
│     ✓ workspace/runs/2026-08-28_close/dataset.json
│
│  ④  只写这个产物
│     workspace/runs/2026-08-28_close/market.json
│     结构见 schemas/market.schema.json
│     照着抄 workspace/runs/2026-08-28_example/market.json（虚构示例，字段齐全）
│
│  ⑤  写完自检并推进
│     python tools/astock.py done market-analyst --run-id 2026-08-28_close
│
│  纪律：数据缺了就写 blocked + 原因，不许编；
│        每条结论都要能追溯到 dataset.json 的具体字段。
└─
```

产物没通过 schema 校验时，`done` 会把具体哪个字段不对打出来，并指向示例文件——
agent 改完再跑一次即可。

### 为什么要做成状态机

**流程状态存在 `run_manifest.json` 里，不在 agent 的上下文里。**

所以：上下文被截断了不影响、换一个 agent 接手能续上、今天跑一半明天继续也能续上。
每一步都重新问一次"我在哪、下一步是什么"，比让 agent 记住六步流程可靠得多。

### 多 harness 适配是生成的

```
agents/*.md + AGENTS.md          ← 唯一事实来源
        ↓ tools/sync_harness.py
.claude/  .opencode/  .cursor/  .codex/    ← 薄适配层，全部生成，不要手改
```

适配文件里**不放内容**，只放路由信息和一个指针（"完整定义在 agents/xxx.md"）。
加一个新 harness 只需在 `sync_harness.py` 里加十行。
`tests/test_harness.py` 会检查两边同步，有人手改生成物就报错。

详见 [`docs/06-harness适配.md`](docs/06-harness适配.md)。

## 六点六、两种执行方式：谁来做那五步判断

系统里有九个章节，其中**五步是判断**（市场、板块、新闻、持仓、报告），
剩下的取数、算指标、算风险、渲染都是确定性代码。

那五步判断可以交给两种执行者，**角色定义、技能、契约完全共用**：

| | harness 模式 | api 模式 |
|---|---|---|
| 谁在做判断 | 你所在的 coding agent（Claude Code / opencode / Codex） | `config/models.yaml` 里配的模型 |
| 怎么跑 | `astock review` → `next` → `done` 循环 | `astock run` 一条命令 |
| 需要 API key | **不需要** | 需要（本地 Ollama 除外） |
| 能否无人值守 | 不能，要人坐在终端前 | **能**，可以挂定时任务 |
| 花费 | 占用你编码 agent 的额度 | 每次复盘 5 次调用，提示词合计约 **12 万字符**（按各家分词器大致 **6–8 万输入 token**） |
| 适合 | 边跑边改、教学演示、调阈值 | 每天例行跑、不想占编码额度 |

> 这是我一开始的设计缺陷：默认了"你一直坐在某个编码 agent 里"。
> 那既跑不了章节九说的"收盘后自动运行"，对每天要跑的人也太贵。

### api 模式怎么配

```bash
cp config/models.yaml.example config/models.yaml
# 在里面挑一个 provider，把对应的 key 填进 .env
python tools/astock.py doctor      # 会告诉你当前处于哪种模式、缺什么
python tools/astock.py run         # 取数 + 五步分析 + 渲染，一条命令跑完
```

具体多少钱取决于你选哪个模型，`astock run` 跑完会把真实用量打出来并写进 `run_manifest.json`。

**只要是 OpenAI 兼容的接口就能接**——DeepSeek、通义、Kimi、智谱、OpenRouter，
以及本地的 Ollama / vLLM（零 API 成本）。Anthropic 原生协议单独做了一条分支。
不装任何厂商 SDK，只用 `requests`：每多一个 SDK 就多一次版本冲突，而这些协议本身是稳定的。

### 三个省钱的机制

**① 按档位分模型。** `agents/*.md` 的 frontmatter 里写的是**档位**不是模型名：

```yaml
model: reasoning     # market / sector / position / report
model: default       # news / data
```

`models.yaml` 的 `tiers` 把档位映射到具体模型。所以"新闻分诊用便宜模型、
情绪阶段判断用强模型"这个决定写在角色定义里，换模型只改三行，不动任何 agent。

**② 只喂该看的数据。** 每个 agent 的 frontmatter 声明 `dataset_blocks`：

```yaml
dataset_blocks: [calendar, sectors, sector_flow, limit_pool, breadth]
```

板块分析师拿不到 `holdings`——**既省 token，也让"不许替持仓找理由"从一句纪律变成一个机制**。
以前那只是 agent 定义里的一句话，现在是代码层面的事实（`tests/test_agent_runner.py` 守着）。

**③ 关掉示例产物。** `models.yaml` 的 `runtime.include_example_artifact: false`
能省约 21% 输入 token——代价是模型少了一份字段形状参考，产物容易缺字段、多重试一轮。
便宜模型建议留着，强模型可以关掉。

**④ 预算闸门。** `models.yaml` 的 `budget` 段设 token / 花费上限，超了立刻停在当前步骤。
跑飞的循环比跑错的结论更可怕。

价格**不写死在代码里**——模型价格随时在变，写死的半年后就是错的。
token 用量永远统计，价格由你在 `models.yaml` 里填；没填就只报用量。

### 每天自动跑（章节九）

api 模式打通之后，「每个交易日收盘后自动运行」才真正可行：

```cron
# 交易日 15:40 收盘复盘
40 15 * * 1-5  cd ~/Code/A-stock && .venv/bin/python tools/astock.py run --mode close
# 次日 08:45 盘前更新
45 8  * * 1-5  cd ~/Code/A-stock && .venv/bin/python tools/astock.py run --mode premarket
```

非交易日会在取数阶段自己停下（交易日历会报 error），不会产出一份没有数据支撑的复盘。

### 两种模式可以混用

api 模式跑到某一步失败了，可以切回手工：

```bash
python tools/astock.py next                    # 看看卡在哪一步、要读什么
# 你自己（或你的 coding agent）完成那一步
python tools/astock.py done sector-analyst     # 校验通过后继续
python tools/astock.py run                     # 剩下的步骤接着自动跑
```

因为流程状态在 `run_manifest.json` 里，两种执行者看到的是同一份状态。

## 七、四种运行方式

| 模式 | 时机 | 做什么 |
|---|---|---|
| `close` | 交易日 15:30 后 | 全量九章 |
| `premarket` | 次日 08:45 | 用隔夜消息更新章节⑤⑥⑧，①②③沿用昨日 |
| `positions` | 你改了 `positions.yaml` | 只重跑章节④⑦⑧ |
| `weekly` | 周末 | 周复盘 + 下周三情景预案 + 本周纪律统计 |

配置在 `config/pipeline.yaml`。想做成定时自动跑，用 cron 调 `orchestrator` 即可。

---

## 八、设计原则与硬约束

这些不是建议，是**跑起来之后不许为了"让流程跑通"而放宽的红线**
（对应 `config/pipeline.yaml` 的 `policy` 段，测试会检查）：

1. **禁止编造数据。** 数据缺失 → `blocked` + 说明原因，报告开头第一句声明。
2. **每条结论必须有 evidence**，指向 `dataset.json` 的具体字段与数值。
3. **每只持仓只能有一个动作。** 写"可以持有也可以减半"等于没给建议——
   第二天早上 9:30 的人没时间做二选一。
4. **禁止输出买卖建议、目标价、荐股。** 本系统输出的是分析与纪律检查，
   卡片上的"动作"是你给自己定的规则，不是"应该这么操作"。
5. **非交易日不出当日复盘。**
6. **改产物结构必须先改 schema。** 顺序反了会造成静默失败。
7. **传闻永远是传闻。** `certainty: rumor` 不许升级为 fact，哪怕后来兑现了。
8. **七条行为自检一条都不能跳。** 说得客气等于没说。

---

## 九、当前留白：需要你填的阈值

代码全部实现完了。**需要填的不是代码，是判断标准。**

打开 `config/thresholds.yaml`：

| 留白项 | 说明 |
|---|---|
| 情绪阶段阈值 | 晋级率、炸板率、涨停家数、最高板各自的分界线 |
| 板块强弱阈值 | 几只涨停算"联动"、多大市值算"容量票"、超额多少算"逆指数" |
| 风险线 | 单票权重上限、同题材上限、当日最大亏损（单笔 0.5% 已定） |
| 各情绪阶段的仓位上限 | 冰点/修复/主升/分歧/退潮各允许多少仓位 |

**为什么这些留给你填？** 因为框架是通用的，数值是个人的。
"炸板率超过 40% 算退潮"这句话，对不同资金量、不同交易风格的人不一样。

**建议不要拍绝对数**，用**过去 60 个交易日的分位数**：
A 股股票总数在变、注册制后涨停家数中枢也在变，写死的绝对值一年后就过期了。

全仓库搜留白位置：

```bash
grep -rn "TODO(strategy)" --include="*.md" --include="*.yaml" .
```

---

## 十、给学生的扩展任务

| # | 任务 | 练的是哪一层 | 难度 |
|---|---|---|---|
| 1 | 读示例 run 的七个 JSON，画出它们的依赖关系图 | ⑥ + ④ | ★ |
| 2 | 给 `sectors.json` 加一个字段，并同步改 schema、agent 定义、示例、测试 | ④ | ★ |
| 3 | 填 `thresholds.yaml` 的情绪阶段阈值，说明你为什么选这些数 | ② | ★★ |
| 4 | 给 `scripts/fetch/` 加一个新数据块（比如两融余额），走完四步 | 数据层 | ★★ |
| 5 | 给 `render_report.py` 加一张图（比如成交额 20 日趋势） | ③ | ★★ |
| 6 | 实现 `weekly` 模式的"本周纪律统计"：读一周的 `memory/runs/` 算触发率 | ⑤ | ★★★ |
| 7 | 新增 `moneyflow-analyst`（资金流分析师），走完 `docs/03` 的六步 | 全链路 | ★★★ |
| 8 | 加入交易流水 `trades.yaml`，让"卖强留弱""亏损补仓""卖飞追回"三条自检自动化 | 全链路 | ★★★★ |
| 9 | 连续两周做 `news.json` 的次日验证，统计你的解读准确率 | 系统性反思 | ★★★★ |
| 10 | 让 opencode 或 Codex 零背景接手跑一次完整复盘，把卡住的地方补进 `AGENTS.md` | harness 设计 | ★★★ |
| 11 | 给 `sync_harness.py` 加一个新 harness（如 Windsurf），跑通 `--check` | harness 设计 | ★★ |

第 9 题没有代码量，但它是这个系统里**唯一能真正提高你水平**的一题。

---

## 十一、免责声明

本项目为**教学与个人复盘工具**，不构成任何投资建议、要约或承诺。
所有数据来自公开渠道的程序化处理，可能存在缺失、延迟或错误；
分析方法存在局限性，`config/thresholds.yaml` 中的阈值由使用者自行设定。

`workspace/runs/2026-08-28_example/` 中的全部标的、板块、新闻与数值均为**虚构**，
`999001.SZ 示例科技`、`999002.SH 示例材料` 不是真实股票。

据本项目产出的任何内容进行投资操作，风险自负。
