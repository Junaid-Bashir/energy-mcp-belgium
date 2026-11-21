from datetime import timedelta

import httpx
import pytest
from test_core import END, START, fixture_rows

from energy_mcp_belgium.elia.client import EliaClient
from energy_mcp_belgium.elia.normalization import fetch, normalize
from energy_mcp_belgium.errors import EnergyError


async def test_arbitrary_dataset_rejected():
    async with httpx.AsyncClient() as http:
        with pytest.raises(EnergyError, match="Unsupported dataset"):
            await EliaClient(http).records("https://example.com", "")


def test_chronological_order_and_resolution_field_required():
    row = fixture_rows("load")[0]
    later = {**row, "datetime": END.isoformat()}
    result = normalize([later, row], "load", "total")
    assert result[0].timestamp == START and result[1].timestamp == END
    del row["resolutioncode"]
    with pytest.raises(EnergyError, match="dataset_contract_error"):
        normalize([row], "load", "total")


@pytest.mark.parametrize("mutation", ["dimension", "outside", "off_grid"])
async def test_invalid_provider_rows(mutation):
    row = fixture_rows("solar")[0]
    if mutation == "dimension":
        row["region"] = "Flanders"
    elif mutation == "outside":
        row["datetime"] = END.isoformat()
    else:
        row["datetime"] = (START + timedelta(minutes=1)).isoformat()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"total_count": 1, "results": [row]})
        )
    ) as http:
        with pytest.raises(EnergyError, match="dataset_contract_error"):
            await fetch(EliaClient(http), "solar", START, END)


async def test_solar_cutover_rejected_before_network():
    async with httpx.AsyncClient() as http:
        with pytest.raises(EnergyError, match="legacy ods032"):
            await fetch(
                EliaClient(http), "solar", START - timedelta(days=30), END - timedelta(days=30)
            )


async def test_changing_total_fails():
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json={
                "total_count": 101 if offset == 0 else 102,
                "results": [{}] * (100 if offset == 0 else 2),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(EnergyError, match="changed during pagination"):
            await EliaClient(http).records("ods001", "")


@pytest.mark.parametrize("retry_after", ["10", "not-a-duration"])
async def test_retry_after_does_not_hammer(retry_after):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": retry_after})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(EnergyError, match="provider_unavailable"):
            await EliaClient(http).records("ods001", "")
    assert len(calls) == 1


async def test_malformed_json():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="<html>maintenance</html>")
        )
    ) as http:
        with pytest.raises(EnergyError, match="provider_response_error"):
            await EliaClient(http).records("ods001", "")
