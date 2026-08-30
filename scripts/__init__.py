"""A 股复盘系统的数据层。

导入本包时自动加载仓库根目录的 .env——
这样无论是 `python -m scripts.build_dataset` 还是 `tools/*.py`，
拿到的环境变量都一致，不用记得先 `source .env`。
"""
from .env import load_dotenv  # noqa: F401

load_dotenv()
