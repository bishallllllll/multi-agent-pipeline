"""Tool implementations that agents can call."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


TOOL_DEFINITIONS = {
    "run_python_script": {
        "description": "Execute a Python script and return stdout/stderr",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"],
        },
    },
    "run_shell_command": {
        "description": "Run a shell command and return output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["command"],
        },
    },
    "run_project_command": {
        "description": "Run a project-level command (npm/pip/etc) and return output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
            },
            "required": ["command"],
        },
    },
    "read_file": {
        "description": "Read a file from disk",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "offset": {"type": "integer", "description": "Line offset (optional)"},
                "limit": {"type": "integer", "description": "Max lines to read (optional)"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "description": "Write content to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write to"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    "get_best_models": {
        "description": "Get the best performing models from experiment history",
        "parameters": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "description": "Number of models to return"},
            },
            "required": [],
        },
    },
    "get_failed_models": {
        "description": "Get failed models from experiment history",
        "parameters": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "description": "Number of models to return"},
            },
            "required": [],
        },
    },
    "compare_with_past": {
        "description": "Compare current results with past experiment results",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "description": "Metric name to compare"},
                "current_value": {"type": "number", "description": "Current metric value"},
            },
            "required": ["metric", "current_value"],
        },
    },
    "query_knowledge": {
        "description": "Query the RAG knowledge base for relevant information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "domain": {"type": "string", "description": "Domain to search (optional)"},
            },
            "required": ["query"],
        },
    },
}


def get_tools_for_provider(provider: str) -> list[dict]:
    """Return tool definitions formatted for the given provider."""
    if provider == "openai":
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc["description"],
                    "parameters": desc["parameters"],
                },
            }
            for name, desc in TOOL_DEFINITIONS.items()
        ]
    elif provider == "anthropic":
        return [
            {
                "name": name,
                "description": desc["description"],
                "input_schema": desc["parameters"],
            }
            for name, desc in TOOL_DEFINITIONS.items()
        ]
    return []


async def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return its result as a string."""
    try:
        if name == "run_python_script":
            code = args["code"]
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                tmp_path = f.name
            try:
                result = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True, text=True, timeout=30,
                )
                output = result.stdout + result.stderr
                return output[:10000] if output else "(no output)"
            finally:
                os.unlink(tmp_path)

        elif name == "run_shell_command":
            cmd = args["command"]
            cwd = args.get("workdir")
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=cwd,
            )
            output = result.stdout + result.stderr
            return output[:10000] if output else "(no output)"

        elif name == "run_project_command":
            cmd = args["command"]
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            return output[:10000] if output else "(no output)"

        elif name == "read_file":
            path = args["path"]
            offset = args.get("offset", 0)
            limit = args.get("limit", 0)
            if not os.path.exists(path):
                return f"Error: file not found: {path}"
            with open(path) as f:
                lines = f.readlines()
            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]
            return "".join(lines)[:10000]

        elif name == "write_file":
            path = args["path"]
            content = args["content"]
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"

        elif name == "get_best_models":
            k = args.get("k", 5)
            experiments_file = Path("experiments.json")
            if not experiments_file.exists():
                return "No experiments found"
            with open(experiments_file) as f:
                experiments = json.load(f)
            sorted_exp = sorted(experiments, key=lambda x: x.get("score", 0), reverse=True)
            top = sorted_exp[:k]
            return json.dumps(top, indent=2)

        elif name == "get_failed_models":
            k = args.get("k", 5)
            experiments_file = Path("experiments.json")
            if not experiments_file.exists():
                return "No experiments found"
            with open(experiments_file) as f:
                experiments = json.load(f)
            failed = [e for e in experiments if e.get("status") == "failed"]
            return json.dumps(failed[:k], indent=2)

        elif name == "compare_with_past":
            metric = args["metric"]
            current_value = args["current_value"]
            experiments_file = Path("experiments.json")
            if not experiments_file.exists():
                return f"No past experiments to compare. Current {metric}: {current_value}"
            with open(experiments_file) as f:
                experiments = json.load(f)
            past_values = [e.get("metrics", {}).get(metric) for e in experiments if e.get("metrics")]
            past_values = [v for v in past_values if v is not None]
            if past_values:
                best = max(past_values)
                avg = sum(past_values) / len(past_values)
                return json.dumps({"current": current_value, "best_past": best, "average_past": avg, "count": len(past_values)})
            return f"No past {metric} data found"

        elif name == "query_knowledge":
            query = args["query"]
            import httpx
            try:
                resp = httpx.post(
                    "http://localhost:8000/query",
                    json={"query": query, "k": 3},
                    timeout=10,
                )
                if resp.status_code == 200:
                    results = resp.json()
                    snippets = []
                    for r in results:
                        if isinstance(r, list) and len(r) >= 1:
                            snippets.append(r[0].get("page_content", ""))
                    return "\n\n".join(snippets[:3])[:10000] or "No results found"
                return f"RAG query returned status {resp.status_code}"
            except Exception as e:
                return f"RAG query failed: {e}"

        else:
            return f"Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return f"Tool '{name}' timed out"
    except Exception as e:
        return f"Tool '{name}' error: {e}"
