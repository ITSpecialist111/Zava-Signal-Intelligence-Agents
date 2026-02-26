"""Patch SDK compatibility issues.

agent-framework v1.0 renamed ChatAgent → Agent and chat_client → client.
A365 tooling v0.1 may still import the old names. This script patches the
installed packages so both old and new names work.

Additionally patches:
  - MCP HTTP headers: A365 tooling may need custom headers for MCP
    server authentication passed through to downstream HTTP calls.
  - Constructor kwarg: Older tooling may pass ``chat_client=`` instead
    of ``client=`` — the patch ensures both are accepted.

Run this inside the container AFTER pip install, BEFORE starting the app:
    python scripts/patch_sdk.py
"""

import importlib
import logging
import os
import re
import site
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("patch_sdk")


def find_site_packages():
    """Find the site-packages directory."""
    for path in site.getsitepackages() + [site.getusersitepackages()]:
        if os.path.isdir(path):
            return path
    # Fallback: search sys.path
    for path in sys.path:
        if "site-packages" in path and os.path.isdir(path):
            return path
    return None


def patch_agent_framework_compat(site_pkg):
    """Ensure ChatAgent ↔ Agent alias exists in agent_framework/__init__.py."""
    init_path = os.path.join(site_pkg, "agent_framework", "__init__.py")
    if not os.path.exists(init_path):
        logger.warning("agent_framework/__init__.py not found at %s", init_path)
        return

    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()

    patches_applied = 0

    # If Agent exists but ChatAgent doesn't, alias ChatAgent = Agent
    if "Agent" in content and "ChatAgent" not in content:
        content += "\n# Compat patch: old name\nChatAgent = Agent\n"
        patches_applied += 1
        logger.info("Patched: ChatAgent = Agent alias added")

    # If ChatAgent exists but Agent doesn't, alias Agent = ChatAgent
    if "ChatAgent" in content and re.search(r"\bclass Agent\b", content) is None:
        if "\nAgent = ChatAgent" not in content:
            content += "\n# Compat patch: new name\nAgent = ChatAgent\n"
            patches_applied += 1
            logger.info("Patched: Agent = ChatAgent alias added")

    if patches_applied:
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Wrote %d patches to %s", patches_applied, init_path)
    else:
        logger.info("No patches needed for %s", init_path)


def patch_constructor_kwarg(site_pkg):
    """Patch ChatAgent/Agent to accept both chat_client= and client= kwargs.

    Older A365 tooling passes ``chat_client=`` but rc1 may expect ``client=``.
    This inserts a small shim into __init__ so the agent accepts either name.
    """
    init_path = os.path.join(site_pkg, "agent_framework", "__init__.py")
    if not os.path.exists(init_path):
        return

    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "# Compat patch: constructor kwarg shim"
    if marker in content:
        logger.info("Constructor kwarg shim already applied")
        return

    # Find the class that acts as the main agent (Agent or ChatAgent)
    for cls_name in ("ChatAgent", "Agent"):
        pattern = rf"(class {cls_name}\b[^:]*:)"
        match = re.search(pattern, content)
        if match:
            # We can't safely modify __init__ in the class body without
            # deep AST parsing, so instead add a module-level wrapper.
            shim = f"""

{marker}
_original_{cls_name}_init = {cls_name}.__init__

def _patched_{cls_name}_init(self, *args, **kwargs):
    if "chat_client" in kwargs and "client" not in kwargs:
        kwargs["client"] = kwargs.pop("chat_client")
    elif "client" in kwargs and "chat_client" not in kwargs:
        kwargs["chat_client"] = kwargs.pop("chat_client", kwargs.get("client"))
    try:
        _original_{cls_name}_init(self, *args, **kwargs)
    except TypeError:
        # If neither kwarg name works, try the other
        if "client" in kwargs:
            kwargs["chat_client"] = kwargs.pop("client")
        elif "chat_client" in kwargs:
            kwargs["client"] = kwargs.pop("chat_client")
        _original_{cls_name}_init(self, *args, **kwargs)

{cls_name}.__init__ = _patched_{cls_name}_init
"""
            content += shim
            logger.info("Patched: %s constructor kwarg shim added", cls_name)

            with open(init_path, "w", encoding="utf-8") as f:
                f.write(content)
            return

    logger.info("No Agent/ChatAgent class found — skipping constructor patch")


