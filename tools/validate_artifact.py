#!/usr/bin/env python3
"""用 schemas/ 下的 JSON Schema 校验某个 run 产物。

用法:
    python tools/validate_artifact.py --run-id 2026-08-28_example --artifact dataset
"""
from __future__ import annotations

import argparse

from _common import SCHEMAS, build_validator, emit, fail, read_json, run_dir

ARTIFACTS = {
    "run_manifest": "run_manifest.schema.json",
    "dataset": "dataset.schema.json",
    "market": "market.schema.json",
    "sectors": "sectors.schema.json",
    "positions_review": "positions_review.schema.json",
    "news": "news.schema.json",
    "report": "report.schema.json",
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--artifact", required=True, choices=sorted(ARTIFACTS))
    args = p.parse_args()

    try:
        import jsonschema  # noqa: F401
    except ImportError:
        fail("MISSING_DEP", "缺少依赖 jsonschema，请先 pip install -r requirements.txt")
        return

    doc = read_json(run_dir(args.run_id) / f"{args.artifact}.json")
    schema = read_json(SCHEMAS / ARTIFACTS[args.artifact])

    validator = build_validator(schema)
    errors = [
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
        for e in validator.iter_errors(doc)
    ]
    emit({"valid": not errors, "errors": errors, "artifact": args.artifact})


if __name__ == "__main__":
    main()
