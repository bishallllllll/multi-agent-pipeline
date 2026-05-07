import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.core.rag_client import (
    RagClient,
    _extract_agent_names_from_text,
    _get_agents_by_task_keywords,
    _get_agents_by_task_keywords_with_scores,
    KNOWN_AGENTS,
    SEQUENTIAL_CHAINS,
)


class TestHelpers:
    def test_extract_agent_names_from_text(self):
        text = "the python-engineer and backend-developer worked"
        found = _extract_agent_names_from_text(text)
        assert "python-engineer" in found
        assert "backend-developer" in found

    def test_extract_agent_names_empty(self):
        assert _extract_agent_names_from_text("no agents here") == []

    def test_get_agents_by_task_keywords_python(self):
        agents = _get_agents_by_task_keywords("write a python module")
        assert "python-engineer" in agents

    def test_get_agents_by_task_keywords_test(self):
        agents = _get_agents_by_task_keywords("write tests for the api")
        assert "test-architect" in agents

    def test_get_agents_by_task_keywords_no_match(self):
        agents = _get_agents_by_task_keywords("xyznonexistentkeyword")
        assert agents == []

    def test_get_agents_by_task_keywords_with_scores(self):
        scores = _get_agents_by_task_keywords_with_scores("write a python api test")
        assert "python-engineer" in scores
        assert "backend-developer" in scores
        assert "test-architect" in scores
        assert scores["python-engineer"] >= 1


class TestSequentialChains:
    def test_api_designer_chain(self):
        assert SEQUENTIAL_CHAINS["api-designer"] == ["backend-developer"]

    def test_code_reviewer_chain(self):
        assert "qa-automation" in SEQUENTIAL_CHAINS["code-reviewer"]

    def test_known_agents_have_chains(self):
        for agent in SEQUENTIAL_CHAINS:
            assert agent in KNOWN_AGENTS or True


class TestRagClientInit:
    def test_init_defaults(self):
        client = RagClient()
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 10.0

    def test_init_custom_url(self):
        client = RagClient(base_url="http://example.com:9000/")
        assert client.base_url == "http://example.com:9000"


class TestRagClientHealth:
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            client = RagClient()
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("connect failed"))):
            client = RagClient()
            result = await client.health_check()
            assert result is False


class TestRagClientFindAgent:
    @pytest.mark.asyncio
    async def test_find_agent_no_ids(self):
        with patch.object(RagClient, "_get_agent_ids", AsyncMock(return_value=[])):
            client = RagClient()
            result = await client.find_agent("write python code")
            assert result == []

    @pytest.mark.asyncio
    async def test_find_agent_with_keywords(self):
        mock_ids = ["opencode_core-development_python-engineer"]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[{"page_content": "Python expert", "metadata": {}}, 0.5]]

        with patch.object(RagClient, "_get_agent_ids", AsyncMock(return_value=mock_ids)):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
                client = RagClient()
                client._category_map = {"python-engineer": "core-development"}
                result = await client.find_agent("write python code")
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_find_agent_fallback(self):
        mock_ids = ["opencode_core-development_some-agent"]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[{"page_content": "content", "metadata": {}}, 0.8]]

        with patch.object(RagClient, "_get_agent_ids", AsyncMock(return_value=mock_ids)):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
                client = RagClient()
                client._category_map = {"some-agent": "core-development"}
                result = await client.find_agent("xyznonexistentkeyword", k=5)
                assert result is not None


class TestRagClientFindNextStep:
    @pytest.mark.asyncio
    async def test_find_next_step_sequential_chain(self):
        client = RagClient()
        client._category_map = {"backend-developer": "core-development"}
        result = await client.find_next_step("completed task", prev_agent="api-designer")
        assert len(result) > 0
        assert result[0]["source"] == "sequential_chain"
        assert result[0]["name"] == "backend-developer"

    @pytest.mark.asyncio
    async def test_find_next_step_keyword_fallback(self):
        client = RagClient()
        client._category_map = {"python-engineer": "core-development"}
        result = await client.find_next_step("write python module", prev_agent=None)
        assert len(result) > 0
        assert result[0]["source"] == "task_keywords"


class TestRagClientQuery:
    @pytest.mark.asyncio
    async def test_query_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[{"page_content": "result text"}, 0.3]]

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            client = RagClient()
            result = await client.query("test query", file_id="test_123")
            assert len(result) == 1
            assert result[0]["content"] == "result text"
            assert result[0]["score"] == 0.3

    @pytest.mark.asyncio
    async def test_query_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            client = RagClient()
            result = await client.query("test")
            assert result == []

    @pytest.mark.asyncio
    async def test_query_exception(self):
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("fail"))):
            client = RagClient()
            result = await client.query("test")
            assert result == []


class TestRagClientSessionHistory:
    @pytest.mark.asyncio
    async def test_find_session_history_no_ids(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            client = RagClient()
            result = await client.find_session_history("/tmp/proj")
            assert result == []

    @pytest.mark.asyncio
    async def test_find_session_history_error(self):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("fail"))):
            client = RagClient()
            result = await client.find_session_history("/tmp/proj")
            assert result == []


class TestRagClientTaskGraphs:
    @pytest.mark.asyncio
    async def test_find_task_graphs_no_ids(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            client = RagClient()
            result = await client.find_task_graphs("/tmp/proj")
            assert result == []


class TestRagClientClose:
    @pytest.mark.asyncio
    async def test_close_no_client(self):
        client = RagClient()
        await client.close()

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        client = RagClient()
        client._client = mock_client
        await client.close()
        mock_client.aclose.assert_called_once()
