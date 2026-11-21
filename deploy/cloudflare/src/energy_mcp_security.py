"""Hosted-only upstream admission and allow-listed operational telemetry."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from time import monotonic

import httpx
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from energy_mcp_belgium.elia.client import EliaClient
from energy_mcp_belgium.elia.datasets import CONTRACTS
from energy_mcp_belgium.errors import EnergyError

Admission = Callable[[], Awaitable[bool]]
TOOLS = frozenset(
    {
        "get_solar_generation",
        "get_wind_generation",
        "get_load",
        "get_generation_mix",
        "get_system_imbalance",
        "get_imbalance_prices",
        "calculate_energy",
        "check_data_quality",
    }
)
METHODS = frozenset(
    {
        "initialize",
        "notifications/initialized",
        "ping",
        "tools/list",
        "tools/call",
        "resources/list",
        "resources/read",
        "resources/templates/list",
        "prompts/list",
        "notifications/cancelled",
    }
)
ERROR_CODES = frozenset(
    {
        "invalid_request",
        "provider_unavailable",
        "provider_response_error",
        "dataset_contract_error",
        "remote_capacity_limited",
        "remote_protection_unavailable",
    }
)


def emit(event: str, **fields: str | int | float | bool | None) -> None:
    """Only callers in this module/adapter supply fixed field names and safe values."""
    print(json.dumps({"event": event, **fields}, separators=(",", ":")))


class ProtectionUnavailable(Exception):
    """Fail closed without leaking a binding/Cloudflare exception."""


class GuardedEliaTransport(httpx.AsyncBaseTransport):
    """Charge every real Elia GET attempt, including retry and pagination traffic."""

    def __init__(self, admission: Admission, inner: httpx.AsyncBaseTransport | None = None):
        self.admission = admission
        # Custom HTTPX transports own their connection pool, so set its limit here.
        self.inner = (
            inner
            if inner is not None
            else httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=2)
            )
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        allowed_paths = {
            f"/api/explore/v2.1/catalog/datasets/{c.dataset_id}/records" for c in CONTRACTS.values()
        }
        if (
            request.method != "GET"
            or request.url.scheme != "https"
            or request.url.host != "opendata.elia.be"
            or request.url.port not in {None, 443}
            or request.url.path not in allowed_paths
            or request.url.userinfo
        ):
            raise EnergyError("invalid_request", "Hosted provider destination is not allowed.")
        dataset = request.url.path.split("/")[-2]
        started = monotonic()
        outcome, status, attempted = "protection_unavailable", None, False
        try:
            try:
                allowed = await self.admission()
            except Exception:
                raise EnergyError(
                    "remote_protection_unavailable", "Hosted admission is unavailable; retry later."
                ) from None
            if not allowed:
                outcome = "rate_limited"
                # EnergyError bypasses the core's HTTPX/network retry loop.
                raise EnergyError(
                    "remote_capacity_limited",
                    "Hosted Elia budget exhausted; retry after 60 seconds.",
                )
            attempted = True
            outcome = "network_error"
            response = await self.inner.handle_async_request(request)
            status = response.status_code
            outcome = "success" if status == 200 else "upstream_error"
            return response
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            emit(
                "elia_attempt",
                dataset=dataset,
                attempted=attempted,
                outcome=outcome,
                status=status,
                duration_ms=round((monotonic() - started) * 1000, 1),
            )

    async def aclose(self) -> None:
        await self.inner.aclose()


async def operational_middleware(
    ctx: ServerRequestContext[EliaClient], call_next: CallNext
) -> HandlerResult:
    """Observe the SDK's validated outcome, never serialize raw params or results."""
    method = ctx.method if ctx.method in METHODS else "other"
    candidate = (ctx.params or {}).get("name") if method == "tools/call" else None
    tool = candidate if isinstance(candidate, str) and candidate in TOOLS else None
    started = monotonic()
    outcome, error_code, records = "internal_error", None, None
    try:
        result = await call_next(ctx)
        outcome = "success"
        # SDK middleware receives the protocol-version-shaped wire dict, not
        # the handler's CallToolResult model. Do not deserialize the full series.
        if method == "tools/call" and isinstance(result, dict):
            if result.get("isError"):
                outcome = "tool_error"
                text = next(
                    (
                        c.get("text", "")
                        for c in result.get("content", [])
                        if isinstance(c, dict) and c.get("type") == "text"
                    ),
                    "",
                )
                wrapper = f"Error executing tool {tool}:"
                diagnostic = text[len(wrapper) :].lstrip() if text.startswith(wrapper) else text
                prefix = diagnostic.split(":", 1)[0]
                error_code = prefix if prefix in ERROR_CODES else "tool_error"
                if error_code.startswith("provider_") or error_code == "dataset_contract_error":
                    outcome = "provider_error"
                elif error_code == "remote_capacity_limited":
                    outcome = "rate_limited"
                elif error_code == "remote_protection_unavailable":
                    outcome = "protection_unavailable"
                # SDK validation strings include raw rejected values and dependency
                # details. Keep hosted errors useful without exposing that material.
                if tool is None or (text.startswith(wrapper) and prefix not in ERROR_CODES):
                    error_code, outcome = "invalid_request", "tool_error"
                    result = {
                        **result,
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "invalid_request: Use a supported tool and documented arguments: "
                                    "ISO 8601 timestamps with explicit offsets, UTC quarter-hour boundaries, "
                                    "start < end, at most 24 hours, and permitted series/wind types."
                                ),
                            }
                        ],
                    }
            elif isinstance(result.get("structuredContent"), dict):
                metadata = result["structuredContent"].get("metadata")
                value = metadata.get("record_count") if isinstance(metadata, dict) else None
                if type(value) is int and 0 <= value <= 5000:
                    records = value
        return result
    except ValidationError:
        outcome, error_code = "protocol_error", "invalid_request"
        raise MCPError(code=-32602, message="Invalid MCP request parameters.") from None
    except MCPError:
        outcome, error_code = "protocol_error", "protocol_error"
        raise
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    except Exception:
        raise MCPError(code=-32603, message="Internal server error.") from None
    finally:
        emit(
            "mcp_request",
            method=method,
            tool=tool,
            outcome=outcome,
            error_code=error_code,
            record_count=records,
            duration_ms=round((monotonic() - started) * 1000, 1),
        )
