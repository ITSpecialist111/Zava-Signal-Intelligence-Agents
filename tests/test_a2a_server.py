"""Tests for the standalone A2A server."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.a2a_server import (
    A2A_AGENT_NAME,
    A2A_AGENT_VERSION,
    _build_agent_card,
    _build_response_message,
    _extract_response_text,
    _extract_user_text,
    create_app,
)


# ── Unit tests for helpers ────────────────────────────────────────────────


class TestBuildAgentCard:
    def test_card_structure(self):
        card = _build_agent_card("example.com")
        assert card["name"] == A2A_AGENT_NAME
        assert card["version"] == A2A_AGENT_VERSION
        assert "https://example.com/" in card["url"]
        assert len(card["skills"]) == 5

    def test_card_url(self):
        card = _build_agent_card("my-host.azurecontainerapps.io")
        assert card["supportedInterfaces"][0]["url"] == (
            "https://my-host.azurecontainerapps.io/"
        )

    def test_card_has_required_fields(self):
        card = _build_agent_card("host")
        for field in ("name", "description", "url", "supportedInterfaces",
                       "capabilities", "skills"):
            assert field in card


class TestExtractUserText:
    def test_standard_message(self):
        body = {"message": {"role": "user", "parts": [{"text": "hello"}]}}
        assert _extract_user_text(body) == "hello"

    def test_message_with_kind(self):
        body = {"message": {"parts": [{"kind": "text", "text": "hi there"}]}}
        assert _extract_user_text(body) == "hi there"

    def test_bare_message(self):
        body = {"parts": [{"text": "bare"}]}
        assert _extract_user_text(body) == "bare"

    def test_empty_parts(self):
        body = {"message": {"parts": []}}
        assert _extract_user_text(body) == ""

    def test_no_parts(self):
        body = {"message": {}}
        assert _extract_user_text(body) == ""

    def test_multiple_parts(self):
        body = {"message": {"parts": [{"text": "a"}, {"text": "b"}]}}
        assert _extract_user_text(body) == "a\nb"

    def test_copilot_studio_history_format(self):
        """Copilot Studio sends conversation history with role/parts."""
        body = {
            "history": [
                {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Show signals"}],
                    "messageId": "abc-123",
                    "contextId": "ctx-456",
                    "kind": "message",
                }
            ]
        }
        assert _extract_user_text(body) == "Show signals"

    def test_copilot_studio_multi_turn_history(self):
        """Multiple messages in history — picks the last user message."""
        body = {
            "history": [
                {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "First question"}],
                },
                {
                    "role": "agent",
                    "parts": [{"kind": "text", "text": "Response"}],
                },
                {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Follow-up question"}],
                },
            ]
        }
        assert _extract_user_text(body) == "Follow-up question"


class TestBuildResponseMessage:
    def test_basic(self):
        msg = _build_response_message("hello")
        assert msg["role"] == "agent"
        assert msg["kind"] == "message"
        assert msg["parts"][0]["text"] == "hello"
        assert msg["parts"][0]["kind"] == "text"
        assert "messageId" in msg
        assert "contextId" in msg

    def test_custom_ids(self):
        msg = _build_response_message("x", context_id="ctx", message_id="msg")
        assert msg["contextId"] == "ctx"
        assert msg["messageId"] == "msg"


class TestExtractResponseText:
    def test_none(self):
        assert _extract_response_text(None) == ""

    def test_text_attr(self):
        r = MagicMock(spec=["text"])
        r.text = "hello"
        assert _extract_response_text(r) == "hello"

    def test_content_attr(self):
        r = MagicMock(spec=["content"])
        r.content = "world"
        assert _extract_response_text(r) == "world"

    def test_str_fallback(self):
        assert _extract_response_text(42) == "42"


# ── Integration tests with aiohttp test client ───────────────────────────


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(aiohttp_client, app):
    return await aiohttp_client(app)


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_get_root(self, client):
        resp = await client.get("/")
        assert resp.status == 200
        data = await resp.json()
        assert data["agent"] == A2A_AGENT_NAME
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_health(self, client):
        resp = await client.get("/health")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_get_liveness(self, client):
        resp = await client.get("/liveness")
        assert resp.status == 200


class TestAgentCard:
    @pytest.mark.asyncio
    async def test_well_known_agent_json(self, client):
        resp = await client.get("/.well-known/agent.json")
        assert resp.status == 200
        data = await resp.json()
        assert data["name"] == A2A_AGENT_NAME
        assert len(data["skills"]) == 5

    @pytest.mark.asyncio
    async def test_well_known_agent_card_json(self, client):
        resp = await client.get("/.well-known/agent-card.json")
        assert resp.status == 200
        data = await resp.json()
        assert data["name"] == A2A_AGENT_NAME


class TestMessageSend:
    @pytest.mark.asyncio
    async def test_post_root_with_message(self, client):
        """POST / with standard A2A message."""
        with patch("src.a2a_server._get_chat_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_result = MagicMock(spec=[])  # no extra attrs
            mock_result.text = "Signal analysis complete"
            mock_agent.run.return_value = mock_result
            mock_get.return_value = mock_agent

            resp = await client.post(
                "/",
                json={"message": {"role": "user", "parts": [{"text": "show signals"}]}},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["role"] == "agent"
            assert "Signal analysis" in data["parts"][0]["text"]

    @pytest.mark.asyncio
    async def test_post_root_with_copilot_studio_history(self, client):
        """POST / with Copilot Studio's conversation history format."""
        with patch("src.a2a_server._get_chat_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_result = MagicMock()
            mock_result.text = "Here are the signals"
            mock_agent.run.return_value = mock_result
            mock_get.return_value = mock_agent

            body = {
                "history": [
                    {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Show HIGH signals"}],
                        "messageId": "e5f20fbd-c5aa-1c43-bd9a-ca2175003ecb",
                        "contextId": "60636ce2-d7cb-4e72-9618-e3b0dd790db2",
                        "kind": "message",
                    }
                ]
            }
            resp = await client.post("/", json=body)
            assert resp.status == 200
            data = await resp.json()
            assert data["role"] == "agent"
            mock_agent.run.assert_called_once_with("Show HIGH signals")

    @pytest.mark.asyncio
    async def test_post_a2a_message_send(self, client):
        """POST /a2a/message:send works too."""
        with patch("src.a2a_server._get_chat_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_result = MagicMock()
            mock_result.text = "Done"
            mock_agent.run.return_value = mock_result
            mock_get.return_value = mock_agent

            resp = await client.post(
                "/a2a/message:send",
                json={"message": {"parts": [{"text": "run sweep"}]}},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_invalid_json(self, client):
        resp = await client.post(
            "/",
            data=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_empty_message(self, client):
        resp = await client.post("/", json={"message": {"parts": []}})
        assert resp.status == 400


class TestCORS:
    @pytest.mark.asyncio
    async def test_options_root(self, client):
        resp = await client.options("/")
        assert resp.status == 204
        assert "Access-Control-Allow-Origin" in resp.headers

    @pytest.mark.asyncio
    async def test_options_a2a(self, client):
        resp = await client.options("/a2a/message:send")
        assert resp.status == 204

    @pytest.mark.asyncio
    async def test_cors_headers_on_response(self, client):
        resp = await client.get("/")
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"


class TestJsonRpc:
    @pytest.mark.asyncio
    async def test_get_agent_card_rpc(self, client):
        resp = await client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "GetExtendedAgentCard",
                "params": {},
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["result"]["name"] == A2A_AGENT_NAME

    @pytest.mark.asyncio
    async def test_unknown_method(self, client):
        resp = await client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "UnknownMethod",
                "params": {},
            },
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_jsonrpc_with_history_fallback(self, client):
        """POST /a2a with history key (no method) falls through to message handler."""
        with patch("src.a2a_server._get_chat_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_result = MagicMock()
            mock_result.text = "Processed"
            mock_agent.run.return_value = mock_result
            mock_get.return_value = mock_agent

            body = {
                "history": [
                    {"role": "user", "parts": [{"text": "hello"}]}
                ]
            }
            resp = await client.post("/a2a", json=body)
            assert resp.status == 200
