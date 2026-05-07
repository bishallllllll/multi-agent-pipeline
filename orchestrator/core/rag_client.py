"""RAG API client for agent discovery and task chain queries."""
import glob
import httpx
import logging
import os
import re

logger = logging.getLogger(__name__)

# Known agent names (from knowledge/opencode_agents/)
KNOWN_AGENTS = {
    "api-designer", "backend-developer", "frontend-developer", "database-developer",
    "database-admin", "database-architect", "database-optimizer", "graphql-architect",
    "code-reviewer", "unit-test-author", "integration-test-author", "qa-tester",
    "test-architect", "performance-tester", "security-tester", "security-auditor",
    "security-hardener", "debugging-specialist", "performance-analyst",
    "profiling-specialist", "infrastructure-architect", "cloud-architect",
    "devops-engineer", "monitoring-specialist", "deploy-engineer",
    "technical-writer", "api-documenter", "documentation-specialist",
    "documentation-reviewer", "product-manager", "requirement-gathering",
    "system-architect", "tech-lead", "frontend-architect", "ux-researcher",
    "ui-designer", "accessibility-specialist", "data-engineer", "etl-developer",
    "data-quality-specialist", "data-scientist", "feature-engineer",
    "model-trainer", "model-evaluator", "ml-engineer", "ml-ops-engineer",
    "bug-report-analyzer", "data-analyst", "business-analyst",
    "market-research-analyst", "python-expert", "javascript-expert",
    "typescript-expert", "go-expert", "rust-expert", "java-expert",
    "csharp-expert", "cpp-expert", "ruby-expert", "php-expert",
    "swift-expert", "kotlin-expert", "sql-expert", "shell-expert",
    "react-expert", "vue-expert", "angular-expert", "node-expert",
    "flutter-expert", "docker-expert", "kubernetes-expert",
    "terraform-expert", "ansible-expert", "git-expert",
    "customer-success", "dependency-manager", "orchestrator",
    "python-engineer", "fintech-engineer", "fullstack-engineer",
    # Agents referenced in SEQUENTIAL_CHAINS
    "performance-engineer", "mlops-engineer", "documentation-engineer",
    "api-documentation", "sre-engineer", "etl-specialist",
    "qa-automation", "multi-agent-coordinator", "error-detective",
    "security-engineer",
}

# Task chain mappings with priority weights (extracted from task_chains.md)
# PRIMARY keywords (weight=3): core intent of the task
# SECONDARY keywords (weight=2): important but supporting concerns
# TERTIARY keywords (weight=1): nice-to-have or cross-cutting concerns
TASK_CHAINS = {
    # PRIMARY — core implementation intent
    "python": (["python-engineer", "backend-developer"], 3),
    "module": (["python-engineer", "backend-developer", "fullstack-engineer"], 3),
    "build": (["fullstack-engineer", "backend-developer", "python-engineer"], 3),
    "implement": (["backend-developer", "fullstack-engineer", "python-engineer"], 3),
    "forex": (["fintech-engineer", "data-engineer", "python-engineer"], 3),
    "indicator": (["data-engineer", "python-engineer", "fintech-engineer"], 3),
    "trading": (["fintech-engineer", "backend-developer"], 3),
    "calculate": (["data-engineer", "python-engineer"], 3),
    "function": (["python-engineer", "backend-developer"], 3),
    "library": (["python-engineer", "backend-developer"], 3),
    "script": (["python-engineer", "backend-developer"], 3),
    "web": (["fullstack-engineer", "frontend-developer", "backend-developer"], 3),
    "docker": (["devops-engineer", "deploy-engineer"], 3),
    "kubernetes": (["devops-engineer", "cloud-architect"], 3),
    # SECONDARY — important supporting concerns
    "design": (["api-designer", "system-architect"], 2),
    "api": (["api-designer", "backend-developer"], 2),
    "backend": (["backend-developer", "database-developer"], 2),
    "frontend": (["frontend-developer", "accessibility-specialist"], 2),
    "database": (["database-admin", "database-optimizer", "database-developer"], 3),
    "schema": (["database-admin", "database-optimizer"], 3),
    "sql": (["database-developer", "database-optimizer"], 3),
    "postgresql": (["database-admin", "database-developer", "database-optimizer"], 3),
    "test": (["test-architect", "unit-test-author", "qa-tester"], 2),
    "review": (["code-reviewer"], 2),
    "deploy": (["deploy-engineer", "devops-engineer"], 2),
    "security": (["security-auditor", "security-hardener"], 2),
    "performance": (["performance-analyst", "profiling-specialist"], 2),
    "ml": (["ml-engineer", "data-scientist"], 2),
    "data": (["data-engineer", "etl-developer"], 1),
    "graphql": (["graphql-architect"], 2),
    "devops": (["devops-engineer", "monitoring-specialist"], 2),
    "infrastructure": (["infrastructure-architect", "cloud-architect"], 2),
    "ux": (["ux-researcher", "ui-designer"], 2),
    "ui": (["ui-designer", "frontend-developer"], 2),
    "bug": (["bug-report-analyzer", "debugging-specialist"], 2),
    "debug": (["debugging-specialist"], 2),
    "monitor": (["monitoring-specialist"], 2),
    # TERTIARY — cross-cutting concerns
    "document": (["technical-writer", "api-documenter"], 1),
    "prd": (["product-manager"], 1),
    "product": (["product-manager"], 1),
}

