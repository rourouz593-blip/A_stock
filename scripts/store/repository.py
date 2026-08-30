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


COERCED: list[str] = []      # 本次写入里被强制转成字符串的类型，用于如实标注


def _sanitize(obj, path: str = "$"):
    """把 pandas / numpy / datetime 的对象转成 JSON 认识的类型。

    为什么必须有这一层：取数层拿回来的是 DataFrame 里的原生对象——
    `datetime.date`、`numpy.int64`、`NaN`。它们在内存里都很正常，
    但 `json.dumps` 一个都不认。

    最糟糕的地方在于**崩溃发生在最后一步**：数据全取回来了（三分钟），
    却在写文件时 TypeError，前面的功夫全白费。
    所以这里宁可多做转换，也不能让最后一步倒在类型上。
    """
    import datetime as _dt

    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        # NaN / inf 不是合法 JSON。缺失就是缺失，转成 null 而不是 0
        return None if (obj != obj or obj in (float("inf"), float("-inf"))) else obj
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v, f"{path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, (_dt.datetime, _dt.date, _dt.time)):
        # ⚠️ pandas 的 NaT 是 datetime 的子类，直接 isoformat() 会得到字符串 "NaT"。
        # 它和 NaN 一样"不等于自己"，用这个特性先把它挡掉。
        if obj != obj:
            return None
        return obj.isoformat()

    # 先判缺失再转换：NaT.item() 会得到一个能 str 化的东西，
    # 顺序反了就会把"缺失"写成字符串 "NaT"，比 null 糟糕得多
    try:
        import pandas as pd

        if obj is pd.NaT or bool(pd.isna(obj)):
            return None
    except (ImportError, ValueError, TypeError):
        pass

    item = getattr(obj, "item", None)      # numpy / pandas 标量
    if callable(item):
        try:
            return _sanitize(item(), path)
        except Exception:
            pass

    COERCED.append(f"{path}: {type(obj).__name__}")
    return str(obj)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    COERCED.clear()
    text = json.dumps(_sanitize(payload), ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
