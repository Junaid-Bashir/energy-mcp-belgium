# Public demo

See five existing v0.1 tools return structured data, explicit units and Elia provenance. This is a **scripted MCP demonstration**, not a chatbot or a natural-language routing implementation. The official Python MCP client starts the installed stdio server; no LLM API key is required.

## Run

From an installed checkout/environment, use the existing live-test opt-in:

```powershell
$env:ENERGY_MCP_LIVE = "1"
python examples/run_public_demo.py
Remove-Item Env:ENERGY_MCP_LIVE
```

In a POSIX shell:

```sh
ENERGY_MCP_LIVE=1 python examples/run_public_demo.py
```

**Network access:** five sequential, bounded, read-only Elia queries. The default window is 12:00–13:00 UTC two days before the run. Without ENERGY_MCP_LIVE=1 the command exits before starting the server or contacting Elia. For an offline walkthrough, use `python examples/demo.py` instead.

| Scenario | MCP tool | What to notice |
|---|---|---|
| Solar generation | get_solar_generation | Quarter-hour power, MW, source ods209 |
| Physical imbalance | get_system_imbalance | Minute-level MW, positive surplus / negative shortage |
| Imbalance prices | get_imbalance_prices | Quarter-hour settlement/marginal prices, EUR/MWh |
| Solar energy | calculate_energy | Source fetch plus deterministic MWh integration and coverage |
| Load completeness | check_data_quality | Expected/received intervals, nulls, gaps, duplicates and coverage |

Each tool fetches its own source. The demo does not add datasets, cache results between tools, rank intervals or change server behavior.

## Dated, repeatable window

Both endpoints must be explicit-offset ISO 8601, quarter-hour aligned, historical, and at most **one elapsed hour** apart for this demo. The server's separate maximum remains 24 hours. Solar cutover limitations still apply.

```sh
python examples/run_public_demo.py --start 2026-11-17T12:00:00Z --end 2026-11-17T13:00:00Z
```

This command also requires ENERGY_MCP_LIVE=1. On 19 November 2026 the window returned four solar records, 60 system-imbalance records, four price records, **2191.975 MWh** of observed solar energy and a complete four-interval load series. Provider revisions or publication problems can change a later result.

Run just one scenario with `--scenario solar`, `imbalance`, `prices`, `energy` or `quality`. For example:

```sh
python examples/run_public_demo.py --scenario energy --start 2026-11-17T12:00:00Z --end 2026-11-17T13:00:00Z
```

## Screenshot-friendly output

Illustrative excerpt from the dated verification (not a promise of current values):

```text
Energy MCP Belgium | LIVE public demo
Read-only Elia access | sequential calls | no LLM API key

[OK] Solar generation -> get_solar_generation
     Elia ods209 | 4 records | 15 min | source unit: MW
[OK] Physical system imbalance -> get_system_imbalance
     Elia ods126 | 60 records | 1 min | source unit: MW
[OK] Imbalance prices -> get_imbalance_prices
     Elia ods134 | 4 records | 15 min | source unit: EUR/MWh
[OK] Solar energy -> calculate_energy
     energy_mwh: 2191.975 | coverage: 100.0%
[OK] Load completeness -> check_data_quality
     expected/received: 4/4 | missing: 0 | null: 0 | duplicates: 0 | coverage: 100.0%
```

Terminal output does not dump raw time-series records. Source MW is distinct from the energy_mwh result; prices retain EUR/MWh. There is no certification, sponsorship or endorsement implied by a successful demo.

## Optional machine-readable evidence

```sh
python examples/run_public_demo.py --output artifacts/public-demo/validation-summary.json
```

The same explicit live opt-in is required. Output contains compact results and provenance, including source URL, retrieval time, interval bounds, units, resolution and record counts. It contains no raw record array or model transcript. Nothing is written unless --output is supplied. The suggested artifacts/public-demo/ directory is ignored; do not automatically commit timestamped live output. Existing public examples are separately curated, dated and attributed.

## Errors and exit codes

- `0`: all selected scenarios returned data and complete analytics coverage.
- `1`: a tool/provider/transport or local output error. The demo stops on the first tool error; it does not add a retry loop over the server's bounded retries.
- `2`: live access not enabled or invalid arguments/range; no provider call is made.
- `3`: no-data or incomplete analytics coverage. Missing data is reported, never relabelled as a successful complete period or replaced with zero.

An unavailable provider produces a short error rather than a traceback or a fabricated result. Check installation/connectivity and retry later. No external write or market action occurs. See [source caveats](elia-data.md), [time semantics](time-semantics.md) and [data terms](../THIRD_PARTY.md).

For a 15–30 second host recording, follow the [recording guide](recording.md). For independent protocol/provider/host checks, see [Validation](validation.md).
