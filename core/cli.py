"""工具层公共代码：统一 IO 与错误约定。

所有工具遵守同一套约定：
  - 成功：stdout 输出一个 JSON 对象，exit 0
  - 失败：stderr 输出 {"error": {...}}，exit 1
这样任何 harness 都能用同一种方式解析结果。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / "workspace"
SCHEMAS = REPO_ROOT / "schemas"

# 让 tools/ 下的每个脚本都能拿到 .env 里的配置（例如 ASTOCK_ACCOUNT_EQUITY）
sys.path.insert(0, str(REPO_ROOT))
try:
    from core.env import load_dotenv

    load_dotenv()
except Exception:  # .env 是可选的，加载失败不该让工具挂掉
    pass


def emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def fail(code: str, message: str, **extra) -> None:
    json.dump(
        {"error": {"code": code, "message": message, **extra}},
        sys.stderr,
        ensure_ascii=False,
        indent=2,
    )
    sys.stderr.write("\n")
    sys.exit(1)


def run_dir(run_id: str) -> Path:
    d = WORKSPACE / "runs" / run_id
    if not d.is_dir():
        fail("RUN_NOT_FOUND", f"run 目录不存在: {d}")
    return d


def read_json(path: Path) -> dict:
    if not path.is_file():
        fail("FILE_NOT_FOUND", f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def stub(tool_name: str, todo: str) -> None:
    """空壳工具的统一出口：明确告诉调用方"还没实现"，而不是返回假数据。"""
    fail(
        "NOT_IMPLEMENTED",
        f"工具 {tool_name} 尚未实现",
        todo=todo,
        hint="请先在 scripts/ 下实现对应函数，再移除本 stub 调用",
    )


def build_validator(schema: dict):
    """构造一个能解析 schemas/ 目录内本地 $ref 的校验器。

    schemas/*.schema.json 会 $ref 到 _common.defs.json，
    需要把同目录下所有 schema 注册进 registry 才能解析。
    """
    import jsonschema
    from referencing import Registry, Resource

    resources = []
    for f in sorted(SCHEMAS.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        resources.append((f.name, Resource.from_contents(doc)))
        if doc.get("$id") and doc["$id"] != f.name:
            resources.append((doc["$id"], Resource.from_contents(doc)))
    registry = Registry().with_contents(
        [(uri, res.contents) for uri, res in resources]
    )
    return jsonschema.Draft202012Validator(schema, registry=registry)
