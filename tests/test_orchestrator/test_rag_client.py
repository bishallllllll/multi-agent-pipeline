import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from orchestrator.core.rag_client import (
    _extract_agent_names_from_text,
    _get_agents_by_task_keywords_with_scores,
    _get_agents_by_task_keywords,
    RagClient,
)


class TestExtractAgentNamesFromText:
    def test_extracts_known_agents(self):
        text = "use the python-engineer and the database-admin for this"
        result = _extract_agent_names_from_text(text)
        assert "python-engineer" in result
        assert "database-admin" in result

    def test_no_agents_found(self):
        result = _extract_agent_names_from_text("some random text")
        assert result == []

    def test_case_insensitive(self):
        result = _extract_agent_names_from_text("Python-Engineer and CODE-REVIEWER")
        assert "python-engineer" in result
        assert "code-reviewer" in result

    def test_partial_match_does_not_false_positive(self):
        result = _extract_agent_names_from_text("engineer")
        assert "python-engineer" not in result


class TestGetAgentsByTaskKeywords:
    def test_primary_keyword(self):
        scores = _get_agents_by_task_keywords_with_scores("build a web app")
        assert len(scores) > 0
        assert any("fullstack-engineer" in scores for s in [scores])

    def test_no_match(self):
        scores = _get_agents_by_task_keywords_with_scores("xyzzy_nonexistent")
        assert scores == {}

    def test_ordered_by_score(self):
        agents = _get_agents_by_task_keywords("build python web app")
        assert len(agents) > 0


class TestRagClient:
    @pytest.mark.asyncio
    async def test_init(self):
        client = RagClient(base_url="http://test:8000", timeout=5.0)
        assert client.base_url == "http://test:8000"
        assert client.timeout == 5.0
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_response)):
            client = RagClient(base_url="http://test:8000")
            result = await client.health_check()
            assert result is True
            await client.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("down"))):
            client = RagClient(base_url="http://test:8000")
            result = await client.health_check()
            assert result is False
            await client.close()

    @pytest.mark.asyncio
    async def test_query_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            [{"page_content": "result 1", "metadata": {}}, 0.1],
            [{"page_content": "result 2", "metadata": {}}, 0.2],
        ]

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = RagClient(base_url="http://test:8000")
            results = await client.query("test query", "file_1", k=3)
            assert len(results) == 2
            assert results[0]["content"] == "result 1"
            await client.close()

    @pytest.mark.asyncio
    async def test_query_failure(self):
        mock_response = AsyncMock()
        mock_response.status_code = 404

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = RagClient(base_url="http://test:8000")
            results = await client.query("test", "x")
            assert results == []
            await client.close()

    @pytest.mark.asyncio
    async def test_find_agent_no_agent_ids(self):
        client = RagClient(base_url="http://test:8000")
        with patch.object(client, "_get_agent_ids", AsyncMock(return_value=[])):
            result = await client.find_agent("build a web app")
            assert result == []

    @pytest.mark.asyncio
    async def test_find_agent_keyword_match(self):
        client = RagClient(base_url="http://test:8000")
        client._category_map = {"python-engineer": "core-development"}
        with patch.object(client, "_get_agent_ids", AsyncMock(return_value=[
            "opencode_core-development_python-engineer",
        ])):
            with patch.object(client, "_query_agents_by_ids", AsyncMock(return_value=[
                {"file_id": "opencode_core-development_python-engineer", "score": 0.1, "content": "Python engineer", "raw_score": 0.1, "keyword_weight": 3, "metadata": {}},
            ])):
                result = await client.find_agent("build python module")
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_find_agent_fallback_to_rag(self):
        client = RagClient(base_url="http://test:8000")
        with patch.object(client, "_get_agent_ids", AsyncMock(return_value=[
            "opencode_core-development_python-engineer",
        ])):
            with patch.object(client, "_query_all_agents_rag", AsyncMock(return_value=[
                {"file_id": "opencode_core-development_python-engineer", "score": 0.1, "content": "Python content", "raw_score": 0.1, "keyword_weight": 0, "metadata": {}},
            ])):
                result = await client.find_agent("something completely different xyzzy")
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_find_next_step_sequential(self):
        client = RagClient(base_url="http://test:8000")
        result = await client.find_next_step("completed task", prev_agent="api-designer")
        assert len(result) > 0
        assert result[0]["source"] == "sequential_chain"

    @pytest.mark.asyncio
    async def test_find_next_step_no_prev_agent(self):
        client = RagClient(base_url="http://test:8000")
        result = await client.find_next_step("build python module")
        assert isinstance(result, list)

    def test_get_category_for_agent_empty(self):
        client = RagClient(base_url="http://test:8000")
        cat = client._get_category_for_agent("python-engineer")
        assert cat == "" or isinstance(cat, str)

    @pytest.mark.asyncio
    async def test_find_session_history(self):
        mock_ids_response = AsyncMock()
        mock_ids_response.status_code = 200
        mock_ids_response.json.return_value = ["opencode_session_abc123_xyz"]

        mock_query_response = AsyncMock()
        mock_query_response.status_code = 200
        mock_query_response.json.return_value = [[{"page_content": "session data"}, 0.1]]

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_ids_response)):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_query_response)):
                client = RagClient(base_url="http://test:8000")
                results = await client.find_session_history("/some/project")
                assert isinstance(results, list)
                await client.close()

    @pytest.mark.asyncio
    async def test_find_task_graphs(self):
        mock_ids_response = AsyncMock()
        mock_ids_response.status_code = 200
        mock_ids_response.json.return_value = ["opencode_task_graph_abc"]

        mock_query_response = AsyncMock()
        mock_query_response.status_code = 200
        mock_query_response.json.return_value = [[{"page_content": "graph data"}, 0.1]]

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_ids_response)):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_query_response)):
                client = RagClient(base_url="http://test:8000")
                results = await client.find_task_graphs("my-project")
                assert isinstance(results, list)
                await client.close()
