"""落盘与读取。

存储格式选 **CSV** 而不是 parquet：
学生可以直接用 Excel / VSCode 打开看一眼数据长什么样，
这比省那点磁盘空间重要得多。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("ASTOCK_DATA_DIR", REPO_ROOT / "data"))


def save_table(df, run_id: str, name: str) -> str:
    """把一张表存成 CSV，返回相对仓库根目录的路径。"""
    out = DATA_DIR / run_id / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")  # utf-8-sig 让 Excel 不乱码
    try:
        return str(out.relative_to(REPO_ROOT))
    except ValueError:
        return str(out)


def load_table(path: str):
    import pandas as pd

    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return pd.read_csv(p, dtype={"代码": str, "板块代码": str})


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
