import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_openai():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content="Hello from GPT",
                tool_calls=None,
            )
        )
    ]
    mock_response.usage.total_tokens = 50
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestOpenAIExecutor:
    @pytest.mark.asyncio
    async def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from agent_executor.openai_executor import execute
        result = await execute("sys", "task", model="gpt-4o")
        assert result["success"] is False
        assert "OPENAI_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_openai, mock_env_openai):
        with patch("agent_executor.openai_executor.AsyncOpenAI", return_value=mock_openai):
            from agent_executor.openai_executor import execute
            result = await execute("Be helpful", "Say hi", model="gpt-4o")
            assert result["success"] is True
            assert "Hello from GPT" in result["text"]
            assert result["tokens"] == 50

    @pytest.mark.asyncio
    async def test_execution_error(self, mock_env_openai):
        with patch("agent_executor.openai_executor.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            from agent_executor.openai_executor import execute
            result = await execute("sys", "task", model="gpt-4o")
            assert result["success"] is False
            assert "API error" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, mock_env_openai):
        tool_call = MagicMock()
        tool_call.function.name = "run_shell_command"
        tool_call.function.arguments = '{"command": "echo hello"}'
        tool_call.id = "call_1"

        first_response = MagicMock()
        first_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="Let me run that",
                    tool_calls=[tool_call],
                )
            )
        ]
        first_response.usage.total_tokens = 20

        second_response = MagicMock()
        second_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="Done",
                    tool_calls=None,
                )
            )
        ]
        second_response.usage.total_tokens = 30

        mock_create = AsyncMock(side_effect=[first_response, second_response])

        with patch("agent_executor.openai_executor.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            from agent_executor.openai_executor import execute
            result = await execute("sys", "run", model="gpt-4o")
            assert result["success"] is True
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_max_tool_calls(self, mock_env_openai):
        tool_call = MagicMock()
        tool_call.function.name = "run_shell_command"
        tool_call.function.arguments = '{"command": "echo hello"}'
        tool_call.id = "call_1"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content="tooling",
                    tool_calls=[tool_call],
                )
            )
        ]
        response.usage.total_tokens = 10

        with patch("agent_executor.openai_executor.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
            from agent_executor.openai_executor import execute
            result = await execute("sys", "run", model="gpt-4o", max_tokens=256)
            assert "[Max tool calls reached]" in result["text"]

    def test_extract_code_blocks(self):
        from agent_executor.openai_executor import _extract_code_blocks
        text = "Here's code:\n```python\nprint('hello')\n```\nAnd more."
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert "print('hello')" in blocks[0]["content"]

    def test_extract_code_blocks_no_blocks(self):
        from agent_executor.openai_executor import _extract_code_blocks
        assert _extract_code_blocks("plain text") == []

    def test_extract_code_blocks_multiple(self):
        from agent_executor.openai_executor import _extract_code_blocks
        text = "```py\na=1\n```\n```js\nb=2\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2
