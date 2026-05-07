import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from orchestrator.pipeline import (
    load_config,
    get_model_for_agent,
    find_agent_prompt,
    extract_agent_description,
    find_first_agent,
    find_next_agents,
    spawn_agent,
)


class TestLoadConfig:
    def test_loads_existing_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"agents_dir": "/custom/path", "models": {"standard": "gpt-4"}}, f)
            tmp_path = f.name
        try:
            config = load_config(tmp_path)
            assert config["agents_dir"] == "/custom/path"
            assert config["models"]["standard"] == "gpt-4"
        finally:
            os.unlink(tmp_path)

    def test_returns_defaults_if_no_config(self):
        config = load_config("/nonexistent/path.yaml")
        assert "agents_dir" in config
        assert "models" in config
        assert "default_max_steps" in config

    def test_default_values(self):
        config = load_config("/nonexistent/path.yaml")
        assert config["default_max_steps"] == 10
        assert config["default_mode"] == "autonomous"
        assert config["retry_count"] == 2
        assert config["agent_timeout"] == 300


class TestGetModelForAgent:
    def test_high_complexity_agent(self):
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

    def test_fast_agent(self):
        config = {
            "model_categories": {
                "high_complexity": ["architect"],
                "fast": ["writer", "formatter"],
            },
            "models": {
                "high_complexity": "gpt-4o",
                "standard": "gpt-4o-mini",
                "fast": "gpt-4o-mini",
            },
        }
        model = get_model_for_agent("writer", config)
        assert model == "gpt-4o-mini"

    def test_standard_agent(self):
        config = {
            "model_categories": {
                "high_complexity": ["architect"],
                "fast": ["writer"],
            },
            "models": {
                "high_complexity": "gpt-4o",
                "standard": "gpt-4o-mini",
                "fast": "gpt-4o-mini",
            },
        }
        model = get_model_for_agent("unknown-agent", config)
        assert model == "gpt-4o-mini"

    def test_case_insensitive(self):
        config = {
            "model_categories": {
                "high_complexity": ["Architect", "Researcher"],
            },
            "models": {
                "high_complexity": "gpt-4o",
                "standard": "gpt-4o-mini",
            },
        }
        model = get_model_for_agent("ARCHITECT", config)
        assert model == "gpt-4o"


class TestFindAgentPrompt:
    def test_finds_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_dir = os.path.join(tmpdir, "backend")
            os.makedirs(agent_dir)
            prompt_path = os.path.join(agent_dir, "python-engineer.md")
            with open(prompt_path, "w") as f:
                f.write("description: Python expert")
            result = find_agent_prompt("python-engineer", tmpdir)
            assert result == Path(prompt_path)

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_agent_prompt("nonexistent-agent", tmpdir)
            assert result is None

    def test_skips_non_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            non_dir = os.path.join(tmpdir, "not_a_dir")
            with open(non_dir, "w") as f:
                f.write("")
            result = find_agent_prompt("any-agent", tmpdir)
            assert result is None


class TestExtractAgentDescription:
    def test_extracts_description(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("description: Python developer expert\n# More content\n")
            tmp_path = f.name
        try:
            desc = extract_agent_description(Path(tmp_path))
            assert desc == "Python developer expert"
        finally:
            os.unlink(tmp_path)

    def test_no_description_found(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Just a header\nSome content\n")
            tmp_path = f.name
        try:
            desc = extract_agent_description(Path(tmp_path))
            assert desc == ""
        finally:
            os.unlink(tmp_path)


class TestFindFirstAgent:
    @pytest.mark.asyncio
    async def test_returns_first_agent(self):
        mock_rag = AsyncMock()
        mock_rag.find_first_agent.return_value = [
            {"name": "python-engineer", "category": "backend", "score": 0.95},
            {"name": "backend-developer", "category": "backend", "score": 0.80},
        ]
        result = await find_first_agent(mock_rag, "build a python module")
        assert result["name"] == "python-engineer"

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self):
        mock_rag = AsyncMock()
        mock_rag.find_first_agent.return_value = []
        result = await find_first_agent(mock_rag, "task")
        assert result is None


class TestFindNextAgents:
    @pytest.mark.asyncio
    async def test_returns_unique_agents(self):
        mock_rag = AsyncMock()
        mock_rag.find_next_step.return_value = [
            {"name": "code-reviewer", "category": "quality"},
            {"name": "code-reviewer", "category": "quality"},  # duplicate
            {"name": "test-architect", "category": "testing"},
        ]
        result = await find_next_agents(mock_rag, "completed task", "prev-agent")
        assert len(result) == 2
        assert result[0]["name"] == "code-reviewer"
        assert result[1]["name"] == "test-architect"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        mock_rag = AsyncMock()
        mock_rag.find_next_step.return_value = []
        result = await find_next_agents(mock_rag, "task", "agent")
        assert result == []


class TestSpawnAgent:
    @pytest.mark.asyncio
    async def test_missing_prompt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"agents_dir": tmpdir, "agent_timeout": 30}
            parser = AsyncMock()
            result = await spawn_agent(
                {"name": "nonexistent", "category": "test"},
                "task", "context", "gpt-4o", config, parser, tmpdir,
            )
            assert result["success"] is False
            assert "Prompt file not found" in result["error"]
