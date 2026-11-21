# Hosted MCP security and operations

This policy applies to the deployment adapter, not to
the installed stdio CLI. It adds no energy tools, datasets, trading, arbitrary
network, shell, filesystem or code-execution capability. The same eight-tool
factory, immutable PyPI core and Elia contracts remain authoritative.

## Threat model and admission policy

| Priority | Threat | Protection and remaining limit |
|---|---|---|
| High | Repeated or distributed calls amplify Elia traffic | Native ingress plus **every-attempt** upstream budgets. Approximate and location-local, not a worldwide quota. |
| High | Mix/minute data, long ranges and retries cost more than discovery | Each actual Elia page/retry consumes upstream admission; no guessed billing weights. An exhausted budget stops without returning partial data. |
| High | Malformed/large messages and probing consume runtime | SDK 64 KiB incremental body cap, explicit routes/methods, controlled errors. Admission happens before body parsing. Platform checks still run; Worker admission cannot eliminate invocation cost. |
| Medium | Retry storms/concurrency | At most three attempts per page, sequential pagination, two connections per request client, aggregate burst/sustained native admission. No process-wide concurrency claim. |
| Medium | Prompts, tool arguments or credentials leak through diagnostics | Allow-listed JSON telemetry; verbose SDK/provider/HTTP logs suppressed; no persisted request logs or traces. |
| Low impact, still rejected | Arbitrary network proxy/write attempts | Fixed core contracts plus hosted transport allowlist of six Elia HTTPS GET paths; no redirects or arbitrary URL input. |

The `test` Wrangler environment configures the hosted workers.dev service. The exact policy is checked into `deploy/cloudflare/wrangler.jsonc`:

| Binding | Namespace | Budget | Key/scope |
|---|---:|---|---|
| MCP_INGRESS | 1001 | 60 MCP POSTs / 60 s | Client IP hash, per Cloudflare location |
| MCP_AGGREGATE | 1002 | 120 MCP POSTs / 60 s | All callers, per location |
| ELIA_BURST | 1003 | 20 Elia attempts / 10 s | All callers, per location |
| ELIA_BUDGET | 1004 | 120 Elia attempts / 60 s | All callers, per location |

These budgets support discovery and interactive multi-tool queries. They are
service limits, not published Elia provider quotas. IP is not a user identity: ChatGPT/shared NAT egress
may share a budget. The Worker uses Cloudflare's ingress `CF-Connecting-IP`, never
a caller-supplied user ID. A missing/invalid IP uses one shared fallback key.
The hash is used only by the native counter, never emitted as telemetry; it is
not represented as anonymization or stored in an application database.

An ingress refusal returns HTTP 429 with `Retry-After: 60`. Exhausted upstream
admission returns a controlled MCP tool error `remote_capacity_limited` asking
the client to retry after 60 seconds. Every attempted provider request, including
failed retries and each pagination page, is charged; denial itself sends no Elia
request and is not retried by the core. A binding failure fails closed with a
generic 503 or `remote_protection_unavailable`, without a binding diagnostic.

Host/Origin/method failures do not consume MCP admission. Health does not consume
MCP or Elia admission. Unknown routes never contact Elia. Normal local configuration
has no native bindings. The public environment requires all four through
`MCP_PROTECTION_REQUIRED=true`; do not unset it on an internet-facing deployment.
Check namespace collisions before deploying to another account.

Native counters are [approximate and separate in each Cloudflare location](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/).
They can overshoot and cannot guarantee a strict maximum number of worldwide
requests or concurrent invocations. Distributed attackers can still consume Worker
resources and multiple locations' budgets. A strict global provider budget would
require coordination, such as a Durable Object, which is deliberately not added
for this small demonstration. Suspend the public route if that limitation becomes
material; do not advertise this as a high-availability or unlimited public API.

## Provider correctness, cost and caching

