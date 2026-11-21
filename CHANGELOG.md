# Changelog

## 0.1.0 — 2026-11-19

First public package release.

- Eight read-only MCP tools covering Belgian solar, wind, load, generation mix, physical imbalance, imbalance prices, energy integration and data quality.
- Six documented Elia Open Data datasets with explicit units, timestamps, provenance and quality metadata.
- Deterministic MW-to-MWh integration and gap/null/duplicate/coverage diagnostics.
- Validated with the official MCP Inspector, bounded Elia requests, a real MCP host, clean-wheel installation and TestPyPI.
- Local stdio transport, bounded requests and fixed read-only provider access. No LLM API key required.

Queries are limited to 24 elapsed hours; detailed responses can be large. Host/model tool selection varies, and Elia records may be revised. Solar ods209 history begins on 26 October 2026. No forecasting or market actions are included.
