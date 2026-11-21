"""Official MCP SDK server; stdio is the only exposed CLI transport."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .analytics import energy, quality
from .elia.client import EliaClient
from .elia.datasets import CONTRACTS
from .elia.normalization import fetch
from .errors import EnergyError
from .models import (
    DataResult,
    EndTime,
    EnergyResult,
    QualityResult,
    Series,
    StartTime,
    WindSelection,
)

PowerSeries = Annotated[
    Literal["solar", "wind", "load"],
    Field(
        description="Source to fetch and integrate: solar PV generation, wind generation or Belgian total load. Fetches data itself; do not resend records. Not suitable for instantaneous imbalance or prices."
    ),
]
QualitySeries = Annotated[
    Literal["solar", "wind", "load", "system_imbalance", "imbalance_prices"],
    Field(
        description="Source to fetch and diagnose for this exact range. Availability/coverage only, not physical plausibility or settlement validation. Mix is excluded because it has multiple categorical series."
    ),
]


def create_server(transport: httpx.AsyncBaseTransport | None = None) -> MCPServer[EliaClient]:
    @asynccontextmanager
    async def lifespan(server: MCPServer[EliaClient]) -> AsyncIterator[EliaClient]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
            headers={"User-Agent": "energy-mcp-belgium/0.1 (public read-only MCP server)"},
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            transport=transport,
        ) as http:
            yield EliaClient(http)

    server = MCPServer(
        "Energy MCP Belgium",
        version="0.1.0",
        lifespan=lifespan,
        instructions=(
            "Read-only Belgian electricity data. Times require explicit offsets and UTC quarter-hour alignment; ranges are [start,end), at most 24 elapsed hours. Missing is not zero. "
            "If 'imbalance' lacks a physical MW versus settlement-price EUR/MWh context, ask which concept is intended before fetching. "
            "For solar/wind/load energy in MWh use calculate_energy, which fetches its own inputs. Never integrate instantaneous system imbalance as energy or infer imbalance costs from it. "
            "For generation or power comparisons, retrieve the solar and wind power series so their quarter-hour profiles can be compared; do not substitute only aggregated energy unless energy totals were requested. "
            "Quality tools refetch a named source for explicit bounds; ask for the source/range if absent. Elia quality status is separate from coverage."
        ),
    )
    network = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    )

    async def get(
        ctx: Context[EliaClient],
        series: Series,
        start: datetime,
        end: datetime,
        wind_type: WindSelection = "total",
    ) -> DataResult:
        logging.getLogger(__name__).info("tool_fetch series=%s", series)
        try:
            return await fetch(ctx.request_context.lifespan_context, series, start, end, wind_type)
        except EnergyError as exc:
            logging.getLogger(__name__).warning("tool_error code=%s", exc.code)
            raise ToolError(str(exc)) from None

    @server.tool(annotations=network)
    async def get_solar_generation(
        start: StartTime, end: EndTime, ctx: Context[EliaClient]
    ) -> DataResult:
        """Retrieve Belgian national measured/upscaled PV generation in MW, never forecasts. Offset-aware start/end, max 24h; solar from 26 October 2026."""
        return await get(ctx, "solar", start, end)

    @server.tool(annotations=network)
    async def get_wind_generation(
        start: StartTime,
        end: EndTime,
        ctx: Context[EliaClient],
        wind_type: WindSelection = "total",
    ) -> DataResult:
        """Retrieve Belgian measured/upscaled wind MW: total, onshore or offshore. Offset-aware start/end, max 24h; missing components yield null totals."""
        return await get(ctx, "wind", start, end, wind_type)

    @server.tool(annotations=network)
    async def get_load(start: StartTime, end: EndTime, ctx: Context[EliaClient]) -> DataResult:
        """Retrieve Belgian total load MW including estimated losses, computed from measurements and extrapolations. Offset-aware start/end, max 24h; never forecasts."""
        return await get(ctx, "load", start, end)

    @server.tool(annotations=network)
    async def get_generation_mix(
        start: StartTime, end: EndTime, ctx: Context[EliaClient]
    ) -> DataResult:
        """Retrieve Belgian control-area generation MW by both official fuel classifications. Offset-aware start/end, max 24h; preserve labels and nulls."""
        return await get(ctx, "generation_mix", start, end)

    @server.tool(annotations=network)
    async def get_system_imbalance(
        start: StartTime, end: EndTime, ctx: Context[EliaClient]
    ) -> DataResult:
        """Retrieve physical Belgian system imbalance in MW, not a price: positive surplus, negative shortage. Instantaneous 1-minute informational values; do not integrate to MWh. Offset-aware start/end, max 24h. Clarify bare 'imbalance' requests lacking MW versus price context."""
        return await get(ctx, "system_imbalance", start, end)

    @server.tool(annotations=network)
    async def get_imbalance_prices(
        start: StartTime, end: EndTime, ctx: Context[EliaClient]
    ) -> DataResult:
        """Retrieve quarter-hour Belgian BRP settlement and distinct upward/downward marginal activation prices in EUR/MWh, not physical imbalance MW. Offset-aware start/end, max 24h; provisional until validated. No separate positive/negative BRP tariff is invented."""
        return await get(ctx, "imbalance_prices", start, end)

    @server.tool(annotations=network)
    async def calculate_energy(
        series: PowerSeries,
        start: StartTime,
        end: EndTime,
        ctx: Context[EliaClient],
        wind_type: WindSelection = "total",
    ) -> EnergyResult:
        """Calculate solar/wind generation energy or total-load energy in MWh by fetching its own power source and summing MW times 0.25h. Use for energy, rather than power in MW. Offset-aware start/end, max 24h; coverage reported, no gap filling. No raw-record input."""
        data = await get(ctx, series, start, end, wind_type)
        try:
            return energy(data)
        except EnergyError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(annotations=network)
    async def check_data_quality(
        series: QualitySeries,
        start: StartTime,
        end: EndTime,
        ctx: Context[EliaClient],
        wind_type: WindSelection = "total",
    ) -> QualityResult:
        """Fetch one Belgian series and diagnose gaps, nulls, duplicate timestamps and coverage without repair. Offset-aware start/end, max 24h; mix excluded because it has multiple keys."""
        return quality(await get(ctx, series, start, end, wind_type))

    @server.resource("energy://belgium/datasets", mime_type="application/json")
    def datasets() -> str:
        """Discover verified source identities, units, dimensions and caveats."""
        return json.dumps(
            {
                name: {
                    **asdict(c),
                    "provider": "elia",
                    "source_url": f"https://opendata.elia.be/explore/dataset/{c.dataset_id}/",
                    "time_field": "datetime",
                    "timezone": "UTC",
                }
                for name, c in CONTRACTS.items()
            }
        )

    @server.resource("energy://belgium/methodology", mime_type="text/plain")
    def methodology() -> str:
        return (
            "UTC interval starts, [start,end), maximum 24h, quarter-hour aligned boundaries. "
            "Integrate solar/wind/load only: sum non-null MW * 0.25h. No interpolation. "
            "Missing components produce null wind totals. Coverage counts unique non-null intervals. "
            "Provider duplicates fail retrieval; quality never silently deduplicates. "
            "Instantaneous system imbalance is not integrated as interval-average power."
        )

    return server


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    create_server().run(transport="stdio")
