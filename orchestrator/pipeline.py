"""
Multi-Agent Pipeline — Autonomous task execution via LLM API.

Adapted from the original opencode-based orchestrator.
Replaces `opencode run --file` with direct OpenAI/Anthropic/Gemini API calls.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from core.rag_client import RagClient
from core.task_graph import TaskGraph
from core.output_parser import OutputParser

from agent_executor.router import AgentExecutorRouter

PACKAGE_DIR = Path(__file__).resolve().parent.parent


def load_config(config_path: Optional[str] = None) -> dict:
    path = Path(config_path) if config_path else PACKAGE_DIR / "config.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return {
        "agents_dir": str(PACKAGE_DIR / "agents"),
        "rag_api_url": "http://localhost:8000",
        "default_max_steps": 10,
        "default_mode": "autonomous",
        "default_execution": "parallel",
        "models": {
            "high_complexity": "gpt-4o",
            "standard": "gpt-4o-mini",
            "fast": "gpt-4o-mini",
        },
        "model_categories": {
            "high_complexity": ["architect", "researcher", "analyst", "strategist", "coordinator", "director", "synthesizer"],
            "fast": ["writer", "documenter", "formatter"],
        },
        "artifact_dir": "./artifacts",
        "task_graph_file": ".task_graph.json",
        "agent_timeout": 300,
        "rag_timeout": 10,
        "retry_count": 2,
        "auto_sync_script": "",
    }


def get_model_for_agent(agent_name: str, config: dict) -> str:
    cats = config.get("model_categories", {})
    models = config.get("models", {})
    for category in cats.get("high_complexity", []):
        if category in agent_name.lower():
            return models.get("high_complexity", "gpt-4o")
    for category in cats.get("fast", []):
        if category in agent_name.lower():
            return models.get("fast", "gpt-4o-mini")
    return models.get("standard", "gpt-4o-mini")


def find_agent_prompt(agent_name: str, agents_dir: str) -> Optional[Path]:
    base = Path(agents_dir)
    for category_dir in sorted(base.iterdir()):
        if not category_dir.is_dir():
            continue
        prompt = category_dir / f"{agent_name}.md"
        if prompt.exists():
            return prompt
    return None


def extract_agent_description(prompt_path: Path) -> str:
    import re
    with open(prompt_path) as f:
        content = f.read()
    m = re.search(r"description:\s*(.+)", content)
    return m.group(1).strip() if m else ""


async def find_first_agent(rag: RagClient, task: str, k: int = 5) -> Optional[dict]:
    agents = await rag.find_first_agent(task, k=k)
    if not agents:
        return None
    return agents[0]


async def find_next_agents(rag: RagClient, completed_task: str, prev_agent: str = None, k: int = 3) -> list[dict]:
    agents = await rag.find_next_step(completed_task, k=k, prev_agent=prev_agent)
    seen = set()
    unique = []
    for a in agents:
        if a["name"] not in seen:
            seen.add(a["name"])
            unique.append(a)
    return unique


async def spawn_agent(
    agent_info: dict,
    task: str,
    context: str,
    model: str,
    config: dict,
    parser: OutputParser,
    artifact_dir: str,
    interactive: bool = False,
) -> dict:
    """Spawn a single agent via direct LLM API call."""
    prompt_path = find_agent_prompt(agent_info["name"], config["agents_dir"])
    if not prompt_path:
        return {
            "success": False,
            "error": f"Prompt file not found for agent: {agent_info['name']}",
            "text": "", "code_blocks": [], "artifacts": [], "tokens": 0,
        }

    with open(prompt_path) as f:
        system_prompt = f.read()

    full_task = f"{context}\n\n## Your Task\n\n{task}" if context else task

    if interactive:
        print(f"\n{'='*60}")
        print(f"Agent: {agent_info['name']} ({agent_info['category']})")
        print(f"Model: {model}")
        print(f"Task: {task[:100]}{'...' if len(task) > 100 else ''}")
        print(f"{'='*60}")
        print("Press Enter to execute, or 's' to skip, or 'q' to quit:")
        choice = input("> ").strip().lower()
        if choice == "q":
            raise KeyboardInterrupt
        if choice == "s":
            return {"success": False, "error": "Skipped by user", "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}

    timeout = config.get("agent_timeout", 300)

    result = await AgentExecutorRouter.execute(
        system_prompt=system_prompt,
        task=full_task,
        model=model,
        max_tokens=4096,
        agent_timeout=timeout,
    )

    if result.get("success"):
        artifacts = []
        if result.get("code_blocks"):
            artifacts = parser.save_artifacts(
                result["code_blocks"], artifact_dir,
                prefix=f"{agent_info['name']}_",
            )
        result["artifacts"] = artifacts

    return result


async def run_pipeline(args: argparse.Namespace, config: dict):
    """Main pipeline execution loop."""
    project_root = os.getcwd()
    artifact_dir = os.path.join(project_root, config.get("artifact_dir", "artifacts"))
    os.makedirs(artifact_dir, exist_ok=True)

    task_graph_path = os.path.join(project_root, config.get("task_graph_file", ".task_graph.json"))

    if args.resume and os.path.exists(task_graph_path):
        print(f"Resuming from {task_graph_path}")
        graph = TaskGraph.load(task_graph_path)
        if graph is None:
            print("Could not load task graph. Starting fresh.")
            graph = TaskGraph(project_root, args.task or "resumed task",
                              mode=args.mode or config.get("default_mode", "autonomous"),
                              execution=args.execution or config.get("default_execution", "parallel"))
    elif args.task:
        graph = TaskGraph(project_root, args.task,
                          mode=args.mode or config.get("default_mode", "autonomous"),
                          execution=args.execution or config.get("default_execution", "parallel"))
    else:
        print("Error: --task is required (or --resume)")
        sys.exit(1)

    task = graph.task
    max_steps = args.max_steps or config.get("default_max_steps", 10)
    interactive = args.interactive
    parallel = graph.execution == "parallel"

    rag = RagClient(
        base_url=config.get("rag_api_url", "http://localhost:8000"),
        timeout=config.get("rag_timeout", 10),
    )
    parser = OutputParser()

    healthy = await rag.health_check()
    if not healthy:
        print(f"WARNING: RAG API not reachable at {config['rag_api_url']}")
        print("Agent routing will be limited. Start RAG with: cd rag_api && docker compose up -d")

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — Task: {task}")
        print(f"Max steps: {max_steps} | Mode: {'interactive' if interactive else 'autonomous'} | Execution: {graph.execution}")
        print(f"{'='*60}\n")
        if healthy:
            agent = await find_first_agent(rag, task)
            if agent:
                prompt = find_agent_prompt(agent["name"], config["agents_dir"])
                desc = extract_agent_description(prompt) if prompt else agent.get("description", "")
                print(f"First agent: {agent['name']} ({agent['category']})")
                print(f"Description: {desc}")
            else:
                print("No agent found for this task.")
        print(f"\nArtifact dir: {artifact_dir}")
        print(f"Task graph: {task_graph_path}")
        await rag.close()
        return

    print(f"\n{'='*60}")
    print(f"Task: {task}")
    print(f"Mode: {'interactive' if interactive else 'autonomous'} | Execution: {graph.execution} | Max steps: {max_steps}")
    print(f"{'='*60}\n")

    completed_nodes = [n for n in graph.nodes if n.status == "completed"]
    step = len(completed_nodes)

    while step < max_steps:
        step += 1

        if step == 1:
            if completed_nodes:
                prev = completed_nodes[-1]
                next_agents = await find_next_agents(rag, prev.task, prev_agent=prev.agent)
                if not next_agents:
                    print("No more agents suggested. Task chain complete.")
                    break
                agent_info = next_agents[0] if not parallel or len(next_agents) == 1 else next_agents
            else:
                agent_info = await find_first_agent(rag, task)
        else:
            prev = graph.nodes[-1] if graph.nodes else None
            if prev and prev.status == "completed":
                next_agents = await find_next_agents(rag, prev.task, prev_agent=prev.agent)
                if not next_agents:
                    print("No more agents suggested. Task chain complete.")
                    break
                used_agents = {n.agent for n in graph.nodes}
                next_agents = [a for a in next_agents if a["name"] not in used_agents]
                if not next_agents:
                    print("Remaining agents already executed. Task chain complete.")
                    break
                if parallel and len(next_agents) > 1:
                    agent_info = next_agents
                else:
                    agent_info = next_agents[0]
            else:
                print("Previous step did not complete. Stopping.")
                break

        if agent_info is None:
            print("No agent found. Task chain may be complete.")
            break

        if isinstance(agent_info, list):
            print(f"\nStep {step}: Running {len(agent_info)} agents in parallel")
            tasks = []
            for ai in agent_info:
                model = get_model_for_agent(ai["name"], config)
                tasks.append(spawn_agent(ai, task, "", model, config, parser, artifact_dir, interactive))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ai, result in zip(agent_info, results):
                if isinstance(result, Exception):
                    result = {"success": False, "error": str(result), "text": "", "code_blocks": [], "artifacts": [], "tokens": 0}
                node = graph.add_node(ai["name"], ai.get("category", ""), get_model_for_agent(ai["name"], config), task)
                if result.get("success"):
                    node.status = "completed"
                    node.output_summary = parser.extract_summary(result.get("text", ""))
                    node.artifacts = result.get("artifacts", [])
                    node.tokens = result.get("tokens", 0)
                else:
                    node.status = "failed"
                    node.error = result.get("error", "Unknown")
                    print(f"  ✗ {ai['name']}: {node.error}")
            graph.save()
            continue

        model = get_model_for_agent(agent_info["name"], config)
        node = graph.add_node(agent_info["name"], agent_info.get("category", ""), model, task)
        agent_name = agent_info["name"]
        desc = agent_info.get("description", "")

        print(f"\n[{step}/{max_steps}] Agent: {agent_name} ({model})")
        print(f"  Task: {task[:80]}{'...' if len(task) > 80 else ''}")
        start_time = time.time()

        result = await spawn_agent(agent_info, task, "", model, config, parser, artifact_dir, interactive)
        duration = time.time() - start_time

        node.started_at = datetime.now(timezone.utc).isoformat()

        if result.get("success"):
            node.status = "completed"
            node.output_summary = parser.extract_summary(result.get("text", ""))
            node.artifacts = result.get("artifacts", [])
            node.tokens = result.get("tokens", 0)
            node.duration_seconds = round(duration, 1)
            node.completed_at = datetime.now(timezone.utc).isoformat()
            print(f"  ✓ Completed ({duration:.0f}s, {node.tokens} tokens)")
        else:
            node.status = "failed"
            node.error = result.get("error", "Unknown")
            node.duration_seconds = round(duration, 1)
            node.completed_at = datetime.now(timezone.utc).isoformat()
            print(f"  ✗ Failed: {node.error}")

            retry_count = config.get("retry_count", 2)
            for attempt in range(retry_count):
                print(f"  Retrying ({attempt + 1}/{retry_count})...")
                start_time = time.time()
                result2 = await spawn_agent(
                    agent_info,
                    task,
                    f"Previous attempt failed: {node.error}\nSimplify and complete this task: {agent_info.get('description', '')}",
                    model, config, parser, artifact_dir, interactive,
                )
                duration2 = time.time() - start_time
                if result2.get("success"):
                    node.status = "completed"
                    node.output_summary = parser.extract_summary(result2.get("text", ""))
                    node.artifacts = result2.get("artifacts", [])
                    node.tokens = result2.get("tokens", 0)
                    node.duration_seconds = round(duration2, 1)
                    node.completed_at = datetime.now(timezone.utc).isoformat()
                    node.error = None
                    print(f"  ✓ Retry succeeded ({duration2:.0f}s)")
                    break
                else:
                    print(f"  ✗ Retry also failed: {result2.get('error')}")

        graph.save()

        if interactive and node.status == "completed":
            print(f"\nOutput preview: {node.output_summary[:150]}...")
            choice = input("Continue? [y/n]: ").strip().lower()
            if choice == "n":
                print("Aborted by user.")
                break

    graph.completed_at = datetime.now(timezone.utc).isoformat()
    completed = sum(1 for n in graph.nodes if n.status == "completed")
    graph.status = "completed" if completed == len(graph.nodes) else "partial"
    graph.save()

    print(f"\n{'='*60}")
    print(graph.summary())
    print(f"{'='*60}")

    auto_sync = config.get("auto_sync_script", "")
    if auto_sync and os.path.exists(auto_sync):
        print("\nRunning auto-sync...")
        proc = await asyncio.create_subprocess_exec(
            "python3", auto_sync,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if stdout:
                print(stdout.decode()[:500])
        except asyncio.TimeoutError:
            proc.kill()
            print("Auto-sync timed out")

    await rag.close()
