#!/usr/bin/env python3
"""CLI entry point for the multi-agent pipeline."""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys

from .pipeline import run_pipeline, load_config


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Pipeline — Autonomous task execution")
    parser.add_argument("--task", "-t", help="Task description for the pipeline")
    parser.add_argument("--config", "-c", help="Path to config YAML file")
    parser.add_argument("--resume", "-r", action="store_true", help="Resume from saved task graph")
    parser.add_argument("--mode", choices=["autonomous", "interactive"], help="Execution mode")
    parser.add_argument("--execution", choices=["parallel", "sequential"], help="Execution style")
    parser.add_argument("--max-steps", type=int, help="Maximum number of agent steps")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Show plan without executing")
    parser.add_argument("--interactive", "-i", action="store_true", help="Pause for confirmation at each step")
    parser.add_argument("--parallel", "-p", action="store_true", help="Run independent agents concurrently")
    parser.add_argument("--sequential", "-s", action="store_true", help="Force sequential execution")

    args = parser.parse_args()

    if args.parallel:
        args.execution = "parallel"
    if args.sequential:
        args.execution = "sequential"

    if not args.task and not args.resume:
        parser.print_help()
        print("\nError: --task is required (or --resume)")
        sys.exit(1)

    config = load_config(args.config)

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    try:
        asyncio.run(run_pipeline(args, config))
    except KeyboardInterrupt:
        print("\nInterrupted. Task graph saved.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
