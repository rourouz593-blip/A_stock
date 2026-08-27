# {{name}}（{{code}}）分析报告

- **分析基准日**：{{as_of}}
- **运行 ID**：{{run_id}}
- **数据完整性**：{{data_completeness}}   <!-- 有任何一路 blocked 必须在此写明 -->

## 摘要

{{summary}}   <!-- 3-5 句。若存在数据缺口，第一句就要说 -->

## 结论一览

| 维度 | 判断 | 置信度 | 主要依据 |
|---|---|---|---|
| 基本面 | {{fundamental.verdict}} | {{fundamental.confidence}} | {{...}} |
| 技术面 | {{technical.trend_state}} | {{technical.confidence}} | {{...}} |
| 情绪面 | {{sentiment.direction}} | {{sentiment.confidence}} | {{...}} |

## 基本面

{{fundamental_section}}

## 技术面

{{technical_section}}

## 情绪面

{{sentiment_section}}

## 分歧与印证

{{divergence_section}}   <!-- 本报告最有价值的一节，不得省略 -->

## 风险提示

{{risks}}

## 数据来源与口径

{{provenance}}   <!-- 数据源、拉取时间、复权口径、quality_flags -->

## 免责声明

{{disclaimer}}
