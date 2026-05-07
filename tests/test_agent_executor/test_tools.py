import json
import pytest
from agent_executor.tools import TOOL_DEFINITIONS, get_tools_for_provider, execute_tool


class TestToolDefinitions:
    def test_all_tools_defined(self):
        expected = {
            "run_python_script", "run_shell_command", "run_project_command",
            "read_file", "write_file", "get_best_models", "get_failed_models",
            "compare_with_past", "query_knowledge",
        }
        assert set(TOOL_DEFINITIONS.keys()) == expected

    def test_each_tool_has_description_and_params(self):
        for name, desc in TOOL_DEFINITIONS.items():
            assert "description" in desc
            assert "parameters" in desc
            assert "type" in desc["parameters"]
            assert desc["parameters"]["type"] == "object"
            assert "properties" in desc["parameters"]

    def test_run_python_script_required_code(self):
        params = TOOL_DEFINITIONS["run_python_script"]["parameters"]
        assert "code" in params["required"]

    def test_read_file_has_optional_params(self):
        params = TOOL_DEFINITIONS["read_file"]["parameters"]
        assert "offset" in params["properties"]
        assert "limit" in params["properties"]


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


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_run_python_script(self):
        result = await execute_tool("run_python_script", {"code": "print('hello')"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_python_script_error(self):
        result = await execute_tool("run_python_script", {"code": "raise ValueError('test')"})
        assert "ValueError" in result or "test" in result

    @pytest.mark.asyncio
    async def test_run_shell_command(self):
        result = await execute_tool("run_shell_command", {"command": "echo hello"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_shell_command_with_workdir(self, tmp_path):
        result = await execute_tool("run_shell_command", {"command": "pwd", "workdir": str(tmp_path)})
        assert str(tmp_path) in result

    @pytest.mark.asyncio
    async def test_run_project_command(self):
        result = await execute_tool("run_project_command", {"command": "echo project"})
        assert "project" in result

    @pytest.mark.asyncio
    async def test_read_file_found(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = await execute_tool("read_file", {"path": str(f)})
        assert "line1" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        result = await execute_tool("read_file", {"path": "/nonexistent/file.txt"})
        assert "Error: file not found" in result

    @pytest.mark.asyncio
    async def test_read_file_with_offset(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\n")
        result = await execute_tool("read_file", {"path": str(f), "offset": 2})
        assert "line1" not in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_read_file_with_limit(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = await execute_tool("read_file", {"path": str(f), "limit": 1})
        assert "line1" in result
        assert "line2" not in result

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        path = str(tmp_path / "out.txt")
        result = await execute_tool("write_file", {"path": path, "content": "hello world"})
        assert "Written" in result
        assert (tmp_path / "out.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_file_creates_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "nested" / "out.txt")
        result = await execute_tool("write_file", {"path": path, "content": "nested"})
        assert "Written" in result
        assert (tmp_path / "sub" / "nested" / "out.txt").read_text() == "nested"

    @pytest.mark.asyncio
    async def test_get_best_models_no_file(self, tmp_path):
        result = await execute_tool("get_best_models", {"k": 5})
        assert "No experiments found" in result

    @pytest.mark.asyncio
    async def test_get_best_models_with_data(self, temp_dir):
        data = [{"name": "a", "score": 10}, {"name": "b", "score": 20}]
        (temp_dir / "experiments.json").write_text(json.dumps(data))
        result = await execute_tool("get_best_models", {"k": 1})
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "b"

    @pytest.mark.asyncio
    async def test_get_failed_models_no_file(self):
        result = await execute_tool("get_failed_models", {"k": 5})
        assert "No experiments found" in result

    @pytest.mark.asyncio
    async def test_get_failed_models_with_data(self, temp_dir):
        data = [{"name": "a", "status": "failed"}, {"name": "b", "status": "completed"}]
        (temp_dir / "experiments.json").write_text(json.dumps(data))
        result = await execute_tool("get_failed_models", {"k": 5})
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "a"

    @pytest.mark.asyncio
    async def test_compare_with_past_no_file(self):
        result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 0.9})
        assert "No past experiments" in result

    @pytest.mark.asyncio
    async def test_compare_with_past_with_data(self, temp_dir):
        data = [{"metrics": {"accuracy": 0.8}}, {"metrics": {"accuracy": 0.85}}]
        (temp_dir / "experiments.json").write_text(json.dumps(data))
        result = await execute_tool("compare_with_past", {"metric": "accuracy", "current_value": 0.9})
        parsed = json.loads(result)
        assert parsed["current"] == 0.9
        assert parsed["best_past"] == 0.85
        assert parsed["count"] == 2

    @pytest.mark.asyncio
    async def test_query_knowledge_no_server(self):
        result = await execute_tool("query_knowledge", {"query": "test"})
        assert "RAG query" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = await execute_tool("nonexistent", {})
        assert "Unknown tool" in result
