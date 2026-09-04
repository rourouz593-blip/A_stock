# A_stock

一套开源、与 Agent 运行环境无关的 A 股每日复盘流水线。项目采集可追溯的市场数据，通过文件契约驱动多个专业分析 Agent，最终生成 Markdown 报告和可独立打开的 HTML 仪表盘。

项目面向稳定运行场景：确定性代码负责数据采集、派生计算、校验和渲染，Agent 负责分析判断。数据缺失时会明确报告，绝不编造。

## 部署

本项目是命令行流水线，不是常驻 Web 服务。部署过程包括：安装到持久目录、选择执行模式，以及按需配置收盘后的定时任务。

### 1. 环境要求

- Git
- Python 3.9+，推荐 Python 3.11+
- 获取实时行情时需要互联网连接
- 无人值守模式需要可用的远程模型 API 或本地 Ollama；使用远程模型时需要对应 API Key

行情数据来自免费的公开接口，不需要行情数据 Token。公开接口可能出现延迟、限流或临时不可用；遇到缺失时，流水线会如实标记，不会自行补造数据。

### 2. 克隆并安装

克隆仓库并进入项目目录：

```bash
git clone https://github.com/JJChand/A_stock.git
cd A_stock
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

安装依赖：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. 验证安装

先检查运行环境，再生成完全离线的示例报告：

```bash
python tools/astock.py doctor
python tools/astock.py demo
```

离线示例不会获取实时行情，生成结果位于 `workspace/runs/2026-08-28_example/`。

首次运行真实复盘前，建议逐项检查所有数据块：

```bash
python tools/astock.py check
```

可选数据块缺失时不会中断整份复盘；必需数据块缺失时命令会返回非零退出码。具体排查顺序见[常见失败模式](docs/05-常见失败模式.md)。

### 4. 配置复盘

下面三个文件都是可选的。即使不配置持仓，市场和板块章节仍可正常运行。

```bash
cp .env.example .env
cp config/positions.example.yaml config/positions.yaml
cp config/thresholds.example.yaml config/thresholds.yaml
```

PowerShell 中的 `cp` 是 `Copy-Item` 的别名，上述命令同样可用。

- `.env`：账户总资产、API Key、路径、超时和请求预算。程序会自动加载，无需执行 `source .env`。
- `config/positions.yaml`：持仓、买入逻辑和失效位。该文件不会提交到 Git。
- `config/thresholds.yaml`：策略阈值和风险限制。该文件不会提交到 Git。
- `config/datasources.yaml`：各类数据的数据源优先级。

密钥只应保存在 `.env` 或系统环境变量中，不要提交 `.env`。系统环境变量的优先级高于 `.env`，因此同一套部署也可以用于 CI 或定时任务。

### 5. 选择执行模式

#### 交互式 Harness 模式

适合在 Codex、Claude Code、Cursor 或 OpenCode 中运行，不需要 `config/models.yaml`，也不需要额外配置模型 API Key。

```bash
python tools/astock.py review
python tools/astock.py next
```

`next` 会输出当前 Agent 包、操作说明、输入文件和需要生成的产物。编码 Agent 写完产物后，执行以下命令进行校验并推进流程：

```bash
python tools/astock.py done <agent>
```

重复执行 `next` 和 `done`，直到报告生成完成。进度保存在 `run_manifest.json` 中，因此更换会话后也能继续：

```bash
python tools/astock.py status
python tools/astock.py next
```

#### 无人值守 API 模式

适合定时运行或用一条命令执行完整流程。复制模型配置，在 `tiers` 中选择模型提供方，并把对应 API Key 写入 `.env`：

```bash
cp config/models.yaml.example config/models.yaml
```

例如，`tiers.default` 或 `tiers.reasoning` 使用 `deepseek` 时，需要在 `.env` 中填写 `DEEPSEEK_API_KEY`。示例配置支持 OpenAI 兼容接口、Anthropic 和本地 Ollama。

配置模型后再次检查环境，然后运行完整流水线：

```bash
python tools/astock.py doctor
python tools/astock.py run
```

API 运行器会自动获取数据、执行所有分析 Agent、校验每份产物，并生成最终的 Markdown 和 HTML 报告。

### 6. 其他复盘模式

```bash
python tools/astock.py review --mode positions       # 只刷新持仓
python tools/astock.py review --mode premarket       # 盘前刷新
python tools/astock.py review --mode weekly          # 周度复盘
python tools/astock.py review --as-of 2026-08-28     # 指定历史日期
```

无人值守运行时，把上述命令中的 `review` 替换为 `run`。非交易日不会发布收盘复盘。

### 7. 配置定时运行

定时任务应直接使用虚拟环境中的 Python，避免依赖 Shell 激活状态。请把机器时区设为 `Asia/Shanghai`，将仓库放在持久化的本地存储中，并把任务安排在行情数据稳定后执行。

以下 Cron 示例会在每个工作日 15:20 执行收盘复盘：

```cron
20 15 * * 1-5 cd /absolute/path/to/A_stock && .venv/bin/python tools/astock.py run >> workspace/scheduled.log 2>&1
```

在 Windows 任务计划程序中创建每日任务，并填写：

- 程序：`C:\absolute\path\to\A_stock\.venv\Scripts\python.exe`
- 参数：`tools\astock.py run`
- 起始于：`C:\absolute\path\to\A_stock`

交易日历保护会阻止系统在周末和休市日生成收盘报告。不要让多个定时任务同时操作同一个工作目录。

### 8. 输出与日常运维

每次运行都会把清单、校验后的中间产物和最终报告写入 `workspace/runs/<run_id>/`。运行记录、缓存、本地历史库、持仓、模型配置和密钥均不会提交到 Git。

```bash
python tools/astock.py status      # 查看当前运行进度
python tools/astock.py check       # 独立检查每个数据块
python tools/astock.py budget      # 查看每日请求预算
python tools/astock.py cooldown    # 查看数据源熔断状态
python tools/astock.py store       # 查看本地历史数据仓库
python tools/astock.py demo        # 重新生成离线示例
```

实时数据获取失败时，请按以下顺序排查，不要反复重跑完整流水线：

```bash
python tools/astock.py doctor
python tools/astock.py check
python tools/net_check.py
python tools/net_probe.py
```

## 架构

每个 Agent 都是一个可独立发现、契约明确的软件包：

```text
agents/<package>/
  AGENT.md                 身份、契约和依赖
  SKILL.md                 主要分析方法
  skills/*/SKILL.md        可选的包内子技能
  tools/*.py               Agent 自有的可执行工具
  scripts/**/*.py          Agent 自有的确定性运行代码
