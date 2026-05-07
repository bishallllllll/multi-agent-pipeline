#!/usr/bin/env python3
"""
Query session history for the current directory from RAG.

Usage:
    python3 query_session.py                    # Query current directory
    python3 query_session.py --dir test         # Query specific directory
    python3 query_session.py --query "what was built"  # Custom query
"""
import os
import sys
import hashlib
import argparse
import requests
from pathlib import Path

RAG_API_URL = "http://localhost:8000"
WORKSPACE_ROOT = Path(__file__).parent.parent.parent  # /home/.../Quant


def get_directory_hash(directory: str) -> str:
    """Get MD5 hash of directory name (relative to workspace)."""
    try:
        rel = Path(directory).relative_to(WORKSPACE_ROOT)
        rel_str = str(rel)
        # If it's just '.', use the parent directory name
        if rel_str == '.':
            rel_str = WORKSPACE_ROOT.name
        return hashlib.md5(rel_str.encode()).hexdigest()[:8]
    except ValueError:
        # If not relative to workspace, just use the directory name
        return hashlib.md5(Path(directory).name.encode()).hexdigest()[:8]


def query_session_history(directory: str, query: str = "what was built", k: int = 3):
    """Query RAG for session history in a directory."""
    dir_hash = get_directory_hash(directory)
    
    # Get session IDs for this directory
    try:
        resp = requests.get(f"{RAG_API_URL}/ids", timeout=5)
        resp.raise_for_status()
        all_ids = resp.json()
    except Exception as e:
        print(f"ERROR: Could not connect to RAG API at {RAG_API_URL}")
        print(f"Start it with: cd rag_api && docker compose -f api-compose.yaml up -d")
        sys.exit(1)
    
    session_ids = [id for id in all_ids if id.startswith(f"opencode_session_{dir_hash}")]
    
    if not session_ids:
        print(f"No session history found for directory: {directory}")
        return
    
    print(f"Found {len(session_ids)} sessions for directory: {directory}")
    print(f"Directory hash: {dir_hash}")
    print()
    
    # Query each session (limit to k)
    results = []
    for file_id in session_ids[:k * 2]:  # Get more to filter by score
        try:
            resp = requests.post(
                f"{RAG_API_URL}/query",
                json={"query": query, "file_id": file_id, "k": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data[0]) >= 2:
                    results.append({
                        "content": data[0][0].get("page_content", ""),
                        "score": data[0][1],
                        "file_id": file_id,
                    })
        except Exception:
            continue
    
    # Sort by score and show top k
    results.sort(key=lambda x: x["score"])
    
    if not results:
        print("No relevant sessions found.")
        return
    
    print(f"=== Top {min(len(results), k)} Sessions ===\n")
    for i, r in enumerate(results[:k]):
        # Extract title from content
        content = r["content"]
        title_line = content.split("\n")[0] if content else "Unknown"
        print(f"--- Session {i+1} ---")
        print(content[:600])
        print("...\n")


def main():
    parser = argparse.ArgumentParser(description="Query session history from RAG")
    parser.add_argument("--dir", "-d", help="Directory to query (default: current)")
    parser.add_argument("--query", "-q", help="Search query", default="what was built")
    parser.add_argument("--k", type=int, help="Number of results", default=3)
    args = parser.parse_args()
    
    directory = args.dir or os.getcwd()
    query_session_history(directory, args.query, args.k)


if __name__ == "__main__":
    main()
