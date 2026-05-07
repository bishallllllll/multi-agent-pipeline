import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from agent_executor.tools import TOOL_DEFINITIONS, get_tools_for_provider, execute_tool


class TestGetToolsForProvider:
    def test_openai_format(self):
        tools = get_tools_for_provider("openai")
        assert len(tools) == len(TOOL_DEFINITIONS)
        for t in tools:
            assert t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]

    def test_anthropic_format(self):
        tools = get_tools_for_provider("anthropic")
        assert len(tools) == len(TOOL_DEFINITIONS)
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "input_schema" in t

    def test_unknown_provider(self):
        tools = get_tools_for_provider("unknown")
        assert tools == []

    def test_openai_tool_names(self):
        tools = get_tools_for_provider("openai")
        names = {t["function"]["name"] for t in tools}
        assert "run_python_script" in names
        assert "run_shell_command" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "query_knowledge" in names


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_run_python_script(self):
        result = await execute_tool("run_python_script", {"code": "print('hello')"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_python_script_empty_output(self):
        result = await execute_tool("run_python_script", {"code": ""})
        assert result == "(no output)" or result == ""

    @pytest.mark.asyncio
    async def test_run_shell_command(self):
        result = await execute_tool("run_shell_command", {"command": "echo hello"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_shell_command_with_workdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_tool(
                "run_shell_command",
                {"command": "pwd", "workdir": tmpdir},
            )
            assert tmpdir in result

    @pytest.mark.asyncio
    async def test_read_file_exists(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            tmp_path = f.name
        try:
            result = await execute_tool("read_file", {"path": tmp_path})
            assert "line1" in result
            assert "line2" in result
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        result = await execute_tool("read_file", {"path": "/nonexistent/file.txt"})
        assert "Error: file not found" in result

    @pytest.mark.asyncio
    async def test_read_file_with_offset_and_limit(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("line1\nline2\nline3\nline4\nline5\n")
            tmp_path = f.name
        try:
            result = await execute_tool("read_file", {"path": tmp_path, "offset": 1, "limit": 2})
            assert "line2" in result
            assert "line3" in result
            assert "line1" not in result
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = await execute_tool("write_file", {"path": path, "content": "hello world"})
            assert "Written" in result
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == "hello world"

    @pytest.mark.asyncio
    async def test_write_file_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "nested", "test.txt")
            result = await execute_tool("write_file", {"path": path, "content": "nested"})
            assert "Written" in result
            assert os.path.exists(path)

    @pytest.mark.asyncio
    async def test_get_best_models_no_file(self):
        result = await execute_tool("get_best_models", {"k": 3})
        assert result == "No experiments found"

    @pytest.mark.asyncio
    async def test_get_best_models_with_file(self):
        experiments = [
            {"name": "model_a", "score": 85},
            {"name": "model_b", "score": 95},
            {"name": "model_c", "score": 75},
        ]
        experiments_file = Path("experiments.json")
        try:
            experiments_file.write_text(json.dumps(experiments))
            result = await execute_tool("get_best_models", {"k": 2})
            data = json.loads(result)
            assert len(data) == 2
            assert data[0]["name"] == "model_b"
        finally:
            experiments_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_failed_models_no_file(self):
        result = await execute_tool("get_failed_models", {"k": 3})
        assert result == "No experiments found"

    @pytest.mark.asyncio
    async def test_get_failed_models(self):
        experiments = [
            {"name": "model_a", "status": "completed", "score": 85},
            {"name": "model_b", "status": "failed", "score": 0},
            {"name": "model_c", "status": "failed", "score": 0},
        ]
        experiments_file = Path("experiments.json")
        try:
            experiments_file.write_text(json.dumps(experiments))
            result = await execute_tool("get_failed_models", {"k": 5})
            data = json.loads(result)
            assert len(data) == 2
        finally:
            experiments_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_compare_with_past_no_file(self):
        result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 90})
        assert "No past experiments" in result

    @pytest.mark.asyncio
    async def test_compare_with_past(self):
        experiments = [
            {"metrics": {"accuracy": 85}},
            {"metrics": {"accuracy": 92}},
            {"metrics": {"accuracy": 78}},
        ]
        experiments_file = Path("experiments.json")
        try:
            experiments_file.write_text(json.dumps(experiments))
            result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 90})
            data = json.loads(result)
            assert data["current"] == 90
            assert data["best_past"] == 92
            assert data["average_past"] == 85.0
        finally:
            experiments_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_compare_with_past_no_metric_data(self):
        experiments = [{"metrics": {"other": 100}}]
        experiments_file = Path("experiments.json")
        try:
            experiments_file.write_text(json.dumps(experiments))
            result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 90})
            assert "No past accuracy data" in result
        finally:
            experiments_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_query_knowledge_success(self):
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                [{"page_content": "relevant info"}, 0.1],
            ]
            mock_post.return_value = mock_response

            result = await execute_tool("query_knowledge", {"query": "test query"})
            assert "relevant info" in result

    @pytest.mark.asyncio
    async def test_query_knowledge_failure(self):
        with patch("httpx.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response

            result = await execute_tool("query_knowledge", {"query": "test"})
            assert "returned status 500" in result

    @pytest.mark.asyncio
    async def test_query_knowledge_exception(self):
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = Exception("connection refused")
            result = await execute_tool("query_knowledge", {"query": "test"})
            assert "RAG query failed" in result

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = await execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_tool_timeout(self):
        with patch("agent_executor.tools.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired("cmd", 30)
            result = await execute_tool("run_shell_command", {"command": "sleep 100"})
            assert "timed out" in result

    @pytest.mark.asyncio
    async def test_tool_general_exception(self):
        with patch("agent_executor.tools.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("something broke")
            result = await execute_tool("run_shell_command", {"command": "echo hi"})
            assert "error" in result

    @pytest.mark.asyncio
    async def test_run_project_command(self):
        result = await execute_tool("run_project_command", {"command": "echo project"})
        assert "project" in result
