import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_mock_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_mock_tool_use(name, tool_input, tool_id="tu_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    block.id = tool_id
    return block


class TestAnthropicExecutor:
    @pytest.mark.asyncio
    async def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from agent_executor.anthropic_executor import execute
        result = await execute("sys", "task")
        assert result["success"] is False
        assert "ANTHROPIC_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_env_anthropic):
        mock_response = MagicMock()
        mock_response.content = [make_mock_text_block("Hello from Claude")]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        with patch("agent_executor.anthropic_executor.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = AsyncMock(return_value=mock_response)
            from agent_executor.anthropic_executor import execute
            result = await execute("Be helpful", "Say hi", model="claude-3-5-sonnet-20241022")
            assert result["success"] is True
            assert "Hello from Claude" in result["text"]
            assert result["tokens"] == 30

    @pytest.mark.asyncio
    async def test_execution_error(self, mock_env_anthropic):
        with patch("agent_executor.anthropic_executor.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = AsyncMock(
                side_effect=Exception("API error")
            )
            from agent_executor.anthropic_executor import execute
            result = await execute("sys", "task")
            assert result["success"] is False
            assert "API error" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_use_flow(self, mock_env_anthropic):
        text_block = make_mock_text_block("Running tool")
        tool_block = make_mock_tool_use("run_shell_command", {"command": "echo hi"})

        response = MagicMock()
        response.content = [text_block, tool_block]
        response.usage.input_tokens = 5
        response.usage.output_tokens = 10

        with patch("agent_executor.anthropic_executor.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = AsyncMock(return_value=response)
            from agent_executor.anthropic_executor import execute
            result = await execute("sys", "run", model="claude-3-5-sonnet-20241022")
            assert result["success"] is True
            assert "Running tool" in result["text"]

    def test_extract_code_blocks(self):
        from agent_executor.anthropic_executor import _extract_code_blocks
        text = "```python\nprint('hello')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"

    def test_extract_code_blocks_empty(self):
        from agent_executor.anthropic_executor import _extract_code_blocks
        assert _extract_code_blocks("no code") == []
