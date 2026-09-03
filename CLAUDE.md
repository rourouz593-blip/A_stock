# Claude Code entry point

This is a harness-neutral A-share daily review pipeline. Read `AGENTS.md`, then drive the deterministic state machine:

```bash
python tools/astock.py review
python tools/astock.py next
python tools/astock.py done <agent>
```

Do not fetch data ad hoc, fabricate missing inputs, or edit generated files under `.claude/`. Regenerate adapters with `python tools/sync_harness.py`.
