# Experimental Streamable HTTP transport

A Cloudflare Python Worker exposes the same eight-tool Python registry over MCP Streamable HTTP. See [architecture](architecture.md), [validation methodology](validation.md) and the [hosted security and operations policy](remote-security.md). The hosted service is experimental and subject to an unresolved CPU capacity gate.

## Two entry points, one core

```text
energy_mcp_belgium.server.create_server()
  ├─ existing main() → stdio → installed CLI / python -m energy_mcp_belgium
  └─ deployment create_http_app() → SDK Streamable HTTP ASGI → Python Worker
```

The PyPI package/stdio commands remain unchanged. There is no `remote_tools.py`, second provider implementation or duplicated analytics. The HTTP adapter and Worker imports live under `deploy/cloudflare/`, outside the runtime wheel.

The current deployment dependency is the immutable `energy-mcp-belgium==0.1.0` wheel, with MCP SDK **2.3.0** pinned. Its runtime source matches this checkout. If shared core code changes later, update the approved wheel/source dependency and rerun parity tests before deploying; never copy the tool implementations into the Worker. A future release can use a wheel built from an approved same-repository commit without first uploading it to PyPI.

## Protocol behavior

The implementation follows the [current MCP Streamable HTTP specification, revision 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) and [official Python SDK ASGI API](https://py.sdk.modelcontextprotocol.io/run/asgi/). It is not the obsolete SSE-only transport.

- Exact endpoint: `POST /mcp`.
- Stateless SDK transport, no issued MCP session IDs and no persistent session storage.
- JSON responses by default; the adapter can also emit request-scoped SSE, tested offline.
- Current protocol requests work without a handshake; legacy SDK initialize/discovery/calls also work.
- `GET`, `DELETE` and `OPTIONS /mcp` return 405. No standalone legacy GET event stream is retained.
- `/mcp/` does not redirect; unknown paths return 404.
- Request bodies are capped at 64 KiB before MCP parsing. Existing Python range, timestamp, enum, row and provider-attempt limits remain authoritative.
- `GET /health` returns only `{"status":"ok","service":"energy-mcp-belgium"}` and makes no Elia request. HEAD has normal Starlette health-route behavior. Health is liveness, not an upstream availability check.

## Local Python/ASGI development

From a source checkout, install the normal development environment:

```sh
python -m pip install -e ".[dev]"
python -m uvicorn energy_mcp_http:create_http_app --factory --app-dir deploy/cloudflare/src --host 127.0.0.1 --port 8797
```

This is an explicit separate HTTP command; `energy-mcp-belgium` still starts stdio. The ASGI factory's defaults accept only loopback hosts and no browser Origins. A bare HTTP run uses the real fixed Elia provider; required automated tests inject synthetic HTTPX transports instead.

## Local Cloudflare runtime

Prerequisites: Node >=22.12, uv (tested 0.13.9), and the target-compatible Python runtime selected by pywrangler. Tool versions are locked: Wrangler 4.166.0, workers-py 1.17.9, workers-runtime-sdk 1.9.6. The verified workerd target was Python 3.14.2. Worker tooling is not a core runtime dependency.

```sh
cd deploy/cloudflare
npm ci
uv run --locked pywrangler dev --local --ip 127.0.0.1 --port 8797
```

No Cloudflare login is required for this local-only invocation. `workers_dev` and preview URLs are disabled in the default local configuration. The separately named `test` environment enables the hosted route and requires native protection bindings; use `--env test` locally to exercise them with simulated counters. Deploy only a reviewed, CI-passing source commit using the explicit approved hostname.

**Windows cross-drive caveat:** uv's Pyodide interpreter probe can fail with `No module named 'python'` when the project and interpreter cache are on different drives. Use a same-drive checkout/workspace or a pinned Linux build environment. Do not bypass dependency or security checks to suppress it.

## Inspector

With a supported Node runtime, the official Inspector CLI can use the local HTTP URL directly:

```sh
npx --yes @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8797/mcp --transport http --method tools/list --format json
```

One explicitly bounded manual live call:

```sh
npx --yes @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8797/mcp --transport http --method tools/call --tool-name get_solar_generation --tool-arg start=2026-11-18T12:00:00Z end=2026-11-18T12:15:00Z --format json
```

The observed local workerd response had source Elia, dataset ods209, one record, zero missing values, MW units and UTC timestamps. It is historical data and may be revised. Both existing resources (`energy://belgium/datasets`, `energy://belgium/methodology`) were also read through HTTP. Raw tool output should stay local.

## Worker lifecycle and configuration

`entry.py:Default.fetch()` reads explicit allowlists, constructs a fresh app inside the request, and delegates to the official Workers ASGI bridge. Do not move `create_server()` or `create_http_app()` to Worker module startup: MCP 2.3.0 creates ephemeral random security material, which Workers forbids at startup. The bridge owns request-scoped ASGI startup/shutdown, HTTPX cleanup and SDK task-group shutdown.

CPython uvicorn uses its normal process lifespan. In legacy stateless compatibility mode, a cancelled call's provider task can be cleaned up at lifespan shutdown; the Worker lifespan is request-scoped. The automated cancellation test verifies provider cancellation and closure on shutdown, rather than claiming immediate cross-request legacy cancellation. Modern protocol cancellation uses the SDK. No application jobs are intentionally retained after a Worker response.

Bindings:

| Variable | Meaning |
|---|---|
| `MCP_ALLOWED_HOSTS` | Comma-separated explicit host authorities. Local config allows loopback hosts with ports. No wildcard domain; wildcard ports are accepted only for loopback. |
| `MCP_ALLOWED_ORIGINS` | Comma-separated complete HTTP(S) Origins, without path, credentials or wildcard; empty rejects every present browser Origin. |

Missing/invalid Worker allowlists fail closed with a generic 503 configuration error. A missing Origin from a server-to-server MCP client is accepted if Host is allowed; an invalid Origin returns 403, an invalid Host 421. SDK checks cover both `/mcp` and health. Wildcard CORS is not enabled. Merely allowing an Origin does not add CORS response headers: current Inspector/OpenAI backend clients do not require a browser application API. Add narrowly scoped CORS only if a later browser client actually needs it.

Do not derive the public allowlist from an untrusted incoming Host header. Configure the actual approved workers.dev hostname at deployment, enable only the intended test route and validate Host forwarding and the real clients. No account ID, account hostname, token or developer filesystem path is hard-coded in the deployment files. The deployed endpoint is `https://energy-mcp-belgium.junaidbashir392.workers.dev/mcp`; it remains experimental and subject to the CPU capacity gate in the security policy.

## Security and logging

The eight tools retain their original read-only annotations, fixed Elia GET endpoint, six dataset allowlist, no redirects, aware timestamps, UTC quarter-hour bounds, start < end, 24-hour maximum, enums and row/retry caps. HTTP adds no arbitrary fetch, write, shell, filesystem, database, code-execution or market capability. No application OAuth or storage was added. The named hosted test environment has native ingress and actual-attempt upstream admission, described in the [security policy](remote-security.md).

The adapter emits bounded HTTP, MCP and Elia-attempt metadata to stdout: safe method/tool/dataset labels, status/outcome, record counts and duration. It never prints request arguments, bodies, time-series data, headers, cookies, IP keys, exception text or query strings. No HTTP adapter module is imported by the stdio CLI, whose stdout remains exclusively the MCP wire. Verbose SDK/provider/HTTPX diagnostics are suppressed remotely. Application telemetry also covers rejection/cancellation; MCP errors are separate from HTTP success. Invocation logs, persistence and traces remain off.

This public-data demonstration has no user authentication. The [threat model and operational policy](remote-security.md) document its limitations, responsible Elia access, caching decision and shutdown procedure. Native counters are approximate per location, not strict global quotas or a global concurrency cap. No Durable Objects, D1, KV, R2, containers or TypeScript tool port are required.

## Automated verification

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python examples/check_docs.py
python -m build
python -m twine check --strict dist/*
python examples/verify_distribution.py
```

Normal tests use no Elia/Cloudflare/ChatGPT services. Both HTTPX client generations are blocked from real network access in unmarked tests. Transport tests use a real stdio subprocess and the official MCP HTTP client over an in-process ASGI transport. They compare complete tool schemas (including annotations) and all eight representative results. The only intentionally volatile scientific field removed is `metadata.retrieved_at`, recursively including nested quality metadata. Hosted input errors deliberately omit SDK raw-value echoes/dependency details; rejection semantics and known safe provider/domain error codes remain equivalent. Hardening tests also cover page/retry charging, fail-closed admission, proxy prevention and telemetry privacy.

Cases include solar, wind, load, mix, physical imbalance, price, energy and quality; 100 MWh arithmetic, gaps/nulls/duplicates; invalid timestamps, naive/numeric times, range reversal, >24 hours, off-grid bounds and wind enums; upstream unavailability/contract failures; both resources; legacy initialize and current stateless requests; JSON/SSE; concurrency; body limits; no redirects; Host/Origin; no-upstream health; sanitized logging; Worker per-request app construction and lifespan cancellation/closure.

The small `typings/workers` stub describes only the bridge surface from workers-runtime-sdk 1.9.6 for strict CPython type checking; it is not a vendored runtime or a fake Worker implementation. Actual Worker behavior is additionally validated in local workerd.

## Distribution and future release

The wheel remains core-only and retains the existing console/module entry points. Public deployment sources/configuration/locks and typing stubs are intentionally included in source builds so transport tests remain runnable. Vendored `python_modules`, node_modules, Worker state, environments, generated target locks, credentials and local evidence are excluded. The existing production PyPI release remains 0.1.0; repository deployment and documentation updates do not replace its published artifacts.

Keep Cloudflare-specific imports deployment-only; do not add Cloudflare tooling to ordinary runtime requirements merely to expose local stdio.

## Hosted deployment and recovery

Current endpoint: `https://energy-mcp-belgium.junaidbashir392.workers.dev/mcp`.

The named `test` environment enables workers.dev; the checked-in localhost allowlist intentionally rejects public requests until explicitly overridden. From `deploy/cloudflare`, deploy a reviewed source commit after its CI passes:

```sh
npm ci
uv run --locked pywrangler deploy --env test --var MCP_ALLOWED_HOSTS:energy-mcp-belgium.junaidbashir392.workers.dev
uv run --locked pywrangler tail --env test --format json
```

The four native bindings implement 60 MCP requests/minute/client IP, 120 aggregate/minute/location, 20 Elia attempts/10 seconds/location and 120 Elia attempts/minute/location. Every provider page/retry needs admission. These approximate counters are not global quotas. Inspect only sanitized application messages; raw tail envelopes can contain private platform metadata. Logs are not persisted and invocation logging/tracing remain off. See the [exact policy and shutdown/recovery procedures](remote-security.md).

After a deploy, verify health, all eight schemas, a short source query and deterministic analytics. The [validation guide](validation.md#cloudflare-remote-mcp-and-chatgpt) records tested Inspector/ChatGPT scenarios and the remaining CPU blocker. The Free plan's 10 ms CPU allowance is below the measured Python workload; successful requests do not establish capacity or uptime. No custom domain, persistent store or application OAuth is configured.

For rollback, select a reviewed known-good version on the Worker dashboard Deployments page, or redeploy its reviewed source/configuration. An older version may lack admission controls. Preserve the same hostname and verify its protection bindings and output parity. A rollback does not resolve the known CPU-capacity issue. To suspend access reversibly, disable the named environment's workers.dev route as described in the security policy; do not delete the service.
