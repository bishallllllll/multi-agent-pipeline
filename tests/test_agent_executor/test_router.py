import pytest
from agent_executor.router import _model_provider, AgentExecutorRouter


class TestModelProvider:
    def test_openai_gpt(self):
        assert _model_provider("gpt-4o") == "openai"
        assert _model_provider("gpt-4o-mini") == "openai"
        assert _model_provider("gpt-4-turbo") == "openai"

    def test_openai_o_series(self):
        assert _model_provider("o1") == "openai"
        assert _model_provider("o3") == "openai"
        assert _model_provider("o3-mini") == "openai"

    def test_anthropic(self):
        assert _model_provider("claude-3-5-sonnet-20241022") == "anthropic"
        assert _model_provider("claude-4") == "anthropic"
        assert _model_provider("claude-3-opus") == "anthropic"

    def test_gemini(self):
        assert _model_provider("gemini-2.0-flash") == "gemini"
        assert _model_provider("gemini-2.5-pro") == "gemini"

    def test_unknown_falls_back_to_openai(self):
        assert _model_provider("llama-3") == "openai"


class TestAgentExecutorRouter:
    @pytest.mark.asyncio
    async def test_execute_openai_no_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = await AgentExecutorRouter.execute("sys", "task", model="gpt-4o")
        assert result["success"] is False
        assert "OPENAI_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_anthropic_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = await AgentExecutorRouter.execute("sys", "task", model="claude-3-5-sonnet-20241022")
        assert result["success"] is False
        assert "ANTHROPIC_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_gemini_no_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        result = await AgentExecutorRouter.execute("sys", "task", model="gemini-2.0-flash")
        assert result["success"] is False
        assert "GEMINI_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_unknown_model_falls_back_to_openai(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = await AgentExecutorRouter.execute("sys", "task", model="unknown-model-xyz")
        assert result["success"] is False
        assert "OPENAI_API_KEY" in result["error"]
