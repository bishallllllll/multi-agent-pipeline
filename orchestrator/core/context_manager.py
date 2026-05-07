"""Context management for passing information between agents."""
from __future__ import annotations


class ContextManager:
    """Builds and manages context strings passed to agents."""

    def __init__(self):
        self.history: list[dict] = []

    def add_step(self, agent: str, category: str, task: str, output: str, artifacts: list[str]):
        """Record a completed step in context history."""
        self.history.append({
            "agent": agent,
            "category": category,
            "task": task,
            "output_summary": output[:500] if len(output) > 500 else output,
            "artifacts": artifacts,
        })

    def build_context(self, max_summary_length: int = 2000) -> str:
        """Build context string from all previous steps for the next agent."""
        if not self.history:
            return ""

        lines = ["## Previous Work Context\n"]
        total_length = 0
        for step in self.history:
            section = (
                f"### Step by {step['agent']} ({step['category']})\n"
                f"- Task: {step['task']}\n"
                f"- Output: {step['output_summary']}\n"
            )
            if step["artifacts"]:
                section += f"- Artifacts: {', '.join(step['artifacts'])}\n"
            section += "\n"

            if total_length + len(section) > max_summary_length:
                lines.append("...(previous steps truncated)\n")
                break

            lines.append(section)
            total_length += len(section)

        return "".join(lines)

    def build_prompt(self, system_prompt: str, task: str) -> str:
        """Combine system prompt, context, and task into a single prompt."""
        context = self.build_context()
        parts = [system_prompt]
        if context:
            parts.append(context)
        parts.append(f"## Current Task\n\n{task}\n\n"
                     "Execute this task concisely. Output only what is needed. "
                     "Do not include preamble or explanations unless specifically asked.")
        return "\n\n---\n\n".join(parts)
