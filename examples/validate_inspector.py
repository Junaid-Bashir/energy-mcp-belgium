"""Opt-in Inspector CLI validation of an installed server; no custom MCP client.

Requires a supported Node runtime and the separately installed official Inspector.
Calls ten one-hour live cases and five one-day cases sequentially. Output is local.
"""

import argparse
import json
import subprocess
from pathlib import Path
from time import monotonic

DATASETS = {
    "get_solar_generation": "ods209",
    "get_wind_generation": "ods031",
    "get_load": "ods001",
    "get_generation_mix": "ods201",
    "get_system_imbalance": "ods126",
    "get_imbalance_prices": "ods134",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ["node", "inspector", "server-command", "cwd", "output"]:
        parser.add_argument("--" + option, required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def invoke(label, method, tool=None, arguments=None):
        command = [
            args.node,
            args.inspector,
            "--cli",
            args.server_command,
            "--method",
            method,
            "--format",
            "json",
        ]
        if tool:
            command += ["--tool-name", tool]
            for key, value in arguments.items():
                command += ["--tool-arg", f"{key}={value}"]
        begun = monotonic()
        result = subprocess.run(
            command,
            cwd=args.cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        (output / f"{label}.json").write_text(result.stdout, encoding="utf-8")
        (output / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
        body = json.loads(result.stdout)
        return body.get("result", body), round(monotonic() - begun, 3), result.returncode

    discovery, seconds, code = invoke("tools", "tools/list")
    assert code == 0 and len(discovery["tools"]) == 8
    for tool in discovery["tools"]:
        assert tool["description"] and tool["outputSchema"]["type"] == "object"
        assert {"start", "end"} <= set(tool["inputSchema"]["required"])
        assert all(p.get("description") for p in tool["inputSchema"]["properties"].values())
    summary = [{"case": "discovery", "tools": len(discovery["tools"]), "seconds": seconds}]
    base = {"start": "2026-11-17T10:00:00Z", "end": "2026-11-17T11:00:00Z"}
    calls = [(name, name, base) for name in DATASETS]
    calls += [
        ("wind_" + kind, "get_wind_generation", {**base, "wind_type": kind})
        for kind in ["onshore", "offshore"]
    ]
    calls += [
        (name, name, {**base, "series": "solar"})
        for name in ["calculate_energy", "check_data_quality"]
    ]
    calls += [
        (name + "_day", name, {"start": "2026-11-17T00:00:00Z", "end": "2026-11-18T00:00:00Z"})
        for name in [
            "get_solar_generation",
            "get_wind_generation",
            "get_load",
            "get_generation_mix",
            "get_imbalance_prices",
        ]
    ]
    for label, name, arguments in calls:
        result, seconds, code = invoke(label, "tools/call", name, arguments)
        assert code == 0 and not result.get("isError"), (label, result)
        data = result["structuredContent"]
        meta = data["metadata"]
        assert meta["source"] == "elia" and meta["timezone"] == "UTC"
        if name in DATASETS:
            assert meta["dataset_id"] == DATASETS[name]
        records = data.get("records", [])
        if records:
            assert meta["record_count"] == len(records)
            assert [r["timestamp"] for r in records] == sorted(r["timestamp"] for r in records)
            assert all(
                isinstance(v, (int, float)) or v is None
                for r in records
                for v in r["values"].values()
            )
        structured_bytes = len(json.dumps(data, separators=(",", ":")).encode())
        wire_bytes = len(json.dumps(result, separators=(",", ":")).encode())
        entry = {
            "case": label,
            "tool": name,
            "arguments": arguments,
            "dataset": meta["dataset_id"],
            "records": meta["record_count"],
            "structured_bytes": structured_bytes,
            "mcp_result_bytes": wire_bytes,
            "seconds": seconds,
        }
        summary.append(entry)
        print(json.dumps(entry), flush=True)
    for label, arguments in [
        ("invalid_time", {**base, "start": "bad"}),
        ("reversed", {**base, "start": base["end"], "end": base["start"]}),
        ("oversized", {**base, "end": "2026-11-19T11:00:00Z"}),
    ]:
        result, seconds, code = invoke(label, "tools/call", "get_load", arguments)
        assert result.get("isError") and "Traceback" not in json.dumps(result)
        summary.append({"case": label, "is_error": True, "exit_code": code, "seconds": seconds})
    result, seconds, code = invoke(
        "no_data",
        "tools/call",
        "get_system_imbalance",
        {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T01:00:00Z"},
    )
    assert code == 0 and not result.get("isError")
    assert result["structuredContent"]["metadata"]["status"] == "no_data"
    assert result["structuredContent"]["records"] == []
    summary.append(
        {
            "case": "no_data",
            "is_error": False,
            "records": 0,
            "seconds": seconds,
            "dataset": "ods126",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-01T01:00:00Z",
        }
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
