# AGENTS.md — 本仓库的 Agent 操作手册

> 本文件是**任何 coding agent（Claude Code / opencode / Cursor / Codex …）进入本仓库后必须读的第一份文件**。
> 读完本文件，你应当在**不了解任何前置背景**的情况下，知道：
> 用户说一句「帮我做今日股市复盘」时该跑什么命令、这仓库是什么、有哪些角色、数据怎么流、你该改哪里。
>
> **赶时间的话只读第 0 节。** 那一节足够你把一次复盘从头跑到尾。

---

## 0. 用户说什么 → 你做什么

| 用户说 | 你做 |
|---|---|
| 「帮我做今日股市复盘」「复盘一下今天大盘」「今天 A 股怎么样」「盘后复盘」「生成复盘报告」 | `python tools/astock.py review` 然后走下面的循环 |
| 「看看我的持仓」「我的票怎么办」（当天已跑过复盘） | `python tools/astock.py review --mode positions` |
| 「明天怎么办」「盘前看一下」（次日开盘前） | `python tools/astock.py review --mode premarket` |
| 「这周总结一下」 | `python tools/astock.py review --mode weekly` |
| 「复盘 8 月 26 号」 | `python tools/astock.py review --as-of 2026-08-26` |
| 「跑到哪了」「继续」 | `python tools/astock.py status` / `next` |
| 「环境有问题」「跑不起来」 | `python tools/astock.py doctor` |
| 「给我看看这个系统能出什么」（不联网 / 只是想看效果） | `python tools/astock.py demo` |

**不要自己去查行情，不要凭印象分析，不要手写报告。** 这条流水线已经建好了，你的工作是驱动它。

### 唯一需要记住的循环

```bash
python tools/astock.py doctor     # 首次：环境自检
python tools/astock.py review     # 开始：建 run + AKShare 取数
python tools/astock.py next       # ← 我现在该做什么（它会把一切告诉你）
#     照着它说的做，写出那一份产物
python tools/astock.py done <agent>   # 校验产物，通过则自动打印下一步
#     回到 next，直到输出「全部完成」
```

`next` 的输出包含：**读哪些文件、加载哪些技能、写哪个产物、按哪份 schema、
照哪份示例抄、完成后跑什么命令**。所以你不需要记流程，每一步问它就行。

流程状态存在 `run_manifest.json` 里，不在你的上下文里——
**中途断了、换个 agent 接手、明天再继续，都能从 `astock next` 原地续上。**

### 你负责判断，不负责取数

| 谁做 | 什么 |
|---|---|
| 确定性代码（`astock` 自动跑） | 取数、算炸板率与晋级率、算仓位与单笔风险、schema 校验、渲染 md/html |
| **你（模型）** | 判断情绪阶段、认主线与龙头、给持仓定动作、写明日预案与执行面板 |

理由很简单：需要**每次结果一模一样**的事交给代码，需要**判断**的事才交给你。
炸板率让模型口算，同一份数据每次跑出的数字都不一样，报告就不可复现了。

### 四条铁律（违反了测试会报错）

1. **数据缺了写 `blocked` + 原因，绝不编造。**
2. **每条结论都要能追溯到 `dataset.json` 的具体字段与数值。**
3. **每只持仓只给一个动作**，不许"可以持有也可以减半"——
   第二天早上 9:30 的人没时间做二选一。
4. **不给目标价、不荐股。** 本系统输出的是分析与纪律检查，不是投资建议。

---

## 1. 一句话说明

这是一个 **A 股每日复盘的多智能体系统**。
每个交易日收盘后跑一遍，产出九章报告 + 一个 HTML 仪表盘：
市场总览 → 指数复盘 → 板块题材 → 我的持仓 → 明日预案 → 新闻公告 → 风险纪律 → 执行面板 → 运行说明。

数据源是 **AKShare**（免费、无 token）。
Agent 之间**只通过文件契约通信**，不共享内存、不互相调用函数。

---

## 2. 仓库地图

