import json
import os
from orchestrator.core.task_graph import TaskNode, TaskGraph


class TestTaskNode:
    def test_initial_state(self):
        node = TaskNode(1, "python-engineer", "core-development", "gpt-4o", "write a module")
        assert node.step == 1
        assert node.agent == "python-engineer"
        assert node.category == "core-development"
        assert node.model == "gpt-4o"
        assert node.task == "write a module"
        assert node.status == "pending"
        assert node.output_summary == ""
        assert node.artifacts == []
        assert node.tokens == 0
        assert node.duration_seconds == 0
        assert node.started_at is None
        assert node.completed_at is None
        assert node.error is None

    def test_to_dict(self):
        node = TaskNode(1, "test-agent", "dev", "gpt-4o", "do stuff")
        node.status = "completed"
        node.tokens = 50
        node.duration_seconds = 10.5
        d = node.to_dict()
        assert d["step"] == 1
        assert d["agent"] == "test-agent"
        assert d["status"] == "completed"
        assert d["tokens"] == 50
        assert d["duration_seconds"] == 10.5


class TestTaskGraph:
    def test_initialization(self):
        graph = TaskGraph("/tmp/project", "my task", "autonomous", "parallel")
        assert graph.project_root == "/tmp/project"
        assert graph.task == "my task"
        assert graph.mode == "autonomous"
        assert graph.execution == "parallel"
        assert graph.status == "running"
        assert graph.nodes == []
        assert graph.edges == []

    def test_add_node(self):
        graph = TaskGraph("/tmp", "test", "autonomous", "sequential")
        node = graph.add_node("agent1", "cat1", "gpt-4o", "task1")
        assert node.step == 1
        assert len(graph.nodes) == 1

        node2 = graph.add_node("agent2", "cat2", "gpt-4o-mini", "task2")
        assert node2.step == 2
        assert len(graph.nodes) == 2

    def test_add_edge(self):
        graph = TaskGraph("/tmp", "test")
        graph.add_edge(1, 2, "sequential")
        assert len(graph.edges) == 1
        assert graph.edges[0]["from_step"] == 1
        assert graph.edges[0]["to_step"] == 2

    def test_file_path(self):
        graph = TaskGraph("/my/project", "test")
        assert graph.file_path == "/my/project/.task_graph.json"

    def test_save_and_load(self, tmp_path):
        graph = TaskGraph(str(tmp_path), "test task", "autonomous", "parallel")
        graph.add_node("agent1", "cat1", "gpt-4o", "task1").status = "completed"
        graph.add_node("agent2", "cat2", "gpt-4o-mini", "task2").status = "pending"
        graph.save()

        assert os.path.exists(graph.file_path)
        with open(graph.file_path) as f:
            data = json.load(f)
        assert data["task"] == "test task"
        assert data["total_steps"] == 2
        assert data["nodes"][0]["status"] == "completed"

        loaded = TaskGraph.load(graph.file_path)
        assert loaded is not None
        assert loaded.task == "test task"
        assert len(loaded.nodes) == 2
        assert loaded.nodes[0].agent == "agent1"
        assert loaded.nodes[1].status == "pending"

    def test_load_nonexistent(self):
        loaded = TaskGraph.load("/nonexistent/file.json")
        assert loaded is None

    def test_summary(self, tmp_path):
        graph = TaskGraph(str(tmp_path), "test task")
        node = graph.add_node("python-engineer", "core", "gpt-4o", "write code")
        node.status = "completed"
        node.tokens = 100
        node.duration_seconds = 5.0
        summary = graph.summary()
        assert "test task" in summary
        assert "python-engineer" in summary
        assert "completed" in summary
