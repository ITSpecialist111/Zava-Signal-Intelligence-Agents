"""A2A Protocol Server — standalone agent for Copilot Studio.

This is a clean, standalone A2A (Agent-to-Agent) protocol server that
serves the Zava Signal Analyst agent via the A2A protocol.

NO Bot Framework SDK. NO A365 SDK. NO JWT auth middleware.

Routes:
  GET   /                             — health check
  POST  /                             — A2A message handler (primary)
  GET   /.well-known/agent.json       — agent card (standard discovery)
  GET   /.well-known/agent-card.json  — agent card (A2A v1.0)
  POST  /a2a/message:send             — A2A message (alternate path)
  POST  /a2a/message:stream           — A2A message (non-streaming fallback)
  POST  /a2a                          — JSON-RPC binding
  GET   /health                       — health check (explicit)

Copilot Studio posts to the ROOT URL (/) — this server handles that
natively, no auth bypass gymnastics needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from os import environ

from aiohttp import web

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

A2A_AGENT_NAME = "Zava Signal Analyst"
A2A_AGENT_VERSION = "1.0.21"
A2A_PROTOCOL_VERSION = "0.3"

_BASE_URL_ENV = environ.get(
    "A2A_BASE_URL",
    environ.get(
        "WEBSITE_HOSTNAME",
        "localhost:8080",
    ),
)

# ── Agent Card ─────────────────────────────────────────────────────────────


def _build_agent_card(base_url: str) -> dict:
    """Build the A2A AgentCard JSON document."""
    return {
        "name": A2A_AGENT_NAME,
        "description": (
            "UK public sector procurement signal intelligence analyst. "
            "Detects and analyses procurement signals from education trusts "
            "(academy trusts and multi-academy trusts), including structural "
            "stress, compliance trends, competitor movements, procurement "
            "shifts, and leadership changes. Provides sweep triggers, HITL "
            "signal review, reports, and actionable intelligence for the "
            "Zava sales team."
        ),
        "url": f"https://{base_url}/",
        "supportedInterfaces": [
            {
                "url": f"https://{base_url}/",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": A2A_PROTOCOL_VERSION,
            }
        ],
        "provider": {
            "organization": "Zellis",
            "url": "https://www.zellis.com",
        },
        "version": A2A_AGENT_VERSION,
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "query-signals",
                "name": "Query Signals",
                "description": (
                    "Search and filter detected procurement signals by "
                    "category, status, confidence level, trust name, or recency."
                ),
                "tags": ["signals", "procurement", "search", "intelligence"],
                "examples": [
                    "Show me recent signals",
                    "What high-confidence signals do we have?",
                    "List signals for Ark Schools",
                ],
            },
            {
                "id": "run-sweep",
                "name": "Run Signal Sweep",
                "description": (
                    "Trigger the full signal collection pipeline: web crawl, "
                    "procurement scan, enrichment, routing, and storage."
                ),
                "tags": ["sweep", "collection", "crawl", "pipeline"],
                "examples": [
                    "Run a sweep now",
                    "Start signal collection",
                ],
            },
            {
                "id": "generate-reports",
                "name": "Generate Reports",
                "description": (
                    "Produce weekly segment briefs or monthly horizon reports "
                    "analysing signal trends and opportunities."
                ),
                "tags": ["report", "brief", "analysis", "trends"],
                "examples": [
                    "Generate the weekly brief",
                    "Create a monthly horizon report",
                ],
            },
            {
                "id": "hitl-review",
                "name": "HITL Signal Review",
                "description": (
                    "Review signals awaiting human approval, approve or reject "
                    "them, and manage the review queue."
                ),
                "tags": ["review", "approval", "hitl", "human-in-the-loop"],
                "examples": [
                    "Show signals pending review",
                    "Approve signal SIG-001",
                ],
            },
            {
                "id": "dashboard-overview",
                "name": "Dashboard & Overview",
                "description": (
                    "Provide high-level overviews, run history, signal "
                    "statistics, and comparisons between sweep runs."
                ),
                "tags": ["dashboard", "overview", "statistics", "history"],
                "examples": [
                    "Show me the dashboard",
                    "What changed in the last sweep?",
                ],
            },
        ],
    }


# ── Agent factory ─────────────────────────────────────────────────────────
#
# Create a FRESH ChatAgent for every request to avoid conversation-state
# leakage.  The Azure OpenAI Responses API stores conversations server-side
# (STORES_BY_DEFAULT = True in the SDK) and the agent framework propagates
# conversation_id back to the session.  With a singleton agent, the second
# request can inadvertently continue the first request's conversation,
# sending `previous_response_id` which forces the API to replay the full
# prior context — causing extreme latency or silent hangs.
#
# A per-request agent is cheap: the heavy resource (DefaultAzureCredential /
# AsyncOpenAI client) is created once and cached by the Azure SDK.
#
# The _run_lock serialises requests so only one agent.run() call is active
# at a time, preventing concurrent-mutation issues in the SDK internals.

_run_lock = asyncio.Lock()


def _create_chat_agent():
    """Create a fresh ChatAgent instance."""
    from src.agents.interactive_agent import create_interactive_agent

    return create_interactive_agent()


def _extract_response_text(result) -> str:
    """Pull plain-text from whatever agent.run() returns."""
    if not result:
        return ""
    if hasattr(result, "contents"):
        return str(result.contents)
    if hasattr(result, "messages"):
        try:
            from agent_framework._types import TextContent
        except ImportError:
            TextContent = None
        parts: list[str] = []
        for msg in result.messages:
            for content in getattr(msg, "contents", []):
                text = None
                if TextContent and isinstance(content, TextContent):
                    text = content.text
                elif hasattr(content, "text"):
                    text = content.text
                if text:
                    parts.append(text)
        return "\n\n".join(parts) if parts else str(result)
    if hasattr(result, "text"):
        return str(result.text)
    if hasattr(result, "content"):
        return str(result.content)
    return str(result)


# ── Request parsing ───────────────────────────────────────────────────────


def _extract_user_text(body: dict) -> str:
    """Extract user text from an A2A message body.

    Supports Copilot Studio format, A2A v0.3 and v1.0::

        { "message": { "parts": [{ "text": "..." }] } }
        { "message": { "parts": [{ "kind": "text", "text": "..." }] } }

    Also handles the conversation-history wrapper that Copilot Studio sends::

        { "history": [{ "role": "user", "parts": [...] }] }
    """
    # Handle Copilot Studio conversation-history format
    history = body.get("history")
    if history and isinstance(history, list):
        # Find the last user message in history
        for entry in reversed(history):
            if entry.get("role") == "user":
                parts = entry.get("parts", [])
                texts = []
                for part in parts:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if text:
                            texts.append(text)
                if texts:
                    return "\n".join(texts)

    # Standard A2A message format
    message = body.get("message", body)
    parts = message.get("parts", [])
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts) if texts else ""


def _build_response_message(
    text: str,
    context_id: str | None = None,
    message_id: str | None = None,
) -> dict:
    """Build an A2A v0.3 Message response."""
    return {
        "kind": "message",
        "role": "agent",
        "parts": [
            {
                "kind": "text",
                "text": text,
            }
        ],
        "messageId": message_id or str(uuid.uuid4()),
        "contextId": context_id or str(uuid.uuid4()),
    }


def _build_task_result(
    text: str,
    context_id: str | None = None,
) -> dict:
    """Build a full A2A Task result with artifact for Copilot Studio.

    Copilot Studio's A2A connector expects a Task object in the result,
    with the agent's reply in ``artifacts`` and the final status set
    to ``completed``.  Without this envelope the orchestrator sees an
    empty observation and generates a generic summary.
    """
    task_id = str(uuid.uuid4())
    ctx_id = context_id or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    # Copilot Studio concatenates text from *all* populated fields
    # (artifacts + history, or status.message + history, etc.).
    # To prevent duplication keep the text in ONE location only —
    # ``history`` — which is what the orchestrator reads as the
    # observation.  ``status`` carries only the state flag and
    # ``artifacts`` is left empty.
    return {
        "id": task_id,
        "contextId": ctx_id,
        "status": {
            "state": "completed",
        },
        "artifacts": [],
        "history": [
            {
                "kind": "message",
                "role": "agent",
                "parts": [{"kind": "text", "text": text}],
                "messageId": msg_id,
                "contextId": ctx_id,
            }
        ],
    }


# ── SSE streaming ─────────────────────────────────────────────────────────


async def _handle_streaming_response(
    request: web.Request,
    user_text: str,
    context_id: str | None = None,
    rpc_id: str | int | None = None,
) -> web.StreamResponse:
    """Stream SSE events back to the caller (Copilot Studio / A2A client).

    Event flow:
      1. Immediate ``working`` status — tells the client we've started.
      2. Heartbeat every 10 s — keeps the connection alive.
      3. ``completed`` with the agent reply — the final answer.
      4. ``done`` sentinel — signals end of stream.
    """
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await resp.prepare(request)

    task_id = str(uuid.uuid4())
    ctx_id = context_id or str(uuid.uuid4())

    # -- helpers -----------------------------------------------------------

    async def _send_sse(data: dict, event: str = "message/stream") -> None:
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        await resp.write(payload.encode("utf-8"))

    def _wrap(body: dict) -> dict:
        if rpc_id is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "result": body}
        return body

    def _status_update(state: str, text: str | None = None) -> dict:
        status: dict = {"state": state}
        if text:
            status["message"] = {
                "role": "agent",
                "parts": [{"kind": "text", "text": text}],
            }
        return _wrap({"id": task_id, "contextId": ctx_id, "status": status})

    # 1) Acknowledge immediately
    await _send_sse(_status_update("working", "\u23f3 Processing your request\u2026"))
    logger.info("SSE stream opened \u2014 task %s, user: %s", task_id, user_text[:80])

    # 2) Run the agent in a background coroutine
    async def _do_agent() -> str:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with _run_lock:
                    agent = _create_chat_agent()
                    result = await asyncio.wait_for(
                        agent.run(user_text, store=False), timeout=120,
                    )
                return _extract_response_text(result) or "Done."
            except Exception as exc:
                err_str = str(exc)
                is_rate_limited = (
                    "429" in err_str or "too_many_requests" in err_str.lower()
                )
                if is_rate_limited and attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "SSE: 429 (attempt %d/%d) \u2014 retry in %ds",
                        attempt, max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        return "Done."  # unreachable but keeps linters happy

    agent_task = asyncio.create_task(_do_agent())

    # 3) Heartbeat every 10 s while the agent works
    heartbeat_n = 0
    while not agent_task.done():
        done, _ = await asyncio.wait({agent_task}, timeout=10)
        if not done:
            heartbeat_n += 1
            await _send_sse(
                _status_update(
                    "working",
                    f"\u23f3 Still working\u2026 ({heartbeat_n * 10}s elapsed)",
                )
            )

    # 4) Final result or error
    t_elapsed = heartbeat_n * 10  # approximate seconds
    try:
        response_text = agent_task.result()
        final = _build_task_result(response_text, context_id=ctx_id)
        final["id"] = task_id
        await _send_sse(_wrap(final))
        logger.info(
            "SSE completed \u2014 %d chars, ~%ds", len(response_text), t_elapsed,
        )
    except asyncio.TimeoutError:
        await _send_sse(
            _status_update("failed", "\u23f3 The request timed out. Please try again.")
        )
    except Exception as exc:
        err_str = str(exc)
        is_rl = "429" in err_str or "too_many_requests" in err_str.lower()
        msg = (
            "\u23f3 Azure OpenAI is temporarily rate-limited. Please wait and try again."
            if is_rl
            else "\u274c Sorry, something went wrong. Please try again."
        )
        logger.error("SSE agent error: %s", exc, exc_info=True)
        await _send_sse(_status_update("failed", msg))

    # 5) Close the stream
    await _send_sse({}, "done")
    await resp.write_eof()
    return resp


async def handle_message_stream(request: web.Request) -> web.StreamResponse:
    """POST /a2a/message:stream \u2014 A2A streaming message handler."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception) as exc:
        return web.json_response(
            {
                "type": "https://a2a-protocol.org/errors/invalid-request",
                "title": "Invalid Request",
                "status": 400,
                "detail": f"Invalid JSON body: {exc}",
            },
            status=400,
        )

    user_text = _extract_user_text(body)
    if not user_text:
        return web.json_response(
            {
                "type": "https://a2a-protocol.org/errors/invalid-request",
                "title": "No text",
                "status": 400,
                "detail": "No text parts found in message.",
            },
            status=400,
        )

    message = body.get("message", body)
    context_id = message.get("contextId")
    logger.info("A2A stream request \u2014 user: %s", user_text[:120])
    return await _handle_streaming_response(request, user_text, context_id)


