#!/usr/bin/env python3
"""清洗与质量标记 —— 空壳工具。

状态: stub / TODO(datasource)
CLI 参数与输出契约已定义，实现留空。填充步骤:
  1. 在 scripts/ 下实现对应函数
  2. 在本文件中把 stub() 换成真实调用
  3. 在 tools/tool_manifest.yaml 把 status 改为 implemented
"""
from __future__ import annotations

import argparse

from _common import stub


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--params", default="{}", help="JSON 字符串，见 tool_manifest.yaml 的 input 定义")
    p.parse_args()
    stub("clean_dataset", "TODO(datasource)")


if __name__ == "__main__":
    main()
