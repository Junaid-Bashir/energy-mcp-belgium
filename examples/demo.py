"""Real MCP client/server demonstration, mocked by default; --live opts into Elia."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

import httpx
from mcp import Client

from energy_mcp_belgium.server import create_server


async def main() -> None:
    live = "--live" in sys.argv
    start = (
        (datetime.now(UTC) - timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        if live
        else datetime(2026, 11, 1, tzinfo=UTC)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        rows = [
            {
                "datetime": (start + timedelta(minutes=15 * i)).isoformat(),
                "region": "Belgium",
                "gridconnectiontype": "Total",
                "measured_upscaled": float(100 + i),
            }
            for i in range(4)
        ]
        return httpx.Response(200, json={"total_count": len(rows), "results": rows})

    server = create_server(None if live else httpx.MockTransport(handler))
    async with Client(server, raise_exceptions=True) as client:
        args = {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}
        for tool, arguments in [
            ("get_solar_generation", args),
            ("calculate_energy", {**args, "series": "solar"}),
        ]:
            result = await client.call_tool(tool, arguments)
            if result.is_error:
                raise RuntimeError(result.content)
            print(
                json.dumps(
                    {"tool": tool, "structured_content": result.structured_content}, indent=2
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
