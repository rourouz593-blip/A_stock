"""落盘与读取。TODO(datasource): 存储方案未确定，全部为空实现。

候选方案：本地 parquet 目录 / DuckDB 单文件 / SQLite。
选型时考虑：学生本地能否零配置跑起来（这是本仓库的教学目标之一）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import DataBlock


def save_block(block_name: str, code: str, df: Any, base_dir: Path) -> str:
    """落盘并返回相对路径。路径规范：data/<code>/<block_name>.parquet"""
    raise NotImplementedError("TODO(datasource): 实现落盘")


def load_block(path: str, base_dir: Path) -> Any:
    """按路径读回。"""
    raise NotImplementedError("TODO(datasource): 实现读取")


def build_dataset_json(run_id: str, as_of: str, blocks: dict[str, DataBlock]) -> dict:
    """把各个 DataBlock 组装成符合 schemas/dataset.schema.json 的字典。

    这是 data-engineer 的最终交付物。实现后务必用
    `python tools/validate_artifact.py --run-id <id> --artifact dataset` 校验。
    """
    raise NotImplementedError("TODO(datasource): 实现 dataset.json 组装")
