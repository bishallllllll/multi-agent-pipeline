import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from agent_executor.openai_executor import execute, _extract_code_blocks, MODELS


class TestExtractCodeBlocks:
    def test_no_blocks(self):
        assert _extract_code_blocks("plain text") == []

    def test_single_block(self):
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert blocks[0]["content"] == "print('hello')"

    def test_multiple_blocks(self):
        text = "```python\nprint(1)\n```\n```js\nconsole.log(2)\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2

    def test_no_language(self):
        text = "```\nplain code\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "text"

    def test_empty_block(self):
        text = "```python\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 0


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await execute("sys", "task", "gpt-4o")
            assert result["success"] is False
            assert "OPENAI_API_KEY not set" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        mock_message = MagicMock()
        mock_message.content = "Hello world"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_usage = MagicMock()
        mock_usage.total_tokens = 50

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch("agent_executor.openai_executor.AsyncOpenAI", return_value=mock_client):
                result = await execute("sys", "task", "gpt-4o")
                assert result["success"] is True
                assert result["text"] == "Hello world"
                assert result["tokens"] == 50

    @pytest.mark.asyncio
    async def test_execution_with_tool_call(self):
        mock_tool_message = MagicMock()
        mock_tool_message.content = "Let me calculate that"
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "run_python_script"
        mock_tool_call.function.arguments = '{"code": "print(2+2)"}'
        mock_tool_call.id = "call_123"
        mock_tool_message.tool_calls = [mock_tool_call]

        mock_final_message = MagicMock()
        mock_final_message.content = "The answer is 4"
        mock_final_message.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.total_tokens = 100

        mock_response_1 = MagicMock()
        mock_response_1.choices = [MagicMock(message=mock_tool_message)]
        mock_response_1.usage = mock_usage

        mock_response_2 = MagicMock()
        mock_response_2.choices = [MagicMock(message=mock_final_message)]
        mock_response_2.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[mock_response_1, mock_response_2]
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch("agent_executor.openai_executor.AsyncOpenAI", return_value=mock_client):
                with patch("agent_executor.openai_executor.execute_tool", AsyncMock(return_value="4")):
                    result = await execute("sys", "task", "gpt-4o")
                    assert result["success"] is True
                    assert "Let me calculate that" in result["text"]
                    assert "The answer is 4" in result["text"]

    @pytest.mark.asyncio
    async def test_api_error(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch("agent_executor.openai_executor.AsyncOpenAI", return_value=mock_client):
                result = await execute("sys", "task", "gpt-4o")
                assert result["success"] is False
                assert "API rate limit exceeded" in result["error"]

    @pytest.mark.asyncio
    async def test_max_tool_calls(self):
        mock_message = MagicMock()
        mock_message.content = "thinking..."
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "run_python_script"
        mock_tool_call.function.arguments = '{"code": "print(1)"}'
        mock_tool_call.id = "call_x"
        mock_message.tool_calls = [mock_tool_call]

        mock_usage = MagicMock()
        mock_usage.total_tokens = 10

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch("agent_executor.openai_executor.AsyncOpenAI", return_value=mock_client):
                with patch("agent_executor.openai_executor.execute_tool", AsyncMock(return_value="4")):
                    result = await execute("sys", "task", "gpt-4o")
                    assert "[Max tool calls reached]" in result["text"]

    def test_models_list(self):
        assert "gpt-4o" in MODELS
        assert "gpt-4o-mini" in MODELS
        assert "o1" in MODELS
