# Multi-Agent Pipeline — Autonomous Production Workflow

You are the autonomous developer for this multi-agent pipeline SaaS product.
Your job is to make it production-ready, one PR at a time.

## Production Readiness Checklist

Each cycle, pick the highest unchecked item. Complete it fully before moving to the next.

- [ ] **1. Test suite** — Create `tests/test_agent_executor/` and `tests/test_orchestrator/` with pytest. Test tools.py, router.py, openai/anthropic/gemini executors, pipeline.py, rag_client.py, task_graph.py. Use pytest-asyncio for async tests. Mock external APIs.
- [ ] **2. CI workflow** — Ensure `.github/workflows/ci.yml` runs on every PR. It should lint with ruff, run pytest, and build a Docker image. Fix any issues.
- [ ] **3. Dockerfile** — Create a multi-stage Dockerfile at repo root. Stage 1: Python 3.11-slim, install deps. Stage 2: copy code, set entrypoint to `python -m orchestrator.cli`. Include health check.
- [ ] **4. Health endpoint** — Add a FastAPI `/health` endpoint or a simple CLI `--health` flag that returns JSON status. Add Docker HEALTHCHECK instruction.
- [ ] **5. Structured error handling** — Define typed exception classes in `agent_executor/exceptions.py` and `orchestrator/exceptions.py`. Add error codes. Wrap all public functions in try/except that returns structured error dicts.
- [ ] **6. JSON logging** — Add structured logging with `logging` module + JSON formatter. Every module gets a logger. Log at key entry/exit points with duration.
- [ ] **7. Auth** — Add JWT or API-key authentication to the RAG API. Add `--require-auth` flag to orchestrator CLI. Validate tokens on all RAG API endpoints.
- [ ] **8. API documentation** — Add docstrings to all public functions. Generate OpenAPI spec for any FastAPI endpoints. Add `--help` examples to CLI.
- [ ] **9. Security scanning** — Add `.github/dependabot.yml`. Add `pip-audit` to CI. Add `safety` check. Add `.env` file validation at startup.
- [ ] **10. CLI completion** — Add shell completion scripts for bash/zsh. Add `--version` flag. Add colored output. Add progress indicators.

## Git Workflow

1. `git checkout -b production/{item-name}` — always branch from main
2. Implement changes. Keep each PR focused on ONE checklist item.
3. Before committing: `python -m pytest tests/ -v --tb=short && ruff check .`
4. `git add -A && git commit -m "feat(production): {item description}"`
5. `gh pr create --title "feat(production): {item}" --body "Closes checklist item {N}\n\n{summary of changes}" --label production`
6. Wait for CI to pass. The workflow auto-merges.

## Orchestrator Usage

For complex multi-step tasks, use the orchestrator to plan:
```bash
python -m orchestrator.cli --task "what needs to change to add tests for agent_executor?" --dry-run
```

This returns a plan showing which agents would handle the task. Use it as guidance, then implement directly.

## Rules

- Never force push. Never rewrite main.
- Never create a PR that spans multiple checklist items.
- If tests don't exist, create them first before implementing features.
- If you encounter an error, fix it before moving on.
- Each module must have: tests, docstrings, type hints, error handling, logging.
- Commit messages follow conventional commits: feat, fix, chore, refactor, docs, test.
