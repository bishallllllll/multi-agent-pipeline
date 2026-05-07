from orchestrator.core.context_manager import ContextManager


class TestContextManager:
    def test_empty_context(self):
        cm = ContextManager()
        assert cm.build_context() == ""

    def test_add_step(self):
        cm = ContextManager()
        cm.add_step("agent1", "dev", "task1", "output1", ["file1.py"])
        assert len(cm.history) == 1
        assert cm.history[0]["agent"] == "agent1"

    def test_build_context_with_history(self):
        cm = ContextManager()
        cm.add_step("agent1", "dev", "Fix bug", "Added type check", ["fix.py"])
        context = cm.build_context()
        assert "Previous Work Context" in context
        assert "agent1" in context
        assert "Fix bug" in context
        assert "fix.py" in context

    def test_build_context_truncates_long_summary(self):
        cm = ContextManager()
        long_output = "x" * 1000
        cm.add_step("agent1", "dev", "task", long_output, [])
        assert len(cm.history[0]["output_summary"]) == 500

    def test_build_context_respects_max_length(self):
        cm = ContextManager()
        cm.add_step("a1", "cat", "t1", "out1", [])
        cm.add_step("a2", "cat", "t2", "out2", [])
        context = cm.build_context(max_summary_length=50)
        assert "(previous steps truncated)" in context

    def test_build_prompt_without_context(self):
        cm = ContextManager()
        prompt = cm.build_prompt("You are helpful", "Do the thing")
        assert "You are helpful" in prompt
        assert "Do the thing" in prompt
        assert "Previous Work Context" not in prompt

    def test_build_prompt_with_context(self):
        cm = ContextManager()
        cm.add_step("agent1", "dev", "Setup project", "Done", ["init.py"])
        prompt = cm.build_prompt("You are helpful", "Add tests")
        assert "Previous Work Context" in prompt
        assert "You are helpful" in prompt
        assert "Add tests" in prompt

    def test_build_prompt_execution_instruction(self):
        cm = ContextManager()
        prompt = cm.build_prompt("sys", "my task")
        assert "Execute this task concisely" in prompt
        assert "Do not include preamble" in prompt
