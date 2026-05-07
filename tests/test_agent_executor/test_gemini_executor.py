import pytest
from unittest.mock import patch, AsyncMock
from agent_executor.gemini_executor import execute, _extract_code_blocks, MODELS


class TestGeminiConstants:
    def test_models_defined(self):
        assert "gemini-2.0-flash" in MODELS
        assert "gemini-2.5-pro" in MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"


@pytest.mark.asyncio
class TestGeminiExecute:
    @patch.dict("os.environ", {}, clear=True)
    async def test_missing_api_key(self):
        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False
        assert "GEMINI_API_KEY" in result["error"]

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("agent_executor.gemini_executor.subprocess.run")
    async def test_successful_execution(self, mock_run):
        mock_result = AsyncMock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello from Gemini"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = await execute(system_prompt="Be helpful", task="Say hello")
        assert result["success"] is True
        assert "Hello from Gemini" in result["text"]

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("agent_executor.gemini_executor.subprocess.run")
    async def test_failed_execution(self, mock_run):
        mock_result = AsyncMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Command not found"
        mock_run.return_value = mock_result

        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    @patch("agent_executor.gemini_executor.subprocess.run")
    async def test_google_api_key_fallback(self, mock_run):
        mock_result = AsyncMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = await execute(system_prompt="test", task="test")
        assert result["success"] is True
