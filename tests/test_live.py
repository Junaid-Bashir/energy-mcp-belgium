import os
import sys
from datetime import UTC, datetime, timedelta
from time import monotonic

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from energy_mcp_belgium.server import create_server


async def test_stdio_registration():
    async with Client(
        StdioServerParameters(command=sys.executable, args=["-m", "energy_mcp_belgium"])
    ) as client:
        assert len((await client.list_tools()).tools) == 8
        result = await client.call_tool(
            "get_load", {"start": "2026-11-01T00:00:00Z", "end": "2026-11-01T00:00:00Z"}
        )
        assert result.is_error


@pytest.mark.live
@pytest.mark.skipif(os.getenv("ENERGY_MCP_LIVE") != "1", reason="Set ENERGY_MCP_LIVE=1")
@pytest.mark.parametrize(
    "tool",
    [
        "get_solar_generation",
        "get_wind_generation",
        "get_load",
        "get_generation_mix",
        "get_system_imbalance",
        "get_imbalance_prices",
    ],
)
async def test_live(tool):
    start = (datetime.now(UTC) - timedelta(days=2)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    args = {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}
    begun = monotonic()
    async with Client(create_server()) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error, result
    body = result.structured_content
    assert body["metadata"]["record_count"] > 0
    assert body["metadata"]["record_count"] == len(body["records"])
    assert body["metadata"]["start"] == start.isoformat().replace("+00:00", "Z")
    assert body["metadata"]["timezone"] == "UTC"
    assert any(v is not None for r in body["records"] for v in r["values"].values())
    print(f"{tool}: {body['metadata']['record_count']} records; {monotonic() - begun:.3f}s; {args}")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("ENERGY_MCP_LIVE") != "1", reason="Set ENERGY_MCP_LIVE=1")
@pytest.mark.parametrize(
    "tool,extra",
    [
        ("get_wind_generation", {"wind_type": "onshore"}),
        ("get_wind_generation", {"wind_type": "offshore"}),
        ("calculate_energy", {"series": "solar"}),
        ("check_data_quality", {"series": "load"}),
    ],
)
async def test_live_variants_and_analytics(tool, extra):
    start = (datetime.now(UTC) - timedelta(days=2)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    args = {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), **extra}
    begun = monotonic()
    async with Client(create_server()) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error, result
    body = result.structured_content
    if tool == "get_wind_generation":
        assert body["metadata"]["record_count"] == 4
        assert all(r["dimensions"]["wind_type"] == extra["wind_type"] for r in body["records"])
        assert all(r["values"]["generation_mw"] is not None for r in body["records"])
    else:
        report = body["quality"] if tool == "calculate_energy" else body
        assert report["expected_intervals"] == 4 and report["status"] == "complete"
        if tool == "calculate_energy":
            assert body["energy_mwh"] is not None and body["covered_hours"] == 1
    print(f"{tool} {extra}: passed; {monotonic() - begun:.3f}s")
