"""Default tests fail immediately if provider HTTP escapes the mocks."""

import os

import httpx
import httpx2
import pytest


@pytest.fixture(autouse=True)
def deny_unmarked_provider_network(request, monkeypatch):
    if request.node.get_closest_marker("live") and os.getenv("ENERGY_MCP_LIVE") == "1":
        return

    async def blocked(*args, **kwargs):
        pytest.fail("Network access requires @pytest.mark.live and ENERGY_MCP_LIVE=1")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", blocked)
