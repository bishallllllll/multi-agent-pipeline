import httpx
import pytest
from unittest.mock import patch, AsyncMock
from orchestrator.core.rag_client import (
    RagClient, _extract_agent_names_from_text,
    _get_agents_by_task_keywords, _get_agents_by_task_keywords_with_scores,
    KNOWN_AGENTS, TASK_CHAINS,
)


class TestHelpers:
    def test_known_agents_contains_core_agents(self):
        assert "python-engineer" in KNOWN_AGENTS
        assert "backend-developer" in KNOWN_AGENTS
        assert "code-reviewer" in KNOWN_AGENTS
        assert "orchestrator" in KNOWN_AGENTS

    def test_task_chains_has_python(self):
        assert "python" in TASK_CHAINS
        agents, weight = TASK_CHAINS["python"]
        assert "python-engineer" in agents
        assert weight == 3

    def test_extract_agent_names_from_text(self):
        text = "We need a python-engineer and a code-reviewer"
        names = _extract_agent_names_from_text(text)
        assert "python-engineer" in names
        assert "code-reviewer" in names

    def test_extract_agent_names_no_match(self):
        names = _extract_agent_names_from_text("no agents here")
        assert names == []

    def test_get_agents_by_task_keywords_python(self):
        agents = _get_agents_by_task_keywords("write a python module")
        assert len(agents) > 0
        assert "python-engineer" in agents

    def test_get_agents_by_task_keywords_database(self):
        agents = _get_agents_by_task_keywords("design database schema")
        assert "database-admin" in agents or "database-optimizer" in agents

    def test_get_agents_by_task_keywords_empty(self):
        agents = _get_agents_by_task_keywords("something completely unrelated xyz123")
        assert agents == []

    def test_get_agents_by_task_keywords_with_scores(self):
        scores = _get_agents_by_task_keywords_with_scores("build a python web api with database")
        assert len(scores) > 0
        for agent, score in scores.items():
            assert score > 0


class TestRagClient:
    def test_initialization(self):
        client = RagClient(base_url="http://test:8000", timeout=5.0)
        assert client.base_url == "http://test:8000"
        assert client.timeout == 5.0

    def test_build_category_map_no_dir(self):
        client = RagClient(agents_dir="/nonexistent/dir")
        assert client._category_map == {}

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        client = RagClient(base_url="http://nonexistent:9999", timeout=1.0)
        healthy = await client.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = RagClient(base_url="http://test:8000", timeout=5.0)
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_instance.get = AsyncMock(return_value=mock_response)

            healthy = await client.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_query_rag_down(self):
        client = RagClient(base_url="http://nonexistent:9999", timeout=1.0)
        results = await client.query("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_success(self):
        client = RagClient(base_url="http://test:8000", timeout=5.0)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [
            [{"page_content": "doc content", "metadata": {}}, 0.5]
        ]

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        mock_client.__aenter__.return_value = mock_client

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await client.query("test", file_id="test_123", k=3)
            assert len(results) == 1
            assert results[0]["content"] == "doc content"

    @pytest.mark.asyncio
    async def test_close(self):
        client = RagClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        client._client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()

    def test_get_category_for_agent(self):
        client = RagClient(agents_dir="/nonexistent")
        category = client._get_category_for_agent("python-engineer")
        assert category == ""

    @pytest.mark.asyncio
    async def test_find_agent_no_ids(self):
        client = RagClient()
        with patch.object(client, "_get_agent_ids", new=AsyncMock(return_value=[])):
            results = await client.find_agent("build a python web app")
            assert results == []

    @pytest.mark.asyncio
    async def test_find_agent_keyword_only(self):
        client = RagClient()
        with patch.object(client, "_get_agent_ids", new=AsyncMock(return_value=["opencode_core-development_python-engineer"])):
            with patch.object(client, "_get_category_for_agent", return_value="core-development"):
                with patch.object(client, "_query_agents_by_ids", new=AsyncMock(return_value=[{"name": "python-engineer", "score": 0.5}])):
                    results = await client.find_agent("write python code")
                    assert len(results) == 1
                    assert results[0]["name"] == "python-engineer"

    @pytest.mark.asyncio
    async def test_find_session_history_no_ids(self):
        client = RagClient()
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_instance.get = AsyncMock(return_value=mock_response)

            results = await client.find_session_history("/tmp/test")
            assert results == []

    @pytest.mark.asyncio
    async def test_find_task_graphs_no_ids(self):
        client = RagClient()
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_instance.get = AsyncMock(return_value=mock_response)

            results = await client.find_task_graphs("/tmp/test")
            assert results == []
