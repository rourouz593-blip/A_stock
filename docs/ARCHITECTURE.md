# Architecture

## Runtime flow

```text
orchestrator
  -> data-engineer -> dataset.json
  -> market-analyst -> market.json
  -> sector-analyst -> sectors.json
  -> news-analyst -> news.json
  -> position-advisor -> positions_review.json
  -> report-writer -> report.json -> report.md / report.html
```

The pipeline is a file-contract system. Agents do not share memory or call each other. `run_manifest.json` records state, and JSON Schema validation is the boundary between steps.

## Deterministic and agent responsibilities

Deterministic Python owns network access, caches, derivations, risk arithmetic, validation, persistence, and rendering. Agents own classification, attribution, scenario construction, and synthesis.

This division makes repeated runs auditable and prevents a model from silently changing numerical definitions.

## Package discovery

`core/agent_registry.py` discovers `AGENT.md` packages from configured roots. The package's `SKILL.md` is mandatory and always loaded. Declared subskills are resolved relative to the package, then from external skill roots.

Harness adapters are generated views of discovered packages. They contain routing metadata and pointers, not duplicated business logic.

## Shared runtime

Agent-specific implementation lives directly under `agents/<package>/tools/` and `agents/<package>/scripts/`. Directory placement is the ownership declaration, so no ownership manifest is needed.

Root `tools/` contains only stable compatibility launchers. `core/` is reserved for code used by multiple agent packages, such as schemas, paths, package discovery, and artifact IO.
