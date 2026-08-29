# AGENTS.md — 本仓库的 Agent 操作手册

> 本文件是**任何 coding agent（Claude Code / opencode / Cursor / Codex …）进入本仓库后必须读的第一份文件**。
> 读完本文件，你应当在**不了解任何前置背景**的情况下，知道：这是什么、有哪些角色、数据怎么流、你该改哪里。

---

## 0. 一句话说明

这是一个 **A 股每日复盘的多智能体系统**。
每个交易日收盘后自动跑一遍，产出一份九章报告 + 一个 HTML 仪表盘：
市场总览 → 指数复盘 → 板块题材 → 我的持仓 → 明日预案 → 新闻公告 → 风险纪律 → 执行面板 → 运行说明。

数据源是 **AKShare**（免费、无 token）。
Agent 之间**只通过文件契约通信**，不共享内存、不互相调用函数。

---

## 1. 仓库地图

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

## 2. 七个 Agent 与调用顺序

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

## 3. 文件契约

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

## 4. 四种运行模式（章节九）

| mode | 时机 | 跑哪些步骤 |
|---|---|---|
| `close` | 交易日收盘后 15:30 | 全量九章 |
| `premarket` | 次日 08:45 | 隔夜消息更新章节⑤⑥⑧，①②③沿用昨日 |
| `positions` | 用户改了 `config/positions.yaml` | 只重跑章节④⑦⑧ |
| `weekly` | 周末 | 周复盘 + 下周三情景预案 + 本周纪律统计 |

配置见 `config/pipeline.yaml`。

---

## 5. 你（coding agent）该怎么干活

### 场景 A：跑一次复盘
```bash
python tools/init_run.py --as-of 2026-08-28 --mode close
python tools/fetch_dataset.py --run-id 2026-08-28_close --as-of 2026-08-28
python tools/validate_artifact.py --run-id 2026-08-28_close --artifact dataset
# → 然后按第 2 节的顺序派发各分析 agent
python tools/render_report.py --run-id 2026-08-28_close
```

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

## 6. 环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/positions.example.yaml  config/positions.yaml
cp config/thresholds.example.yaml config/thresholds.yaml
cp .env.example .env        # 填 ASTOCK_ACCOUNT_EQUITY（账户总资产）
```

Python >= 3.10。所有命令从仓库根目录执行。

**离线自检**（不联网，验证仓库装好没有）：

```bash
python tools/make_demo_run.py
python tools/render_report.py --run-id 2026-08-28_example
pytest tests/ -q
```
