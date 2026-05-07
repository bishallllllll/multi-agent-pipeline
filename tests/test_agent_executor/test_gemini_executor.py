import pytest
from unittest.mock import patch, MagicMock


class TestGeminiExecutor:
    @pytest.mark.asyncio
    async def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        from agent_executor.gemini_executor import execute
        result = await execute("sys", "task")
        assert result["success"] is False
        assert "GEMINI_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_env_gemini):
        mock_result = MagicMock()
        mock_result.stdout = "Hello from Gemini"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("agent_executor.gemini_executor.subprocess.run", return_value=mock_result):
            from agent_executor.gemini_executor import execute
            result = await execute("Be helpful", "Say hi", model="gemini-2.0-flash")
            assert result["success"] is True
            assert "Hello from Gemini" in result["text"]

    @pytest.mark.asyncio
    async def test_execution_failure(self, mock_env_gemini):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Command not found"
        mock_result.returncode = 1

        with patch("agent_executor.gemini_executor.subprocess.run", return_value=mock_result):
            from agent_executor.gemini_executor import execute
            result = await execute("sys", "task", model="gemini-2.0-flash")
            assert result["success"] is False
            assert result["error"] == "Command not found"

    @pytest.mark.asyncio
    async def test_timeout(self, mock_env_gemini):
        import asyncio

        with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("timed out")
            from agent_executor.gemini_executor import execute
            result = await execute("sys", "task", model="gemini-2.0-flash", agent_timeout=1)
            assert result["success"] is False
            assert "timed out" in result["error"]
