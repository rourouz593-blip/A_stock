# 数据源踩坑记录

> 每发现一个坑就追加一条。格式固定，方便 agent 检索。
> **本文件当前为空模板**，数据源确定后开始积累。

## 条目格式

```
### <数据源>.<接口> — <一句话概括>
- 现象：
- 影响：哪个 agent 的哪类结论会被污染
- 处理：
- 发现于：YYYY-MM-DD，run_id
```

## 条目

<!-- TODO(datasource): 数据源确定后开始记录。以下为格式示例，非真实内容。

### EXAMPLE_SOURCE_B.income_statement — 金额单位不统一
- 现象：部分年份返回单位为万元，部分为元，接口文档未说明
- 影响：fundamental-analyst 的所有绝对值判断（营收规模、利润规模）会差 10000 倍
- 处理：在 clean/normalize.py:unify_units 中按量级启发式校正，并强制打 warning flag
- 发现于：YYYY-MM-DD，run_id
-->
