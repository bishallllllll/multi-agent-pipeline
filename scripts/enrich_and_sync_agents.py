"""Enrich RAG agent docs with actual capabilities from prompt files, then re-sync."""
import os
import re
import httpx
import asyncio
import glob

AGENTS_DIR = os.path.expanduser("~/.opencode/agents")
KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge", "opencode_agents"
)
RAG_URL = "http://localhost:8000"


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown."""
    m = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if m:
        fm = {}
        for line in m.group(1).split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                fm[key.strip()] = val.strip().strip('"').strip("'")
        return fm, m.group(2).strip()
    return {}, content.strip()


def build_enriched_content(prompt_path: str, category: str) -> str:
    """Build enriched RAG doc from agent prompt."""
    with open(prompt_path) as f:
        raw = f.read()
    
    frontmatter, body = extract_frontmatter(raw)
    description = frontmatter.get("description", "")
    mode = frontmatter.get("mode", "subagent")
    
    # Extract first 500 chars of body as capabilities summary
    body_clean = body.replace('\n', ' ').strip()
    capabilities = body_clean[:500] + ("..." if len(body_clean) > 500 else "")
    
    # Extract "best for" summary from body — deduplicate against description
    best_for_keywords = []
    body_lower = body.lower()
    desc_lower = description.lower()
    for phrase in ["specializing in", "specializes in", "expert in", "focus on",
                    "handles", "builds", "implements", "designs", "optimizes"]:
        idx = body_lower.find(phrase)
        if idx >= 0:
            rest = body[idx + len(phrase):idx + len(phrase) + 150]
            extracted = rest.strip().split('.')[0].strip().rstrip(',')
            # Skip if it overlaps significantly with description
            desc_words = set(desc_lower.replace(',', ' ').split())
            extracted_words = set(extracted.lower().replace(',', ' ').split())
            overlap = len(desc_words & extracted_words) / max(len(desc_words), 1)
            if overlap > 0.7 or len(extracted) < 10:
                continue
            best_for_keywords.append(extracted)
    
    best_for = "; ".join(best_for_keywords[:3]) if best_for_keywords else description
    
    agent_name = os.path.basename(prompt_path).replace(".md", "")
    
    return f"""# Agent: {category}/{agent_name}

## Category
{category.replace('-', ' ').title()}

## Description
{description}

## Best For
{best_for}

## Capabilities
{capabilities}

## How to Invoke
In opencode.json: spawn as subagent with prompt file at .agents/agents/{category}/{agent_name}.md

## RAG Integration
- Query RAG at http://localhost:8000/query for context at task start
- Log completed task to RAG at task end for next-step routing
- Related agents are discoverable via RAG query: what agent handles [domain]?

## Source File
.agents/agents/{category}/{agent_name}.md
"""


async def sync_all():
    """Enrich all agent docs and re-sync to RAG."""
    print("--- ENRICHING AND RE-SYNCING AGENT DOCS ---")
    
    # Find all agent prompts
    prompt_files = glob.glob(f"{AGENTS_DIR}/**/*.md", recursive=True)
    print(f"Found {len(prompt_files)} agent prompts in {AGENTS_DIR}")
    
    # Collect file_ids for delete
    file_ids = []
    for pf in prompt_files:
        agent_name = os.path.basename(pf).replace(".md", "").lower()
        rel = os.path.relpath(pf, AGENTS_DIR)
        category = os.path.dirname(rel).lower()
        file_id = f"opencode_{category}_{agent_name}"
        file_ids.append(file_id)
    
    async with httpx.AsyncClient() as client:
        # Delete existing entries
        print(f"\nClearing {len(file_ids)} existing agent entries...")
        try:
            del_resp = await client.request("DELETE", f"{RAG_URL}/documents", json=file_ids)
            print(f"  Delete response: {del_resp.status_code}")
        except Exception as e:
            print(f"  Delete skipped: {e}")
        
        success = 0
        failed = 0
        
        for prompt_path in prompt_files:
            agent_name = os.path.basename(prompt_path).replace(".md", "").lower()
            rel = os.path.relpath(prompt_path, AGENTS_DIR)
            category = os.path.dirname(rel).lower()
            file_id = f"opencode_{category}_{agent_name}"
            display_name = f"{category}/{agent_name}"
            
            try:
                # Build enriched content
                enriched = build_enriched_content(prompt_path, category)
                
                # Write to knowledge dir
                knowledge_file = os.path.join(KNOWLEDGE_DIR, f"{category}_{agent_name}.md")
                os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
                with open(knowledge_file, "w") as f:
                    f.write(enriched)
                
                # Upload to RAG
                with open(knowledge_file, "rb") as f:
                    files_payload = {"file": (f"{category}_{agent_name}.md", f, "text/markdown")}
                    data_payload = {"file_id": file_id}
                    
                    resp = await client.post(
                        f"{RAG_URL}/embed",
                        data=data_payload,
                        files=files_payload,
                        timeout=60.0
                    )
                
                if resp.status_code == 200:
                    print(f"  OK: {display_name}")
                    success += 1
                else:
                    print(f"  FAIL: {display_name} ({resp.status_code})")
                    failed += 1
            except Exception as e:
                print(f"  EXCEPT: {display_name} | {e}")
                failed += 1
        
        print(f"\n--- SYNC COMPLETE ---")
        print(f"Success: {success}, Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(sync_all())
