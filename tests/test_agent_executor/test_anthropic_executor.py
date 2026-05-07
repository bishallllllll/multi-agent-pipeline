import pytest
from unittest.mock import patch, AsyncMock
from agent_executor.anthropic_executor import execute, _extract_code_blocks, MODELS


class TestAnthropicConstants:
    def test_models_defined(self):
        assert "claude-3-5-sonnet-20241022" in MODELS
        assert "claude-4" in MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"


@pytest.mark.asyncio
class TestAnthropicExecute:
    @patch.dict("os.environ", {}, clear=True)
    async def test_missing_api_key(self):
        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False
        assert "ANTHROPIC_API_KEY not set" in result["error"]

    @patch("agent_executor.anthropic_executor.AsyncAnthropic")
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    async def test_successful_execution(self, mock_anthropic):
        mock_instance = AsyncMock()
        mock_anthropic.return_value = mock_instance

        mock_block = AsyncMock()
        mock_block.type = "text"
        mock_block.text = "Hello from Claude"

        mock_response = AsyncMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        result = await execute(system_prompt="Be helpful", task="Say hello")
        assert result["success"] is True
        assert "Hello from Claude" in result["text"]
        assert result["tokens"] == 30

    @patch("agent_executor.anthropic_executor.AsyncAnthropic")
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    async def test_execution_with_tool_use(self, mock_anthropic):
        mock_instance = AsyncMock()
        mock_anthropic.return_value = mock_instance

        mock_text_block = AsyncMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Let me use a tool"

        mock_tool_block = AsyncMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "run_shell_command"
        mock_tool_block.id = "toolu_1"
        mock_tool_block.input = {"command": "echo hello"}

        mock_response = AsyncMock()
        mock_response.content = [mock_text_block, mock_tool_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        result = await execute(system_prompt="Use tools", task="Do something")
        assert result["success"] is True

    @patch("agent_executor.anthropic_executor.AsyncAnthropic")
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    async def test_execution_exception(self, mock_anthropic):
        mock_instance = AsyncMock()
        mock_anthropic.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(side_effect=Exception("API error"))

        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False
        assert "API error" in result["error"]
