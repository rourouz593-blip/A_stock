# scripts/ — 数据层（AKShare）

## 这一层是什么

**唯一被允许接触外部世界的代码。** 所有网络请求、清洗、落盘都在这里。
上层（tools → agents）只调用这里暴露的函数，不自己发请求。

```
scripts/
├── contracts.py       # 数据契约：DataBlock / Provenance / QualityFlag + 代码与日期转换
├── ak_client.py       # AKShare 调用封装：重试、缓存、响亮失败
├── fetch/
│   ├── calendar.py    # 交易日历（第一个要跑通的接口）
│   ├── market.py      # 四大指数日线 + 分时（日内四段拆解）
│   ├── breadth.py     # 涨跌家数、涨停/炸板/跌停池、炸板率、晋级率、连板梯队
│   ├── sectors.py     # 行业与概念板块、板块资金流、成分股
│   ├── stocks.py      # 持仓个股日线与均线位置、北向资金
│   └── news.py        # 财联社电报、东财快讯、交易所公告
├── clean/derive.py    # 派生指标：两市成交额、相对强弱、均线位置、交付前自检
├── store/repository.py# 落盘（CSV，Excel 可直接打开）
├── positions.py       # 读取校验 positions.yaml + 按收盘价估值
└── build_dataset.py   # 主入口：一条命令产出 dataset.json
```

## 用法

```bash
python -m scripts.build_dataset --run-id 2026-08-28_close --as-of 2026-08-28
python -m scripts.build_dataset --run-id ... --as-of ... --no-cache   # 强制重取
```

或者走工具层（agent 走的就是这条）：

```bash
python tools/fetch_dataset.py --run-id 2026-08-28_close --as-of 2026-08-28
```

## 三条硬规矩

1. **函数保持纯粹**：取数就只取数，不做分析、不打标签。
   新闻的"利好/利空"由 news-analyst 判断，不在这里预设。
2. **失败要响亮**：拿不到就抛异常或返回 `status=missing` + flag，
   绝不返回空 DataFrame 让上层以为"今天就是没数据"。
3. **口径必须显式**：复权方式、金额单位、请求参数，全部写进 `Provenance`。

## 缓存

默认开启，落在 `workspace/cache/`。调试时能省大量时间，也少给 AKShare 添麻烦。
需要拿最新数据时加 `--no-cache`。

## 已知限制

见 `memory/knowledge/akshare-gotchas.md`。最要紧的三条：

- 分时接口只保留最近几个交易日 → 历史日期拿不到日内四段
- 炸板池/跌停池只有最近 30 个交易日
- 涨跌家数是实时快照 → 只在收盘后跑 `close` 模式

> 教学要点：多智能体系统的可靠性上限，由最底下这一层决定。
> 模型再聪明，喂进去的是错口径的数据，输出的就是错得很有说服力的报告。
