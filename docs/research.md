# Official sources and implementation choices

Reference check: **19 November 2026**. External APIs and clients can change; update the documented source contract and tests together when their behavior changes.

## MCP

- [Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [Official Python SDK v2](https://py.sdk.modelcontextprotocol.io/whats-new/), tested with mcp 2.3.0
- [Tools](https://py.sdk.modelcontextprotocol.io/servers/tools/), [structured outputs](https://py.sdk.modelcontextprotocol.io/servers/structured-output/) and [resources](https://py.sdk.modelcontextprotocol.io/servers/resources/)
- [Lifecycle](https://py.sdk.modelcontextprotocol.io/handlers/lifespan/), [transport](https://py.sdk.modelcontextprotocol.io/run/), [errors](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/) and [testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/)

The package uses the official high-level MCPServer API and typed Pydantic output models. Local stdio fits a host-launched process; the experimental remote adapter is documented separately in the [deployment guide](remote-mcp.md). A lifespan owns the shared HTTP client. Stable resource endpoints expose dataset identities and methodology. Analytics fetches its source directly, avoiding mutable session handles and record resubmission. Python 3.11+ is the chosen baseline; plain records avoid a pandas dependency.

## Elia

The [official catalog](https://opendata.elia.be/api/explore/v2.1/catalog/datasets?limit=100), per-dataset metadata and small records queries establish the six [source contracts](elia-data.md). The portal links to the platform's [Explore v2.1 API reference](https://help.opendatasoft.com/apis/ods-explore-v2/). Use fixed GET records endpoints with explicit filters and bounded pagination; do not substitute forecast fields for actuals.

The [Elia Open Data Licence](https://opendata.elia.be/pages/licence/) is separate from the software license. See [third-party notices](../THIRD_PARTY.md) for dependency and data references. Client-specific sources and tested versions are in [client setup](clients.md).