The core requires explicit-offset timestamps, UTC quarter-hour-aligned
start/end, `[start,end)`, and at most **24 elapsed hours**. Its page size is 100,
maximum 5,000 raw rows, with consistency checks and no silent partial return.
Pages are awaited sequentially. Each HTTPX client has two connections, a 20-second
timeout and 5-second connect timeout. These are per-client limits, not a global
concurrency semaphore. Multiple hosted requests may run concurrently.

Retries are limited to three attempts per page for network errors and selected 429/5xx
responses. Default backoff is 0.25 then 0.5 seconds; numeric Retry-After is honored
only up to five seconds. Longer/non-numeric retry instructions stop with a useful
error. Every retry also needs hosted admission, preventing an exhausted budget
from producing another retry burst.

Heavy queries naturally cost more upstream units: a complete 24-hour minute series
usually takes 15 pages, while mix depends on the number of categories and wind on
the five raw components. Discovery/resources/health make no provider calls. Budgets count actual provider attempts rather than assigning per-tool weights.

Responses are not cached. Elia can revise historical values and quality status, including settlement validation. Separate queries can therefore return different revisions; each response includes retrieval provenance. No result is silently truncated.

Workers execution, native rate checks, telemetry and provider subrequests consume platform resources. Rejected requests can still incur invocation and CPU usage. Rate counters are not spending caps. Maintainers should review [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/) and account limits when sizing a deployment.

## Service availability

The hosted demo is best-effort and has no uptime or response-time SLA. Runtime CPU limits can cause HTTP 503 / Cloudflare 1102 errors even for valid queries. If failures recur, use the local stdio server; repeatedly retrying does not increase the available CPU budget. HTTP 429 and upstream-capacity errors have separate retry guidance above.

