"""Anthropic API agent executor (Claude)."""
import json
import os
from anthropic import AsyncAnthropic
from .tools import get_tools_for_provider, execute_tool


MODELS = ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku", "claude-3-5-sonnet", "claude-3-5-haiku", "claude-4"]


async def execute(
    system_prompt: str,
    task: str,
    model: str = "claude-3-5-sonnet-20241022",
    max_tokens: int = 4096,
    agent_timeout: int = 120,
) -> dict:
    """Execute an agent via Anthropic API with tool support."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set", "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}

    client = AsyncAnthropic(api_key=api_key)
    tools = get_tools_for_provider("anthropic")

    text_parts = []
    total_tokens = 0
    code_blocks = []
    tool_use_count = 0
    max_tool_uses = 25

    messages = [{"role": "user", "content": task}]

    try:
        while tool_use_count < max_tool_uses:
            response = await client.messages.create(
                model=model,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None,
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=agent_timeout,
            )

            total_tokens += (
                (response.usage.input_tokens + response.usage.output_tokens)
                if response.usage else 0
            )

            content_blocks = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                    code_blocks.extend(_extract_code_blocks(block.text))
                    content_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_use_count += 1
                    name = block.name
                    args = block.input if isinstance(block.input, dict) else {}
                    result = await execute_tool(name, args)
                    content_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            if tool_use_count >= max_tool_uses or not any(b.get("type") == "tool_use" for b in content_blocks):
                break

            messages.append({"role": "assistant", "content": content_blocks})

        if tool_use_count >= max_tool_uses:
            text_parts.append("\n[Max tool calls reached]")

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "text": "".join(text_parts),
            "code_blocks": code_blocks,
            "artifacts": [],
            "tokens": total_tokens,
        }

    full_text = "".join(text_parts)
    return {
        "success": True,
        "error": None,
        "text": full_text,
        "code_blocks": code_blocks,
        "artifacts": [],
        "tokens": total_tokens,
    }


def _extract_code_blocks(text: str) -> list[dict]:
    import re
    blocks = []
    pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(text):
        lang = m.group(1) or "text"
        content = m.group(2).strip()
        if content:
            blocks.append({"language": lang, "content": content})
    return blocks
