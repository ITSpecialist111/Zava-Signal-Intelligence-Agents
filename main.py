"""Zava Signal Analyst — A2A Protocol server entrypoint.

Usage:
    python main.py              # Start the A2A server on port 8080
    python main.py --port 3000  # Custom port
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv


def _patch_span_attributes():
    """Monkey-patch SpanAttributes with LLM_* attrs before agent_framework loads.

    agent-framework-core 1.0.0rc1 references SpanAttributes.LLM_SYSTEM etc.
    from opentelemetry-semantic-conventions, but those attributes live in the
    opentelemetry-semantic-conventions-ai package under a different class.
    We copy them across before any agent_framework imports happen.
    """
    try:
        from opentelemetry.semconv.trace import SpanAttributes
        if hasattr(SpanAttributes, "LLM_SYSTEM"):
            return  # Already available, nothing to patch

        try:
            from opentelemetry.semconv_ai import SpanAttributes as AIAttrs
            for attr in dir(AIAttrs):
                if attr.startswith("LLM_") and not hasattr(SpanAttributes, attr):
                    setattr(SpanAttributes, attr, getattr(AIAttrs, attr))
        except ImportError:
            # Fallback: define the core LLM attributes manually
            _defaults = {
                "LLM_SYSTEM": "gen_ai.system",
                "LLM_REQUEST_MODEL": "gen_ai.request.model",
                "LLM_RESPONSE_MODEL": "gen_ai.response.model",
                "LLM_REQUEST_MAX_TOKENS": "gen_ai.request.max_tokens",
                "LLM_REQUEST_TEMPERATURE": "gen_ai.request.temperature",
                "LLM_REQUEST_TOP_P": "gen_ai.request.top_p",
                "LLM_PROMPTS": "gen_ai.prompt",
                "LLM_COMPLETIONS": "gen_ai.completion",
                "LLM_USAGE_PROMPT_TOKENS": "gen_ai.usage.prompt_tokens",
                "LLM_USAGE_COMPLETION_TOKENS": "gen_ai.usage.completion_tokens",
                "LLM_USAGE_TOTAL_TOKENS": "gen_ai.usage.total_tokens",
            }
            for attr, val in _defaults.items():
                if not hasattr(SpanAttributes, attr):
                    setattr(SpanAttributes, attr, val)
    except ImportError:
        pass  # opentelemetry not installed — agent_framework will handle it


def main():
    # MUST be called before any agent_framework imports
    _patch_span_attributes()

    load_dotenv()

    parser = argparse.ArgumentParser(description="Zava Signal Analyst — A2A Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logger = logging.getLogger("main")

    # Startup banner
    print("=" * 60)
    print("  Zava Signal Analyst — A2A Protocol Server")
    print("=" * 60)
    print(f"  Host:     http://{args.host}:{args.port}")
    print(f"  Health:   http://{args.host}:{args.port}/health")
    print(f"  Card:     http://{args.host}:{args.port}/.well-known/agent.json")
    print(f"  Message:  POST http://{args.host}:{args.port}/")
    print("=" * 60)

    # Agent is created lazily on first request inside _get_chat_agent()
    logger.info("ChatAgent will be created on first request")

    from aiohttp import web
    from src.a2a_server import create_app

    app = create_app()

    logger.info("Starting server on %s:%d", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
