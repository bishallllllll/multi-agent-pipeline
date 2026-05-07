import pytest
from unittest.mock import patch, AsyncMock
from agent_executor.router import _model_provider, AgentExecutorRouter


class TestModelProvider:
    def test_openai_gpt(self):
        assert _model_provider("gpt-4o") == "openai"
        assert _model_provider("gpt-4o-mini") == "openai"

    def test_openai_o_series(self):
        assert _model_provider("o1") == "openai"
        assert _model_provider("o3-mini") == "openai"

    def test_anthropic(self):
        assert _model_provider("claude-3-5-sonnet-20241022") == "anthropic"
        assert _model_provider("claude-4") == "anthropic"

    def test_gemini(self):
        assert _model_provider("gemini-2.0-flash") == "gemini"
        assert _model_provider("gemini-2.5-pro") == "gemini"

    def test_case_insensitive(self):
        assert _model_provider("GPT-4O") == "openai"
        assert _model_provider("Claude-3") == "anthropic"

    def test_fallback_openai(self):
        assert _model_provider("unknown-model") == "openai"


@pytest.mark.asyncio
class TestAgentExecutorRouter:
    @patch("agent_executor.router.openai_executor.execute", new_callable=AsyncMock)
    async def test_execute_openai(self, mock_openai):
        mock_openai.return_value = {"success": True, "text": "done"}
        result = await AgentExecutorRouter.execute(
            system_prompt="test", task="test", model="gpt-4o"
        )
        assert result["success"] is True
        mock_openai.assert_awaited_once()

    @patch("agent_executor.router.anthropic_executor.execute", new_callable=AsyncMock)
    async def test_execute_anthropic(self, mock_anthropic):
        mock_anthropic.return_value = {"success": True, "text": "done"}
        result = await AgentExecutorRouter.execute(
            system_prompt="test", task="test", model="claude-3-5-sonnet-20241022"
        )
        assert result["success"] is True
        mock_anthropic.assert_awaited_once()

    @patch("agent_executor.router.gemini_executor.execute", new_callable=AsyncMock)
    async def test_execute_gemini(self, mock_gemini):
        mock_gemini.return_value = {"success": True, "text": "done"}
        result = await AgentExecutorRouter.execute(
            system_prompt="test", task="test", model="gemini-2.0-flash"
        )
        assert result["success"] is True
        mock_gemini.assert_awaited_once()

    async def test_execute_unknown_provider_falls_back_to_openai(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await AgentExecutorRouter.execute(
                system_prompt="test", task="test", model="unknown-123"
            )
        assert result["success"] is False
        assert "OPENAI_API_KEY not set" in result["error"]
