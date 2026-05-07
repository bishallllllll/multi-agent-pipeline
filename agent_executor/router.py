"""Route model names to the correct API executor."""
from . import openai_executor, anthropic_executor, gemini_executor


def _model_provider(model: str) -> str:
    """Determine which provider a model belongs to."""
    m = model.lower()
    if any(k in m for k in ("gpt", "o1", "o3")):
        return "openai"
    if any(k in m for k in ("claude", "anthropic")):
        return "anthropic"
    if any(k in m for k in ("gemini",)):
        return "gemini"
    return "openai"


class AgentExecutorRouter:

    @staticmethod
    async def execute(
        system_prompt: str,
        task: str,
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        agent_timeout: int = 120,
    ) -> dict:
        """Execute an agent with the correct provider based on model name."""
        provider = _model_provider(model)

        if provider == "openai":
            return await openai_executor.execute(
                system_prompt, task, model, max_tokens, agent_timeout,
            )
        elif provider == "anthropic":
            return await anthropic_executor.execute(
                system_prompt, task, model, max_tokens, agent_timeout,
            )
        elif provider == "gemini":
            return await gemini_executor.execute(
                system_prompt, task, model, max_tokens, agent_timeout,
            )
        else:
            return {
                "success": False,
                "error": f"Unknown model provider for: {model}",
                "text": "", "code_blocks": [], "artifacts": [], "tokens": 0,
            }