```

内置 Agent 包：

- `orchestrator`
- `data_engineer`
- `market_analyst`
- `sector_analyst`
- `news_analyst`
- `position_advisor`
- `report_writer`

Agent 之间只通过 `workspace/runs/<run_id>/` 下经过校验的产物通信。`schemas/` 中的 Schema 是各软件包之间稳定的 API。

文件系统本身就是所有权模型，不需要额外的所有权清单。根目录的 `tools/` 只保留向后兼容的命令入口，真正由多个软件包共享的基础能力位于 `core/`。

更多说明见[架构](docs/ARCHITECTURE.md)、[扩展机制](docs/EXTENSIONS.md)和[数据接入指南](docs/04-数据接入指南.md)。

## 扩展

可通过 `config/extensions.yaml` 或环境变量配置外部软件包目录：

```yaml
paths:
  agents: [../my-astock-agents]
  skills: [../my-skills]
  providers: [../my-market-providers]

agent_skills:
  market-analyst: [my-market-method]
```

对应环境变量使用当前操作系统的路径分隔符：

- `ASTOCK_AGENTS_PATHS`
- `ASTOCK_SKILLS_PATHS`
- `ASTOCK_PROVIDER_PATHS`

数据源优先级仍在 `config/datasources.yaml` 中声明。数据提供方只需实现对应数据集所需的命名能力，例如 `spot()`。

## Harness 支持

Agent 定义不绑定具体运行环境。Claude Code、OpenCode、Cursor 和 Codex 使用的轻量适配器由已发现的软件包自动生成：

```bash
python tools/sync_harness.py
python tools/sync_harness.py --check
```

不要直接编辑自动生成的适配器文件。

## 安全与输出规则

- 每个结论都必须追溯到具体的输入字段和值。
- 必需数据缺失时输出 `blocked`，绝不编造数据。
- 每只持仓只能给出一个动作。
- 报告不提供目标价，也不推荐新的证券。
- 非交易日不生成收盘复盘。

## 开发

```bash
pytest tests/ -q
python tools/sync_harness.py --check
```

`workspace/runs/2026-08-28_example/` 中的离线示例使用合成数据，并作为契约测试夹具提交。实际运行记录、缓存、本地历史库、持仓和密钥均不会提交到 Git。
