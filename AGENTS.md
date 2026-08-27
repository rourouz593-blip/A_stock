# AGENTS.md — 本仓库的 Agent 操作手册

> 本文件是**任何 coding agent（Claude Code / opencode / Cursor / Codex …）进入本仓库后必须读的第一份文件**。
> 读完本文件，你应当在**不了解任何前置背景**的情况下，知道：这是什么、有哪些角色、数据怎么流、你该改哪里。

---

## 0. 一句话说明

这是一个**A 股市场多智能体分析工厂（harness factory）**的骨架仓库。
它把「基本面 / 技术面 / 情绪面」三路分析拆成独立 agent，由一个 orchestrator 编排，
所有 agent 之间**只通过文件契约通信**（不共享内存、不互相调用函数）。

**当前状态：骨架已完成，业务内容为空。** 数据源 API 与投资策略尚未确定，所有涉及
"具体怎么算""从哪拿数据"的地方都是 `TODO` 占位。这是刻意的设计，不是未完成的 bug。

---

## 1. 仓库地图

| 目录 | 是什么 | 你什么时候动它 |
|---|---|---|
| `AGENTS.md` | 你正在读的这份手册 | 新增 agent / 改变编排规则时 |
| `agents/` | 6 个 agent 的角色定义（Markdown + YAML frontmatter） | 定义角色职责、输入输出 |
| `skills/` | 可复用的专业技能包（方法论、检查清单、模板） | 沉淀"怎么做一件事"的知识 |
| `tools/` | agent 可调用的 CLI 工具（对 `scripts/` 的薄封装） | 让 agent 能"动手"而不是只能"说话" |
| `scripts/` | 数据抓取 / 清洗 / 存储的 Python 代码 | 接入真实数据源时 |
| `schemas/` | JSON Schema，定义 agent 之间传递的文件长什么样 | 改变 agent 产物结构时 |
| `workspace/` | 运行时产物交换区，一次分析 = 一个 run 目录 | 运行时自动写入，不手改 |
| `memory/` | 长期记忆：知识沉淀、决策记录、历史复盘 | 每次 run 结束后追加 |
| `config/` | 股票池、流水线开关、参数 | 调整分析范围与参数 |
| `docs/` | 面向学生的教学文档 | 教学内容更新时 |
| `tests/` | 契约与数据层测试 | 写实现的同时补测试 |

---

## 2. 六个 Agent 与调用顺序

```
                        ┌──────────────────┐
                        │  orchestrator    │  ← 总控，唯一有权决定"下一步"的角色
                        └────────┬─────────┘
                                 │ 1) 建 run 目录、写 run_manifest.json
                                 ▼
                        ┌──────────────────┐
                        │  data-engineer   │  调 tools/ → scripts/ 拉数、清洗、落盘
                        └────────┬─────────┘
                                 │ 产出 dataset.json（唯一数据事实来源）
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │ fundamental-   │ │ technical-     │ │ sentiment-     │   ← 三者可并行
     │ analyst        │ │ analyst        │ │ analyst        │
     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘
             │ fundamental.json │ technical.json   │ sentiment.json
             └───────────────┬──┴──────────────────┘
                             ▼
                    ┌──────────────────┐
                    │  report-writer   │  汇总三份结论 → report.md + report.json
                    └──────────────────┘
```

**硬规则：**

1. 三个分析 agent **只读 `dataset.json`**，不许自己去抓数据。
   （教学要点：数据获取与数据分析分离，才能保证三路结论建立在同一份事实上。）
2. 每个 agent 只写**自己名下的产物文件**，不许改别人的。
3. `report-writer` **只读三份分析产物**，不许重新读原始数据、不许自己下结论。
4. 任何 agent 拿不到需要的输入 → 写 `blocked` 状态到自己的产物里并退出，**不许编造数据**。

---

## 3. 文件契约（Agent 之间唯一的通信方式）

一次分析运行的目录结构：

```
workspace/runs/<YYYY-MM-DD>_<slug>/
├── run_manifest.json      # orchestrator 写：本次 run 的标的、时间窗、各步状态
├── dataset.json           # data-engineer 写：清洗后的结构化数据（或指向 parquet 的路径）
├── fundamental.json       # fundamental-analyst 写
├── technical.json         # technical-analyst 写
├── sentiment.json         # sentiment-analyst  写
├── report.json            # report-writer 写：结构化最终结论
├── report.md              # report-writer 写：给人看的报告
└── logs/                  # 各 agent 的过程日志（可选）
```

每种文件的结构由 `schemas/*.schema.json` 定义。**改结构 = 先改 schema，再改 agent 定义。**
`workspace/runs/2026-01-02_example/` 下有一份填了假数据的完整示例，照着抄即可。

---

## 4. 你（coding agent）该怎么干活

### 场景 A：要接入真实数据源
1. 读 `scripts/README.md` 与 `scripts/contracts.py`
2. 在 `scripts/fetch/` 里实现对应的 `NotImplementedError` 函数
3. 在 `tools/tool_manifest.yaml` 里登记新工具
4. 补 `tests/`

### 场景 B：要实现某一路分析逻辑
1. 读对应的 `agents/<name>.md`（职责与输入输出）
2. 读它引用的 `skills/`（方法论）
3. 把结论按 `schemas/<name>.schema.json` 写进 run 目录

### 场景 C：要新增一个 agent（比如「资金流分析」）
1. `agents/` 加一个 `.md`（照抄现有 frontmatter 字段）
2. `schemas/` 加它的产物 schema
3. 在 `agents/orchestrator.md` 的调度表里加一行
4. 在本文件第 2 节的图里加上它

### 通用纪律
- **不要跳过 schema 直接改产物结构**，这会让下游 agent 静默失败。
- **不要把业务逻辑写进 agent 定义**；方法论进 `skills/`，代码进 `scripts/`，
  agent 定义只写"我是谁、我读什么、我写什么"。
- **占位就是占位**：看到 `TODO(strategy)` / `TODO(datasource)` 不要自作主张填内容，
  这些必须由人来确认。

---

## 5. 环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # 填数据源凭证
```

Python >= 3.10。所有脚本从仓库根目录执行。
