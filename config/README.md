# config/ — 配置层

把"会变的东西"从代码和 prompt 里抽出来。改分析范围、调阈值、换运行模式，
都应该只改这里，不改 `agents/` 与 `scripts/`。

| 文件 | 作用 | 入库 |
|---|---|---|
| `pipeline.yaml` | 四种运行模式、并行分组、重试与硬约束 | ✅ |
| `positions.example.yaml` | 持仓模板（复制为 `positions.yaml` 填写） | 示例入库 |
| `thresholds.example.yaml` | 判定阈值（复制为 `thresholds.yaml` 调整） | 示例入库 |

```bash
cp config/positions.example.yaml  config/positions.yaml
cp config/thresholds.example.yaml config/thresholds.yaml
```

**钱不写进 yaml。** 账户总资产放在 `.env` 的 `ASTOCK_ACCOUNT_EQUITY`，
`.env` 已在 `.gitignore` 里。

## 需要你反复调的只有一个文件

`thresholds.yaml`。`skills/` 写的是框架（怎么判断），这里写的是数值（多少算强）。
框架通用，数值因人而异。目前大部分是 `null` + `TODO(strategy)`，
唯一已确定的是 `risk.per_trade_max_pct: 0.5`（单笔风险不超过账户 0.5%）。
