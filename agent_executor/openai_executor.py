"""OpenAI API agent executor (GPT-4o, o1, o3, etc.)."""
import json
import os
from openai import AsyncOpenAI
from .tools import get_tools_for_provider, execute_tool


MODELS = ["gpt-4o", "gpt-4o-mini", "o1", "o3", "o3-mini", "gpt-4-turbo"]


async def execute(
    system_prompt: str,
    task: str,
    model: str = "gpt-4o",
    max_tokens: int = 4096,
    agent_timeout: int = 120,
) -> dict:
    """Execute an agent via OpenAI API with tool support."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "error": "OPENAI_API_KEY not set", "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}

    client = AsyncOpenAI(api_key=api_key)
    tools = get_tools_for_provider("openai")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    text_parts = []
    total_tokens = 0
    code_blocks = []
    tool_use_count = 0
    max_tool_uses = 25

    try:
        while tool_use_count < max_tool_uses:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=agent_timeout,
            )

            choice = response.choices[0]
            msg = choice.message
            total_tokens += response.usage.total_tokens if response.usage else 0

            if msg.content:
                text_parts.append(msg.content)
                code_blocks.extend(_extract_code_blocks(msg.content))

            if msg.tool_calls:
                tool_use_count += len(msg.tool_calls)
                messages.append(msg)
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    result = await execute_tool(name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                break

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
    """Extract ```lang ... ``` code blocks from text."""
    import re
    blocks = []
    pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(text):
        lang = m.group(1) or "text"
        content = m.group(2).strip()
        if content:
            blocks.append({"language": lang, "content": content})
    return blocks