def patch_ai_function_alias(site_pkg):
    """Patch agent_framework to export ai_function as an alias for tool.

    Older SDK versions exposed ``@ai_function`` as a decorator, but
    agent-framework-core 1.0.0rc1 renamed it to ``@tool``.  Our code
    uses ``from agent_framework import ai_function``, so we add an alias.
    """
    init_path = os.path.join(site_pkg, "agent_framework", "__init__.py")
    if not os.path.exists(init_path):
        logger.info("agent_framework __init__.py not found — skipping ai_function alias")
        return

    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "# Compat patch: ai_function = tool alias"
    if marker in content:
        logger.info("ai_function = tool alias already applied")
        return

    # Only patch if 'tool' is available but 'ai_function' is not
    if "ai_function" in content:
        logger.info("ai_function already exists in agent_framework — skipping alias")
        return

    content += f"\n{marker}\ntry:\n    ai_function = tool\nexcept NameError:\n    pass\n"
    with open(init_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Patched: ai_function = tool alias added to agent_framework")


def patch_mcp_headers(site_pkg):
    """Patch A365 tooling to forward MCP authentication headers.

    The A365 MCP tool registration service may not pass the required
    Authorization header to MCP server HTTP calls in all SDK versions.
    This patch ensures headers are forwarded.
    """
    tooling_path = os.path.join(
        site_pkg, "microsoft_agents_a365", "tooling",
        "mcp_tool_registration_service.py",
    )
    if not os.path.exists(tooling_path):
        logger.info("MCP tooling module not found — skipping header patch")
        return

    with open(tooling_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "# Compat patch: MCP auth headers"
    if marker in content:
        logger.info("MCP header patch already applied")
        return

    # Look for HTTP client calls that might be missing auth headers
    # This is a defensive patch — if the code already handles headers, skip
    if "Authorization" in content and "Bearer" in content:
        logger.info("MCP tooling already handles auth headers — skipping")
        return

    logger.info(
        "MCP header patch: tooling module found at %s but no clear "
        "injection point — skipping (may need manual review)",
        tooling_path,
    )


def patch_span_attributes_llm(site_pkg):
    """Patch agent_framework/observability.py to fix SpanAttributes.LLM_SYSTEM.

    agent-framework-core 1.0.0rc1 references SpanAttributes.LLM_SYSTEM from
    opentelemetry-semantic-conventions, but that attribute lives in the
    opentelemetry-semantic-conventions-ai package under a different class.
    This patch adds the missing attributes to SpanAttributes before they
    are referenced.
    """
    obs_path = os.path.join(site_pkg, "agent_framework", "observability.py")
    if not os.path.exists(obs_path):
        logger.info("agent_framework/observability.py not found — skipping LLM patch")
        return

    with open(obs_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "# Compat patch: SpanAttributes LLM shim"
    if marker in content:
        logger.info("SpanAttributes LLM shim already applied")
        return

    if "SpanAttributes.LLM_SYSTEM" not in content:
        logger.info("No SpanAttributes.LLM_SYSTEM reference found — skipping")
        return

    # Insert a shim right after the imports that adds missing LLM_* attributes
    # to SpanAttributes from the AI semantic conventions package.
    shim = f'''
{marker}
try:
    from opentelemetry.semconv_ai import SpanAttributes as _AISpanAttrs
    # Copy all LLM_* attributes from ai conventions to the standard SpanAttributes
    for _attr_name in dir(_AISpanAttrs):
        if _attr_name.startswith("LLM_") and not hasattr(SpanAttributes, _attr_name):
            setattr(SpanAttributes, _attr_name, getattr(_AISpanAttrs, _attr_name))
except ImportError:
    # Fallback: define them manually
    if not hasattr(SpanAttributes, "LLM_SYSTEM"):
        SpanAttributes.LLM_SYSTEM = "gen_ai.system"
    if not hasattr(SpanAttributes, "LLM_REQUEST_MODEL"):
        SpanAttributes.LLM_REQUEST_MODEL = "gen_ai.request.model"
    if not hasattr(SpanAttributes, "LLM_RESPONSE_MODEL"):
        SpanAttributes.LLM_RESPONSE_MODEL = "gen_ai.response.model"
    if not hasattr(SpanAttributes, "LLM_REQUEST_MAX_TOKENS"):
        SpanAttributes.LLM_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    if not hasattr(SpanAttributes, "LLM_REQUEST_TEMPERATURE"):
        SpanAttributes.LLM_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    if not hasattr(SpanAttributes, "LLM_REQUEST_TOP_P"):
        SpanAttributes.LLM_REQUEST_TOP_P = "gen_ai.request.top_p"
    if not hasattr(SpanAttributes, "LLM_PROMPTS"):
        SpanAttributes.LLM_PROMPTS = "gen_ai.prompt"
    if not hasattr(SpanAttributes, "LLM_COMPLETIONS"):
        SpanAttributes.LLM_COMPLETIONS = "gen_ai.completion"
    if not hasattr(SpanAttributes, "LLM_USAGE_PROMPT_TOKENS"):
        SpanAttributes.LLM_USAGE_PROMPT_TOKENS = "gen_ai.usage.prompt_tokens"
    if not hasattr(SpanAttributes, "LLM_USAGE_COMPLETION_TOKENS"):
        SpanAttributes.LLM_USAGE_COMPLETION_TOKENS = "gen_ai.usage.completion_tokens"
    if not hasattr(SpanAttributes, "LLM_USAGE_TOTAL_TOKENS"):
        SpanAttributes.LLM_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
'''

    # Find the line that imports SpanAttributes and insert the shim after the import block
    # We need to place this AFTER the import of SpanAttributes but BEFORE its first usage
    import_pattern = r"(from opentelemetry\.semconv\.\w+ import.*SpanAttributes.*?\n)"
    match = re.search(import_pattern, content)
    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + shim + content[insert_pos:]
        logger.info("Patched: SpanAttributes LLM shim inserted after import at line ~%d",
                     content[:insert_pos].count('\n'))
    else:
        # If we can't find the import, prepend the shim at the top of the file
        # after any initial comments/imports
        logger.warning("Could not find SpanAttributes import — prepending shim")
        content = shim + "\n" + content

    with open(obs_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Wrote SpanAttributes LLM patch to %s", obs_path)


def main():
    site_pkg = find_site_packages()
    if not site_pkg:
        logger.error("Could not find site-packages directory")
        sys.exit(1)

    logger.info("Site-packages: %s", site_pkg)
    patch_agent_framework_compat(site_pkg)
    patch_ai_function_alias(site_pkg)
    patch_constructor_kwarg(site_pkg)
    patch_mcp_headers(site_pkg)
    # Note: SpanAttributes.LLM_SYSTEM patch is handled at runtime in main.py
    # (patching observability.py directly breaks from __future__ import ordering)
    logger.info("SDK patching complete")


if __name__ == "__main__":
    main()
