# tools/ — 工具层

## 这一层是什么

**Skill 让 agent"知道怎么做"，Tool 让 agent"真的能做"。**

工具是 agent 与确定性代码之间的接口。凡是需要精确结果的事——算指标、校验 JSON、
读写文件、拉数据——都必须走工具，**不允许让模型心算或凭印象生成**。

> 教学要点：判断一件事该交给 prompt 还是交给 tool，看它是否需要**可复现的精确结果**。
> "MA20 是多少" → tool；"这个趋势结构说明什么" → prompt。

## 设计约定

1. 每个工具是一个**独立可执行的 CLI**，输入输出都是 JSON，走 stdin/stdout。
   这样任何 harness（Claude Code / opencode / 一个 shell 脚本）都能调用，零耦合。
2. 工具**只做一件事**，不做编排，不做判断。
3. 工具**不实现业务逻辑**，只做 `scripts/` 的薄封装。业务逻辑在 `scripts/`，方便单测。
4. 失败时 **exit code 非 0 + stderr 输出结构化错误**，绝不返回半成品。

## 调用约定

```bash
python tools/<tool_name>.py --help
python tools/validate_artifact.py --run-id 2026-08-28_example --artifact dataset
```

所有工具在 `tool_manifest.yaml` 中登记。**没登记的工具，agent 不许调用。**

## 当前状态

| 工具 | 状态 | 说明 |
|---|---|---|
| `init_run` | ✅ | 建 run 目录，按 mode 生成步骤列表 |
| `fetch_dataset` | ✅ | AKShare 全量取数 → `dataset.json` + `data/<run_id>/*.csv` |
| `compute_risk` | ✅ | 仓位、集中度、单笔风险、0.5% 线 |
| `render_report` | ✅ | `report.json` → `report.md` + 单文件 HTML 仪表盘 |
| `validate_artifact` | ✅ | 七种产物的 schema 校验 |
| `make_demo_run` | ✅ | 生成全虚构示例 run，离线可跑 |

**全部已实现。** 需要你填的不是代码，是 `config/thresholds.yaml` 里的判定阈值。

## 快速自检

```bash
python tools/make_demo_run.py                                   # 造一份示例 run
python tools/render_report.py --run-id 2026-08-28_example       # 渲染
open workspace/runs/2026-08-28_example/report.html              # 看效果
```

这条链路**完全不联网**，是验证仓库有没有装好的最快方式。
