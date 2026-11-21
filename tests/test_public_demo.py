"""Exercise the public presentation layer without provider/model access."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from mcp import Client

from energy_mcp_belgium.server import create_server

spec = importlib.util.spec_from_file_location(
    "public_demo", Path(__file__).resolve().parents[1] / "examples/run_public_demo.py"
)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

START = datetime(2026, 11, 17, 12, tzinfo=UTC)
END = START + timedelta(hours=1)


def provider(request):
    dataset = request.url.path.split("/")[-2]
    if dataset == "ods209":
        records = [
            {
                "datetime": (START + timedelta(minutes=15 * i)).isoformat(),
                "region": "Belgium",
                "gridconnectiontype": "Total",
                "measured_upscaled": 100,
            }
            for i in range(4)
        ]
    elif dataset == "ods001":
        records = [
            {
                "datetime": (START + timedelta(minutes=15 * i)).isoformat(),
                "resolutioncode": "PT15M",
                "totalload": 100,
            }
            for i in range(4)
        ]
    elif dataset == "ods126":
        records = [
            {
                "datetime": (START + timedelta(minutes=i)).isoformat(),
                "resolutioncode": "PT1M",
                "systemimbalance": -10,
                "qualitystatus": "Non Validated",
            }
            for i in range(60)
        ]
    else:
        assert dataset == "ods134"
        records = [
            {
                "datetime": (START + timedelta(minutes=15 * i)).isoformat(),
                "resolutioncode": "PT15M",
                "qualitystatus": "Non Validated",
                "imbalanceprice": 50,
                "marginalincrementalprice": 55,
                "marginaldecrementalprice": 45,
            }
            for i in range(4)
        ]
    return httpx.Response(200, json={"total_count": len(records), "results": records})


async def test_five_sequential_tools_compact_output(capsys):
    calls = []

    def tracked(request):
        calls.append(request.url.path.split("/")[-2])
        return provider(request)

    async with Client(create_server(httpx.MockTransport(tracked))) as client:
        result = await demo.run_demo(client, START, END, list(demo.SCENARIOS))
    assert calls == ["ods209", "ods126", "ods134", "ods209", "ods001"]
    assert result["status"] == "passed" and len(result["scenarios"]) == 5
    assert result["scenarios"][3]["result"]["energy_mwh"] == 100
    assert result["scenarios"][4]["result"]["coverage_pct"] == 100
    encoded = json.dumps(result)
    assert '"records"' not in encoded and len(encoded) < 6500
    assert all(
        s["metadata"]["source_url"].startswith("https://opendata.elia.be/")
        for s in result["scenarios"]
    )
    output = capsys.readouterr().out
    assert len(output.splitlines()) < 20 and "source unit: EUR/MWh" in output


async def test_failure_stops_without_dumping_traceback(capsys):
    calls = []

    def failure(request):
        calls.append(request)
        return httpx.Response(400)

    async with Client(create_server(httpx.MockTransport(failure))) as client:
        result = await demo.run_demo(client, START, END, list(demo.SCENARIOS))
    assert len(calls) == 1 and result["status"] == "failed"
    assert "provider_response_error" in result["scenarios"][0]["error"]
    assert "Traceback" not in capsys.readouterr().out


async def test_no_data_is_not_green_success(capsys):
    async with Client(
        create_server(
            httpx.MockTransport(
                lambda request: httpx.Response(200, json={"total_count": 0, "results": []})
            )
        )
    ) as client:
        result = await demo.run_demo(client, START, END, ["energy", "quality"])
    assert result["status"] == "incomplete"
    assert all(s["status"] == "no_data" for s in result["scenarios"])
    assert result["scenarios"][0]["result"]["energy_mwh"] is None
    assert "[OK]" not in capsys.readouterr().out


def test_environment_opt_in_before_client_start(monkeypatch, capsys):
    monkeypatch.delenv("ENERGY_MCP_LIVE", raising=False)
    monkeypatch.setattr(demo, "Client", lambda *a, **k: pytest.fail("Unexpected MCP start"))
    assert demo.main([]) == 2
    assert "No network requests" in capsys.readouterr().out


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-11-17T12:00:00Z", "2026-11-17T14:00:00Z"),
        ("2026-11-17T12:01:00Z", "2026-11-17T13:00:00Z"),
        ("2026-11-17T12:00:00", "2026-11-17T13:00:00"),
        ("2026-11-17T12:00:00Z", None),
        ("2026-10-01T12:00:00Z", "2026-10-01T13:00:00Z"),
        ("2099-11-17T12:00:00Z", "2099-11-17T13:00:00Z"),
    ],
)
def test_invalid_ranges_fail_before_client_start(start, end, monkeypatch):
    monkeypatch.setenv("ENERGY_MCP_LIVE", "1")
    monkeypatch.setattr(demo, "Client", lambda *a, **k: pytest.fail("Unexpected MCP start"))
    args = ["--start", start] + (["--end", end] if end is not None else [])
    assert demo.main(args) == 2


def test_default_range_is_one_historical_hour():
    start, end = demo.demo_range(None, None)
    assert start.tzinfo == UTC and end - start == timedelta(hours=1) and end < datetime.now(UTC)