# Sequential chains (from task_chains.md)
# All agents referenced here MUST have prompt files in ~/.opencode/agents/
SEQUENTIAL_CHAINS = {
    # API & Backend
    "api-designer": ["backend-developer"],
    "backend-developer": ["python-engineer", "test-architect", "code-reviewer"],
    # Frontend & UI
    "fullstack-engineer": ["code-reviewer", "deployment-engineer"],
    "ui-designer": ["fullstack-engineer"],
    # Database
    "database-admin": ["database-optimizer"],
    "database-optimizer": ["code-reviewer"],
    # Quality & Testing
    "test-architect": ["code-reviewer"],
    "code-reviewer": ["qa-automation"],
    "qa-automation": ["documentation-engineer"],
    "accessibility-specialist": ["code-reviewer"],
    # Documentation & Deployment
    "documentation-engineer": ["deployment-engineer"],
    "api-documentation": ["deployment-engineer"],
    # Security
    "security-auditor": ["security-engineer"],
    "security-engineer": ["code-reviewer"],
    # Performance & ML
    "performance-engineer": ["code-reviewer"],
    "ml-engineer": ["data-scientist"],
    "data-scientist": ["feature-engineer"],
    "feature-engineer": ["ml-engineer"],
    "mlops-engineer": ["security-auditor"],
    # UX & Research
    "ux-researcher": ["ui-designer"],
    # Infrastructure
    "cloud-architect": ["devops-engineer"],
    "devops-engineer": ["sre-engineer"],
    "sre-engineer": ["security-auditor"],
    "deployment-engineer": ["sre-engineer"],
    # Debugging & Error Handling
    "error-detective": ["backend-developer", "database-admin"],
    # Orchestration
    "multi-agent-coordinator": [],
    # Data & ETL
    "data-engineer": ["etl-specialist"],
    "etl-specialist": ["code-reviewer"],
    # Domain-specific
    "python-engineer": ["backend-developer", "code-reviewer"],
    "fintech-engineer": ["python-engineer", "data-engineer"],
}


def _extract_agent_names_from_text(text: str) -> list[str]:
    """Extract known agent names from arbitrary text."""
    found = []
    text_lower = text.lower()
    for agent in KNOWN_AGENTS:
        if agent in text_lower:
            found.append(agent)
    return found


