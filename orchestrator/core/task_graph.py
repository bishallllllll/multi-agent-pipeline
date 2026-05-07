"""Task graph state management per project."""
import json
import os
from datetime import datetime, timezone
from typing import Optional


class TaskNode:
    """Represents a single agent execution in the task graph."""

    def __init__(self, step: int, agent: str, category: str, model: str, task: str):
        self.step = step
        self.agent = agent
        self.category = category
        self.model = model
        self.task = task
        self.status = "pending"
        self.output_summary = ""
        self.artifacts: list[str] = []
        self.tokens = 0
        self.duration_seconds = 0
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.error = None

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "agent": self.agent,
            "category": self.category,
            "model": self.model,
            "status": self.status,
            "task": self.task,
            "output_summary": self.output_summary,
            "artifacts": self.artifacts,
            "tokens": self.tokens,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class TaskGraph:
    """Persistent task graph stored per project."""

    def __init__(self, project_root: str, task: str, mode: str = "autonomous", execution: str = "parallel"):
        self.project_root = project_root
        self.task = task
        self.mode = mode
        self.execution = execution
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None
        self.status = "running"
        self.nodes: list[TaskNode] = []
        self.edges: list[dict] = []

    def add_node(self, agent: str, category: str, model: str, task: str) -> TaskNode:
        step = len(self.nodes) + 1
        node = TaskNode(step, agent, category, model, task)
        self.nodes.append(node)
        return node

    def add_edge(self, from_step: int, to_step: int, edge_type: str = "sequential"):
        self.edges.append({"from_step": from_step, "to_step": to_step, "type": edge_type})

    @property
    def file_path(self) -> str:
        return os.path.join(self.project_root, ".task_graph.json")

    def save(self):
        """Persist task graph to disk."""
        data = {
            "project": self.project_root,
            "task": self.task,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "mode": self.mode,
            "execution": self.execution,
            "total_steps": len(self.nodes),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
        }
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, file_path: str) -> Optional["TaskGraph"]:
        """Load task graph from disk."""
        if not os.path.exists(file_path):
            return None
        with open(file_path) as f:
            data = json.load(f)
        graph = cls(data["project"], data["task"], data.get("mode", "autonomous"), data.get("execution", "parallel"))
        graph.started_at = data["started_at"]
        graph.completed_at = data.get("completed_at")
        graph.status = data["status"]
        graph.nodes = [
            TaskNode(n["step"], n["agent"], n["category"], n["model"], n["task"])
            for n in data.get("nodes", [])
        ]
        for i, n in enumerate(graph.nodes):
            orig = data["nodes"][i]
            n.status = orig["status"]
            n.output_summary = orig.get("output_summary", "")
            n.artifacts = orig.get("artifacts", [])
            n.tokens = orig.get("tokens", 0)
            n.duration_seconds = orig.get("duration_seconds", 0)
            n.started_at = orig.get("started_at")
            n.completed_at = orig.get("completed_at")
            n.error = orig.get("error")
        graph.edges = data.get("edges", [])
        return graph

    def summary(self) -> str:
        """Generate a human-readable summary."""
        completed = sum(1 for n in self.nodes if n.status == "completed")
        total = len(self.nodes)
        total_tokens = sum(n.tokens for n in self.nodes)
        total_time = sum(n.duration_seconds for n in self.nodes)
        lines = [
            f"Task: {self.task}",
            f"Status: {self.status}",
            f"Progress: {completed}/{total} steps completed",
            f"Total tokens: {total_tokens:,}",
            f"Total time: {total_time:.0f}s",
            "",
            "Steps:",
        ]
        for n in self.nodes:
            status_icon = {"completed": "✓", "running": "⠋", "failed": "✗", "pending": "⏳"}.get(n.status, "?")
            lines.append(f"  [{n.step}/{total}] {n.agent:30s} {status_icon} {n.output_summary or n.task[:60]}")
        if self.nodes:
            last = self.nodes[-1]
            lines.append("")
            lines.append("Artifacts:")
            for a in last.artifacts:
                lines.append(f"  - {a}")
        return "\n".join(lines)
