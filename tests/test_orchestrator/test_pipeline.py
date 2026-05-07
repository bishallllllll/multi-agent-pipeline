import os
import tempfile
from pathlib import Path
from orchestrator.pipeline import (
    load_config, get_model_for_agent, find_agent_prompt,
    extract_agent_description,
)


def test_load_config_default():
    config = load_config("/nonexistent/config.yaml")
    assert config["agents_dir"] is not None
    assert config["default_max_steps"] == 10
    assert config["default_mode"] == "autonomous"


def test_load_config_from_file(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("agents_dir: /tmp/agents\ndefault_max_steps: 5\n")
    config = load_config(str(config_file))
    assert config["agents_dir"] == "/tmp/agents"
    assert config["default_max_steps"] == 5


def test_get_model_for_agent_high_complexity():
    config = {
        "model_categories": {
            "high_complexity": ["architect", "researcher"],
            "fast": ["writer"],
        },
        "models": {
            "high_complexity": "gpt-4o",
            "standard": "gpt-4o-mini",
            "fast": "gpt-4o-mini",
        },
    }
    model = get_model_for_agent("architect", config)
    assert model == "gpt-4o"


def test_get_model_for_agent_fast():
    config = {
        "model_categories": {
            "high_complexity": ["architect"],
            "fast": ["writer", "documenter"],
        },
        "models": {
            "high_complexity": "gpt-4o",
            "standard": "gpt-4o-mini",
            "fast": "gpt-4o-mini",
        },
    }
    model = get_model_for_agent("writer", config)
    assert model == "gpt-4o-mini"


def test_get_model_for_agent_standard():
    config = {
        "model_categories": {
            "high_complexity": ["architect"],
            "fast": ["writer"],
        },
        "models": {
            "high_complexity": "gpt-4o",
            "standard": "claude-3-haiku",
            "fast": "gpt-4o-mini",
        },
    }
    model = get_model_for_agent("python-engineer", config)
    assert model == "claude-3-haiku"


def test_find_agent_prompt_found(tmp_path):
    agents_dir = tmp_path / "agents"
    category_dir = agents_dir / "core-development"
    category_dir.mkdir(parents=True)
    prompt_file = category_dir / "test-agent.md"
    prompt_file.write_text("# Test Agent\n")
    result = find_agent_prompt("test-agent", str(agents_dir))
    assert result is not None
    assert result.name == "test-agent.md"


def test_find_agent_prompt_not_found(tmp_path):
    result = find_agent_prompt("nonexistent", str(tmp_path))
    assert result is None


def test_extract_agent_description():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Agent\n\ndescription: This is a test agent\n\nSome more content\n")
        tmp_path = f.name
    try:
        desc = extract_agent_description(Path(tmp_path))
        assert desc == "This is a test agent"
    finally:
        os.unlink(tmp_path)


def test_extract_agent_description_no_match():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Agent with no description field\n")
        tmp_path = f.name
    try:
        desc = extract_agent_description(Path(tmp_path))
        assert desc == ""
    finally:
        os.unlink(tmp_path)
