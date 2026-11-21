# Tool reference

All eight tools use explicit snake_case names and structured Pydantic output schemas. All make bounded read-only Elia queries, including analytics. Dates are offset-aware ISO 8601 strings, UTC quarter-hour aligned, `start < end`, maximum 24 elapsed hours. All ranges are `[start,end)`. Split larger ranges. No paging or arbitrary queries are exposed to the host.

## Data tools

| Tool / purpose | Additional inputs | Output values | Unit / resolution | Source / limitations |
|---|---|---|---|---|
| `get_solar_generation`: national PV actual estimation | none | generation_mw | MW / 15min | ods209; measured/upscaled, from 26 October 2026 only |
| `get_wind_generation`: national wind actual estimation | wind_type: total (default), onshore, offshore | generation_mw; wind_type dimension | MW / 15min | ods031; complete expected component set required for non-null aggregate |
| `get_load`: national total load | none | total_load_mw | MW / 15min | ods001; calculated/measured/extrapolated including losses; no forecast substitution |
| `get_generation_mix`: control-area production | none | generation_mw; fueltypepublication and fueltypeentsoe dimensions | MW / 15min | ods201; preserve both labels; nulls and provider revisions possible |
| `get_system_imbalance`: signed instantaneous SI | none | system_imbalance_mw; quality_status | MW / 1min | ods126; positive surplus, negative shortage; informational, non-validated |
| `get_imbalance_prices`: BRP settlement and activation prices | none | settlement_price_eur_per_mwh, marginal_incremental_price_eur_per_mwh, marginal_decremental_price_eur_per_mwh; quality_status | EUR/MWh / 15min | ods134; settlement versus marginal concepts stay separate; provisional until validated |

### Complete response shape

Synthetic one-record example:

```json
{
  "metadata": {
    "source": "elia",
    "dataset_id": "ods209",
    "source_url": "https://opendata.elia.be/explore/dataset/ods209/",
    "retrieved_at": "2026-11-19T12:00:00Z",
    "start": "2026-11-17T08:00:00Z",
    "end": "2026-11-17T08:15:00Z",
    "timezone": "UTC",
    "unit": "MW",
    "resolution_minutes": 15,
    "record_count": 1,
    "missing_value_count": 0,
    "status": "ok",
    "caveats": ["Measured and upscaled PV; not a forecast."]
  },
  "records": [
    {
      "timestamp": "2026-11-17T08:00:00Z",
      "values": {"generation_mw": 100.5},
      "dimensions": {"region": "Belgium", "gridconnectiontype": "Total"},
      "quality_status": null
    }
  ]
}
```

`missing_value_count` counts null cells in normalized output, not absent grid slots. Empty periods yield `records=[]`, `record_count=0`, `status=no_data`. Timestamp order is chronological; mix retains separate logical keys. Prices/imbalance keep the provider reliability label, distinct from availability diagnostics.

### Examples

All calls below use `start="2026-11-17T08:00:00Z", end="2026-11-17T12:00:00Z"`. These are sample arguments, not promised live results.

```text
get_solar_generation(start, end)
get_wind_generation(start, end, wind_type="offshore")
get_load(start, end)
get_generation_mix(start, end)
get_system_imbalance(start, end)
get_imbalance_prices(start, end)
```

See [Elia contracts](elia-data.md) for exact official dataset names, URLs, field semantics, caveats and refresh timing.

## calculate_energy

Purpose: fetch interval-average power and compute observed energy. Inputs: `series=solar|wind|load`, start/end, optional wind_type. Output: metadata, `energy_mwh` (number or null if no usable observations), `covered_hours`, nested quality report and method. Unit MWh, source resolution 15 minutes. Sources are the same solar/wind/load contracts above. Limitations: no gap filling or extrapolation; not available for instantaneous imbalance, prices or categorical mix.

```json
{"name":"calculate_energy","arguments":{"series":"solar","start":"2026-11-17T08:00:00Z","end":"2026-11-17T12:00:00Z"}}
```

Synthetic abbreviated output for four complete 100 MW quarter-hours: `{"energy_mwh":100.0,"covered_hours":1.0,"quality":{"expected_intervals":4,"missing_intervals":0,"coverage_pct":100.0,"status":"complete"}}`. Full output includes source metadata and all quality fields.

## check_data_quality

Purpose: diagnose one fetched series without repairs. Inputs: `series=solar|wind|load|system_imbalance|imbalance_prices`, start/end, optional wind_type. Output: metadata, record_count, expected_intervals, missing_intervals, null_intervals, duplicate_timestamps, off_grid_records, coverage_pct, first_timestamp, last_timestamp and status. Unit percent for coverage; counts for interval fields. Resolution/source match the selected data contract. Limitations: mix excluded, provider duplicates fail retrieval before diagnostics, no physical plausibility tests. Full completeness requires all exposed values non-null at every expected interval.

```json
{"name":"check_data_quality","arguments":{"series":"load","start":"2026-11-17T08:00:00Z","end":"2026-11-17T12:00:00Z"}}
```

## Resources and failures

`energy://belgium/datasets` returns JSON contract mappings, units, dimensions, resolutions and caveats. `energy://belgium/methodology` describes time and numerical rules. No session handles or reusable data snapshots are stored.

Invalid arguments fail SDK validation or return `invalid_request` ToolError. HTTP/transport issues distinguish `provider_unavailable` and `provider_response_error`. Missing required fields, changed types/resolutions, unexpected dimensions and duplicate keys fail as `dataset_contract_error`. The model sees a safe message through MCP's `isError` tool result, without expected-error stack traces.
