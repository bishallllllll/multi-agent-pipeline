import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.pipeline import (
    load_config,
    get_model_for_agent,
    find_agent_prompt,
    extract_agent_description,
)


class TestLoadConfig:
    def test_load_config_default(self, temp_dir):
        os.chdir(temp_dir)
        config = load_config()
        assert config["default_max_steps"] == 10
        assert "models" in config
        assert config["models"]["high_complexity"] == "gpt-4o"

    def test_load_config_custom_path(self, tmp_path):
        cfg = tmp_path / "custom.yaml"
        cfg.write_text("default_max_steps: 5\n")
        config = load_config(str(cfg))
        assert config["default_max_steps"] == 5

    def test_load_config_not_found(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert config["default_max_steps"] == 10


class TestGetModelForAgent:
    def test_high_complexity_agent(self):
        config = {
            "model_categories": {"high_complexity": ["architect"], "fast": []},
            "models": {"high_complexity": "gpt-4o", "standard": "gpt-4o-mini", "fast": "gpt-4o-mini"},
        }
        assert get_model_for_agent("system-architect", config) == "gpt-4o"

    def test_fast_agent(self):
        config = {
            "model_categories": {"high_complexity": [], "fast": ["writer"]},
            "models": {"high_complexity": "gpt-4o", "standard": "gpt-4o-mini", "fast": "gpt-4o-mini"},
        }
        assert get_model_for_agent("technical-writer", config) == "gpt-4o-mini"

    def test_default_agent(self):
        config = {
            "model_categories": {"high_complexity": [], "fast": []},
            "models": {"high_complexity": "gpt-4o", "standard": "gpt-4o-mini", "fast": "gpt-4o-mini"},
        }
        assert get_model_for_agent("unknown-agent", config) == "gpt-4o-mini"


class TestFindAgentPrompt:
    def test_find_existing_prompt(self, tmp_path):
        agents_dir = tmp_path / "agents"
        cat_dir = agents_dir / "core-development"
        cat_dir.mkdir(parents=True)
        prompt_file = cat_dir / "test-agent.md"
        prompt_file.write_text("description: A test agent")
        result = find_agent_prompt("test-agent", str(agents_dir))
        assert result == prompt_file

    def test_find_nonexistent_agent(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = find_agent_prompt("nonexistent", str(agents_dir))
        assert result is None


class TestExtractAgentDescription:
    def test_extract_description(self, tmp_path):
        f = tmp_path / "agent.md"
        f.write_text("description: This agent does X\nSome more text")
        assert extract_agent_description(f) == "This agent does X"

    def test_extract_no_description(self, tmp_path):
        f = tmp_path / "agent.md"
        f.write_text("no description field here")
        assert extract_agent_description(f) == ""


class TestFindFirstAgent:
    @pytest.mark.asyncio
    async def test_with_agents(self):
        mock_rag = AsyncMock()
        mock_rag.find_first_agent = AsyncMock(return_value=[{"name": "agent1", "category": "dev"}])
        from orchestrator.pipeline import find_first_agent
        result = await find_first_agent(mock_rag, "build stuff")
        assert result == {"name": "agent1", "category": "dev"}

    @pytest.mark.asyncio
    async def test_no_agents(self):
        mock_rag = AsyncMock()
        mock_rag.find_first_agent = AsyncMock(return_value=[])
        from orchestrator.pipeline import find_first_agent
        result = await find_first_agent(mock_rag, "build stuff")
        assert result is None


class TestFindNextAgents:
    @pytest.mark.asyncio
    async def test_deduplicates(self):
        mock_rag = AsyncMock()
        mock_rag.find_next_step = AsyncMock(return_value=[
            {"name": "agent1", "category": "dev"},
            {"name": "agent1", "category": "dev"},
            {"name": "agent2", "category": "test"},
        ])
        from orchestrator.pipeline import find_next_agents
        result = await find_next_agents(mock_rag, "task", "prev")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty(self):
        mock_rag = AsyncMock()
        mock_rag.find_next_step = AsyncMock(return_value=[])
        from orchestrator.pipeline import find_next_agents
        result = await find_next_agents(mock_rag, "task")
        assert result == []


class TestSpawnAgent:
    @pytest.mark.asyncio
    async def test_missing_prompt(self, tmp_path):
        from orchestrator.pipeline import spawn_agent
        config = {"agents_dir": str(tmp_path), "agent_timeout": 30}
        parser = MagicMock()
        result = await spawn_agent(
            {"name": "nonexistent", "category": "dev"},
            "do task", "", "gpt-4o", config, parser, str(tmp_path / "artifacts"),
        )
        assert result["success"] is False
        assert "Prompt file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_spawn(self, tmp_path):
        cat_dir = tmp_path / "agents" / "dev"
        cat_dir.mkdir(parents=True)
        (cat_dir / "test-agent.md").write_text("You are a test agent")

        config = {"agents_dir": str(tmp_path / "agents"), "agent_timeout": 30}
        parser = MagicMock()
        parser.save_artifacts.return_value = ["/tmp/out.py"]

        from orchestrator.pipeline import spawn_agent

        with patch("orchestrator.pipeline.AgentExecutorRouter.execute") as mock_exec:
            mock_exec.return_value = {
                "success": True, "error": None, "text": "done",
                "code_blocks": [{"language": "python", "content": "print('hi')"}],
                "artifacts": [], "tokens": 50,
            }
            result = await spawn_agent(
                {"name": "test-agent", "category": "dev"},
                "do task", "", "gpt-4o", config, parser, str(tmp_path / "artifacts"),
            )
            assert result["success"] is True


class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_dry_run(self):
        import argparse
        args = argparse.Namespace(
            task="build something", config=None, resume=False,
            mode=None, execution=None, max_steps=None,
            dry_run=True, interactive=False, parallel=False, sequential=False,
        )
        from orchestrator.pipeline import run_pipeline
        config = {
            "rag_api_url": "http://localhost:8000", "rag_timeout": 5,
            "default_mode": "autonomous", "default_execution": "parallel",
            "default_max_steps": 10, "artifact_dir": "./artifacts",
            "task_graph_file": ".task_graph.json", "agent_timeout": 300,
            "retry_count": 2, "models": {"high_complexity": "gpt-4o", "standard": "gpt-4o-mini", "fast": "gpt-4o-mini"},
            "model_categories": {"high_complexity": [], "fast": []},
        }
        with patch("orchestrator.pipeline.RagClient") as MockRag:
            mock_rag = AsyncMock()
            mock_rag.health_check.return_value = False
            MockRag.return_value = mock_rag
            await run_pipeline(args, config)

    @pytest.mark.asyncio
    async def test_no_task_no_resume(self):
        import argparse
        args = argparse.Namespace(
            task=None, config=None, resume=False,
            mode=None, execution=None, max_steps=None,
            dry_run=False, interactive=False, parallel=False, sequential=False,
        )
        config = {
            "rag_api_url": "http://localhost:8000", "rag_timeout": 5,
            "default_mode": "autonomous", "default_execution": "parallel",
            "default_max_steps": 10, "artifact_dir": "./artifacts",
            "task_graph_file": ".task_graph.json", "agent_timeout": 300,
            "retry_count": 2, "models": {"high_complexity": "gpt-4o", "standard": "gpt-4o-mini", "fast": "gpt-4o-mini"},
            "model_categories": {"high_complexity": [], "fast": []},
        }
        from orchestrator.pipeline import run_pipeline
        with patch("orchestrator.pipeline.RagClient") as MockRag:
            mock_rag = AsyncMock()
            mock_rag.health_check.return_value = False
            MockRag.return_value = mock_rag
            with pytest.raises(SystemExit):
                await run_pipeline(args, config)
