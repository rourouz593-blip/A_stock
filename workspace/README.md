# workspace/ — 运行时产物交换区

## 这一层是什么

Agent 之间传递消息的"信箱"。一次复盘 = 一个 run 目录，目录里的文件就是全部通信内容。

```
workspace/runs/<YYYY-MM-DD>_<mode>/
├── run_manifest.json      # orchestrator：模式、日期、各步状态
├── dataset.json           # data-engineer：12 个数据块摘要 + 质量标记
├── market.json            # market-analyst：章节① 市场总览　② 指数复盘
├── sectors.json           # sector-analyst：章节③ 板块与题材
├── news.json              # news-analyst：章节⑥ 新闻与公告
├── positions_review.json  # position-advisor：章节④ 持仓计划　⑦ 风险纪律
├── report.json            # report-writer：章节⑤⑧ + 全文（给程序看）
├── report.md              # 给人读、可 diff
├── report.html            # 单文件仪表盘，浏览器直接打开
└── logs/                  # 各 agent 的过程日志
```

明细数据（几百行的涨停池、板块表）不在这里，落在 `data/<run_id>/*.csv`。
`dataset.json` 只放摘要与路径——否则它会大到塞不进模型上下文。

另有 `workspace/cache/`：AKShare 的本地缓存，调试时省时间，不入库。

## 为什么用文件而不是内存传参

1. **可观察** —— 出问题时直接打开看是哪一步写错了，而不是猜模型在想什么。
2. **可复现** —— run 目录整个拷走就能复现，不依赖任何进程状态。
3. **可断点续跑** —— 某一步失败，改完重跑那一步即可，前面的产物还在。
4. **harness 无关** —— 换任何 coding agent 都能接着干，约定只是"读这个、写那个"。

> 教学要点：这是把「多智能体系统」变成「可调试的软件」的关键一步。
> 消息藏在内存里的系统，出了问题只能重跑；
> 消息落在磁盘上的系统，出了问题可以**验尸**。

## 规则

- 每个 agent **只写自己名下的文件**，不改别人的。
- 写完必须过 schema 校验：
  `python tools/validate_artifact.py --run-id <id> --artifact <name>`
- `runs/` 下除示例外均不入库（见 `.gitignore`）。

## 示例

`runs/2026-08-28_example/` 是一份**填了虚构数据的完整示例**，
包含全部七个 JSON 产物和渲染好的 `report.html`。

标的 `999001.SZ 示例科技`、`999002.SH 示例材料` 与所有板块、新闻均为虚构。

它刻意做了三件事：

1. **保留一块数据缺失**（北向资金）→ 演示"缺了一块时系统如何诚实降级"
2. **触发两条行为自检** → 演示这个系统会说不爱听的话
3. **有一笔风险超限**（1.2% > 0.5%）→ 演示"已超纪律线的存量仓位该怎么处理"

用途：让新来的 agent 或学生一眼看清产物长什么样。**照着它抄准没错。**
