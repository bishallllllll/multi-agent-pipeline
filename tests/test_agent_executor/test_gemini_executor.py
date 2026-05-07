import pytest
from unittest.mock import patch, MagicMock

from agent_executor.gemini_executor import execute, _extract_code_blocks, MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await execute("sys", "task", "gemini-2.0-flash")
            assert result["success"] is False
            assert "API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_only_gemini_key_google_key_present(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello"
        mock_result.stderr = ""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=True):
            with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
                mock_run.return_value = mock_result
                result = await execute("sys", "task", "gemini-2.0-flash")
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello from Gemini"
        mock_result.stderr = ""

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
                mock_run.return_value = mock_result
                result = await execute("sys", "task", "gemini-2.0-flash")
                assert result["success"] is True
                assert "Hello from Gemini" in result["text"]

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error occurred"

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
                mock_run.return_value = mock_result
                result = await execute("sys", "task", "gemini-2.0-flash")
                assert result["success"] is False
                assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_timeout(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
                mock_run.side_effect = TimeoutError("timed out")
                result = await execute("sys", "task", "gemini-2.0-flash")
                assert result["success"] is False
                assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_exception(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("agent_executor.gemini_executor.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("unexpected error")
                result = await execute("sys", "task", "gemini-2.0-flash")
                assert result["success"] is False
                assert "unexpected error" in result["error"]

    def test_models_list(self):
        assert "gemini-2.0-flash" in MODELS
        assert "gemini-2.5-pro" in MODELS
