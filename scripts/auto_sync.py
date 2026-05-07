#!/usr/bin/env python3
"""
Unified auto-sync daemon for RAG vector store.

Syncs three data sources on every run:
  1. OpenCode sessions (incremental from opencode.db)
  2. Task graphs (hash-based change detection)
  3. Research/knowledge docs (hash-based change detection)

Usage:
    python3 auto_sync.py              # Single run (for cron)
    python3 auto_sync.py --full       # Full re-sync of sessions
    python3 auto_sync.py --only research  # Only sync research docs
    python3 auto_sync.py --skip-tasks     # Skip task graph sync
"""
import os
import sys
import json
import glob
import hashlib
import argparse
import tempfile
import logging
import time
import sqlite3
import httpx
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

# ── Paths ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent
LOGS_DIR = WORKSPACE_ROOT / "agents_system" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
RAG_API_URL = "http://localhost:8000"

SYNC_STATE_DIR = SCRIPT_DIR
SESSION_STATE_FILE = SYNC_STATE_DIR / ".session_sync_state.json"
TASK_GRAPH_STATE_FILE = SYNC_STATE_DIR / ".task_graph_sync_state.json"
RESEARCH_STATE_FILE = SYNC_STATE_DIR / ".research_sync_state.json"

LOCK_FILE = Path("/tmp/quant_auto_sync.lock")

# ── Logging ────────────────────────────────────────────────────
logger = logging.getLogger("auto_sync")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOGS_DIR / "auto_sync.log")
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(console_handler)


# ── Lock File ─────────────────────────────────────────────────
@contextmanager
def acquire_lock():
    """Acquire exclusive lock, release on exit. Returns False if lock not acquired."""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if os.path.exists(f"/proc/{pid}"):
                logger.info(f"Another sync running (PID {pid}), skipping.")
                yield False
                return
            else:
                logger.info(f"Stale lock (PID {pid}), removing.")
                LOCK_FILE.unlink(missing_ok=True)
        except (ValueError, OSError):
            LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.write_text(str(os.getpid()))
    try:
        yield True
    finally:
        LOCK_FILE.unlink(missing_ok=True)


