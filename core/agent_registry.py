"""Harness-neutral discovery for agent packages and optional skills."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "config" / "extensions.yaml"


def _config() -> dict:
    try:
        import yaml

        return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, OSError, ValueError):
        return {}


def _paths(kind: str, default: Path | None = None) -> list[Path]:
    configured = (_config().get("paths") or {}).get(kind) or []
    env = os.getenv(f"ASTOCK_{kind.upper()}_PATHS", "").split(os.pathsep)
    paths = [Path(p) for p in [*configured, *env] if p]
    resolved = [p if p.is_absolute() else REPO_ROOT / p for p in paths]
    if default is not None:
        resolved.append(default)
    return resolved


def agent_files() -> Iterator[Path]:
    """Yield one AGENT.md per discovered package; first name wins."""
    seen: set[str] = set()
    for root in _paths("agents", REPO_ROOT / "agents"):
        candidates = [root / "AGENT.md", *sorted(root.glob("*/AGENT.md"))]
        for path in candidates:
            if not path.is_file():
                continue
            meta = read_meta(path)
            name = str(meta.get("name") or path.parent.name.replace("_", "-"))
            if name not in seen:
                seen.add(name)
                yield path


def agent_file(name: str) -> Path:
    for path in agent_files():
        if read_meta(path).get("name") == name:
            return path
    raise FileNotFoundError(f"agent package not found: {name}")


def read_meta(path: Path) -> dict:
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing YAML frontmatter: {path}")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def skill_files(path: Path, meta: dict | None = None) -> list[Path]:
    """Return the package skill followed by declared local/external skills."""
    meta = meta or read_meta(path)
    found: list[Path] = []
    primary = path.parent / "SKILL.md"
    if primary.is_file():
        found.append(primary)
    extra = (_config().get("agent_skills") or {}).get(meta.get("name")) or []
    for name in [*(meta.get("skills") or []), *extra]:
        raw = Path(str(name))
        candidates = [raw if raw.is_absolute() else path.parent / raw]
        candidates += [root / raw for root in _paths("skills")]
        for candidate in candidates:
            skill = candidate if candidate.name == "SKILL.md" else candidate / "SKILL.md"
            if skill.is_file():
                if skill not in found:
                    found.append(skill)
                break
        else:
            raise FileNotFoundError(f"skill not found for {meta.get('name')}: {name}")
    return found
