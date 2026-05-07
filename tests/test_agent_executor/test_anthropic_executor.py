import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from agent_executor.anthropic_executor import execute, _extract_code_blocks, MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"

    def test_multiple_blocks(self):
        text = "```py\na=1\n```\n```js\nb=2\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await execute("sys", "task")
            assert result["success"] is False
            assert "ANTHROPIC_API_KEY not set" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_text_response(self):
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Hello from Claude"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("agent_executor.anthropic_executor.AsyncAnthropic", return_value=mock_client):
                result = await execute("sys", "task")
                assert result["success"] is True
                assert "Hello from Claude" in result["text"]
                assert result["tokens"] == 30
                assert result["error"] is None

    @pytest.mark.asyncio
    async def test_tool_use_response(self):
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I'll run a calculation"

        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "run_python_script"
        mock_tool_block.input = {"code": "print(2+2)"}
        mock_tool_block.id = "toolu_123"

        mock_tool_result_block = MagicMock()
        mock_tool_result_block.type = "tool_result"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 15
        mock_usage.output_tokens = 25

        mock_response_1 = MagicMock()
        mock_response_1.content = [mock_text_block, mock_tool_block]
        mock_response_1.usage = mock_usage

        mock_response_2 = MagicMock()
        mock_response_2.content = [mock_tool_result_block]
        mock_response_2.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[mock_response_1, mock_response_2]
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("agent_executor.anthropic_executor.AsyncAnthropic", return_value=mock_client):
                with patch("agent_executor.anthropic_executor.execute_tool", AsyncMock(return_value="4")):
                    result = await execute("sys", "task")
                    assert result["success"] is True
                    assert "I'll run a calculation" in result["text"]

    @pytest.mark.asyncio
    async def test_api_error(self):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("Anthropic API error")
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("agent_executor.anthropic_executor.AsyncAnthropic", return_value=mock_client):
                result = await execute("sys", "task")
                assert result["success"] is False
                assert "Anthropic API error" in result["error"]

    def test_models_list(self):
        assert "claude-3-5-sonnet" in MODELS
        assert "claude-4" in MODELS