# ── State Management ──────────────────────────────────────────
def load_state(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_state(path: Path, state: dict):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


# ── RAG Indexing Helper ───────────────────────────────────────
async def index_to_rag(client: httpx.AsyncClient, file_id: str, content: str) -> bool:
    """Index text content to RAG via /embed endpoint."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            temp_path = f.name

        with open(temp_path, "rb") as f:
            files_payload = {"file": (f"{file_id}.md", f, "text/markdown")}
            data_payload = {"file_id": file_id}

            response = await client.post(
                f"{RAG_API_URL}/embed",
                data=data_payload,
                files=files_payload,
                timeout=60.0,
            )

        os.unlink(temp_path)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"  Exception indexing {file_id}: {e}")
        return False


async def rag_health_check() -> bool:
    """Quick health check on RAG API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{RAG_API_URL}/health", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False


# ── 1. Session Sync ──────────────────────────────────────────
def normalize_directory(directory: str) -> str:
    try:
        return str(Path(directory).relative_to(WORKSPACE_ROOT))
    except ValueError:
        return directory


def generate_session_file_id(session_id: str, directory: str) -> str:
    normalized = normalize_directory(directory)
    dir_hash = hashlib.md5(normalized.encode()).hexdigest()[:8]
    return f"opencode_session_{dir_hash}_{session_id}"


def extract_session_summary(session: dict, parts: list, messages: list) -> str:
    title = session.get("title", "Untitled")
    directory = normalize_directory(session.get("directory", ""))
    agent = session.get("agent", "default")
    model = session.get("model", "unknown")
    created = session.get("time_created", 0)
    created_dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat() if created else "unknown"

    user_request = ""
    for msg in messages:
        try:
            data = json.loads(msg[0])
            if data.get("role") == "user":
                content = data.get("content", "")
                if isinstance(content, str) and content.strip():
                    user_request = content.strip()[:500]
                    break
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            user_request = part.get("text", "").strip()[:500]
                            break
                if user_request:
                    break
        except (json.JSONDecodeError, Exception):
            continue

    actions = []
    artifacts = []
    final_output = ""

    for part_data in parts:
        try:
            data = json.loads(part_data[0])
            part_type = data.get("type", "")

            if part_type == "text":
                text = data.get("text", "")
                if text and len(text) > 50:
                    final_output = text[:1000]

            elif part_type == "tool-call":
                tool = data.get("toolCall", {})
                tool_name = tool.get("name", "")
                tool_input = tool.get("input", {})
                if tool_name in ("write", "edit"):
                    file_path = tool_input.get("file_path", tool_input.get("path", ""))
                    if file_path:
                        artifacts.append(file_path)
                        actions.append(f"Modified: {file_path}")

        except (json.JSONDecodeError, Exception):
            continue

    summary_lines = [
        f"# Session: {title}",
        f"",
        f"- **Directory**: `{directory}`",
        f"- **Agent**: {agent}",
        f"- **Model**: {model}",
        f"- **Created**: {created_dt}",
        f"- **Session ID**: {session.get('id', 'unknown')}",
        f"",
    ]

    if user_request:
        summary_lines.append(f"## User Request\n\n{user_request}\n")
    if actions:
        summary_lines.append(f"## Actions Taken\n\n" + "\n".join(f"- {a}" for a in actions[:10]) + "\n")
    if artifacts:
        unique_artifacts = list(dict.fromkeys(artifacts))
        summary_lines.append(f"## Artifacts\n\n" + "\n".join(f"- `{a}`" for a in unique_artifacts[:10]) + "\n")
    if final_output:
        summary_lines.append(f"## Final Output\n\n{final_output[:500]}...\n")

    return "\n".join(summary_lines)


async def sync_sessions(full: bool = False) -> dict:
    """Sync opencode sessions to RAG. Returns stats dict."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    if not OPENCODE_DB.exists():
        logger.debug("Session sync: opencode.db not found, skipping.")
        return stats

    state = load_state(SESSION_STATE_FILE)
    last_sync = state.get("last_sync_timestamp", 0) if not full else 0
    synced = set(state.get("synced_sessions", []))

    conn = sqlite3.connect(OPENCODE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if last_sync > 0:
        cursor.execute(
            "SELECT * FROM session WHERE time_created > ? ORDER BY time_created ASC",
            (last_sync,),
        )
    else:
        cursor.execute("SELECT * FROM session ORDER BY time_created ASC")

    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not sessions:
        logger.debug("Session sync: no new sessions.")
        return stats

    logger.info(f"Session sync: {len(sessions)} new sessions")

    async with httpx.AsyncClient() as http_client:
        max_timestamp = last_sync
        new_synced = []

        for session in sessions:
            session_id = session["id"]
            if session_id in synced:
                stats["skipped"] += 1
                continue

            directory = session.get("directory", "")
            file_id = generate_session_file_id(session_id, directory)

            # Re-fetch data inside the httpx context
            conn = sqlite3.connect(OPENCODE_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT data FROM message WHERE session_id = ? ORDER BY time_created ASC",
                (session_id,),
            )
            messages = cursor.fetchall()

            cursor.execute(
                "SELECT data FROM part WHERE session_id = ? ORDER BY time_created ASC",
                (session_id,),
            )
            parts = cursor.fetchall()
            conn.close()

            summary = extract_session_summary(session, parts, messages)
            success = await index_to_rag(http_client, file_id, summary)

            if success:
                logger.info(f"  Session synced: {session.get('title', 'Untitled')[:50]}")
                stats["success"] += 1
                new_synced.append(session_id)
            else:
                logger.warning(f"  Session failed: {file_id}")
                stats["failed"] += 1

            if session["time_created"] > max_timestamp:
                max_timestamp = session["time_created"]

        state["last_sync_timestamp"] = max_timestamp
        state["synced_sessions"] = list(synced | set(new_synced))
        save_state(SESSION_STATE_FILE, state)

    return stats


# ── 2. Task Graph Sync ───────────────────────────────────────
def find_task_graphs(workspace: Path) -> list[Path]:
    graphs = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if not d.startswith('.') or d == '.git']
        if '.task_graph.json' in files:
            graphs.append(Path(root) / '.task_graph.json')
    return graphs


def generate_task_graph_file_id(graph_path: Path) -> str:
    try:
        rel_path = graph_path.parent.relative_to(WORKSPACE_ROOT)
        path_hash = hashlib.md5(str(rel_path).encode()).hexdigest()[:8]
        return f"opencode_task_graph_{path_hash}"
    except ValueError:
        path_hash = hashlib.md5(str(graph_path).encode()).hexdigest()[:8]
        return f"opencode_task_graph_{path_hash}"


def build_task_graph_summary(graph: dict, graph_path: Path) -> str:
    project = graph.get("project", str(graph_path.parent))
    task = graph.get("task", "Unknown task")
    status = graph.get("status", "unknown")
    mode = graph.get("mode", "autonomous")
    execution = graph.get("execution", "parallel")
    started = graph.get("started_at", "unknown")
    completed = graph.get("completed_at", "unknown")

    nodes = graph.get("nodes", [])
    total_steps = len(nodes)
    completed_steps = sum(1 for n in nodes if n.get("status") == "completed")
    failed_steps = sum(1 for n in nodes if n.get("status") == "failed")
    total_tokens = sum(n.get("tokens", 0) for n in nodes)
    total_time = sum(n.get("duration_seconds", 0) for n in nodes)

    agent_chain = " -> ".join(n.get("agent", "?") for n in nodes if n.get("status") == "completed")

    all_artifacts = []
    for n in nodes:
        all_artifacts.extend(n.get("artifacts", []))
    unique_artifacts = list(dict.fromkeys(all_artifacts))

    summary_lines = [
        f"# Task Graph: {task}",
        f"",
        f"- **Project**: `{project}`",
        f"- **Status**: {status}",
        f"- **Mode**: {mode} / {execution}",
        f"- **Started**: {started}",
        f"- **Completed**: {completed}",
        f"- **Progress**: {completed_steps}/{total_steps} steps",
        f"- **Failed**: {failed_steps} steps",
        f"- **Total Tokens**: {total_tokens:,}",
        f"- **Total Time**: {total_time:.0f}s",
        f"",
        f"## Agent Chain\n\n`{agent_chain}`\n",
    ]

    if unique_artifacts:
        summary_lines.append(f"## Artifacts Produced\n\n" + "\n".join(f"- `{a}`" for a in unique_artifacts[:15]) + "\n")

    summary_lines.append(f"## Execution Steps\n\n")
    for i, n in enumerate(nodes, 1):
        status_icon = {"completed": "OK", "failed": "FAIL", "running": "RUN", "pending": "PEND"}.get(n.get("status", "?"), "?")
        agent = n.get("agent", "unknown")
        agent_task = n.get("task", "") or n.get("output_summary", "")[:80]
        duration = n.get("duration_seconds", 0)
        tokens = n.get("tokens", 0)
        summary_lines.append(f"{i}. [{status_icon}] **{agent}** ({duration:.0f}s, {tokens:,} tokens): {agent_task}")

    return "\n".join(summary_lines)


async def sync_task_graphs() -> dict:
    """Sync task graphs to RAG. Returns stats dict."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    state = load_state(TASK_GRAPH_STATE_FILE)
    indexed = state.get("indexed_graphs", {})

    graphs = find_task_graphs(WORKSPACE_ROOT)
    if not graphs:
        logger.debug("Task graph sync: no graphs found.")
        return stats

    logger.info(f"Task graph sync: {len(graphs)} graphs found")

    async with httpx.AsyncClient() as http_client:
        for graph_path in graphs:
            with open(graph_path) as f:
                content = f.read()
            content_hash = hashlib.md5(content.encode()).hexdigest()

            file_id = generate_task_graph_file_id(graph_path)

            if indexed.get(file_id) == content_hash:
                stats["skipped"] += 1
                continue

            try:
                graph = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"Task graph invalid JSON: {graph_path}: {e}")
                stats["failed"] += 1
                continue

            summary = build_task_graph_summary(graph, graph_path)
            success = await index_to_rag(http_client, file_id, summary)

            if success:
                logger.info(f"  Task graph synced: {graph_path.parent.name}")
                stats["success"] += 1
                indexed[file_id] = content_hash
            else:
                logger.warning(f"  Task graph failed: {file_id}")
                stats["failed"] += 1

        state["indexed_graphs"] = indexed
        save_state(TASK_GRAPH_STATE_FILE, state)

    return stats


