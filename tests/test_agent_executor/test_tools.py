import json
import os
import tempfile
from pathlib import Path
import pytest
from agent_executor.tools import TOOL_DEFINITIONS, get_tools_for_provider, execute_tool


class TestToolDefinitions:
    def test_all_tools_defined(self):
        assert "run_python_script" in TOOL_DEFINITIONS
        assert "run_shell_command" in TOOL_DEFINITIONS
        assert "read_file" in TOOL_DEFINITIONS
        assert "write_file" in TOOL_DEFINITIONS
        assert "get_best_models" in TOOL_DEFINITIONS
        assert "get_failed_models" in TOOL_DEFINITIONS
        assert "compare_with_past" in TOOL_DEFINITIONS
        assert "query_knowledge" in TOOL_DEFINITIONS

    def test_tool_parameters_have_required(self):
        for name, desc in TOOL_DEFINITIONS.items():
            assert "parameters" in desc
            assert "properties" in desc["parameters"]
            assert "required" in desc["parameters"]


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


@pytest.mark.asyncio
class TestExecuteTool:
    async def test_run_python_script_success(self):
        result = await execute_tool("run_python_script", {"code": "print('hello')"})
        assert "hello" in result

    async def test_run_python_script_error(self):
        result = await execute_tool("run_python_script", {"code": "raise ValueError('test')"})
        assert "ValueError" in result or "test" in result or "Traceback" in result

    async def test_run_shell_command(self):
        result = await execute_tool("run_shell_command", {"command": "echo hello"})
        assert "hello" in result

    async def test_run_shell_command_with_workdir(self):
        result = await execute_tool("run_shell_command", {"command": "pwd", "workdir": "/tmp"})
        assert "/tmp" in result

    async def test_run_project_command(self):
        result = await execute_tool("run_project_command", {"command": "echo hello_project"})
        assert "hello_project" in result

    async def test_read_file_found(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            tmp_path = f.name
        try:
            result = await execute_tool("read_file", {"path": tmp_path})
            assert "line1" in result
            assert "line2" in result
            assert "line3" in result
        finally:
            os.unlink(tmp_path)

    async def test_read_file_with_offset_limit(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\nline3\nline4\nline5\n")
            tmp_path = f.name
        try:
            result = await execute_tool("read_file", {"path": tmp_path, "offset": 1, "limit": 2})
            lines = result.strip().split("\n")
            assert len(lines) <= 2
        finally:
            os.unlink(tmp_path)

    async def test_read_file_not_found(self):
        result = await execute_tool("read_file", {"path": "/nonexistent/file.txt"})
        assert "Error" in result
        assert "not found" in result

    async def test_write_file(self):
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, "test_write.txt")
        try:
            result = await execute_tool("write_file", {"path": file_path, "content": "hello world"})
            assert "Written" in result
            assert os.path.exists(file_path)
            with open(file_path) as f:
                assert f.read() == "hello world"
        finally:
            os.unlink(file_path)
            os.rmdir(tmp_dir)

    async def test_get_best_models_no_file(self):
        result = await execute_tool("get_best_models", {"k": 3})
        assert result == "No experiments found"

    async def test_get_best_models_with_file(self, tmp_path):
        experiments = [
            {"name": "model_a", "score": 0.9},
            {"name": "model_b", "score": 0.8},
        ]
        exp_file = tmp_path / "experiments.json"
        exp_file.write_text(json.dumps(experiments))
        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            result = await execute_tool("get_best_models", {"k": 5})
            data = json.loads(result)
            assert len(data) == 2
            assert data[0]["name"] == "model_a"
        finally:
            os.chdir(original_cwd)

    async def test_get_failed_models_no_file(self):
        result = await execute_tool("get_failed_models", {"k": 3})
        assert result == "No experiments found"

    async def test_get_failed_models_with_file(self, tmp_path):
        experiments = [
            {"name": "model_a", "status": "failed"},
            {"name": "model_b", "status": "completed"},
        ]
        exp_file = tmp_path / "experiments.json"
        exp_file.write_text(json.dumps(experiments))
        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            result = await execute_tool("get_failed_models", {"k": 5})
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["name"] == "model_a"
        finally:
            os.chdir(original_cwd)

    async def test_compare_with_past_no_file(self):
        result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 0.95})
        assert "No past experiments" in result

    async def test_compare_with_past_with_data(self, tmp_path):
        experiments = [
            {"metrics": {"accuracy": 0.8}},
            {"metrics": {"accuracy": 0.9}},
        ]
        exp_file = tmp_path / "experiments.json"
        exp_file.write_text(json.dumps(experiments))
        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 0.95})
            data = json.loads(result)
            assert data["current"] == 0.95
            assert data["best_past"] == 0.9
            assert data["average_past"] == pytest.approx(0.85)
        finally:
            os.chdir(original_cwd)

    async def test_query_knowledge_rag_down(self):
        result = await execute_tool("query_knowledge", {"query": "test query"})
        assert "RAG query failed" in result or "failed" in result

    async def test_unknown_tool(self):
        result = await execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result
