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

**钱不写进 yaml。** 账户总资产放在 `.env` 的 `ASTOCK_ACCOUNT_EQUITY`，`.env` 已在 `.gitignore` 里。
`.env` 由 `scripts/env.py` 自动加载（纯标准库，不依赖 python-dotenv），**不需要 `source .env`**；
真实环境变量优先于 `.env`，方便 CI 覆盖。

## 都不配会怎样

三份配置**全都是可选的**，缺了只影响对应章节，不阻塞流程：

| 缺什么 | 后果 |
|---|---|
| `positions.yaml` | 章节④持仓计划、⑦风险纪律为空；①②③⑤⑥⑧ 照常 |
| `ASTOCK_ACCOUNT_EQUITY` | 风险章节只给比例、给不出金额。**绝不允许拿持仓市值当账户规模估算**——满仓的人和三成仓的人，同样的市值对应的风险完全不同 |
| `thresholds.yaml` | 自动回退到 `thresholds.example.yaml`（阈值全 `null`），判定由模型自己拿捏，失去可复现性 |

建议顺序：先 `python tools/astock.py demo` 看产出 → 再决定配哪些。
`tests/test_config.py` 钉住了上面这些降级行为。

## 需要你反复调的只有一个文件

`thresholds.yaml`。`skills/` 写的是框架（怎么判断），这里写的是数值（多少算强）。
框架通用，数值因人而异。目前大部分是 `null` + `TODO(strategy)`，
唯一已确定的是 `risk.per_trade_max_pct: 0.5`（单笔风险不超过账户 0.5%）。
