"""Synthetic Elia responses shared by the real stdio and HTTP test servers."""

from datetime import UTC, datetime, timedelta

import httpx

from energy_mcp_belgium.elia.datasets import CONTRACTS, WIND_KEYS

START = datetime(2026, 11, 18, 12, tzinfo=UTC)
ARGS = {"start": START.isoformat(), "end": (START + timedelta(hours=1)).isoformat()}


class Provider:
    def __init__(self, mode="complete"):
        self.mode = mode
        self.requests = []
        self.closed = False

    def handler(self, request):
        self.requests.append(request)
        assert request.method == "GET" and request.url.host == "opendata.elia.be"
        assert request.url.path.startswith("/api/explore/v2.1/catalog/datasets/")
        dataset = request.url.path.split("/")[-2]
        contract = next(c for c in CONTRACTS.values() if c.dataset_id == dataset)
        if self.mode == "unavailable":
            return httpx.Response(503)
        rows = []
        for i in range(60 // contract.minutes):
            row = {
                "datetime": (START + timedelta(minutes=contract.minutes * i)).isoformat(),
                "resolutioncode": f"PT{contract.minutes}M",
                "qualitystatus": "NotValidated",
                **{raw: 100.0 for raw, _ in contract.fields},
            }
            if dataset == "ods209":
                row.update(region="Belgium", gridconnectiontype="Total")
            if dataset == "ods201":
                row.update(fueltypepublication="Nuclear", fueltypeentsoe="Nuclear")
            if dataset == "ods031":
                for onshore, region, grid in sorted(WIND_KEYS):
                    rows.append(
                        {
                            **row,
                            "offshoreonshore": onshore,
                            "region": region,
                            "gridconnectiontype": grid,
                            "measured": 20.0,
                        }
                    )
            else:
                rows.append(row)
        if self.mode == "null":
            rows[1][contract.fields[0][0]] = None
        elif self.mode == "gap":
            rows.pop(1)
        elif self.mode == "duplicate":
            rows.append(rows[0])
        elif self.mode == "contract":
            del rows[0][contract.fields[0][0]]
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200, json={"total_count": len(rows), "results": rows[offset : offset + 100]}
        )

    def transport(self):
        owner = self

        class TrackedTransport(httpx.MockTransport):
            async def aclose(self):
                owner.closed = True
                await super().aclose()

        return TrackedTransport(self.handler)


def stable(value):
    """Retrieval wall-clock time is the only intentionally volatile result field."""
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k != "retrieved_at"}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value
