"""Five sequential one-hour MCP demonstrations; live access requires ENERGY_MCP_LIVE=1."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from energy_mcp_belgium.errors import EnergyError
from energy_mcp_belgium.models import time_range

SCENARIOS = {
    "solar": ("Solar generation", "get_solar_generation", {}),
    "imbalance": ("Physical system imbalance", "get_system_imbalance", {}),
    "prices": ("Imbalance prices", "get_imbalance_prices", {}),
    "energy": ("Solar energy", "calculate_energy", {"series": "solar"}),
    "quality": ("Load completeness", "check_data_quality", {"series": "load"}),
}


def demo_range(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    if (start is None) != (end is None):
        raise ValueError("Supply both --start and --end, or neither.")
    if start is None:
        first = (datetime.now(UTC) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        last = first + timedelta(hours=1)
    else:
        assert end is not None
        first = datetime.fromisoformat(start.replace("Z", "+00:00"))
        last = datetime.fromisoformat(end.replace("Z", "+00:00"))
    first, last = time_range(first, last)
    if last - first > timedelta(hours=1):
        raise ValueError("The public demo allows at most one elapsed hour per scenario.")
    if last > datetime.now(UTC):
        raise ValueError("Choose a historical period, not a future interval.")
    if first < datetime(2026, 10, 25, 23, tzinfo=UTC):
        raise ValueError("Choose a period from the 26 October 2026 solar dataset cutover onward.")
    return first, last


async def run_demo(client: Client, start: datetime, end: datetime, scenarios: list[str]) -> dict:
    """Use actual MCP tools; retain compact metrics/provenance rather than raw records."""
    summary = {
        "kind": "live MCP demonstration",
        "generated_at": datetime.now(UTC).isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "status": "passed",
        "scenarios": [],
    }
    for scenario in scenarios:
        title, tool, extra = SCENARIOS[scenario]
        result = await client.call_tool(
            tool, {"start": start.isoformat(), "end": end.isoformat(), **extra}
        )
        if result.is_error:
            message = " ".join(getattr(item, "text", "") for item in result.content)[:400]
            summary["scenarios"].append(
                {"scenario": scenario, "tool": tool, "status": "failed", "error": message}
            )
            summary["status"] = "failed"
            print(f"[FAIL] {title}: {message}")
            break  # No repeated requests when the provider fails.
        data = result.structured_content
        if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
            raise ValueError(f"{tool} did not return structured provenance metadata.")
        metadata = data["metadata"]
        status = "no_data" if metadata["status"] == "no_data" else "passed"
        metrics = {}
        if scenario == "energy":
            metrics = {
                "energy_mwh": data["energy_mwh"],
                "covered_hours": data["covered_hours"],
                "coverage_pct": data["quality"]["coverage_pct"],
            }
            if data["quality"]["status"] != "complete":
                status = "incomplete" if status != "no_data" else status
        elif scenario == "quality":
            metrics = {
                key: data[key]
                for key in (
                    "expected_intervals",
                    "record_count",
                    "missing_intervals",
                    "null_intervals",
                    "duplicate_timestamps",
                    "off_grid_records",
                    "coverage_pct",
                    "status",
                )
            }
            if data["status"] != "complete":
                status = "incomplete" if status != "no_data" else status
        entry = {
            "scenario": scenario,
            "tool": tool,
            "status": status,
            "metadata": metadata,
            "result": metrics,
        }
        summary["scenarios"].append(entry)
        if status != "passed":
            summary["status"] = "incomplete"
        marker = "OK" if status == "passed" else status.upper()
        print(f"[{marker}] {title} -> {tool}")
        print(
            f"     Elia {metadata['dataset_id']} | {metadata['record_count']} records | "
            f"{metadata['resolution_minutes']} min | source unit: {metadata['unit']}"
        )
        if scenario == "energy":
            print(
                f"     energy_mwh: {metrics['energy_mwh']} | coverage: {metrics['coverage_pct']}%"
            )
        elif scenario == "quality":
            print(
                f"     expected/received: {metrics['expected_intervals']}/{metrics['record_count']} | "
                f"missing: {metrics['missing_intervals']} | null: {metrics['null_intervals']} | "
                f"duplicates: {metrics['duplicate_timestamps']} | coverage: {metrics['coverage_pct']}%"
            )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="Inclusive ISO 8601 start with explicit offset.")
    parser.add_argument("--end", help="Exclusive ISO 8601 end; maximum one hour after start.")
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS), help="Run one scenario; default: all five."
    )
    parser.add_argument(
        "--output", type=Path, help="Optional local compact JSON summary; no raw records."
    )
    args = parser.parse_args(argv)
    if os.getenv("ENERGY_MCP_LIVE") != "1":
        print("Live demo is OFF. Set ENERGY_MCP_LIVE=1 to contact public Elia Open Data.")
        print("No network requests were made. For an offline example: python examples/demo.py")
        return 2
    try:
        start, end = demo_range(args.start, args.end)
    except (ValueError, EnergyError) as exc:
        print(f"Invalid demo range: {exc}", file=sys.stderr)
        return 2
    print("Energy MCP Belgium | LIVE public demo")
    print(f"UTC range: {start.isoformat()} -> {end.isoformat()} (end exclusive)")
    print("Read-only Elia access | sequential calls | no LLM API key")
    print("Scripted tool calls; natural-language selection belongs to an MCP host.\n")

    async def invoke() -> dict:
        async with Client(
            StdioServerParameters(command=sys.executable, args=["-m", "energy_mcp_belgium"])
        ) as client:
            return await run_demo(
                client, start, end, [args.scenario] if args.scenario else list(SCENARIOS)
            )

    try:
        summary = asyncio.run(invoke())
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(f"\nCompact summary saved to {args.output}")
        print(f"\nDemo status: {summary['status']}")
        return {"passed": 0, "failed": 1, "incomplete": 3}[summary["status"]]
    except Exception as exc:
        print(
            f"Demo could not complete ({type(exc).__name__}). "
            "Check installation/connectivity and retry later; no external writes occurred.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
