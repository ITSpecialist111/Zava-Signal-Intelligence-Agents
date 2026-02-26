"""Browser Automation tool — POC using direct Playwright.

For the POC phase we bypass Azure AI Foundry Browser Automation
(which needs a full Playwright Testing workspace provisioned in
the Azure subscription) and use local Playwright instead.

Upgrade path:
  local Playwright (now)
  → Azure Playwright Testing workspace (next)
  → Foundry Agent Service BrowserAutomationTool (production)

Ref (future): https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/browser-automation
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# JavaScript executed inside Playwright to extract article content from pages.
# Kept as a raw string to avoid Python/JS escape conflicts.
_EXTRACT_JS = r"""() => {
    var REMOVE = ['nav','footer','aside','header','.ad','.ads','.advertisement',
        '.cookie-banner','.cookie-consent','.sidebar','.menu','.navigation',
        '#cookie','.social-share','.comments','script','style','noscript','iframe'];
    REMOVE.forEach(function(s){ document.querySelectorAll(s).forEach(function(el){ el.remove(); }); });

    var ARTICLE = ['article','main','[role=main]','.post-content','.article-content',
        '.entry-content','.story','.news-item','.post'];
    for (var i = 0; i < ARTICLE.length; i++) {
        var els = document.querySelectorAll(ARTICLE[i]);
        if (els.length > 0) {
            var texts = [];
            els.forEach(function(el){ var t = el.innerText.trim(); if (t.length > 50) texts.push(t); });
            if (texts.length > 0) return texts.join('\n\n---\n\n');
        }
    }

    var blocks = [];
    document.querySelectorAll('h1,h2,h3,h4').forEach(function(h){
        var text = h.innerText.trim();
        var sib = h.nextElementSibling;
        while (sib && ['H1','H2','H3','H4'].indexOf(sib.tagName) === -1) {
            if (sib.innerText && sib.innerText.trim().length > 20) text += '\n' + sib.innerText.trim();
            sib = sib.nextElementSibling;
        }
        if (text.length > 30) blocks.push(text);
    });
    if (blocks.length > 0) return blocks.join('\n\n---\n\n');

    return document.body.innerText;
}"""


class BrowserAutomationWrapper:
    """Wraps either local Playwright or Azure Foundry Browser Automation.

    POC mode (PLAYWRIGHT_MODE=local):
        Uses playwright directly — ``pip install playwright``
        then ``playwright install chromium``.

    Azure mode (future):
        Uses Foundry Agent Service's BrowserAutomationTool with a
        Microsoft Playwright Testing workspace.
    """

    def __init__(
        self,
        project_endpoint: str | None = None,
        model_deployment: str | None = None,
        playwright_mode: str | None = None,
    ):
        self.project_endpoint = project_endpoint or os.environ.get(
            "AZURE_AI_PROJECT_ENDPOINT", ""
        )
        self.model_deployment = model_deployment or os.environ.get(
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o"
        )
        self.mode = playwright_mode or os.environ.get("PLAYWRIGHT_MODE", "local")

    # --------------------------------------------------------------------- #
    # Public API (same interface regardless of mode)
    # --------------------------------------------------------------------- #

    async def navigate_and_extract(
        self,
        url: str,
        task_description: str,
        additional_instructions: str = "",
    ) -> dict[str, Any]:
        """Navigate to a URL and extract page content.

        In POC mode this fetches the page HTML with Playwright and
        returns the text content. In production mode the Foundry
        Agent Service's Browser Automation tool handles DOM parsing
        and multi-turn reasoning.
        """
        if self.mode == "local":
            return await self._local_extract(url, task_description)
        return await self._azure_extract(url, task_description, additional_instructions)

    async def scan_for_signals(
        self,
        url: str,
        signal_types: list[str],
    ) -> dict[str, Any]:
        """Scan a page for specific signal types."""
        signal_descriptions = ", ".join(signal_types)
        return await self.navigate_and_extract(
            url=url,
            task_description=(
                f"Scan this page for the following types of signals: {signal_descriptions}. "
                "For each signal found, extract: the entity name (trust/MAT), "
                "the specific evidence text, what type of signal it is, and your "
                "confidence (high/medium/low) that this is a genuine signal. "
                "Return results as a structured list."
            ),
        )

    # --------------------------------------------------------------------- #
    # POC — local Playwright
    # --------------------------------------------------------------------- #

    async def _local_extract(
        self, url: str, task_description: str
    ) -> dict[str, Any]:
        """Use local Playwright to fetch and return page text."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            return {
                "status": "error",
                "url": url,
                "content": "",
                "error": "playwright not installed",
            }

        logger.info("Playwright (local): navigating to %s", url)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

                # Extract the main text content, focusing on articles
                text_content = await page.evaluate(_EXTRACT_JS)

                # Also grab the page title
                title = await page.title()

                await browser.close()

            # Truncate to avoid overwhelming the LLM downstream
            max_chars = 15_000
            if len(text_content) > max_chars:
                text_content = text_content[:max_chars] + "\n\n[…truncated]"

            return {
                "status": "success",
                "url": url,
                "title": title,
                "content": text_content,
                "mode": "local_playwright",
            }

        except Exception as e:
            logger.error("Playwright (local) failed for %s: %s", url, e)
            return {
                "status": "error",
                "url": url,
                "content": "",
                "error": str(e),
            }

    # --------------------------------------------------------------------- #
    # Azure Foundry Browser Automation (future upgrade)
    # --------------------------------------------------------------------- #

    async def _azure_extract(
        self,
        url: str,
        task_description: str,
        additional_instructions: str = "",
    ) -> dict[str, Any]:
        """Use Azure Foundry Agent Service Browser Automation tool.

        Requires:
        - Azure AI Foundry project
        - Microsoft Playwright Testing workspace provisioned
        - azure-ai-agents>=1.2.0b2 installed
        """
        try:
            from azure.ai.agents import AgentsClient
            from azure.ai.agents.models import BrowserAutomationTool
            from azure.identity import DefaultAzureCredential
        except ImportError:
            logger.error("azure-ai-agents not installed for Azure mode")
            return {
                "status": "error",
                "url": url,
                "content": "",
                "error": "azure-ai-agents not installed",
            }

        logger.info("Browser Automation (Azure): navigating to %s — %s", url, task_description)

        credential = DefaultAzureCredential()
        client = AgentsClient(
            endpoint=self.project_endpoint,
            credential=credential,
        )

        connection_name = os.environ.get("AZURE_PLAYWRIGHT_CONNECTION_NAME", "")
        browser_tool = BrowserAutomationTool(connection_id=connection_name)

        agent = client.create_agent(
            model=self.model_deployment,
            name="signal-browser-agent",
            instructions=(
                "You are a web research assistant for Zava Market Intelligence. "
                "Your job is to navigate public-sector education websites and extract "
                "specific information about academy trusts, MATs, and leadership changes. "
                "Be thorough but concise. Extract structured data when possible. "
                f"{additional_instructions}"
            ),
            tools=[browser_tool],
        )

        try:
            thread = client.create_thread()
            client.create_message(
                thread_id=thread.id,
                role="user",
                content=f"Navigate to {url} and {task_description}",
            )

            run = client.create_and_process_run(
                thread_id=thread.id,
                agent_id=agent.id,
            )

            messages = client.list_messages(thread_id=thread.id)
            assistant_messages = [
                m for m in messages.data if m.role == "assistant"
            ]

            extracted_content = ""
            if assistant_messages:
                last_msg = assistant_messages[0]
                for block in last_msg.content:
                    if hasattr(block, "text"):
                        extracted_content += block.text.value

            return {
                "status": "success",
                "url": url,
                "content": extracted_content,
                "run_status": run.status,
                "mode": "azure_browser_automation",
            }

        except Exception as e:
            logger.error("Browser Automation (Azure) failed for %s: %s", url, e)
            return {
                "status": "error",
                "url": url,
                "content": "",
                "error": str(e),
            }
        finally:
            try:
                client.delete_agent(agent.id)
            except Exception:
                pass
