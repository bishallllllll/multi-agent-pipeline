import pytest
from unittest.mock import patch, AsyncMock
from agent_executor.openai_executor import execute, _extract_code_blocks, MODELS


class TestOpenAIConstants:
    def test_models_defined(self):
        assert "gpt-4o" in MODELS
        assert "gpt-4o-mini" in MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert "print" in blocks[0]["content"]

    def test_multiple_blocks(self):
        text = "```py\na=1\n```\nand\n```js\nconsole.log(1)\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) >= 2

    def test_block_without_lang(self):
        text = "```\nplain code\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "text"


@pytest.mark.asyncio
class TestOpenAIExecute:
    @patch.dict("os.environ", {}, clear=True)
    async def test_missing_api_key(self):
        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False
        assert "OPENAI_API_KEY not set" in result["error"]

    @patch("agent_executor.openai_executor.AsyncOpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    async def test_successful_execution(self, mock_openai):
        mock_instance = AsyncMock()
        mock_openai.return_value = mock_instance

        mock_choice = AsyncMock()
        mock_choice.message.content = "Hello world"
        mock_choice.message.tool_calls = None

        mock_response = AsyncMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 10

        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await execute(system_prompt="Be helpful", task="Say hello")
        assert result["success"] is True
        assert "Hello" in result["text"]
        assert result["tokens"] == 10

    @patch("agent_executor.openai_executor.AsyncOpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    async def test_execution_with_tool_call(self, mock_openai):
        mock_instance = AsyncMock()
        mock_openai.return_value = mock_instance

        mock_tool_call = AsyncMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "run_shell_command"
        mock_tool_call.function.arguments = '{"command": "echo hello"}'

        mock_choice = AsyncMock()
        mock_choice.message.content = "Using tool"
        mock_choice.message.tool_calls = [mock_tool_call]

        mock_response = AsyncMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 20
        mock_response.usage = AsyncMock()
        mock_response.usage.total_tokens = 20

        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await execute(system_prompt="Use tools", task="Run a command")
        assert result["success"] is True

    @patch("agent_executor.openai_executor.AsyncOpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    async def test_execution_exception(self, mock_openai):
        mock_instance = AsyncMock()
        mock_openai.return_value = mock_instance
        mock_instance.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        result = await execute(system_prompt="test", task="test")
        assert result["success"] is False
        assert "API error" in result["error"]
