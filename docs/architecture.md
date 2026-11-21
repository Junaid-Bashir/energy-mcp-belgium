# Architecture

```text
MCP host → stdio or Streamable HTTP adapter → official SDK MCPServer
         → tools and typed Pydantic outputs
         → Elia normalization and verified contracts
         → focused httpx client → Elia Explore v2.1 GET records
```

`server.py` owns registration, two static discovery/methodology resources, user-facing ToolError conversion and a typed lifespan. One shared async HTTP client is closed on shutdown. `models.py` defines the public response shapes. `elia/datasets.py` contains provider-specific mappings and wind component identities. `elia/client.py` handles bounded pagination/retries. `elia/normalization.py` checks contracts and produces chronological UTC records. `analytics.py` holds deterministic functions. There is no provider abstraction hierarchy or pandas dependency.

All eight tools are read-only, idempotent queries with open-world annotations because their inputs come from an external provider. Analytics also fetches data. Dataset resources make no network requests. Expected errors use stable prefixes: `invalid_request`, `provider_unavailable`, `provider_response_error`, `dataset_contract_error`. No data is a successful structured response with `status=no_data`, empty records and zero count.

## Safety and operation

Only fixed Elia HTTPS paths and allowlisted dataset IDs are reachable through tools. Users supply typed dates/enums, never URLs, SQL, files or code. Redirects disabled. The core has no external writes, arbitrary network fetch tools, credentials, conversation storage, LLM libraries or persistent cache. The separate hosted adapter emits bounded operational metadata; see [hosted security](remote-security.md). HTTP connection pool has two connections; pagination is sequential. Requests project only required actual values, dimensions, time, resolution and quality fields; unused forecasts are not downloaded. Timeout: 5s connect, 20s per operation. Three attempts maximum for transport failures, HTTP 429 and selected 5xx statuses. Numeric Retry-After up to 5s is honored; longer/unparseable delays fail and ask callers to retry later. Responses are capped at 5000 raw rows; at 24h current datasets produce at most about 1440 minute or 1152 mix records. Nothing is silently truncated. Changing total counts between pages fails for retry.

Logging uses Python stderr, never datasets or prompts. Default is WARNING; INFO includes capability, provider dataset, count and elapsed time. No MCP-level log dependency. The deployment adapter reuses the same server factory and official SDK ASGI transport; see [remote deployment](remote-mcp.md). No database, chatbot or trading system.

## Client path

```text
MCP-compatible host
   -> Energy MCP Belgium (stdio tools)
      -> Elia Client
         -> Elia Open Data

MCP Host
   -> Energy MCP Belgium analytics tool
      -> bounded source fetch
         -> deterministic energy/quality calculation
```

The server supplies data and calculations. Natural-language selection and narrative belong to the host. See [client setup](clients.md).

## Remote runtime design

The Cloudflare Python Worker delegates to the official Workers ASGI bridge and the same Python server factory. Deployment-only imports and tooling stay outside the core wheel. Each fetch constructs its app inside request scope: the SDK generates security material that cannot be created at Worker module startup. ASGI lifespan closes the HTTP client and request tasks.

The SDK transport is stateless; it needs no session database or Durable Object. JSON replies are the default, with request-scoped SSE compatibility tested separately. Explicit Host/Origin checks, body limits, native ingress admission and fixed-destination upstream admission add protection without changing tool schemas or scientific calculations. The [security policy](remote-security.md) explains approximate per-location counters and residual distributed-traffic risks.

Reusing Python avoids duplicating source contracts and analytics in another language. A container would add image/runtime orchestration and is not part of this architecture. The current Python Worker exceeds the retained Free-plan CPU allowance, so the hosted endpoint remains experimental; architectural compatibility is not a claim of capacity or uptime.
