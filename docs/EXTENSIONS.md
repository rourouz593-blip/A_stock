# Extensions

## Search paths

Add local package roots to `config/extensions.yaml`:

```yaml
paths:
  agents: [extensions/agents]
  skills: [extensions/skills]
  providers: [extensions/providers]

agent_skills:
  market-analyst: [my-market-method]
```

Paths may be absolute or repository-relative. Environment variables `ASTOCK_AGENTS_PATHS`, `ASTOCK_SKILLS_PATHS`, and `ASTOCK_PROVIDER_PATHS` add temporary roots using the operating system path separator.

Configured paths are searched before built-ins, allowing a local package to replace a built-in agent or provider by name.

## External agent

An agent root may contain one package or multiple child packages. Each package needs `AGENT.md` and `SKILL.md`; optional executable code belongs in its own `tools/` and `scripts/` directories.

The stable ID comes from `AGENT.md`:

```yaml
---
name: my-market-analyst
display_name: My market analyst
model: reasoning
depends_on: [data-engineer]
reads: [workspace/runs/{run_id}/dataset.json]
writes: [workspace/runs/{run_id}/my_market.json]
schema: schemas/my_market.schema.json
skills: [my-extra-method]
tools: [validate_artifact]
---
```

## External skill

A skill root contains `<name>/SKILL.md`. Attach a skill to a built-in agent through `agent_skills` without editing the package. Package authors can also use the `skills:` field in `AGENT.md`; a relative entry such as `skills/local-method` loads a package-owned skill first.

## External provider

A provider root contains `<name>.py` or `<name>/__init__.py`. The module exports capabilities requested by datasets. For example:

```python
def spot(codes, **kwargs):
    return {code: {"code": code, "price": None} for code in codes}
```

Add the provider name to the relevant chain in `config/datasources.yaml`, validate it with `python tools/verify_provider.py`, and keep provenance enabled.
