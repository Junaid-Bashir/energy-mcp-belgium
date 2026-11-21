from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp import Client

from energy_mcp_belgium.analytics import energy, quality
from energy_mcp_belgium.elia.client import EliaClient
from energy_mcp_belgium.elia.datasets import CONTRACTS, WIND_KEYS
from energy_mcp_belgium.elia.normalization import fetch, normalize
from energy_mcp_belgium.errors import EnergyError
from energy_mcp_belgium.models import DataResult, Metadata, Record, time_range
from energy_mcp_belgium.server import create_server

START = datetime(2026, 11, 1, tzinfo=UTC)
END = START + timedelta(hours=1)
ARGS = {"start": START.isoformat(), "end": END.isoformat()}


def fixture_rows(series):
    base = {"datetime": START.isoformat(), "resolutioncode": "PT15M"}
    if series == "wind":
        return [
            {
                **base,
                "offshoreonshore": k[0],
                "region": k[1],
                "gridconnectiontype": k[2],
                "measured": 10,
            }
            for k in sorted(WIND_KEYS)
        ]
    c = CONTRACTS[series]
    row = {**base, "resolutioncode": f"PT{c.minutes}M", "qualitystatus": "Non-validated"}
    row.update({raw: 100.5 for raw, public in c.fields})
    row.update({d: "Nuclear" for d in c.dimensions})
    if series == "solar":
        row.update(region="Belgium", gridconnectiontype="Total")
    return [row]


def make_data(start, end, records):
    return DataResult(
        metadata=Metadata(
            dataset_id="synthetic",
            source_url="https://opendata.elia.be/",
            retrieved_at=start,
            start=start,
            end=end,
            unit="MW",
            resolution_minutes=15,
            record_count=len(records),
            missing_value_count=0,
            status="ok",
            caveats=[],
        ),
        records=records,
    )


@pytest.mark.parametrize(
    "start,end",
    [
        (START.replace(tzinfo=None), END),
        (START, START),
        (END, START),
        (START, START + timedelta(hours=25)),
        (START + timedelta(minutes=1), END),
    ],
)
def test_range_validation(start, end):
    with pytest.raises(EnergyError, match="invalid_request"):
        time_range(start, end)


@pytest.mark.parametrize("series", list(CONTRACTS))
def test_normalization(series):
    result = normalize(fixture_rows(series), series, "total")
    assert result[0].timestamp.tzinfo == UTC
    assert all(isinstance(v, (int, float)) for v in result[0].values.values())


@pytest.mark.parametrize(
    "mutation", ["missing", "string", "nan", "bool", "naive", "resolution", "duplicate"]
)
def test_contract_drift(mutation):
    row = fixture_rows("load")[0]
    if mutation == "missing":
        del row["totalload"]
    elif mutation == "string":
        row["totalload"] = "100"
    elif mutation == "nan":
        row["totalload"] = float("nan")
    elif mutation == "bool":
        row["totalload"] = True
    elif mutation == "naive":
        row["datetime"] = "2026-11-01T00:00:00"
    elif mutation == "resolution":
        row["resolutioncode"] = "PT60M"
    with pytest.raises(EnergyError, match="dataset_contract_error"):
        normalize([row, row] if mutation == "duplicate" else [row], "load", "total")


def test_wind_and_nulls():
    rows = fixture_rows("wind")
    assert normalize(rows, "wind", "total")[0].values["generation_mw"] == 50
    assert normalize(rows[:-1], "wind", "total")[0].values["generation_mw"] is None
    subset = [r for r in rows if r["offshoreonshore"] == "Offshore"]
    assert normalize(subset, "wind", "offshore")[0].values["generation_mw"] == 10
    row = fixture_rows("solar")[0]
    row["measured_upscaled"] = None
    assert normalize([row], "solar", "total")[0].values["generation_mw"] is None


async def test_pagination():
    calls = []

    def handler(request):
        calls.append(request)
        offset = int(request.url.params["offset"])
        page = [
            {
                "datetime": (START + timedelta(minutes=i)).isoformat(),
                "systemimbalance": 1,
                "resolutioncode": "PT1M",
                "qualitystatus": "Non-validated",
            }
            for i in range(offset, min(125, offset + 100))
        ]
        return httpx.Response(200, json={"total_count": 125, "results": page})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        data = await fetch(EliaClient(http), "system_imbalance", START, START + timedelta(hours=3))
    assert len(data.records) == 125 and len(calls) == 2
    assert calls[0].url.params["order_by"] == "datetime ASC"
    assert "datetime >= date'" in calls[0].url.params["where"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"total_count": 2, "results": []},
        {"total_count": 5001, "results": []},
        {"total_count": True, "results": []},
        {"total_count": 1, "results": [5]},
    ],
)
async def test_bad_envelopes(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(EnergyError):
            await EliaClient(http).records("ods001", "")


async def test_empty_and_filter():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"total_count": 0, "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        data = await fetch(EliaClient(http), "solar", START, END)
    assert data.metadata.status == "no_data" and data.records == []
    assert 'gridconnectiontype = "Total"' in calls[0].url.params["where"]


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, "provider_response_error"),
        (429, "provider_unavailable"),
        (503, "provider_unavailable"),
    ],
)
async def test_provider_errors(status, expected, monkeypatch):
    async def no_sleep(seconds):
        pass

    monkeypatch.setattr("energy_mcp_belgium.elia.client.asyncio.sleep", no_sleep)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(EnergyError, match=expected):
            await EliaClient(http).records("ods001", "")
    assert len(calls) == (1 if status == 400 else 3)


