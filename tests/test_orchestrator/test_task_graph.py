import os
import tempfile


from orchestrator.core.task_graph import TaskNode, TaskGraph


class TestTaskNode:
    def test_init(self):
        node = TaskNode(1, "python-engineer", "backend", "gpt-4o", "build a module")
        assert node.step == 1
        assert node.agent == "python-engineer"
        assert node.category == "backend"
        assert node.model == "gpt-4o"
        assert node.task == "build a module"
        assert node.status == "pending"
        assert node.output_summary == ""
        assert node.artifacts == []
        assert node.tokens == 0
        assert node.duration_seconds == 0
        assert node.started_at is None
        assert node.completed_at is None
        assert node.error is None

    def test_to_dict(self):
        node = TaskNode(1, "test-agent", "test-cat", "gpt-4o", "do something")
        node.status = "completed"
        node.tokens = 100
        d = node.to_dict()
        assert d["step"] == 1
        assert d["agent"] == "test-agent"
        assert d["status"] == "completed"
        assert d["tokens"] == 100

    def test_to_dict_contains_all_keys(self):
        node = TaskNode(1, "a", "b", "c", "d")
        d = node.to_dict()
        expected_keys = {
            "step", "agent", "category", "model", "status", "task",
            "output_summary", "artifacts", "tokens", "duration_seconds",
            "started_at", "completed_at", "error",
        }
        assert set(d.keys()) == expected_keys


class TestTaskGraph:
    def test_init(self):
        graph = TaskGraph("/project", "my task", "interactive", "sequential")
        assert graph.project_root == "/project"
        assert graph.task == "my task"
        assert graph.mode == "interactive"
        assert graph.execution == "sequential"
        assert graph.status == "running"
        assert graph.nodes == []
        assert graph.edges == []

    def test_add_node(self):
        graph = TaskGraph("/project", "task")
        node = graph.add_node("agent1", "cat1", "model1", "task1")
        assert node.step == 1
        assert node.agent == "agent1"
        assert len(graph.nodes) == 1

        node2 = graph.add_node("agent2", "cat2", "model2", "task2")
        assert node2.step == 2
        assert len(graph.nodes) == 2

    def test_add_edge(self):
        graph = TaskGraph("/project", "task")
        graph.add_edge(1, 2, "sequential")
        assert len(graph.edges) == 1
        assert graph.edges[0] == {"from_step": 1, "to_step": 2, "type": "sequential"}

    def test_file_path(self):
        graph = TaskGraph("/my/project", "task")
        assert graph.file_path == "/my/project/.task_graph.json"

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = TaskGraph(tmpdir, "test task", "autonomous", "parallel")
            n1 = graph.add_node("agent1", "cat1", "gpt-4o", "task one")
            n1.status = "completed"
            n1.tokens = 50
            n1.duration_seconds = 10.0
            n2 = graph.add_node("agent2", "cat2", "gpt-4o-mini", "task two")
            n2.status = "failed"
            n2.error = "something went wrong"
            graph.add_edge(1, 2)
            graph.status = "partial"
            graph.save()

            loaded = TaskGraph.load(os.path.join(tmpdir, ".task_graph.json"))
            assert loaded is not None
            assert loaded.task == "test task"
            assert loaded.mode == "autonomous"
            assert loaded.execution == "parallel"
            assert loaded.status == "partial"
            assert len(loaded.nodes) == 2
            assert loaded.nodes[0].agent == "agent1"
            assert loaded.nodes[0].status == "completed"
            assert loaded.nodes[0].tokens == 50
            assert loaded.nodes[1].agent == "agent2"
            assert loaded.nodes[1].status == "failed"
            assert loaded.nodes[1].error == "something went wrong"
            assert len(loaded.edges) == 1

    def test_load_nonexistent(self):
        result = TaskGraph.load("/nonexistent/path.json")
        assert result is None

    def test_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = TaskGraph(tmpdir, "test task", "autonomous", "sequential")
            n1 = graph.add_node("agent1", "cat1", "gpt-4o", "task one")
            n1.status = "completed"
            n1.tokens = 100
            n1.duration_seconds = 5.0
            n2 = graph.add_node("agent2", "cat2", "gpt-4o-mini", "task two")
            n2.status = "running"

            summary = graph.summary()
            assert "test task" in summary
            assert "agent1" in summary
            assert "agent2" in summary
            assert "1/2" in summary or "completed" in summary

    def test_summary_empty_graph(self):
        graph = TaskGraph("/proj", "empty")
        summary = graph.summary()
        assert "empty" in summary
        assert "0/0" in summary or "0 steps" in summary

    def test_summary_with_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = TaskGraph(tmpdir, "task")
            n = graph.add_node("agent", "cat", "model", "do it")
            n.status = "completed"
            n.artifacts = ["/path/to/file.py", "/path/to/file2.js"]
            summary = graph.summary()
            assert "file.py" in summary
            assert "file2.js" in summary
