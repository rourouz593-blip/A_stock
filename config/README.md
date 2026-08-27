# config/ — 配置层

把"会变的东西"从代码和 prompt 里抽出来。改分析范围、换数据源、调流水线行为，
都应该只改这里，不改 `agents/` 与 `scripts/`。

| 文件 | 作用 | 入库 |
|---|---|---|
| `pipeline.yaml` | 流水线开关、并行度、重试与校验策略 | ✅ |
| `universe.example.yaml` | 股票池定义（复制为 `universe.yaml` 使用） | 示例入库 |
| `datasources.example.yaml` | 各类数据用哪个源、降级链 | 示例入库 |

带凭证的真实配置走 `.env`，不要写进 yaml。
