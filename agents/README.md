# Agent packages

Each child directory is a self-contained agent package. The directory name is filesystem-safe; the stable agent ID is the `name` field in `AGENT.md`.

Required files:

```text
<package>/
  AGENT.md
  SKILL.md
  tools/*.py
  scripts/**/*.py
```

`AGENT.md` declares identity, model tier, dependencies, reads, writes, schema, tools, and optional additional skills. `SKILL.md` is always loaded. Additional entries in `skills:` resolve first relative to the package and then through configured external skill roots.

To add an agent:

1. Copy a package and assign a unique `name` in `AGENT.md`.
2. Define its input/output contract and add the schema first.
3. Put agent-specific tools and scripts inside the package; directory placement declares ownership.
4. Add the agent ID to `config/pipeline.yaml` where required.
5. Run `python tools/sync_harness.py` and `pytest tests/ -q`.
