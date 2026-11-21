"""Product-level analytics and failure scenarios through the official MCP client."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp import Client

from energy_mcp_belgium.server import create_server

START = datetime(2026, 11, 17, 12, tzinfo=UTC)


def rows(start, intervals):
    return [
        {
            "datetime": (start + timedelta(minutes=15 * i)).isoformat(),
            "resolutioncode": "PT15M",
            "totalload": 100.0,
        }
        for i in range(intervals)
    ]


async def call_pair(records, start=START, hours=1):
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200, json={"total_count": len(records), "results": records[offset : offset + 100]}
        )

    args = {
        "series": "load",
        "start": start.isoformat(),
        "end": (start + timedelta(hours=hours)).isoformat(),
    }
    async with Client(create_server(httpx.MockTransport(handler))) as client:
        return (
            await client.call_tool("calculate_energy", args),
            await client.call_tool("check_data_quality", args),
        )


@pytest.mark.parametrize(
    "case,energy,coverage,missing,nulls",
    [
        ("complete", 100, 100, 0, 0),
        ("missing", 75, 75, 1, 0),
        ("null", 75, 75, 0, 1),
    ],
)
async def test_manual_energy_and_quality(case, energy, coverage, missing, nulls):
    records = rows(START, 4)
    if case == "missing":
        records.pop(1)
    elif case == "null":
        records[1]["totalload"] = None
    calculation, diagnosis = await call_pair(records)
    assert not calculation.is_error and not diagnosis.is_error
    assert calculation.structured_content["energy_mwh"] == energy
    q = diagnosis.structured_content
    assert q["expected_intervals"] == 4 and q["coverage_pct"] == coverage
    assert q["missing_intervals"] == missing and q["null_intervals"] == nulls
    assert q["duplicate_timestamps"] == 0


@pytest.mark.parametrize("case", ["duplicate", "irregular"])
async def test_mcp_rejects_ambiguous_intervals(case):
    records = rows(START, 4)
    if case == "duplicate":
        records.append(records[0])
    else:
        records[1]["datetime"] = (START + timedelta(minutes=16)).isoformat()
    for result in await call_pair(records):
        assert result.is_error
        assert "dataset_contract_error" in result.content[0].text
        assert "Traceback" not in result.content[0].text


async def test_mcp_empty_is_success_not_provider_failure(monkeypatch):
    for result in await call_pair([]):
        assert not result.is_error
        assert result.structured_content["metadata"]["status"] == "no_data"

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr("energy_mcp_belgium.elia.client.asyncio.sleep", no_sleep)
    async with Client(create_server(httpx.MockTransport(lambda r: httpx.Response(503)))) as client:
        result = await client.call_tool(
            "get_load",
            {"start": START.isoformat(), "end": (START + timedelta(hours=1)).isoformat()},
        )
        assert result.is_error and "provider_unavailable" in result.content[0].text


@pytest.mark.parametrize("date,hours,intervals", [("2026-03-29", 23, 92), ("2026-10-25", 25, 100)])
async def test_dst_through_mcp_with_required_range_splitting(date, hours, intervals):
    start = datetime.fromisoformat(date).replace(tzinfo=ZoneInfo("Europe/Brussels")).astimezone(UTC)
    parts = [min(hours, 24)] + ([hours - 24] if hours > 24 else [])
    total_energy, total_intervals = 0, 0
    for part in parts:
        calculation, diagnosis = await call_pair(rows(start, part * 4), start, part)
        assert not calculation.is_error and not diagnosis.is_error
        total_energy += calculation.structured_content["energy_mwh"]
        total_intervals += diagnosis.structured_content["expected_intervals"]
        assert diagnosis.structured_content["coverage_pct"] == 100
        start += timedelta(hours=part)
    assert total_energy == 100 * hours and total_intervals == intervals


async def test_every_host_parameter_has_actionable_description():
    async with Client(create_server()) as client:
        for tool in (await client.list_tools()).tools:
            for name, schema in tool.input_schema["properties"].items():
                assert schema.get("description"), (tool.name, name)
            assert "quarter-hour" in tool.input_schema["properties"]["start"]["description"]
