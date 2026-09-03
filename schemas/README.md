# Artifact contracts

Agents communicate through files, and JSON Schema is the API between packages.

| Schema | Producer |
|---|---|
| `run_manifest.schema.json` | orchestrator |
| `dataset.schema.json` | data-engineer |
| `market.schema.json` | market-analyst |
| `sectors.schema.json` | sector-analyst |
| `news.schema.json` | news-analyst |
| `positions_review.schema.json` | position-advisor |
| `report.schema.json` | report-writer |

Change order:

1. Update the schema.
2. Update the producer and consumers' `AGENT.md` files.
3. Update the synthetic example artifact.
4. Run `python tools/validate_artifact.py` and `pytest tests/ -q`.
