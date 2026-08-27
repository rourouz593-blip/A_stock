# workspace/ — 运行时产物交换区

## 这一层是什么

Agent 之间传递消息的"信箱"。一次分析 = 一个 run 目录，目录里的文件就是全部通信内容。

```
workspace/runs/<YYYY-MM-DD>_<slug>/
├── run_manifest.json    # orchestrator
├── dataset.json         # data-engineer
├── fundamental.json     # fundamental-analyst
├── technical.json       # technical-analyst
├── sentiment.json       # sentiment-analyst
├── report.json          # report-writer（结构化，给程序看）
├── report.md            # report-writer（成文，给人看）
└── logs/                # 各 agent 的过程日志
```

## 为什么用文件而不是内存传参

1. **可观察** — 出问题时能直接打开看是哪一步写错了，而不是猜模型在想什么。
2. **可复现** — run 目录整个拷走就能复现，不依赖任何进程状态。
3. **可断点续跑** — 某一步失败，改完重跑那一步即可，前面的产物还在。
4. **harness 无关** — 换成任何 coding agent 都能接着干，因为约定只是"读这个文件、写那个文件"。

> 教学要点：这是把「多智能体系统」变成「可调试的软件」的关键一步。
> 消息藏在内存里的系统，出了问题只能重跑；消息落在磁盘上的系统，出了问题可以验尸。

## 规则

- 每个 agent **只写自己名下的文件**，不改别人的。
- 写完必须过 schema 校验：`python tools/validate_artifact.py --run-id <id> --artifact <name>`
- `runs/` 下除示例外均不入库（见 `.gitignore`）。

## 示例

`runs/2026-01-02_example/` 是一份**填了假数据的完整示例**，标的 `000000.SZ 示例科技`
是虚构的，数值全为占位。用途：让新来的 agent 或学生一眼看清产物长什么样。
