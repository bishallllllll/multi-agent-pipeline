from orchestrator.core.context_manager import ContextManager


class TestContextManager:
    def setup_method(self):
        self.ctx = ContextManager()

    def test_initial_empty_history(self):
        assert self.ctx.history == []

    def test_add_step(self):
        self.ctx.add_step("agent1", "cat1", "task1", "output1", ["art1.py"])
        assert len(self.ctx.history) == 1
        step = self.ctx.history[0]
        assert step["agent"] == "agent1"
        assert step["category"] == "cat1"
        assert step["artifacts"] == ["art1.py"]

    def test_build_context_empty(self):
        context = self.ctx.build_context()
        assert context == ""

    def test_build_context_with_steps(self):
        self.ctx.add_step("agent1", "cat1", "task1", "output text", ["art1.py"])
        context = self.ctx.build_context()
        assert "Previous Work Context" in context
        assert "agent1" in context
        assert "task1" in context
        assert "art1.py" in context

    def test_build_context_truncates_output(self):
        long_output = "X" * 600
        self.ctx.add_step("agent1", "cat1", "task1", long_output, [])
        step = self.ctx.history[0]
        assert len(step["output_summary"]) <= 500

    def test_build_context_respects_max_length(self):
        self.ctx.add_step("agent1", "cat1", "task1", "output", ["a.py"])
        self.ctx.add_step("agent2", "cat2", "task2", "output", ["b.py"])
        self.ctx.add_step("agent3", "cat3", "task3", "output", ["c.py"])
        context = self.ctx.build_context(max_summary_length=100)
        assert "(previous steps truncated)" in context

    def test_build_prompt_no_context(self):
        prompt = self.ctx.build_prompt("system prompt", "do the task")
        assert "system prompt" in prompt
        assert "do the task" in prompt
        assert "Previous Work Context" not in prompt

    def test_build_prompt_with_context(self):
        self.ctx.add_step("agent1", "cat1", "task1", "output", [])
        prompt = self.ctx.build_prompt("system prompt", "do the task")
        assert "system prompt" in prompt
        assert "do the task" in prompt
        assert "Previous Work Context" in prompt