# ── Route handlers ────────────────────────────────────────────────────────


async def handle_health(request: web.Request) -> web.Response:
    """GET / or /health — health check."""
    return web.json_response(
        {
            "status": "ok",
            "agent": A2A_AGENT_NAME,
            "version": A2A_AGENT_VERSION,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def handle_agent_card(request: web.Request) -> web.Response:
    """GET /.well-known/agent.json or /.well-known/agent-card.json"""
    host = _BASE_URL_ENV
    req_host = request.headers.get("X-Forwarded-Host") or request.host
    if req_host and "localhost" not in req_host:
        host = req_host.split(":")[0]

    card = _build_agent_card(host)
    return web.json_response(card, headers={"Access-Control-Allow-Origin": "*"})


async def handle_root(request: web.Request) -> web.Response:
    """Handle requests to / — routes GET to health, POST to message handler."""
    if request.method == "GET":
        return await handle_health(request)
    # POST / — this is what Copilot Studio sends
    return await handle_message_send(request)


async def handle_message_send(request: web.Request) -> web.Response:
    """POST /a2a/message:send or POST / — A2A message handler."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("A2A: invalid JSON body: %s", exc)
        return web.json_response(
            {
                "type": "https://a2a-protocol.org/errors/invalid-request",
                "title": "Invalid Request",
                "status": 400,
                "detail": f"Invalid JSON body: {exc}",
            },
            status=400,
        )

    logger.info("A2A request body keys: %s", list(body.keys()))

    # Copilot Studio may send JSON-RPC to POST / — delegate to JSON-RPC handler
    if "jsonrpc" in body and "method" in body:
        logger.info("A2A: detected JSON-RPC envelope at POST /, delegating")
        return await handle_jsonrpc(request)

    user_text = _extract_user_text(body)
    if not user_text:
        logger.warning("A2A: no text found in body: %s", json.dumps(body)[:500])
        return web.json_response(
            {
                "type": "https://a2a-protocol.org/errors/invalid-request",
                "title": "Invalid Request",
                "status": 400,
                "detail": "No text parts found in message.",
            },
            status=400,
        )

    # Extract context for multi-turn
    message = body.get("message", body)
    context_id = message.get("contextId")

    logger.info("A2A message — user: %s (ctx=%s)", user_text[:120], context_id)

    # Retry loop — Azure OpenAI can return 429 (Too Many Requests) under
    # rate-limit pressure.  We retry up to 3 times with exponential back-off
    # (2 s → 4 s → 8 s) before surfacing a proper 429 to the caller.
    max_retries = 3
    response_text: str | None = None
    t0 = time.monotonic()

    for attempt in range(1, max_retries + 1):
        try:
            async with _run_lock:
                agent = _create_chat_agent()
                result = await asyncio.wait_for(
                    agent.run(user_text, store=False), timeout=120,
                )
            response_text = _extract_response_text(result) or "Done."
            break  # success — exit retry loop

        except asyncio.TimeoutError:
            logger.error("A2A: agent.run() timed out after 120s")
            return web.json_response(
                {
                    "type": "https://a2a-protocol.org/errors/internal-error",
                    "title": "Timeout",
                    "status": 504,
                    "detail": "Agent processing timed out after 120 seconds.",
                },
                status=504,
            )

        except Exception as exc:
            err_str = str(exc)
            is_rate_limited = "429" in err_str or "too_many_requests" in err_str.lower()

            if is_rate_limited and attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(
                    "A2A: 429 rate-limited (attempt %d/%d) — retrying in %ds",
                    attempt, max_retries, wait,
                )
                await asyncio.sleep(wait)
                continue

            if is_rate_limited:
                logger.error(
                    "A2A: 429 rate-limited — exhausted %d retries", max_retries,
                )
                error_msg = (
                    "⏳ Azure OpenAI is temporarily rate-limited. "
                    "Please wait a moment and try again."
                )
                response = _build_response_message(
                    error_msg, context_id=context_id,
                )
                return web.json_response(
                    response,
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*"},
                )

            # Non-rate-limit error — fail immediately
            logger.error("A2A: agent.run() error: %s", exc, exc_info=True)
            error_msg = (
                "❌ Sorry, something went wrong processing your request. "
                "Please try again in a moment."
            )
            response = _build_response_message(
                error_msg, context_id=context_id,
            )
            return web.json_response(
                response,
                status=200,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    response = _build_response_message(response_text, context_id=context_id)
    elapsed = time.monotonic() - t0
    logger.info("A2A response: %d chars in %.1fs", len(response_text), elapsed)
    return web.json_response(response, headers={"Access-Control-Allow-Origin": "*"})


async def handle_jsonrpc(request: web.Request) -> web.Response:
    """POST /a2a — JSON-RPC 2.0 binding."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception) as exc:
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            },
            status=400,
        )

    method = body.get("method", "")
    rpc_id = body.get("id")
    params = body.get("params", {})

    # ── Streaming path ──────────────────────────────────────────────────
    if method in ("SendStreamingMessage", "message/stream"):
        user_text = _extract_user_text(params)
        if not user_text:
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": -32602,
                        "message": "No text parts found in message",
                    },
                },
                status=400,
            )
        message = params.get("message", params)
        context_id = message.get("contextId")
        logger.info(
            "A2A JSON-RPC %s (streaming) \u2014 %s (ctx=%s)",
            method, user_text[:100], context_id,
        )
        return await _handle_streaming_response(
            request, user_text, context_id, rpc_id=rpc_id,
        )

    # ── Non-streaming path ────────────────────────────────────────────────
    if method in ("SendMessage", "message/send"):
        user_text = _extract_user_text(params)
        if not user_text:
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": -32602,
                        "message": "No text parts found in message",
                    },
                },
                status=400,
            )

        message = params.get("message", params)
        context_id = message.get("contextId")

        logger.info("A2A JSON-RPC %s — %s (ctx=%s)", method, user_text[:100], context_id)

        # Retry loop — same logic as handle_message_send
        max_retries = 3
        response_text: str | None = None
        t0 = time.monotonic()

        for attempt in range(1, max_retries + 1):
            try:
                async with _run_lock:
                    agent = _create_chat_agent()
                    result = await asyncio.wait_for(
                        agent.run(user_text, store=False), timeout=120,
                    )
                response_text = _extract_response_text(result) or "Done."
                break  # success

            except asyncio.TimeoutError:
                logger.error("A2A JSON-RPC: agent.run() timed out")
                error_result = _build_task_result(
                    "⏳ The request timed out. Please try again.",
                    context_id=context_id,
                )
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": error_result,
                    },
                )

            except Exception as exc:
                err_str = str(exc)
                is_rate_limited = (
                    "429" in err_str
                    or "too_many_requests" in err_str.lower()
                )

                if is_rate_limited and attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "A2A JSON-RPC: 429 (attempt %d/%d) — retry in %ds",
                        attempt, max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                if is_rate_limited:
                    logger.error(
                        "A2A JSON-RPC: 429 — exhausted %d retries",
                        max_retries,
                    )
                    error_result = _build_task_result(
                        "⏳ Azure OpenAI is temporarily rate-limited. "
                        "Please wait a moment and try again.",
                        context_id=context_id,
                    )
                    return web.json_response(
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": error_result,
                        },
                    )

                # Non-rate-limit error — fail immediately
                logger.error(
                    "A2A JSON-RPC: agent error: %s", exc, exc_info=True,
                )
                error_result = _build_task_result(
                    "❌ Sorry, something went wrong processing your "
                    "request. Please try again in a moment.",
                    context_id=context_id,
                )
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": error_result,
                    },
                )

        task_result = _build_task_result(
            response_text, context_id=context_id
        )
        rpc_response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": task_result,
        }
        elapsed = time.monotonic() - t0
        logger.info(
            "A2A JSON-RPC response: %d chars in %.1fs, task status=%s",
            len(response_text),
            elapsed,
            task_result.get("status", {}).get("state", "?"),
        )
        return web.json_response(rpc_response)

    if method in ("GetExtendedAgentCard", "getAgentCard"):
        host = _BASE_URL_ENV
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": _build_agent_card(host),
            }
        )

    # If it has a "message" key but no "method", treat as direct A2A message
    if "message" in body or "history" in body:
        return await handle_message_send(request)

    return web.json_response(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        },
        status=400,
    )


