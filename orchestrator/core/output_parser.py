"""Parse agent output from opencode JSON stream."""
import json
import re
import os
import logging

logger = logging.getLogger(__name__)


class OutputParser:
    """Parse opencode JSON event stream into structured output."""

    CODE_LANG_MAP = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "json": ".json",
        "yaml": ".yaml",
        "yml": ".yaml",
        "sql": ".sql",
        "bash": ".sh",
        "html": ".html",
        "css": ".css",
        "rust": ".rs",
        "go": ".go",
        "java": ".java",
    }

    def parse_stream(self, json_stream: str) -> dict:
        """Parse a stream of JSON events from opencode run --format json.
        
        Returns dict with:
        - text: full text output
        - code_blocks: list of extracted code blocks with language and content
        - tokens: total token count
        - error: error message if any
        """
        text_parts = []
        error = None
        tokens = 0

        for line in json_stream.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")

            if event_type == "text":
                part = event.get("part", {})
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

            elif event_type == "step_finish":
                part = event.get("part", {})
                token_info = part.get("tokens", {})
                tokens = token_info.get("total", 0)
                reason = part.get("reason", "")
                if reason == "error":
                    error = part.get("error", "Unknown error")

            elif event_type == "error":
                err = event.get("error", {})
                error = err.get("message", "Unknown error")

        full_text = "".join(text_parts)
        code_blocks = self._extract_code_blocks(full_text)

        return {
            "text": full_text,
            "code_blocks": code_blocks,
            "tokens": tokens,
            "error": error,
            "success": error is None and bool(full_text),
        }

    def _extract_code_blocks(self, text: str) -> list[dict]:
        """Extract fenced code blocks from text."""
        pattern = r"```(\w+)?\n(.*?)```"
        blocks = []
        for match in re.finditer(pattern, text, re.DOTALL):
            lang = match.group(1) or "text"
            content = match.group(2).strip()
            blocks.append({
                "language": lang,
                "content": content,
                "extension": self.CODE_LANG_MAP.get(lang.lower(), f".{lang}"),
            })
        return blocks

    def save_artifacts(self, code_blocks: list[dict], artifact_dir: str, prefix: str = "") -> list[str]:
        """Save extracted code blocks to files in artifact directory."""
        os.makedirs(artifact_dir, exist_ok=True)
        saved = []
        for i, block in enumerate(code_blocks):
            ext = block.get("extension", ".txt")
            filename = f"{prefix}block_{i:02d}{ext}" if not prefix else f"{prefix}{ext}"
            # Avoid overwriting
            if prefix and os.path.exists(os.path.join(artifact_dir, filename)):
                filename = f"{prefix}_{i}{ext}"
            filepath = os.path.join(artifact_dir, filename)
            with open(filepath, "w") as f:
                f.write(block["content"])
            saved.append(filepath)
            logger.info(f"Saved artifact: {filepath}")
        return saved

    def extract_summary(self, text: str, max_length: int = 200) -> str:
        """Extract a brief summary from agent output."""
        # Remove code blocks for summary
        clean = re.sub(r"```[\s\S]*?```", "[code]", text)
        # Remove markdown headers
        clean = re.sub(r"^#+\s*", "", clean, flags=re.MULTILINE)
        # Get first meaningful paragraph
        paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
        if paragraphs:
            summary = paragraphs[0]
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."
            return summary
        return text[:max_length] + "..." if len(text) > max_length else text
