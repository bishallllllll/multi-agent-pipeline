# AGENTS.md — Quant Agent Rules & System Instructions

## System Rules

These rules apply to all agents operating in this Quant repo.

### Coding Style
- Follow PEP 8 for Python, standard conventions for JS/TS
- Type hints required for all Python functions
- Docstrings for all public APIs
- No look-ahead bias in any ML/data pipeline code
- Account for transaction costs (spread/slippage/swap) in all trading simulations

### Git Workflow
- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Branch naming: `feature/<name>`, `fix/<name>`, `experiment/<name>`
- PRs require: description, test plan, risk assessment

### Security
- Never commit secrets, API keys, or credentials
- Use environment variables for all configuration
- Parameterize all database queries
- Validate all external inputs

### Testing
- Minimum 80% code coverage for new code
- Walk-forward validation for all ML models
- No look-ahead bias in any feature engineering
- Test transaction cost handling in all backtests

### Data Engineering
- Source-first data quality: validate at ingestion
- Log all data transformations for auditability
- Preserve raw data immutability
- Version all datasets and features

### ML Pipeline
- Always use walk-forward validation, never random splits
- Log all experiments with hyperparameters, metrics, and metadata
- Feature importance analysis required before model deployment
- Baseline models (XGBoost/LightGBM) before advanced architectures

### Agent Communication
- Query RAG API at `http://localhost:8000/query` for knowledge retrieval
- Use `query_knowledge` tool for cross-document search
- After completing a task, suggest the next appropriate agent or tool
- Task chain: orchestrator → project_manager → data_engineer → feature_engineer → ml_engineer → backtest_analyst → strategy_manager → risk_manager → supervisor

### File Organization
- `agents_system/` — Multi-agent pipeline code
- `rag_api/` — FastAPI RAG service (Chroma/pgvector/Mongo)
- `knowledge/` — Domain knowledge bases for RAG indexing
- `scripts/` — Utility scripts (sync, query, test, monitor)
- `docs/` — Design docs, session handoffs, research notes

## Agent Registry

All agents in this system are documented in:
- `.agents/agents/<category>/<name>.md` — Agent system prompts
- `knowledge/opencode_agents/<name>.md` — RAG-indexed capability docs
- `knowledge/opencode_toolkit/` — Task chains and tool documentation

## Available Skills

All skills are in `.agents/skills/<name>/SKILL.md` — each skill provides domain-specific instructions and workflows.

## RAG Integration

The RAG system serves as the central knowledge base:
- **Query**: `http://localhost:8000/query` (default file_id: `test_123`)
- **Index**: `python3 scripts/sync_research.py` (from `agents_system/scripts/`)
- **All documents**: Automatically searchable via `query_knowledge` tool
- **Task chains**: `knowledge/opencode_toolkit/task_chains.md` maps task sequences

## Next Step Protocol

Every agent MUST:
1. At task start: Query RAG for relevant context about the current task
2. At task end: Query RAG for "what comes next after <completed_task>"
3. Output the suggested next agent/tool for the orchestrator to route to
4. If uncertain, escalate to `supervisor` agent