async def handle_options(request: web.Request) -> web.Response:
    """Handle CORS preflight for any endpoint."""
    return web.Response(
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, Authorization, A2A-Version, A2A-Extensions"
            ),
            "Access-Control-Max-Age": "86400",
        },
    )


# ── App factory ───────────────────────────────────────────────────────────


def create_app() -> web.Application:
    """Create the aiohttp Application with all A2A routes."""
    app = web.Application()

    # -- routes -------------------------------------------------------------

    # Root — GET for health, POST for A2A messages
    app.router.add_get("/", handle_health)
    app.router.add_post("/", handle_message_send)

    # Agent card discovery
    app.router.add_get("/.well-known/agent.json", handle_agent_card)
    app.router.add_get("/.well-known/agent-card.json", handle_agent_card)

    # Explicit health endpoints
    app.router.add_get("/health", handle_health)
    app.router.add_get("/liveness", handle_health)
    app.router.add_get("/readiness", handle_health)

    # A2A explicit paths (alternate to /)
    app.router.add_post("/a2a/message:send", handle_message_send)
    app.router.add_post("/a2a/message:stream", handle_message_stream)
    app.router.add_post("/a2a", handle_jsonrpc)

    # CORS preflight
    app.router.add_route("OPTIONS", "/{path:.*}", handle_options)

    # -- scheduled sweep background task -----------------------------------
    from src.workflows.scheduled_sweep import (
        start_scheduled_sweep,
        stop_scheduled_sweep,
    )

    app.on_startup.append(start_scheduled_sweep)
    app.on_cleanup.append(stop_scheduled_sweep)

    logger.info("A2A app created — agent: %s", A2A_AGENT_NAME)
    return app