async def test_retry_timeout(monkeypatch):
    async def no_sleep(seconds):
        pass

    monkeypatch.setattr("energy_mcp_belgium.elia.client.asyncio.sleep", no_sleep)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"total_count": 0, "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await EliaClient(http).records("ods001", "") == []
    assert len(calls) == 3


@pytest.mark.parametrize(
    "day,expected", [("2026-03-29", 92), ("2026-10-25", 100), ("2026-11-01", 96)]
)
def test_dst(day, expected):
    local = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Europe/Brussels"))
    start = local.astimezone(UTC)
    end = (local + timedelta(days=1)).astimezone(UTC)
    records = [
        Record(timestamp=start + timedelta(minutes=15 * i), values={"power": 4})
        for i in range(expected)
    ]
    result = energy(make_data(start, end, records))
    assert result.energy_mwh == expected
    assert result.quality.coverage_pct == 100
    assert result.quality.expected_intervals == expected


def test_gaps_nulls_zero():
    records = [
        Record(timestamp=START, values={"power": 4}),
        Record(timestamp=START + timedelta(minutes=15), values={"power": None}),
        Record(timestamp=START + timedelta(minutes=45), values={"power": 0}),
    ]
    result = energy(make_data(START, END, records))
    assert result.energy_mwh == 1 and result.covered_hours == 0.5
    assert result.quality.missing_intervals == 1 and result.quality.null_intervals == 1
    assert result.quality.coverage_pct == 50
    assert energy(make_data(START, END, [])).energy_mwh is None


def test_duplicates_irregular():
    r = Record(timestamp=START, values={"power": 4})
    data = make_data(
        START, END, [r, r, Record(timestamp=START + timedelta(minutes=2), values={"power": 4})]
    )
    report = quality(data)
    assert report.duplicate_timestamps == 1 and report.off_grid_records == 1
    assert report.status == "invalid"
    with pytest.raises(EnergyError):
        energy(data)


async def test_mcp_registration_and_calls():
    def handler(request):
        id = request.url.path.split("/")[-2]
        name = next(k for k, c in CONTRACTS.items() if c.dataset_id == id)
        rows = fixture_rows(name)
        return httpx.Response(200, json={"total_count": len(rows), "results": rows})

    async with Client(create_server(httpx.MockTransport(handler)), raise_exceptions=True) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 8
        for tool in tools.tools:
            assert tool.description and tool.input_schema and tool.output_schema
            assert "ctx" not in tool.input_schema["properties"]
            assert tool.annotations.read_only_hint
        names = {
            "solar": "get_solar_generation",
            "wind": "get_wind_generation",
            "load": "get_load",
            "generation_mix": "get_generation_mix",
            "system_imbalance": "get_system_imbalance",
            "imbalance_prices": "get_imbalance_prices",
        }
        for series, name in names.items():
            result = await client.call_tool(name, ARGS)
            assert not result.is_error, result
            assert (
                result.structured_content["metadata"]["dataset_id"] == CONTRACTS[series].dataset_id
            )
        for tool in ["calculate_energy", "check_data_quality"]:
            result = await client.call_tool(tool, {**ARGS, "series": "solar"})
            assert not result.is_error and result.structured_content
        resource = await client.read_resource("energy://belgium/datasets")
        assert "ods209" in resource.contents[0].text
        for args in [
            {**ARGS, "start": "2026-11-01T00:00:00"},
            {**ARGS, "end": ARGS["start"]},
            {**ARGS, "wind_type": "invalid"},
        ]:
            result = await client.call_tool("get_wind_generation", args)
            assert result.is_error


async def test_mcp_provider_error():
    async with Client(create_server(httpx.MockTransport(lambda r: httpx.Response(400)))) as client:
        result = await client.call_tool("get_load", ARGS)
        assert result.is_error
        assert "provider_response_error" in result.content[0].text
        assert "Traceback" not in result.content[0].text
