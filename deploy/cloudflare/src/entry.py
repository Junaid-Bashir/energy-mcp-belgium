"""Cloudflare Python Worker entry point. No business logic or tool definitions."""

from hashlib import sha256
from ipaddress import ip_address

from energy_mcp_http import create_http_app, host_allowlist, origin_allowlist
from energy_mcp_security import GuardedEliaTransport, ProtectionUnavailable, emit
from workers import Response, WorkerEntrypoint, asgi


class Default(WorkerEntrypoint):
    async def fetch(self, request: object) -> object:
        ingress = getattr(self.env, "MCP_INGRESS", None)
        aggregate = getattr(self.env, "MCP_AGGREGATE", None)
        upstream_burst = getattr(self.env, "ELIA_BURST", None)
        upstream_budget = getattr(self.env, "ELIA_BUDGET", None)
        required = getattr(self.env, "MCP_PROTECTION_REQUIRED", "false") == "true"
        bindings = (ingress, aggregate, upstream_burst, upstream_budget)
        if required and any(binding is None for binding in bindings):
            emit("worker_rejection", outcome="protection_unavailable")
            return Response('{"error":"service_temporarily_unavailable"}', status=503)
        protected = all(binding is not None for binding in bindings)

        # Cloudflare overwrites CF-Connecting-IP on public ingress. It is not a
        # user identity; shared egress/NATs share a budget. Never emit this key.
        headers = getattr(request, "headers", {})
        try:
            client_ip = str(ip_address(headers.get("CF-Connecting-IP", "")))
        except (ValueError, TypeError):
            client_ip = "shared"
        key = sha256(client_ip.encode()).hexdigest()

        async def admission() -> bool:
            assert ingress is not None and aggregate is not None
            try:
                individual = await ingress.limit({"key": key})
                if not individual.success:
                    return False
                result = await aggregate.limit({"key": "mcp-all"})
                return bool(result.success)
            except Exception:
                raise ProtectionUnavailable from None

        async def provider_admission() -> bool:
            assert upstream_burst is not None and upstream_budget is not None
            burst = await upstream_burst.limit({"key": "elia-all"})
            if not burst.success:
                return False
            budget = await upstream_budget.limit({"key": "elia-all"})
            return bool(budget.success)

        try:
            hosts = getattr(self.env, "MCP_ALLOWED_HOSTS", "")
            origins = getattr(self.env, "MCP_ALLOWED_ORIGINS", "")
            if not isinstance(hosts, str) or not isinstance(origins, str):
                raise ValueError("Invalid transport configuration")
            app = create_http_app(
                allowed_hosts=host_allowlist(hosts),
                allowed_origins=origin_allowlist(origins),
                admission=admission if protected else None,
                transport=GuardedEliaTransport(provider_admission) if protected else None,
            )
        except ValueError:
            return Response('{"error":"transport_not_configured"}', status=503)
        # This bridge owns ASGI startup/shutdown for this request, including
        # the shared factory's HTTPX client and SDK session-manager task group.
        try:
            return await asgi.fetch(app, request, self.env, self.ctx)
        except Exception:
            emit("worker_rejection", outcome="internal_error")
            return Response('{"error":"service_temporarily_unavailable"}', status=503)
