# Repository agent operations

This repository is an open-source, harness-neutral A-share daily review pipeline. Use the deterministic CLI to drive it; do not fetch market data ad hoc or write reports from memory.

Runtime requirement: Python >= 3.9; Python 3.11+ is recommended.

## User intent to command

| Intent | Command |
|---|---|
| Daily close review | `python tools/astock.py review` |
| Position-only refresh | `python tools/astock.py review --mode positions` |
| Premarket refresh | `python tools/astock.py review --mode premarket` |
| Weekly review | `python tools/astock.py review --mode weekly` |
| Historical date | `python tools/astock.py review --as-of YYYY-MM-DD` |
| Progress / resume | `python tools/astock.py status` then `python tools/astock.py next` |
| Environment diagnosis | `python tools/astock.py doctor` |
| Dataset diagnosis | `python tools/astock.py check` |
| Source rejection | `python tools/astock.py budget`, then `python tools/astock.py cooldown` |
| Offline example | `python tools/astock.py demo` |

## Execution loop

```bash
python tools/astock.py review
python tools/astock.py next
# Read the returned AGENT.md and SKILL.md files, then write only the requested artifact.
python tools/astock.py done <agent>
```

Repeat `next` / `done` until complete. State is stored in `run_manifest.json`, not conversational memory.

## Package contract

Every built-in or external agent is a directory containing:

```text
AGENT.md
SKILL.md
tools/*.py
scripts/**/*.py
```

Additional package-owned skills go under `skills/<name>/SKILL.md`. Do not recreate a global skills directory.

Directory placement declares ownership; do not add ownership manifests. Agent packages are discovered through `core/agent_registry.py`. Extension roots are configured in `config/extensions.yaml` or `ASTOCK_AGENTS_PATHS` / `ASTOCK_SKILLS_PATHS`.

## Data providers

Provider order belongs in `config/datasources.yaml`; provider implementation roots belong in `config/extensions.yaml` or `ASTOCK_PROVIDER_PATHS`. Validate a provider with `python tools/verify_provider.py` before adding it to an active chain.

Analysis agents only read `dataset.json` and declared upstream artifacts. They never call providers directly.

## Hard rules

1. Missing data becomes `blocked` with a reason; never fabricate.
2. Every conclusion cites concrete fields and values from its declared inputs.
3. Each position has one action, not alternatives.
4. Do not provide target prices or recommend new securities.
5. Do not publish a close review for a non-trading day.
6. Change an artifact shape by updating its schema first.
7. Do not edit generated harness adapters; run `python tools/sync_harness.py`.

## Repository map

| Path | Purpose |
|---|---|
| `agents/` | Self-contained agent packages |
| `core/` | Genuinely shared contracts, paths, discovery, and CLI primitives |
| `tools/` | Thin compatibility launchers for stable public commands |
| `schemas/` | Artifact contracts |
| `config/` | Pipeline, provider, model, extension, and user configuration |
| `workspace/` | Runtime artifacts; only the synthetic example is tracked |
| `memory/` | Operational knowledge and local run history |
| `tests/` | Offline contract, runtime, provider, and harness checks |

Preserve unrelated working-tree changes. Use `rg` for discovery and `apply_patch` for edits.
