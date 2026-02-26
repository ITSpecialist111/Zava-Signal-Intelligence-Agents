"""Unit tests for BrowserAutomationWrapper."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.tools.browser_automation import BrowserAutomationWrapper


class TestBrowserAutomationWrapper:

    def test_default_mode_is_local(self):
        with patch.dict(os.environ, {}, clear=True):
            wrapper = BrowserAutomationWrapper()
        assert wrapper.mode == "local"

    def test_mode_from_constructor(self):
        wrapper = BrowserAutomationWrapper(playwright_mode="azure")
        assert wrapper.mode == "azure"

    def test_mode_from_env(self):
        with patch.dict(os.environ, {"PLAYWRIGHT_MODE": "azure"}, clear=True):
            wrapper = BrowserAutomationWrapper()
        assert wrapper.mode == "azure"

    def test_project_endpoint_from_constructor(self):
        wrapper = BrowserAutomationWrapper(project_endpoint="https://my-project.azure.com")
        assert wrapper.project_endpoint == "https://my-project.azure.com"

    def test_model_deployment_from_constructor(self):
        wrapper = BrowserAutomationWrapper(model_deployment="gpt-4o-mini")
        assert wrapper.model_deployment == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_local_extract_returns_content(self):
        """Integration test — requires Playwright chromium installed."""
        wrapper = BrowserAutomationWrapper(playwright_mode="local")
        # Use a simple data URI to avoid network dependency
        result = await wrapper._local_extract(
            url="data:text/html,<html><body><p>Hello Test</p></body></html>",
            task_description="Extract text.",
        )
        assert result["status"] == "success"
        assert "Hello Test" in result["content"]
        assert result["mode"] == "local_playwright"

    @pytest.mark.asyncio
    async def test_scan_for_signals_delegates_to_navigate(self):
        """scan_for_signals should call navigate_and_extract."""
        wrapper = BrowserAutomationWrapper(playwright_mode="local")
        result = await wrapper.scan_for_signals(
            url="data:text/html,<html><body><p>Signal test</p></body></html>",
            signal_types=["STRUCTURAL_STRESS"],
        )
        assert result["status"] == "success"
        assert "Signal test" in result["content"]
