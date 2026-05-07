# Multi-Agent Pipeline

Standalone SaaS product for autonomous multi-agent task execution. 137 specialized AI agents coordinated through a sequential pipeline with RAG-based routing.

## Architecture

```
User Task → [Orchestrator] → RAG routing → Agent 1 → Agent 2 → ... → Agent N
                │
                ├── Agent Executor (OpenAI / Anthropic / Gemini)
                ├── RAG API (Chroma vector DB for agent discovery)
                ├── Task Graph (persistence + resume)
                └── Tools (Python, Shell, File I/O, Knowledge query)
```

- **Orchestrator**: Routes tasks to the right agents using hybrid keyword + RAG scoring
- **137 Agent Prompts**: Each defines a specialized agent persona with tools
- **Agent Executor**: Direct LLM API calls (no opencode dependency) — supports GPT-4o, Claude, Gemini
- **RAG API**: Chroma-based vector database for agent discovery and knowledge retrieval
- **Task Graph**: Persists execution state for resume and audit

## Quick Start

```bash
# 1. Clone and install
cd multi-agent-pipeline
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API key(s)

# 2. Start the RAG API (for agent routing)
docker compose up -d

# 3. Run the pipeline
python -m orchestrator.cli --task "build a REST API with Python and FastAPI"
```

## CLI Usage

```bash
# Basic
python -m orchestrator.cli --task "analyze this dataset and train a model"

# Interactive mode (confirm each agent step)
python -m orchestrator.cli --task "..." --interactive

# Sequential execution
python -m orchestrator.cli --task "..." --sequential

# Resume from saved state
python -m orchestrator.cli --resume

# Dry run (see what agents would be selected)
python -m orchestrator.cli --task "..." --dry-run

# Custom config
python -m orchestrator.cli --task "..." --config ./my-config.yaml
```

## Configuration

Edit `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `agents_dir` | `./agents` | Directory with agent prompt `.md` files |
| `rag_api_url` | `http://localhost:8000` | RAG API endpoint |
| `default_max_steps` | `10` | Maximum agents in a chain |
| `agent_timeout` | `300` | Seconds per agent execution |
| `retry_count` | `2` | Retry attempts on failure |
| `models.high_complexity` | `gpt-4o` | Model for complex agents |

## Model Support

| Provider | Models | Env Var Required |
|----------|--------|-----------------|
| OpenAI | gpt-4o, o1, o3, gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | claude-3-5-sonnet, claude-3-opus | `ANTHROPIC_API_KEY` |
| Google | gemini-2.0-flash, gemini-3.1-pro | `GEMINI_API_KEY` |

The router selects the provider automatically based on the model name.

## Agent Prompts

137 agent prompt files in `agents/` organized by category:

```
agents/
├── business-product/     (business analyst, product manager, etc.)
├── core-development/     (backend, frontend, fullstack, etc.)
├── data-ai/             (data scientist, ML engineer, etc.)
├── infrastructure/      (devops, cloud, security, etc.)
├── language-experts/    (Python, Rust, Go, TypeScript, etc.)
├── specialized-domains/ (fintech, healthcare, blockchain, etc.)
└── ...
```

Each agent has tools available: `run_python_script`, `run_shell_command`, `read_file`, `write_file`, `query_knowledge`, and more.

## Tested

- 151 routing integration tests
- All 8 sequential pipeline chains validated
- Cycle detection prevents infinite loops
- 3 retry mechanism with simplified fallback prompts
- Resume from partial task graph
