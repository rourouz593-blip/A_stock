# scripts/ — 数据层

## 这一层是什么

**唯一被允许接触外部世界的代码。** 所有网络请求、文件落盘、数据清洗都在这里。
上层（tools → agents）只调用这里暴露的函数，不自己发请求。

```
scripts/
├── contracts.py     # 数据契约：函数签名与返回结构，本层的"接口定义文件"
├── fetch/           # 取数：一个模块对应一类数据
├── clean/           # 清洗：交易日历、复权、单位、缺失处理
├── store/           # 落盘与读取
└── run_pipeline.py  # 不经过 agent，直接跑数据流水线（调试用）
```

## 当前状态：OHLCV 已实现，其余为空实现

`fetch/market_data.py:fetch_ohlcv` 已通过 AKShare 接入；它校验上游字段、统一字段名，
并返回带 `Provenance` / `QualityFlag` 的 `DataBlock`。交易日历、财务、新闻、清洗与存储
仍然明确抛出 `NotImplementedError`。

**这是刻意的渐进实现。** 用户已经确认 AKShare 用于行情，但没有授权它承担其他数据
类别。先接通一条最小链路，学生能清楚看到 contract → script → tool → artifact 的关系。

## 填空的正确顺序

1. 读 `contracts.py`，理解返回结构要求（尤其是 `Provenance` 与 `QualityFlag`）
2. 在 `config/datasources.yaml` 里登记你选的数据源
3. 实现 `fetch/` 里对应的函数，**返回值必须带 provenance**
4. 实现 `clean/` 里的口径统一
5. 在 `tests/` 里补测试：至少覆盖"源返回空"和"源返回缺列"两种情况
6. 把 `tools/` 里对应工具的 `stub()` 换成真实调用，并改 `tool_manifest.yaml` 的 status

## 三条硬规矩

1. **函数必须是纯粹的**：取数就只取数，不要顺手做分析。
2. **失败要响亮**：拿不到数据就抛异常或返回 `status=missing`，
   绝不返回空 DataFrame 让上层以为"这只票就是没数据"。
3. **口径必须显式**：复权方式、金额单位、报告期 vs 披露日，全部写进 `Provenance`。

> 教学要点：多智能体系统的可靠性上限，由最底下这一层决定。
> 模型再聪明，喂进去的是错口径的数据，输出的就是错得很有说服力的报告。
