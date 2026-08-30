"""极简 .env 加载器。

为什么不用 python-dotenv：本项目的依赖越少，学生第一次跑通的概率越高。
这个功能只值 30 行代码，不值一个第三方依赖。

约定：
  - 只在**没有**同名环境变量时才写入（真实环境变量优先于 .env，方便 CI 覆盖）
  - 支持 `KEY=value`、`export KEY=value`、`#` 注释、值两端的引号
  - 文件不存在就静默跳过——.env 是可选的，不是必需的
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    """把 .env 里的键值读进 os.environ，返回本次实际写入的键值。"""
    p = Path(path) if path else REPO_ROOT / ".env"
    if not p.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not key:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if val == "":                       # 留空等于没填，不要写入空串
            continue
        if override or key not in os.environ:
            os.environ[key] = val
            loaded[key] = val
    return loaded


def dotenv_path() -> Path:
    return REPO_ROOT / ".env"
