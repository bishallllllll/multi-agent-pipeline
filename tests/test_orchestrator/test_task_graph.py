from orchestrator.core.task_graph import TaskNode, TaskGraph


class TestTaskNode:
    def test_initial_state(self):
        node = TaskNode(1, "test-agent", "testing", "gpt-4o", "do something")
        assert node.step == 1
        assert node.agent == "test-agent"
        assert node.status == "pending"
        assert node.tokens == 0
        assert node.duration_seconds == 0
        assert node.error is None

    def test_to_dict(self):
        node = TaskNode(1, "agent", "cat", "gpt-4o", "task")
        node.status = "completed"
        d = node.to_dict()
        assert d["step"] == 1
        assert d["agent"] == "agent"
        assert d["status"] == "completed"
        assert d["tokens"] == 0


class TestTaskGraph:
    def test_initialization(self):
        graph = TaskGraph("/tmp/project", "test task", mode="autonomous", execution="parallel")
        assert graph.task == "test task"
        assert graph.mode == "autonomous"
        assert graph.execution == "parallel"
        assert graph.status == "running"
        assert graph.nodes == []
        assert graph.edges == []

    def test_add_node(self):
        graph = TaskGraph("/tmp/project", "task")
        node = graph.add_node("agent1", "dev", "gpt-4o", "do stuff")
        assert node.step == 1
        assert len(graph.nodes) == 1
        assert graph.nodes[0] is node

    def test_add_multiple_nodes(self):
        graph = TaskGraph("/tmp/project", "task")
        graph.add_node("a", "cat", "m", "t1")
        graph.add_node("b", "cat", "m", "t2")
        assert len(graph.nodes) == 2
        assert graph.nodes[0].step == 1
        assert graph.nodes[1].step == 2

    def test_add_edge(self):
        graph = TaskGraph("/tmp/project", "task")
        graph.add_edge(1, 2, "sequential")
        assert graph.edges == [{"from_step": 1, "to_step": 2, "type": "sequential"}]

    def test_file_path(self):
        graph = TaskGraph("/my/project", "task")
        assert graph.file_path == "/my/project/.task_graph.json"

    def test_save_and_load(self, temp_dir):
        graph = TaskGraph(str(temp_dir), "my task", execution="sequential")
        graph.add_node("agent1", "dev", "gpt-4o", "step 1 task")
        n2 = graph.add_node("agent2", "test", "gpt-4o-mini", "step 2 task")
        n2.status = "completed"
        n2.tokens = 100
        n2.duration_seconds = 5.5
        n2.output_summary = "did stuff"
        n2.artifacts = ["/tmp/out.py"]
        graph.add_edge(1, 2)
        graph.save()

        loaded = TaskGraph.load(str(temp_dir / ".task_graph.json"))
        assert loaded is not None
        assert loaded.task == "my task"
        assert loaded.execution == "sequential"
        assert len(loaded.nodes) == 2
        assert loaded.nodes[0].agent == "agent1"
        assert loaded.nodes[1].status == "completed"
        assert loaded.nodes[1].tokens == 100
        assert loaded.edges == [{"from_step": 1, "to_step": 2, "type": "sequential"}]

    def test_load_nonexistent(self):
        graph = TaskGraph.load("/nonexistent/file.json")
        assert graph is None

    def test_summary(self, temp_dir):
        graph = TaskGraph(str(temp_dir), "test task")
        n1 = graph.add_node("agent1", "dev", "m", "step 1")
        n1.status = "completed"
        n1.tokens = 50
        n1.duration_seconds = 2.0
        graph.save()
        summary = graph.summary()
        assert "test task" in summary
        assert "1/1 steps completed" in summary
        assert "50" in summary

    def test_status_running_on_init(self):
        graph = TaskGraph("/tmp/p", "test")
        assert graph.status == "running"

    def test_save_creates_file(self, temp_dir):
        graph = TaskGraph(str(temp_dir), "task")
        graph.add_node("a", "cat", "m", "t")
        graph.save()
        assert (temp_dir / ".task_graph.json").exists()
