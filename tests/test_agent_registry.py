from pathlib import Path

from core import agent_registry
from core.agent_registry import agent_file, agent_files, read_meta, skill_files


def test_builtin_agents_are_strict_packages():
    found = {read_meta(path)["name"]: path for path in agent_files()}
    assert "market-analyst" in found
    for path in found.values():
        assert path.name == "AGENT.md"
        assert (path.parent / "SKILL.md").is_file()


def test_external_agent_path_precedes_builtins(monkeypatch, tmp_path):
    package = tmp_path / "custom"
    package.mkdir()
    (package / "AGENT.md").write_text(
        "---\nname: custom-agent\ndisplay_name: Custom\n---\n\n# Custom\n",
        encoding="utf-8")
    (package / "SKILL.md").write_text("# Custom method\n", encoding="utf-8")
    monkeypatch.setenv("ASTOCK_AGENTS_PATHS", str(tmp_path))
    assert agent_file("custom-agent") == package / "AGENT.md"


def test_config_can_extend_builtin_agent_skills(monkeypatch, tmp_path):
    skill = tmp_path / "my-method"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# My method\n", encoding="utf-8")
    config = tmp_path / "extensions.yaml"
    config.write_text(
        f"paths:\n  skills: [{tmp_path.as_posix()}]\n"
        "agent_skills:\n  news-analyst: [my-method]\n",
        encoding="utf-8")
    monkeypatch.setattr(agent_registry, "CONFIG", config)
    definition = agent_file("news-analyst")
    assert skill / "SKILL.md" in skill_files(definition)