# ── 3. Research/Knowledge Sync ───────────────────────────────
RESEARCH_DIR = WORKSPACE_ROOT / "knowledge" / "forex_ml"


def find_research_files(directory: Path) -> list[Path]:
    """Find all markdown files in research directory."""
    if not directory.exists():
        return []
    return list(directory.glob("*.md"))


async def sync_research() -> dict:
    """Sync research/knowledge docs to RAG. Returns stats dict."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    state = load_state(RESEARCH_STATE_FILE)
    indexed = state.get("indexed_files", {})

    files = find_research_files(RESEARCH_DIR)
    if not files:
        logger.debug("Research sync: no files found.")
        return stats

    logger.info(f"Research sync: {len(files)} files found")

    # Collect file_ids for delete-before-upsert
    file_ids = [f.stem.lower().replace("_", "").replace("-", "") for f in files]
    # Actually use consistent file_id format
    file_ids = []
    for f in files:
        file_id = f.name.replace(".md", "").lower()
        file_ids.append(file_id)

    # Delete existing entries (safe, idempotent)
    async with httpx.AsyncClient() as http_client:
        try:
            await http_client.request("DELETE", f"{RAG_API_URL}/documents", json=file_ids)
        except Exception:
            pass

        for file_path in files:
            content_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
            file_id = file_path.name.replace(".md", "").lower()

            if indexed.get(file_id) == content_hash:
                stats["skipped"] += 1
                continue

            try:
                with open(file_path, "rb") as f:
                    files_payload = {"file": (file_path.name, f, "text/markdown")}
                    data_payload = {"file_id": file_id}

                    response = await http_client.post(
                        f"{RAG_API_URL}/embed",
                        data=data_payload,
                        files=files_payload,
                        timeout=60.0,
                    )

                if response.status_code == 200:
                    logger.info(f"  Research synced: {file_path.name}")
                    stats["success"] += 1
                    indexed[file_id] = content_hash
                else:
                    logger.warning(f"  Research failed: {file_id} ({response.status_code})")
                    stats["failed"] += 1
            except Exception as e:
                logger.warning(f"  Research exception: {file_id}: {e}")
                stats["failed"] += 1

        state["indexed_files"] = indexed
        save_state(RESEARCH_STATE_FILE, state)

    return stats


# ── Main Orchestrator ────────────────────────────────────────
async def run_sync(full: bool = False, skip_tasks: bool = False, only: str = None) -> dict:
    """
    Run all sync operations. Call this from the orchestrator or CLI.

    Args:
        full: Full re-sync of sessions
        skip_tasks: Skip task graph sync
        only: Only sync specified source ('sessions', 'tasks', 'research')
    """
    overall = {"sessions": {}, "tasks": {}, "research": {}}

    if not await rag_health_check():
        logger.warning("RAG API not reachable at %s, skipping sync.", RAG_API_URL)
        overall["_health"] = False
        return overall

    overall["_health"] = True
    start = time.time()

    if only in (None, "sessions"):
        overall["sessions"] = await sync_sessions(full=full)

    if only in (None, "tasks") and not skip_tasks:
        overall["tasks"] = await sync_task_graphs()

    if only in (None, "research"):
        overall["research"] = await sync_research()

    elapsed = time.time() - start
    overall["_elapsed"] = round(elapsed, 2)

    # Summary
    total_success = sum(s.get("success", 0) for s in [overall["sessions"], overall["tasks"], overall["research"]])
    total_failed = sum(s.get("failed", 0) for s in [overall["sessions"], overall["tasks"], overall["research"]])
    total_skipped = sum(s.get("skipped", 0) for s in [overall["sessions"], overall["tasks"], overall["research"]])

    logger.info(
        f"Sync complete in {elapsed:.1f}s: {total_success} synced, "
        f"{total_failed} failed, {total_skipped} skipped"
    )

    return overall


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Auto-sync knowledge to RAG vector store")
    parser.add_argument("--full", action="store_true", help="Full re-sync of sessions")
    parser.add_argument("--skip-tasks", action="store_true", help="Skip task graph sync")
    parser.add_argument("--only", choices=["sessions", "tasks", "research"], help="Only sync specified source")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress console output")
    args = parser.parse_args()

    if args.quiet:
        console_handler.setLevel(logging.WARNING)

    with acquire_lock() as acquired:
        if not acquired:
            sys.exit(0)

        result = asyncio.run(run_sync(full=args.full, skip_tasks=args.skip_tasks, only=args.only))

        if not result.get("_health"):
            sys.exit(2)

        # Exit with error if any failures
        total_failed = sum(s.get("failed", 0) for s in [result["sessions"], result["tasks"], result["research"]])
        if total_failed > 0:
            sys.exit(1)

        sys.exit(0)


if __name__ == "__main__":
    main()
