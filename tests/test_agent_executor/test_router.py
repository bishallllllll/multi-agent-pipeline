import pytest
from unittest.mock import patch

from agent_executor.router import _model_provider, AgentExecutorRouter


class TestModelProvider:
    def test_openai_gpt(self):
        assert _model_provider("gpt-4o") == "openai"

    def test_openai_o1(self):
        assert _model_provider("o1") == "openai"

    def test_openai_o3(self):
        assert _model_provider("o3-mini") == "openai"

    def test_anthropic_claude(self):
        assert _model_provider("claude-3-5-sonnet-20241022") == "anthropic"

    def test_anthropic_anthropic(self):
        assert _model_provider("anthropic/claude-4") == "anthropic"

    def test_gemini(self):
        assert _model_provider("gemini-2.0-flash") == "gemini"

    def test_default_fallback(self):
        assert _model_provider("unknown-model") == "openai"

    def test_case_insensitive(self):
        assert _model_provider("GPT-4O") == "openai"
        assert _model_provider("CLAUDE-3") == "anthropic"
        assert _model_provider("GEMINI-2.0") == "gemini"


class TestAgentExecutorRouter:
    @pytest.mark.asyncio
    async def test_execute_openai(self):
        with patch("agent_executor.router.openai_executor.execute") as mock_exec:
            mock_exec.return_value = {"success": True, "text": "done", "tokens": 100}
            result = await AgentExecutorRouter.execute(
                system_prompt="test", task="test", model="gpt-4o"
            )
            assert result["success"] is True
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_anthropic(self):
        with patch("agent_executor.router.anthropic_executor.execute") as mock_exec:
            mock_exec.return_value = {"success": True, "text": "done", "tokens": 100}
            result = await AgentExecutorRouter.execute(
                system_prompt="test", task="test", model="claude-3-5-sonnet-20241022"
            )
            assert result["success"] is True
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_gemini(self):
        with patch("agent_executor.router.gemini_executor.execute") as mock_exec:
            mock_exec.return_value = {"success": True, "text": "done", "tokens": 0}
            result = await AgentExecutorRouter.execute(
                system_prompt="test", task="test", model="gemini-2.0-flash"
            )
            assert result["success"] is True
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_provider_falls_back_to_openai(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch("agent_executor.router.openai_executor.execute") as mock_exec:
                mock_exec.return_value = {"success": True, "text": "done", "tokens": 0}
                result = await AgentExecutorRouter.execute(
                    system_prompt="test", task="test", model="unknown-model-123"
                )
                assert result["success"] is True
                mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_passes_parameters(self):
        with patch("agent_executor.router.openai_executor.execute") as mock_exec:
            mock_exec.return_value = {"success": True, "text": "", "tokens": 0}
            await AgentExecutorRouter.execute(
                system_prompt="sys", task="t", model="gpt-4o-mini",
                max_tokens=2048, agent_timeout=60,
            )
            mock_exec.assert_called_once_with("sys", "t", "gpt-4o-mini", 2048, 60)
