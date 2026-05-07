#!/usr/bin/env python3
"""Manual query tool for the RAG knowledge brain.
Searches across ALL documents in the vector DB and returns top results.
"""
import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def fetch_ids(client):
    resp = await client.get(f"{BASE_URL}/ids")
    if resp.status_code == 200:
        return resp.json()
    return []

async def query_one(client, query, file_id, k):
    try:
        resp = await client.post(
            f"{BASE_URL}/query",
            json={"query": query, "file_id": file_id, "k": k},
            timeout=10.0,
        )
        if resp.status_code == 200:
            results = resp.json()
            return [(doc, score, file_id) for doc, score in results]
    except Exception:
        pass
    return []

async def run_query(query, top_k=5):
    async with httpx.AsyncClient() as client:
        ids = await fetch_ids(client)
        if not ids:
            print("No documents in the knowledge brain.")
            return

        print(f"\nAvailable documents ({len(ids)}): {', '.join(sorted(ids))}")
        print(f"Querying all documents...")

        # Query all files in parallel, asking for top_k from each
        tasks = [query_one(client, query, fid, top_k) for fid in ids]
        all_results = await asyncio.gather(*tasks)

    # Flatten and sort by score (lower = closer match)
    merged = []
    for results in all_results:
        merged.extend(results)

    merged.sort(key=lambda x: x[1])
    top_results = merged[:top_k]

    if not top_results:
        print("No matches found.")
        return

    for i, (doc, score, file_id) in enumerate(top_results, 1):
        relevance = 1 - score
        content = doc.get("page_content", "N/A")
        print(f"\n[{i}] Relevance: {relevance:.2f}  (from: {file_id})")
        print(f"{'─' * 50}")
        print(content)
        print(f"{'─' * 50}")

def main():
    print("=== Query the RAG Knowledge Brain ===")
    print()

    query = input("Query: ").strip()
    if not query:
        print("Empty query. Exiting.")
        sys.exit(0)

    k_str = input("Results count (default 5): ").strip()
    k = int(k_str) if k_str else 5

    asyncio.run(run_query(query, k))

if __name__ == "__main__":
    main()