| 目录 | 是什么 | 你什么时候动它 |
|---|---|---|
| `AGENTS.md` | 你正在读的这份手册 | 新增 agent / 改变编排规则时 |
| `agents/` | 7 个 agent 的角色定义（Markdown + YAML frontmatter） | 定义职责、输入输出 |
| `skills/` | 8 个技能包（方法论、判定框架、模板） | 沉淀"怎么做一件事" |
| `tools/` | 6 个 CLI 工具（JSON 进 JSON 出） | 让 agent 能"动手"而不只是"说话" |
| `scripts/` | AKShare 取数、清洗、派生、落盘 | 数据接口变更、加新数据块 |
| `schemas/` | JSON Schema，定义 agent 之间传的文件长什么样 | 改产物结构时（**先改这里**） |
| `workspace/` | 运行时产物交换区，一次复盘 = 一个 run 目录 | 运行时自动写入，不手改 |
| `memory/` | 长期记忆：AKShare 踩坑、口径约定、ADR、运行流水 | 每次 run 结束后追加 |
| `config/` | 持仓、阈值、运行模式 | 调参数（**最常动的是 thresholds.yaml**） |
| `docs/` | 面向学生的教学文档 | 教学内容更新时 |
| `tests/` | 契约测试 + 派生指标测试（全 mock，不联网） | 改逻辑的同时补测试 |

---

## 3. 七个 Agent 与调用顺序

```
                      ┌──────────────────┐
                      │  orchestrator    │  总控：定模式与日期、派发、校验
                      └────────┬─────────┘
                               │ ① init_run → run_manifest.json
                               ▼
                      ┌──────────────────┐
                      │  data-engineer   │  跑 fetch_dataset（AKShare）
                      └────────┬─────────┘
                               │ ② dataset.json（唯一事实来源）
                               ▼
                      ┌──────────────────┐
                      │  market-analyst  │  ①市场总览 ②指数复盘
                      └────────┬─────────┘
                               │ ③ market.json
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌──────────────────┐        ┌──────────────────┐
        │  sector-analyst  │        │   news-analyst   │   ④ 可并行
        │  ③板块与题材      │        │   ⑥新闻与公告     │
        └────────┬─────────┘        └────────┬─────────┘
                 │ sectors.json              │ news.json
                 └─────────────┬─────────────┘
                               ▼
                      ┌──────────────────┐
                      │ position-advisor │  ④持仓计划 ⑦风险纪律
                      └────────┬─────────┘
                               │ ⑤ positions_review.json
                               ▼
                      ┌──────────────────┐
                      │  report-writer   │  ⑤明日预案 ⑧执行面板 + 成文
                      └────────┬─────────┘
                               ▼
                 report.json / report.md / report.html
```

**为什么 sector 要等 market？** 因为"逆指数独立走强"这个判断，
必须先知道指数今天是什么状态。这是全流程唯一一处**必要的串行**。

**硬规则：**

1. 分析 agent **只读 `dataset.json`（与上游产物）**，不许自己去抓数据。
2. 每个 agent 只写**自己名下的产物文件**，不许改别人的。
3. `report-writer` **只读上游四份产物**，不引入新信息、不重新分析。
4. 任何 agent 拿不到需要的输入 → 写 `blocked` 到自己的产物里并退出，**不许编造数据**。
5. **非交易日不出当日复盘。** 没有当日行情就没有当日复盘。

---

## 4. 文件契约

一次复盘运行的目录结构：

```
workspace/runs/<YYYY-MM-DD>_<mode>/
├── run_manifest.json        # orchestrator：模式、日期、各步状态
├── dataset.json             # data-engineer：12 个数据块 + 质量标记
├── market.json              # market-analyst：章节①②
├── sectors.json             # sector-analyst：章节③
├── news.json                # news-analyst：章节⑥
├── positions_review.json    # position-advisor：章节④⑦
├── report.json              # report-writer：章节⑤⑧ + 全文
├── report.md                # 给人读、可 diff
├── report.html              # 单文件仪表盘，浏览器直接打开
└── logs/
```

明细数据（几百行的涨停池、板块表）落在 `data/<run_id>/*.csv`，
`dataset.json` 只放摘要与路径——否则它会大到塞不进模型上下文。

