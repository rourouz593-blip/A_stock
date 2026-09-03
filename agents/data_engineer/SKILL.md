---
name: a-share-data-engineering
description: Build a traceable A-share daily dataset with explicit provenance and honest degradation.
---

# A-share data engineering

- Treat `dataset.json` as the only factual input to downstream agents.
- Every block records status, row count, provenance, parameters, and quality flags.
- Never fill missing market data with estimates or stale values without an explicit degraded flag.
- Prefer configured provider chains, batch endpoints, the local history store, and deterministic derivations.
- Validate a new provider against an existing source before adding it to the active chain.
- A failed optional block degrades the report; a failed trading calendar or required index block blocks its consumers.

