"""Compatibility launcher for agent-owned command-line tools."""
from __future__ import annotations

import sys
import runpy
from pathlib import Path


def expose(namespace: dict, agent: str, filename: str) -> None:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    loaded = runpy.run_path(str(root / "agents" / agent / "tools" / filename))
    namespace.update({key: value for key, value in loaded.items() if not key.startswith("__")})
