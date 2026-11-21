from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp import Client
from pydantic import ValidationError
from test_core import ARGS, END, START, fixture_rows, make_data

from energy_mcp_belgium.analytics import energy, quality
from energy_mcp_belgium.elia.client import EliaClient
from energy_mcp_belgium.elia.normalization import fetch
from energy_mcp_belgium.errors import EnergyError
from energy_mcp_belgium.models import Metadata, Record
from energy_mcp_belgium.server import create_server


@pytest.mark.parametrize(
    "change",
    [
        {"resolution_minutes": 0},
        {"resolution_minutes": -15},
        {"resolution_minutes": True},
        {"end": START},
        {"end": START + timedelta(minutes=16)},
        {"record_count": -1},
        {"missing_value_count": -1},
    ],
)
def test_invalid_analytics_metadata(change):
    meta = make_data(START, END, []).metadata.model_dump()
    with pytest.raises(ValidationError):
        Metadata.model_validate({**meta, **change})


@pytest.mark.parametrize("day,expected", [("2026-03-29", 92), ("2026-10-25", 100)])
def test_local_timezone_inputs_are_normalized_before_dst_arithmetic(day, expected):
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Europe/Brussels"))
    end = start + timedelta(days=1)
    utc_start = start.astimezone(UTC)
    records = [
        Record(timestamp=utc_start + timedelta(minutes=15 * i), values={"mw": 4})
        for i in range(expected)
    ]
    data = make_data(start, end, records)
    assert data.metadata.start.tzinfo == UTC and data.metadata.end.tzinfo == UTC
    assert quality(data).expected_intervals == expected
    assert energy(data).energy_mwh == expected
    assert Record(timestamp=start, values={"mw": 4}).timestamp == utc_start


@pytest.mark.parametrize(
    "kind",
    ["multiple_values", "instantaneous", "prices", "mix", "changing_dimensions", "empty_values"],
)
def test_unsuitable_series_cannot_be_integrated(kind):
    records = [Record(timestamp=START, values={"mw": 4})]
    data = make_data(START, END, records)
    if kind == "multiple_values":
        data.records[0].values["another"] = 10
    elif kind == "instantaneous":
        data.metadata.resolution_minutes = 1
        data.metadata.dataset_id = "ods126"
    elif kind == "prices":
        data.metadata.unit = "EUR/MWh"
    elif kind == "mix":
        data.metadata.dataset_id = "ods201"
    elif kind == "changing_dimensions":
        data.records.append(
            Record(
                timestamp=START + timedelta(minutes=15),
                values={"mw": 4},
                dimensions={"region": "other"},
            )
        )
    else:
        data.records[0].values = {}
    with pytest.raises(EnergyError, match="invalid_request"):
        energy(data)


async def test_requests_project_only_required_fields():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"total_count": 0, "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = EliaClient(http)
        await client.records("ods031", "")
        await client.records("ods134", "")
    assert set(calls[0].url.params["select"].split(",")) == {
        "datetime",
        "offshoreonshore",
        "region",
        "gridconnectiontype",
        "measured",
        "resolutioncode",
    }
    assert "forecast" not in calls[0].url.params["select"]
    assert "qualitystatus" in calls[1].url.params["select"]
    assert (
        calls[0].url.params["order_by"]
        == "datetime ASC, offshoreonshore ASC, region ASC, gridconnectiontype ASC"
    )


async def test_wind_type_not_silently_ignored():
    async with httpx.AsyncClient() as http:
        with pytest.raises(EnergyError, match="only applies"):
            await fetch(EliaClient(http), "solar", START, END, "offshore")


async def test_all_tools_expose_schemas_and_registered_error_paths():
    async with Client(create_server(httpx.MockTransport(lambda r: httpx.Response(503)))) as client:
        tools = (await client.list_tools()).tools
        by_name = {t.name: t for t in tools}
        assert set(by_name) == {
            "get_solar_generation",
            "get_wind_generation",
            "get_load",
            "get_generation_mix",
            "get_system_imbalance",
            "get_imbalance_prices",
            "calculate_energy",
            "check_data_quality",
        }
        for tool in tools:
            schema = tool.input_schema
            assert {"start", "end"} <= set(schema["required"])
            assert schema["properties"]["start"]["format"] == "date-time"
            assert tool.output_schema["type"] == "object"
            assert tool.annotations.read_only_hint and not tool.annotations.destructive_hint
        for tool in ["calculate_energy", "check_data_quality"]:
            result = await client.call_tool(tool, {**ARGS, "series": "generation_mix"})
            assert result.is_error


async def test_provider_lifespan_closes_transport():
    class TrackedTransport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            return httpx.Response(200, json={"total_count": 0, "results": []})

        async def aclose(self):
            self.closed = True

    transport = TrackedTransport()
    async with Client(create_server(transport)) as client:
        result = await client.call_tool("get_load", ARGS)
        assert not result.is_error
        assert not transport.closed
    assert transport.closed


@pytest.mark.parametrize(
    "timestamp", [1793491200, "1793491200", "2026-11-01", "2026-11-01T00:00:00"]
)
async def test_mcp_rejects_non_offset_iso_timestamps(timestamp):
    async with Client(create_server()) as client:
        result = await client.call_tool("get_load", {**ARGS, "start": timestamp})
        assert result.is_error


@pytest.mark.parametrize("timestamp", ["2026-11-01T01:00:00+01:00", "2026-11-01T00:00:00Z"])
async def test_mcp_accepts_explicit_offsets(timestamp):
    async with Client(
        create_server(
            httpx.MockTransport(
                lambda r: httpx.Response(200, json={"total_count": 0, "results": []})
            )
        )
    ) as client:
        result = await client.call_tool("get_load", {**ARGS, "start": timestamp})
        assert not result.is_error
        assert result.structured_content["metadata"]["start"] == "2026-11-01T00:00:00Z"


async def test_wind_subtype_filtered_and_null_component_preserved():
    calls = []
    rows = [r for r in fixture_rows("wind") if r["offshoreonshore"] == "Onshore"]
    rows[0]["measured"] = None

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"total_count": len(rows), "results": rows})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        data = await fetch(EliaClient(http), "wind", START, END, "onshore")
    assert 'offshoreonshore = "Onshore"' in calls[0].url.params["where"]
    assert data.records[0].values["generation_mw"] is None
