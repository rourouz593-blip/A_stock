# AStock Daily Review

An open-source, harness-neutral A-share daily review pipeline. It collects traceable market data, runs specialized analysis agents through file contracts, and renders a Markdown report plus a standalone HTML dashboard.

The project is production-oriented: deterministic code owns collection, derivation, validation, and rendering; agents own judgment. Missing data is reported explicitly and never fabricated.

## Quick start

Requirements: Python 3.9+ (3.11+ recommended).

```bash
python -m venv .venv
pip install -r requirements.txt
python tools/astock.py doctor
python tools/astock.py review
```

For an interactive coding-agent harness, continue until completion:

```bash
python tools/astock.py next
# Produce the requested artifact.
python tools/astock.py done <agent>
```

For unattended API execution, copy `config/models.yaml.example` to `config/models.yaml`, configure a provider, then run:

```bash
python tools/astock.py run
```

Useful operations:

```bash
python tools/astock.py check       # test each dataset block
python tools/astock.py status      # inspect the active run
python tools/astock.py cooldown    # inspect source circuit breakers
python tools/astock.py store       # inspect the local history store
python tools/astock.py demo        # generate the offline example
```

## Architecture

Each agent is a strict, discoverable package:

```text
agents/<package>/
  AGENT.md                 identity, contracts, dependencies
  SKILL.md                 primary method
  skills/*/SKILL.md        optional owned subskills
  tools/*.py               agent-owned executable capabilities
  scripts/**/*.py          agent-owned deterministic runtime
```

Built-in packages:

- `orchestrator`
- `data_engineer`
- `market_analyst`
- `sector_analyst`
- `news_analyst`
- `position_advisor`
- `report_writer`

Agents communicate only through validated artifacts under `workspace/runs/<run_id>/`. Schemas under `schemas/` are the stable API between packages.

The filesystem is the ownership model: there are no ownership manifests. Root `tools/` only provides backward-compatible launchers, while genuinely shared primitives live in `core/`.

See [Architecture](docs/ARCHITECTURE.md), [Extensions](docs/EXTENSIONS.md), and [Data integration](docs/04-数据接入指南.md).

## Extensibility

Configure external package roots in `config/extensions.yaml` or environment variables:

```yaml
paths:
  agents: [../my-astock-agents]
  skills: [../my-skills]
  providers: [../my-market-providers]

agent_skills:
  market-analyst: [my-market-method]
```

Equivalent environment variables use the platform path separator:

- `ASTOCK_AGENTS_PATHS`
- `ASTOCK_SKILLS_PATHS`
- `ASTOCK_PROVIDER_PATHS`

Data-source priority remains declarative in `config/datasources.yaml`. A provider is a small Python module exposing the named capability used by a dataset, such as `spot()`.

## Harness support

Agent definitions are harness-neutral. Thin adapters for Claude Code, OpenCode, Cursor, and Codex are generated from the discovered packages:

```bash
python tools/sync_harness.py
python tools/sync_harness.py --check
```

Generated adapter files must not be edited directly.

## Safety and output policy

- Every claim must trace to a concrete input field and value.
- Missing required data produces `blocked`, never invented data.
- Each position receives exactly one action.
- Reports do not provide target prices or recommend new securities.
- A non-trading day does not produce a close review.

## Development

```bash
pytest tests/ -q
python tools/sync_harness.py --check
```

The offline example in `workspace/runs/2026-08-28_example/` is synthetic and is committed as a contract fixture. Runtime runs, caches, local history, positions, and credentials are ignored by Git.