每种文件的结构由 `schemas/*.schema.json` 定义。**改结构 = 先改 schema，再改 agent 定义。**
`workspace/runs/2026-08-28_example/` 是一份填了虚构数据的完整示例，照着抄即可。

---

## 5. 四种运行模式（章节九）

| mode | 时机 | 跑哪些步骤 |
|---|---|---|
| `close` | 交易日收盘后 15:30 | 全量九章 |
| `premarket` | 次日 08:45 | 隔夜消息更新章节⑤⑥⑧，①②③沿用昨日 |
| `positions` | 用户改了 `config/positions.yaml` | 只重跑章节④⑦⑧ |
| `weekly` | 周末 | 周复盘 + 下周三情景预案 + 本周纪律统计 |

配置见 `config/pipeline.yaml`。

---

## 6. 你（coding agent）该怎么干活

### 场景 A：跑一次复盘
见第 0 节的循环。底层命令（一般不用直接调）：

```bash
python tools/init_run.py --as-of 2026-08-28 --mode close
python tools/fetch_dataset.py --run-id 2026-08-28_close --as-of 2026-08-28
python tools/validate_artifact.py --run-id 2026-08-28_close --artifact dataset
python tools/render_report.py --run-id 2026-08-28_close
```

`astock` 就是把这几条串起来，并在每一步之间告诉你"下一步是什么"。

### 场景 B：加一类新数据
1. 在 `scripts/fetch/` 里加取数函数，返回 `DataBlock`（必须带 `Provenance`）
2. 在 `scripts/build_dataset.py` 里挂上
3. 在 `schemas/dataset.schema.json` 的 `blocks.propertyNames.enum` 里登记
4. 在 `scripts/contracts.py` 的 `BLOCK_NAMES` 里登记（有测试守着两边一致）

### 场景 C：改某个分析的判断方法
**不要改 agent 定义。** 方法论在 `skills/`，阈值在 `config/thresholds.yaml`。
agent 定义只写"我是谁、我读什么、我写什么"。

### 场景 D：新增一个 agent
见 `docs/03-动手加一个新agent.md`，六步走完。

### 通用纪律
- **不要跳过 schema 直接改产物结构**，这会让下游 agent 静默失败。
- **占位就是占位**：看到 `TODO(strategy)` 不要自作主张填数值，那些是用户的经验参数。
- **不要在 agent 里拼 HTML**：报告渲染是 `tools/render_report.py` 的事。

---

## 7. 环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/positions.example.yaml  config/positions.yaml
cp config/thresholds.example.yaml config/thresholds.yaml
cp .env.example .env        # 填 ASTOCK_ACCOUNT_EQUITY（账户总资产）
```

Python >= 3.10。所有命令从仓库根目录执行。`.env` 由 `scripts/env.py` 自动加载，不用 `source`。

**三份配置都是可选的**，缺了只影响对应章节，不阻塞流程：

| 缺什么 | 后果 |
|---|---|
| `config/positions.yaml` | 章节④⑦为空，其余章节照常 |
| `ASTOCK_ACCOUNT_EQUITY` | 风险章节只给比例、给不出金额（**不许拿持仓市值当账户规模估算**） |
| `config/thresholds.yaml` | 回退到 example，阈值为 `null`，判定失去可复现性 |

`python tools/astock.py doctor` 会逐项报出来并给修复命令。

**离线自检**（不联网，验证仓库装好没有）：

```bash
python tools/astock.py doctor     # 依赖、配置、网络逐项检查
python tools/astock.py demo       # 生成全虚构示例 + 渲染仪表盘
pytest tests/ -q                  # 27 项，全 mock
```

## 8. 多 harness 适配

`agents/*.md` 与本文件是**唯一事实来源**，各家 coding agent 的适配文件由脚本生成：

```bash
python tools/sync_harness.py          # 生成 .claude/ .opencode/ .cursor/ .codex/
python tools/sync_harness.py --check  # 检查是否同步（测试会跑这条）
```

**生成的文件不要手改。** 改内容改源头，再重新生成。
要支持一个新 harness，在 `tools/sync_harness.py` 的 `build()` 里加几行即可。