The current hosted service uses Workers Free. Its 10 ms CPU allowance per request is insufficient for reliable execution of this Python MCP workload. For a dedicated deployment, choose runtime capacity that accommodates server initialization, validation, normalization and serialization. See [Workers resource limits](https://developers.cloudflare.com/workers/platform/limits/). Provider availability and publication delays are separate from runtime capacity.

## Public HTTP and authentication boundary

Only POST `/mcp` and GET/HEAD `/health` are implemented. Unsupported MCP methods
return 405; unrelated paths and `/mcp/` return 404, with no slash redirect. Health
returns only `{"status":"ok","service":"energy-mcp-belgium"}`, no Elia request,
versions, account, environment or internal health diagnostics.

MCP request bodies are limited to 64 KiB, including chunked bodies. The SDK owns
protocol parsing, current stateless requests and legacy initialization. Explicit
Host and Origin allowlists stay enabled: bad Host 421, bad Origin 403; origin-less
backend clients work. Wildcard domains, wildcard Origins and wildcard browser CORS
are not accepted. Do not derive the allowed Host from an untrusted request header.

Hosted argument errors remove raw input echoes and SDK validation internals while
retaining useful argument guidance. Known safe core failures retain their codes;
unexpected failures are generic. Logs never include exception text/stack traces.
Cancelling a legacy call can defer cleanup until the request-scoped ASGI lifespan
ends; no provider/background job is intentionally retained after the response.

The hosted endpoint does not require authentication: it exposes public Elia data through read-only, bounded queries, with fixed network destinations and no private data store or account actions. These restrictions do not guarantee protection against distributed abuse. Private data, market actions, individual user quotas or guaranteed service levels require a separate authentication and capacity design.

[WAF custom rules](https://developers.cloudflare.com/waf/custom-rules/)
are zone-scoped; a workers.dev deployment cannot attach its own zone WAF policy to Cloudflare's
workers.dev zone. [workers.dev Browser Integrity Check](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)
still applies and cannot be disabled here. No interactive bot challenge is added
to MCP POSTs. Some default automated User-Agents may be rejected before the Worker;
use descriptive client identification, not disabled TLS or weakened security.

## Observability and retention

The adapter emits these bounded JSON event types to stdout (Worker console):

| Event | Allowed operational fields |
|---|---|
| http_request | Known route or `other`, HTTP status, outcome, duration_ms |
| mcp_request | Allow-listed protocol method/tool or `other`/null, outcome, safe error_code, record_count, duration_ms |
| elia_attempt | Allow-listed dataset, attempted flag, upstream status, outcome, duration_ms |
| worker_rejection | Fixed failure outcome only |

MCP `isError` outcomes are counted separately from HTTP status: HTTP 200 is not
proof of tool success. Attempt timing covers admission plus transport-to-response
headers, not complete body normalization. MCP/HTTP timing covers their respective
processing lifetimes; none of these are rigorous latency benchmarks.

No complete prompt, conversation, arguments/date ranges, request ID, full IP or IP
hash, account ID, URI/probe path, full response/record, raw exception, authorization,
cookie or secret is emitted. Tool/resource/provider semantics are not inferred by
parsing full response bodies; official SDK middleware observes their wire outcome.
Verbose SDK/HTTPX/shared-core diagnostics are suppressed only in the HTTP adapter.
The stdio CLI does not import this module and keeps its protocol stdout untouched.

Keep `observability.enabled=true`, query redaction on, **invocation_logs=false**,
**logs.persist=false**, and traces disabled. There is **no retained Workers Logs
dataset under this configuration**. Live tail is transient unless a maintainer
explicitly saves it. Cloudflare's platform request envelope can contain connection
metadata/headers even though application messages do not: do not save/publish raw
tail output. If retaining evidence, extract only allowlisted application messages
and aggregate timings into a private local summary. No external log destination or long-term analytics DB.

[Built-in aggregate Worker metrics](https://developers.cloudflare.com/workers/observability/metrics-and-analytics/)
provide invocation/request/error/CPU/wall-time observations and can be inspected for
up to three months, in week-sized ranges. They do not distinguish MCP tool errors
from HTTP-success invocations or contain historical tool-level counters. Use the
sanitized live events during a demo to inspect tool/provider failures and 429s.
This deliberate privacy tradeoff means detailed historical tool failure counts are
unavailable when no live capture is running. Sampled/platform metrics can lag or
omit events; report only the observed dataset, time window and precision.

Enabling persisted logs changes metadata retention and cost. Consult [Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) for plan-specific retention and pricing before enabling it. Disabling application-log persistence does not erase Cloudflare platform, security or account metadata.

## Deploy, inspect, suspend and recover

Run local tests, Ruff, formatting, mypy, docs, build/Twine and distribution checks.
Push reviewed changes without force and wait for all required CI jobs on the
exact source commit. From the deployment directory, use the pinned tooling:

```sh
npm ci
uv run --locked pywrangler deploy --env test --var MCP_ALLOWED_HOSTS:energy-mcp-belgium.YOUR-SUBDOMAIN.workers.dev
uv run --locked pywrangler tail --env test --format json
```

Keep credentials and account identifiers in private deployment settings, not
source; the public endpoint hostname is documented in the deployment guide. Use Wrangler OAuth login; never paste tokens/passwords into chat or files.
Confirm all four active bindings, exact Host, no Origin wildcard and non-persisted
observability after deployment. Inspector and the connected ChatGPT must still
discover exactly eight unchanged tools. Test short real requests, invalid inputs
and a bounded sequence of no-provider resource discovery requests for 429; do not
load-test Elia. Legacy ping is not a current-protocol discovery replacement.

To stop public access reversibly, set **env.test.workers_dev=false** (not only the
top-level local value), retain preview_urls=false, and redeploy the reviewed
configuration. Or disable the Worker route in the dashboard immediately, then
update source so the next deploy cannot re-enable it accidentally. There are no
custom routes/domains. Verify the old public URL stops serving MCP. Do not delete
the Worker, GitHub repository or package as an emergency shutdown mechanism.

For recovery, review the chosen known-good commit/config and its CI, redeploy
with the explicit hostname, then repeat health, Inspector and ChatGPT regressions.
An older version may lack protections; confirm that the selected version includes all required admission controls. Verify the resulting route state after every recovery change.
