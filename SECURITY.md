# Security

Version 0.1.0 provides public, read-only electricity data and deterministic calculations over that data. It exposes fixed Elia HTTPS GET queries, validates timestamps and enums, bounds ranges and result counts, disables redirects, and limits retries. It exposes no arbitrary URL fetch, shell, filesystem, code-execution or market-action tool. The server has no LLM provider dependency or LLM credentials.

The published CLI uses local stdio. The MCP host launches the process and decides which tools to call. Host configuration, host credentials and model behavior are outside this server's boundary. The repository also supplies a separate Cloudflare Streamable HTTP adapter for bounded public-data demonstrations; do not expose a bare stdio process as an unprotected HTTP service. No security certification or independent penetration test is claimed.

The hosted boundary adds native ingress and every-attempt Elia budgets, a 64 KiB body limit, explicit Host/Origin checks, controlled errors and operational-only telemetry. It exposes the same eight read-only tools and two resources, no private data store, arbitrary network proxy, shell/filesystem access, writes or trading. Public data and rate limiting do not make the service immune to abuse; counters are approximate per Cloudflare location and shared client IPs may share admission. See the [remote security and operations policy](docs/remote-security.md) for exact limits, privacy/retention, authentication recommendation and reversible shutdown instructions.

Provider data may be missing, provisional or revised. Coverage diagnostics are not physical validation, settlement certification or trading advice. Avoid placing secrets in date arguments or changing the fixed provider endpoint to an untrusted destination. Logs should contain operational counts/errors rather than data dumps or credentials.

## Reporting a vulnerability

Do not post credentials, raw authenticated host traces or an exploit containing sensitive information in a public issue. For a public repository, use its GitHub **Security → Advisories → Report a vulnerability** option if available, or an owner-published private contact. If neither exists, open a minimal issue requesting a private reporting channel without including vulnerability details or secrets.

This is a pre-1.0 project; fixes target the latest 0.1 release. No response-time guarantee is offered. A repository owner should confirm the private reporting channel before accepting sensitive reports.
