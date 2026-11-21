# Energy MCP Belgium 0.1.0

First public Python package release: an open-source MCP server providing structured access to Belgian electricity-system data through Elia Open Data.

Eight read-only MCP tools provide solar generation, wind generation, load, generation mix, physical system imbalance, imbalance settlement prices, deterministic energy integration and data-quality diagnostics. Six explicit Elia Open Data contracts preserve timestamps, units, provenance and quality information.

Validation includes official MCP Inspector discovery, bounded live Elia queries, real MCP-host tool selection, synthetic deterministic analytics, clean-wheel installation and exact remote TestPyPI wheel installation. Eight installed tools and their complete schemas were verified against the reviewed snapshot.

Queries are bounded to 24 elapsed hours. The server exposes no arbitrary HTTP, shell, filesystem, code-execution or market-action tools and requires no LLM dependency or API key. Compatible hosts choose the model.

Detailed responses can be large; prefer short windows. Tool selection depends on the host/model. Elia historical records may lag, contain nulls or be revised; provisional prices are not validated for settlement. Solar ods209 starts on 26 October 2026; legacy history stitching is not implemented. Only local stdio and Elia are supported. No forecasting, weather, remote deployment or production certification is claimed.

Software is MIT licensed; Elia data retains its separate license and attribution requirements. See the [release procedure](releasing.md) and [validation evidence](validation.md).
