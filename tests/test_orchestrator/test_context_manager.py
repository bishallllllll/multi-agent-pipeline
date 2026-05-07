
from orchestrator.core.context_manager import ContextManager


class TestContextManager:
    def test_init_empty(self):
        cm = ContextManager()
        assert cm.history == []

    def test_add_step(self):
        cm = ContextManager()
        cm.add_step(
            agent="python-engineer",
            category="backend",
            task="build module",
            output="created module with functions",
            artifacts=["/path/to/module.py"],
        )
        assert len(cm.history) == 1
        assert cm.history[0]["agent"] == "python-engineer"
        assert cm.history[0]["output_summary"] == "created module with functions"

    def test_add_step_truncates_long_output(self):
        cm = ContextManager()
        long_output = "x" * 1000
        cm.add_step("agent", "cat", "task", long_output, [])
        assert len(cm.history[0]["output_summary"]) == 500

    def test_build_context_empty(self):
        cm = ContextManager()
        context = cm.build_context()
        assert context == ""

    def test_build_context_single_step(self):
        cm = ContextManager()
        cm.add_step("python-engineer", "backend", "build module", "created module", ["mod.py"])
        context = cm.build_context()
        assert "Python Engineer" in context or "python-engineer" in context
        assert "Previous Work Context" in context
        assert "build module" in context

    def test_build_context_multiple_steps(self):
        cm = ContextManager()
        cm.add_step("agent1", "cat1", "task1", "output1", ["file1.py"])
        cm.add_step("agent2", "cat2", "task2", "output2", ["file2.py"])
        context = cm.build_context()
        assert "agent1" in context
        assert "agent2" in context
        assert "file1.py" in context
        assert "file2.py" in context

    def test_build_context_max_summary_length(self):
        cm = ContextManager()
        cm.add_step("agent1", "cat1", "task1", "output1", [])
        cm.add_step("agent2", "cat2", "task2", "output2", [])
        context = cm.build_context(max_summary_length=50)
        # Should have at least some truncated content
        assert "truncated" in context or len(context) < 500

    def test_build_prompt_no_context(self):
        cm = ContextManager()
        prompt = cm.build_prompt("system prompt", "do the task")
        assert "system prompt" in prompt
        assert "do the task" in prompt
        assert "Previous Work Context" not in prompt

    def test_build_prompt_with_context(self):
        cm = ContextManager()
        cm.add_step("agent1", "cat1", "prev task", "prev output", [])
        prompt = cm.build_prompt("system prompt", "current task")
        assert "system prompt" in prompt
        assert "current task" in prompt
        assert "Prev" in prompt or "prev" in prompt.lower()

    def test_build_prompt_adds_execution_instruction(self):
        cm = ContextManager()
        prompt = cm.build_prompt("sys", "task")
        assert "Execute this task concisely" in prompt
