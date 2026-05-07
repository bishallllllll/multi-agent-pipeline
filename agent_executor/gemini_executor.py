"""Google Gemini API agent executor (Gemini 2.0, 3.0, 3.1)."""
import os
import subprocess


MODELS = [
    "gemini-2.0-flash", "gemini-2.0-pro", "gemini-2.5-flash", "gemini-2.5-pro",
    "gemini-3.1-flash-lite", "gemini-3.1-pro",
]


async def execute(
    system_prompt: str,
    task: str,
    model: str = "gemini-2.0-flash",
    max_tokens: int = 4096,
    agent_timeout: int = 120,
) -> dict:
    """Execute an agent via Gemini CLI (gemini -e) — matching the existing pattern.

    The Gemini Python SDK has limited tool/function-calling support in some versions,
    so we use the CLI which handles tool calling natively.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GEMINI_API_KEY or GOOGLE_API_KEY not set", "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}

    full_prompt = f"{system_prompt}\n\n## Task\n\n{task}"

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["gemini", "-e", full_prompt, "-m", model],
                    capture_output=True, text=True, timeout=agent_timeout,
                    env={k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")},
                ),
            ),
            timeout=agent_timeout + 10,
        )

        text = result.stdout or result.stderr or ""
        code_blocks = _extract_code_blocks(text)

        return {
            "success": result.returncode == 0,
            "error": result.stderr if result.returncode != 0 else None,
            "text": text,
            "code_blocks": code_blocks,
            "artifacts": [],
            "tokens": 0,
        }

    except asyncio.TimeoutError:
        return {"success": False, "error": f"Gemini timed out after {agent_timeout}s", "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}
    except Exception as e:
        return {"success": False, "error": str(e), "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}


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
