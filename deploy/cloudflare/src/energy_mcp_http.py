"""Deployment-only ASGI adapter; all MCP semantics live in the shared factory."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from time import monotonic
from urllib.parse import urlsplit

import httpx
from energy_mcp_security import ProtectionUnavailable, emit, operational_middleware
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from energy_mcp_belgium.server import create_server

LOCAL_HOSTS = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*")
MAX_REQUEST_BYTES = 64 * 1024


def host_allowlist(value: str) -> tuple[str, ...]:
    """Accept explicit hosts; only loopback hosts may use a wildcard port."""
    hosts = tuple(part.strip() for part in value.split(",") if part.strip())
    if not hosts:
        raise ValueError("An explicit MCP_ALLOWED_HOSTS allowlist is required")
    for host in hosts:
        if host in LOCAL_HOSTS:
            continue
        parsed = urlsplit("//" + host)
        if (
            not parsed.hostname
            or parsed.netloc != host
            or parsed.path
            or parsed.username
            or parsed.password
            or any(c in host for c in "*?#@\\ \t\r\n")
        ):
            raise ValueError("Invalid allowed host")
        # Accessing port also rejects malformed/non-numeric port values.
        _ = parsed.port
    return hosts


def origin_allowlist(value: str) -> tuple[str, ...]:
    origins = tuple(part.strip() for part in value.split(",") if part.strip())
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
            or any(c.isspace() for c in origin)
        ):
            raise ValueError("Invalid allowed origin")
        _ = parsed.port
    return origins


class TransportBoundary:
    """Apply SDK Host/Origin checks to every route; log only bounded metadata."""

    def __init__(
        self,
        app: ASGIApp,
        security: TransportSecuritySettings,
        admission: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self.app = app
        self.security = TransportSecurityMiddleware(security)
        self.admission = admission

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = monotonic()
        status = 500
        response_started, response_complete = False, False
        outcome = "http_error"

        async def observed_send(message: Message) -> None:
            nonlocal status, response_started, response_complete
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                response_complete = True
            await send(message)

        try:
            rejection = await self.security.validate_request(Request(scope))
            if rejection is not None:
                await rejection(scope, receive, observed_send)
            elif scope["path"] == "/mcp" and scope["method"] != "POST":
                # Stateless Streamable HTTP has no standalone legacy GET/SSE
                # channel or DELETE session. Request-scoped SSE POSTs still work.
                await Response(status_code=405, headers={"Allow": "POST"})(
                    scope, receive, observed_send
                )
            elif scope["path"] == "/mcp" and self.admission and not await self.admission():
                await JSONResponse(
                    {"error": "temporarily_rate_limited"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )(scope, receive, observed_send)
            else:
                await self.app(scope, receive, observed_send)
            outcome = (
                "rate_limited" if status == 429 else "success" if status < 400 else "http_error"
            )
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception as exc:
            outcome = (
                "protection_unavailable"
                if isinstance(exc, ProtectionUnavailable)
                else "internal_error"
            )
            if not response_started:
                await JSONResponse(
                    {"error": "service_temporarily_unavailable"},
                    status_code=503,
                    headers={"Retry-After": "60"},
                )(scope, receive, observed_send)
            elif not response_complete:
                # Never append diagnostic data to an already-started response.
                await observed_send({"type": "http.response.body", "body": b""})
        finally:
            # Python Workers maps stdout to console.log. This module is never
            # imported by the stdio CLI, whose stdout remains the MCP wire.
            emit(
                "http_request",
                route=scope["path"] if scope["path"] in {"/mcp", "/health"} else "other",
                status=status,
                outcome=outcome,
                duration_ms=round((monotonic() - started) * 1000, 1),
            )


def create_http_app(
    *,
    allowed_hosts: Sequence[str] = LOCAL_HOSTS,
    allowed_origins: Sequence[str] = (),
    transport: httpx.AsyncBaseTransport | None = None,
    json_response: bool = True,
    admission: Callable[[], Awaitable[bool]] | None = None,
) -> Starlette:
    """Build inside Worker fetch; never construct an MCP server at Worker startup."""
    hosts = host_allowlist(",".join(allowed_hosts))
    origins = origin_allowlist(",".join(allowed_origins))
    # Library diagnostics can include request URLs or exception payloads. Remote
    # telemetry deliberately uses the small allowlisted record above instead.
    for name in ("mcp", "httpx", "httpcore", "httpx2", "httpcore2", "energy_mcp_belgium"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    security = TransportSecuritySettings(allowed_hosts=list(hosts), allowed_origins=list(origins))
    server = create_server(transport)
    server.middleware.append(operational_middleware)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=json_response,
        max_request_body_size=MAX_REQUEST_BYTES,
        transport_security=security,
    )

    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "energy-mcp-belgium"})

    app.router.routes.append(Route("/health", health, methods=["GET"]))
    app.router.redirect_slashes = False
    app.add_middleware(TransportBoundary, security=security, admission=admission)
    return app
