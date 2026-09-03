"""Pipeline configuration derived from config and discovered agent packages."""
from __future__ import annotations

from pathlib import Path

from core.agent_registry import agent_files, read_meta
from core.paths import REPO_ROOT

CONFIG = REPO_ROOT / "config" / "pipeline.yaml"


def load() -> dict:
    import yaml

    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def mode_steps() -> dict[str, list[str]]:
    return {name: list(spec.get("steps") or [])
            for name, spec in (load().get("modes") or {}).items()}


def artifact_map() -> dict[str, str]:
    out = {}
    for definition in agent_files():
        meta = read_meta(definition)
        if meta.get("name") == "orchestrator" or not meta.get("writes"):
            continue
        out[meta["name"]] = Path(meta["writes"][0]).stem
    return out


def automated_agents() -> set[str]:
    return {read_meta(path)["name"] for path in agent_files()
            if read_meta(path).get("automated") is True}
