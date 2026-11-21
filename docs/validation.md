# Validation methodology

Energy MCP Belgium is tested at three boundaries: MCP protocol, Elia data contracts and client interoperability. Tests check structured data and deterministic calculations; they do not certify provider data or guarantee a model's free-text answers.

## MCP protocol

Use the official [MCP Inspector CLI](clients.md) to initialize a connection, discover exactly eight tools and call a bounded query. Compare names, descriptions, input/output schemas and read-only annotations with the [schema reference](examples/tools-schema.json). The running server is authoritative.

The automated suite compares local stdio and Streamable HTTP schemas, resources, results and error behavior. It covers JSON/request-scoped SSE replies, request lifecycle, concurrency, cancellation, Host/Origin handling and body limits. Fresh-wheel checks launch both installed entry points outside the source checkout and block provider networking during startup/discovery.

## Elia data contracts

The [source contracts](elia-data.md) define the six allowlisted datasets, fields, dimensions, units and resolutions. Use small historical windows to check live responses against those contracts:

| Capability | Dataset | Resolution | Unit |
|---|---|---|---|
| Solar | ods209 | 15 min | MW |
| Wind | ods031 | 15 min | MW |
| Load | ods001 | 15 min | MW |
| Generation mix | ods201 | 15 min | MW |
| Physical system imbalance | ods126 | 1 min | MW |
| Imbalance prices | ods134 | 15 min | EUR/MWh |

Check source URLs, retrieval time, explicit bounds, chronological UTC ordering, numeric types, dimensions and quality status. Nulls must remain null, empty data must remain distinct from provider failure, and actual-value fields must not be replaced with forecasts. The [Inspector examples](examples/inspector-results.json) and [small attributed solar response](examples/solar-response.json) illustrate these checks. Historical records can be revised or delayed.

## Deterministic analytics

Offline tests use synthetic provider-shaped rows: four complete 100 MW quarter-hours must produce exactly 100 MWh. They also exercise missing/null values, duplicate and off-grid timestamps, invalid ranges, provider failures and 92/96/100-quarter-hour daylight-saving days. Missing intervals are not filled; coverage accompanies observed energy. See [analytics](analytics.md) and [time semantics](time-semantics.md).

For a dated real-data example, solar generation on 17 November 2026, [12:00,13:00) UTC produced 2,191.975 MWh from four usable quarter-hours with 100% coverage when retrieved on 19 November 2026. This example illustrates MW-to-MWh integration, not an immutable provider snapshot. Instantaneous physical imbalance and prices are not eligible for energy integration.

## Remote client interoperability

The hosted Streamable HTTP endpoint has been tested with MCP Inspector and ChatGPT. Compatible clients own dialogue, date resolution, tool selection and narration. Model behavior can vary; a successful scenario is not an uptime or capacity guarantee. See [client setup](clients.md) and [service availability](remote-security.md#service-availability).

Use these scenarios when evaluating a client:

| Request | What to inspect |
|---|---|
| Solar over a populated two-hour window | Eight quarter-hour MW records with provenance |
| Solar energy over one hour | `calculate_energy`, MWh, usable intervals and coverage |
| “What was Belgium's imbalance?” | Clarification of physical MW versus price EUR/MWh before selecting a tool |
| Solar versus total wind over four hours | Both MW series, rather than only energy summaries |
| Load completeness | Expected/received intervals, gaps, nulls, duplicates and coverage |

The server supplies descriptions and structured results; it does not generate a conversational clarification. To evaluate MCP retrieval, inspect actual tool calls and provenance rather than relying on host narration. A host may also use web search or other tools, so attribution should follow the actual call path.

## Response size

The following reference sizes use compact UTF-8 JSON, excluding JSON-RPC framing. MCP results include text content and structuredContent and are larger than the structured payload alone. Sizes vary with values, dimensions and SDK serialization; these examples are not response-size limits.

| Series | 1h records | 1h structured / MCP bytes | 24h records | 24h structured / MCP bytes |
|---|---:|---:|---:|---:|
| Solar | 4 | 1,054 / 2,827 | 96 | 15,094 / 41,795 |
| Wind total | 4 | 945 / 2,549 | 96 | 12,958 / 35,965 |
| Load | 4 | 882 / 2,331 | 96 | 11,047 / 29,931 |
| Generation mix | 48 | 8,751 / 23,379 | 1,152 | 199,367 / 534,101 |
| Imbalance prices | 4 | 1,361 / 3,405 | 96 | 22,433 / 55,445 |
| System imbalance | 60 | 8,096 / 21,303 | not measured here | not measured here |

Prefer short windows for mix and minute imbalance. Use energy/quality tools when only totals or coverage are needed. The maximum 24-hour bound prevents uncontrolled downloads but does not guarantee a comfortable model context. No records are silently truncated.

## Running checks

| Layer | How to check |
|---|---|
| Offline suite | Follow [development setup](../CONTRIBUTING.md), then `python -m pytest -q` |
| Protocol | Follow [Inspector setup](clients.md), discover schemas, then make a short tools/call |
| Live Elia | Set `ENERGY_MCP_LIVE=1`, then run `python -m pytest tests/test_live.py -m live -s` |
| Scripted demo | With the same opt-in, run `python examples/run_public_demo.py` |
| Client | Configure a compatible host and inspect the scenarios above |

Default tests block unmarked provider HTTP and do not depend on Elia or an external model. Live checks are opt-in and should use small windows. Coverage diagnostics measure availability, not physical plausibility or settlement validation. No MCP/Elia certification or endorsement is implied; see [data terms](../THIRD_PARTY.md) and [security](../SECURITY.md).