def _get_agents_by_task_keywords_with_scores(task: str) -> dict[str, int]:
    """Get relevant agents with their keyword priority scores."""
    task_lower = task.lower()
    agent_scores = {}
    for keyword, (agent_list, weight) in TASK_CHAINS.items():
        if keyword in task_lower:
            for agent in agent_list:
                if agent not in agent_scores:
                    agent_scores[agent] = 0
                agent_scores[agent] += weight
    return agent_scores


def _get_agents_by_task_keywords(task: str) -> list[str]:
    """Get relevant agents based on task keywords, sorted by keyword priority."""
    scores = _get_agents_by_task_keywords_with_scores(task)
    return [a for a, _ in sorted(scores.items(), key=lambda x: -x[1])]


class RagClient:
    """Client for the RAG API at http://localhost:8000."""

    # Agent doc ID prefixes (from knowledge/opencode_agents/)
    AGENT_PREFIXES = [
        "opencode_core-development_",
        "opencode_infrastructure_",
        "opencode_quality-assurance_",
        "opencode_data-ai_",
        "opencode_language-experts_",
        "opencode_developer-experience_",
        "opencode_specialized-domains_",
        "opencode_business-product_",
        "opencode_orchestration_",
        "opencode_research-analysis_",
    ]

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 10.0,
                 agents_dir: str = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._agent_ids: list[str] | None = None
        # Build category map dynamically from filesystem
        self._category_map = self._build_category_map(agents_dir)

    def _build_category_map(self, agents_dir: str = None) -> dict[str, str]:
        """Build agent-to-category mapping from actual filesystem structure."""
        if agents_dir is None:
            agents_dir = os.path.expanduser("~/.opencode/agents")
        category_map = {}
        if os.path.isdir(agents_dir):
            for pf in glob.glob(os.path.join(agents_dir, "**", "*.md"), recursive=True):
                agent_name = os.path.basename(pf).replace(".md", "").lower()
                category = os.path.basename(os.path.dirname(pf)).lower()
                if agent_name and category and category != "agents":
                    category_map[agent_name] = category
        return category_map

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def _get_agent_ids(self) -> list[str]:
        """Cache agent document IDs."""
        if self._agent_ids is not None:
            return self._agent_ids
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
                resp = await client.get("/ids")
                resp.raise_for_status()
                all_ids = resp.json()
                self._agent_ids = [
                    fid for fid in all_ids
                    if any(fid.startswith(p) for p in self.AGENT_PREFIXES)
                ]
                return self._agent_ids
        except Exception as e:
            logger.error(f"Failed to fetch RAG document IDs: {e}")
            return []

    async def find_agent(self, query: str, k: int = 5) -> list[dict]:
        """Find the best agent(s) for a given task query.

        Uses hybrid scoring: keyword match (fast, primary) + RAG similarity (slow, secondary).
        If keywords match agents, query RAG only for those candidates.
        Falls back to full RAG search if no keyword match.
        """
        agent_ids = await self._get_agent_ids()
        if not agent_ids:
            return []

        # Step 1: Get keyword-matched candidates with priority scores
        keyword_scores = _get_agents_by_task_keywords_with_scores(query)

        if keyword_scores:
            # Build candidate file_ids from keyword-matched agents
            candidate_ids = []
            for agent_name in keyword_scores:
                category = self._get_category_for_agent(agent_name)
                if category:
                    file_id = f"opencode_{category}_{agent_name}"
                    if file_id in agent_ids:
                        candidate_ids.append(file_id)

            # If we found valid candidate IDs, query RAG only for them
            if candidate_ids:
                return await self._query_agents_by_ids(query, candidate_ids, keyword_scores, k)

        # Step 2: Fallback - full RAG search across all agents
        return await self._query_all_agents_rag(query, agent_ids, k)

    async def _query_agents_by_ids(self, query: str, candidate_ids: list[str],
                                   keyword_scores: dict[str, int], k: int) -> list[dict]:
        """Query RAG for specific candidate agent IDs, then re-rank with keyword priority."""
        all_results = []
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for file_id in candidate_ids:
                try:
                    resp = await client.post("/query", json={
                        "query": query,
                        "file_id": file_id,
                        "k": 2,
                    })
                    if resp.status_code != 200:
                        continue
                    results = resp.json()
                    if isinstance(results, list):
                        for item in results:
                            if isinstance(item, list) and len(item) >= 2:
                                doc, score = item[0], item[1]
                                agent_name = file_id.replace("opencode_", "").split("_", 1)[1]
                                # Adjust score by keyword priority: higher weight = lower adjusted score
                                kw_weight = keyword_scores.get(agent_name, 1)
                                # Score multiplier: primary (weight >= 6) = 0.3x, secondary (3-5) = 0.6x, tertiary (1-2) = 0.9x
                                if kw_weight >= 6:
                                    multiplier = 0.3
                                elif kw_weight >= 3:
                                    multiplier = 0.6
                                else:
                                    multiplier = 0.9
                                adjusted_score = score * multiplier
                                all_results.append({
                                    "file_id": file_id,
                                    "content": doc.get("page_content", ""),
                                    "score": adjusted_score,
                                    "raw_score": score,
                                    "keyword_weight": kw_weight,
                                    "metadata": doc.get("metadata", {}),
                                })
                except Exception:
                    continue

        # Sort by adjusted score (lower = better)
        all_results.sort(key=lambda x: x["score"])
        return all_results[:k]

    async def _query_all_agents_rag(self, query: str, agent_ids: list[str], k: int) -> list[dict]:
        """Fallback: query RAG for all agent IDs (original behavior)."""
        all_results = []
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for file_id in agent_ids:
                try:
                    resp = await client.post("/query", json={
                        "query": query,
                        "file_id": file_id,
                        "k": 2,
                    })
                    if resp.status_code != 200:
                        continue
                    results = resp.json()
                    if isinstance(results, list):
                        for item in results:
                            if isinstance(item, list) and len(item) >= 2:
                                doc, score = item[0], item[1]
                                all_results.append({
                                    "file_id": file_id,
                                    "content": doc.get("page_content", ""),
                                    "score": score,
                                    "raw_score": score,
                                    "keyword_weight": 0,
                                    "metadata": doc.get("metadata", {}),
                                })
                except Exception:
                    continue

        all_results.sort(key=lambda x: x["score"])
        return all_results[:k]

    async def find_next_step(self, completed_task: str, k: int = 2, prev_agent: str = None) -> list[dict]:
        """Find what comes next after a completed task."""
        agents = []

        # Strategy 1: Use sequential chain mapping if we know the previous agent
        if prev_agent and prev_agent in SEQUENTIAL_CHAINS:
            next_agents = SEQUENTIAL_CHAINS[prev_agent]
            for agent_name in next_agents:
                agents.append({
                    "name": agent_name,
                    "category": self._get_category_for_agent(agent_name),
                    "description": completed_task,
                    "source": "sequential_chain",
                })
            if agents:
                return agents[:k]

        # Strategy 2: Use task keywords to find relevant agents
        agents = []
        keyword_agents = _get_agents_by_task_keywords(completed_task)
        for agent_name in keyword_agents:
            agents.append({
                "name": agent_name,
                "category": self._get_category_for_agent(agent_name),
                "description": f"Relevant for: {completed_task[:80]}",
                "source": "task_keywords",
            })
        if agents:
            return agents[:k]

        # Strategy 3: Extract agent names from RAG response
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                resp = await client.post("/query", json={
                    "query": f"what comes next after {completed_task}",
                    "file_id": "opencode_task_chains",
                    "k": k,
                })
                if resp.status_code == 200:
                    results = resp.json()
                    if isinstance(results, list):
                        for item in results:
                            if isinstance(item, list) and len(item) >= 2:
                                content = item[0].get("page_content", "")
                                extracted = _extract_agent_names_from_text(content)
                                for agent_name in extracted:
                                    agents.append({
                                        "name": agent_name,
                                        "category": self._get_category_for_agent(agent_name),
                                        "description": content[:80],
                                        "source": "rag_extraction",
                                    })
        except Exception as e:
            logger.error(f"Failed to query next step: {e}")

        # Deduplicate by agent name
        seen = set()
        unique = []
        for a in agents:
            if a["name"] not in seen:
                seen.add(a["name"])
                unique.append(a)
        return unique[:k]

    def _get_category_for_agent(self, agent_name: str) -> str:
        """Get category for a known agent name, derived from filesystem."""
        return self._category_map.get(agent_name, "")

    async def query(self, query: str, file_id: str = "test_123", k: int = 3) -> list[dict]:
        """Generic RAG query."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                resp = await client.post("/query", json={
                    "query": query,
                    "file_id": file_id,
                    "k": k,
                })
                if resp.status_code != 200:
                    return []
                results = resp.json()
                if isinstance(results, list):
                    return [
                        {"content": item[0].get("page_content", ""), "score": item[1]}
                        for item in results
                        if isinstance(item, list) and len(item) >= 2
                    ]
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
        return []

    async def health_check(self) -> bool:
        """Check if RAG API is running."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
                resp = await client.get("/ids")
                return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def find_session_history(self, directory: str, k: int = 5) -> list[dict]:
        """Find previous sessions in a directory."""
        try:
            # First, get all session IDs from RAG
            async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
                resp = await client.get("/ids")
                if resp.status_code != 200:
                    return []
                all_ids = resp.json()
                # Filter for session IDs matching directory hash
                import hashlib
                dir_hash = hashlib.md5(directory.encode()).hexdigest()[:8]
                session_ids = [id for id in all_ids if id.startswith(f"opencode_session_{dir_hash}")]

            if not session_ids:
                return []

            # Query each session (limit to k)
            all_results = []
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                for file_id in session_ids[:k * 2]:  # Get more to filter by score
                    try:
                        resp = await client.post("/query", json={
                            "query": f"previous work in {directory}",
                            "file_id": file_id,
                            "k": 1,
                        })
                        if resp.status_code != 200:
                            continue
                        results = resp.json()
                        if isinstance(results, list) and results:
                            item = results[0]
                            if isinstance(item, list) and len(item) >= 2:
                                all_results.append({
                                    "content": item[0].get("page_content", ""),
                                    "score": item[1],
                                    "file_id": file_id,
                                })
                    except Exception:
                        continue

            # Sort by score and return top k
            all_results.sort(key=lambda x: x["score"])
            return all_results[:k]
        except Exception as e:
            logger.error(f"Session history query failed: {e}")
        return []

    async def find_task_graphs(self, project: str, k: int = 3) -> list[dict]:
        """Find task graphs for a project."""
        try:
            # Get all task graph IDs
            async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
                resp = await client.get("/ids")
                if resp.status_code != 200:
                    return []
                all_ids = resp.json()
                task_graph_ids = [id for id in all_ids if id.startswith("opencode_task_graph_")]

            if not task_graph_ids:
                return []

            # Query each task graph
            all_results = []
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                for file_id in task_graph_ids:
                    try:
                        resp = await client.post("/query", json={
                            "query": f"orchestrator task history in {project}",
                            "file_id": file_id,
                            "k": 1,
                        })
                        if resp.status_code != 200:
                            continue
                        results = resp.json()
                        if isinstance(results, list) and results:
                            item = results[0]
                            if isinstance(item, list) and len(item) >= 2:
                                all_results.append({
                                    "content": item[0].get("page_content", ""),
                                    "score": item[1],
                                    "file_id": file_id,
                                })
                    except Exception:
                        continue

            all_results.sort(key=lambda x: x["score"])
            return all_results[:k]
        except Exception as e:
            logger.error(f"Task graph query failed: {e}")
        return []
