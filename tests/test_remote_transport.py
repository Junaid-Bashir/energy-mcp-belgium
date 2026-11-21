import asyncio
import importlib.util
import json
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import httpx2
import pytest
from energy_mcp_http import MAX_REQUEST_BYTES, create_http_app, host_allowlist, origin_allowlist
from mcp import Client
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from transport_fixtures import ARGS, Provider, stable

TOOLS = {
    "get_solar_generation",
    "get_wind_generation",
    "get_load",
    "get_generation_mix",
    "get_system_imbalance",
    "get_imbalance_prices",
    "calculate_energy",
    "check_data_quality",
}


@asynccontextmanager
async def http_client(provider, json_response=True):
    app = create_http_app(transport=provider.transport(), json_response=json_response)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app), base_url="http://localhost"
        ) as wire:
            async with streamable_http_client("http://localhost/mcp", http_client=wire) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    yield session


@asynccontextmanager
async def stdio_client(mode="complete"):
    async with Client(
        StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("transport_stdio_server.py")), mode],
        )
    ) as client:
        yield client


async def test_exact_stdio_http_schemas_and_resources():
    provider = Provider()
    async with stdio_client() as local, http_client(provider) as remote:
        a = (await local.list_tools()).tools
        b = (await remote.list_tools()).tools
        assert {t.name for t in b} == TOOLS
        assert [t.model_dump(by_alias=True) for t in a] == [t.model_dump(by_alias=True) for t in b]
        for uri in ("energy://belgium/datasets", "energy://belgium/methodology"):
            assert (await local.read_resource(uri)).contents == (
                await remote.read_resource(uri)
            ).contents
    assert not provider.requests and provider.closed


@pytest.mark.parametrize(
    "tool,extra",
    [
        ("get_solar_generation", {}),
        ("get_wind_generation", {}),
        ("get_load", {}),
        ("get_generation_mix", {}),
        ("get_system_imbalance", {}),
        ("get_imbalance_prices", {}),
        ("calculate_energy", {"series": "solar"}),
        ("check_data_quality", {"series": "load"}),
    ],
)
async def test_real_stdio_http_result_equivalence(tool, extra):
    async with stdio_client() as local, http_client(Provider()) as remote:
        a = await local.call_tool(tool, {**ARGS, **extra})
        b = await remote.call_tool(tool, {**ARGS, **extra})
        assert not a.is_error and not b.is_error
        assert stable(a.structured_content) == stable(b.structured_content)
        if tool == "calculate_energy":
            assert b.structured_content["energy_mwh"] == 100
            assert b.structured_content["quality"]["coverage_pct"] == 100
        elif tool.startswith("get_"):
            assert isinstance(
                next(iter(b.structured_content["records"][0]["values"].values())), float
            )
            assert b.structured_content["metadata"]["source"] == "elia"


@pytest.mark.parametrize("mode,expected", [("null", 75), ("gap", 75), ("complete", 100)])
async def test_observed_energy_nulls_gaps_and_coverage(mode, expected):
    async with stdio_client(mode) as local, http_client(Provider(mode)) as remote:
        for tool, extra in [
            ("get_solar_generation", {}),
            ("calculate_energy", {"series": "solar"}),
        ]:
            a = await local.call_tool(tool, {**ARGS, **extra})
            b = await remote.call_tool(tool, {**ARGS, **extra})
            assert not a.is_error and not b.is_error
            assert stable(a.structured_content) == stable(b.structured_content)
            if tool == "calculate_energy":
                assert b.structured_content["energy_mwh"] == expected
                assert b.structured_content["quality"]["coverage_pct"] == expected
            elif mode == "null":
                assert b.structured_content["records"][1]["values"]["generation_mw"] is None


@pytest.mark.parametrize(
    "tool,changes",
    [
        ("get_solar_generation", {"start": "invalid"}),
        ("get_solar_generation", {"start": "2026-11-18T12:00:00"}),
        ("get_solar_generation", {"start": 1795000000}),
        ("get_solar_generation", {"start": ARGS["end"]}),
        ("get_solar_generation", {"end": "2026-11-19T13:00:00Z"}),
        ("get_solar_generation", {"start": "2026-11-18T12:01:00Z"}),
        ("get_wind_generation", {"wind_type": "invalid"}),
    ],
)
async def test_invalid_inputs_equivalent_and_no_provider_access(tool, changes):
    provider = Provider()
    async with stdio_client() as local, http_client(provider) as remote:
        a = await local.call_tool(tool, {**ARGS, **changes})
        b = await remote.call_tool(tool, {**ARGS, **changes})
        assert a.is_error and b.is_error
        if a.content != b.content:
            # Hosted validation removes SDK input-value echoes/dependency details.
            assert "invalid_request" in b.content[0].text
            assert "errors.pydantic.dev" not in b.content[0].text
        assert "Traceback" not in b.content[0].text
    assert not provider.requests


@pytest.mark.parametrize(
    "mode,code",
    [
        ("unavailable", "provider_unavailable"),
        ("contract", "dataset_contract_error"),
        ("duplicate", "dataset_contract_error"),
    ],
)
async def test_provider_errors_equivalent_and_sanitized(mode, code):
    async with stdio_client(mode) as local, http_client(Provider(mode)) as remote:
        a = await local.call_tool("get_solar_generation", ARGS)
        b = await remote.call_tool("get_solar_generation", ARGS)
        assert a.is_error and b.is_error and a.content == b.content
        assert code in b.content[0].text and "Traceback" not in b.content[0].text


async def test_health_routes_host_origin_and_no_sensitive_logging(caplog, capsys):
    provider = Provider()
    app = create_http_app(
        transport=provider.transport(), allowed_origins=["https://client.example"]
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as wire:
            r = await wire.get(
                "/health",
                headers={"Authorization": "secret-auth-marker", "Cookie": "secret-cookie-marker"},
            )
            assert r.json() == {"status": "ok", "service": "energy-mcp-belgium"}
            assert (
                await wire.get("/health", headers={"Origin": "https://client.example"})
            ).status_code == 200
            assert (
                await wire.get("/health", headers={"Origin": "https://bad.invalid"})
            ).status_code == 403
            assert (await wire.get("/mcp", headers={"Host": "bad.invalid"})).status_code == 421
            assert (await wire.get("/mcp", headers={"Origin": "null"})).status_code == 403
            assert (await wire.get("/mcp/")).status_code == 404
            assert (await wire.get("/debug")).status_code == 404
            assert (await wire.post("/health")).status_code == 405
            assert (await wire.options("/mcp")).status_code == 405
            assert "access-control-allow-origin" not in r.headers
    assert not provider.requests and provider.closed
    assert "secret-auth-marker" not in caplog.text and "secret-cookie-marker" not in caplog.text
    output = capsys.readouterr().out
    assert "secret-auth-marker" not in output and "secret-cookie-marker" not in output
    assert any(json.loads(line)["event"] == "http_request" for line in output.splitlines())


async def test_wire_initialize_stateless_body_caps_and_bad_json():
    provider = Provider()
    app = create_http_app(transport=provider.transport())
    headers = {"Accept": "application/json, text/event-stream"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as wire:
            r = await wire.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "offline-test", "version": "1"},
                    },
                },
            )
            assert r.status_code == 200 and "result" in r.json()
            assert "mcp-session-id" not in r.headers
            assert (await wire.get("/mcp", headers=headers)).status_code == 405
            assert (await wire.delete("/mcp", headers=headers)).status_code == 405
            r = await wire.post(
                "/mcp", headers={**headers, "Content-Type": "application/json"}, content="{"
            )
            assert r.status_code == 400 and "Traceback" not in r.text
            r = await wire.post(
                "/mcp",
                headers={**headers, "Content-Type": "application/json"},
                content="x" * (MAX_REQUEST_BYTES + 1),
            )
            assert r.status_code == 413
    assert not provider.requests


async def test_current_protocol_stateless_requests_without_handshake():
    provider = Provider()
    app = create_http_app(transport=provider.transport())
    metadata = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "offline-modern", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/list",
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as wire:
            r = await wire.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {"_meta": metadata},
                },
            )
            assert r.status_code == 200 and len(r.json()["result"]["tools"]) == 8
            assert "mcp-session-id" not in r.headers and not provider.requests
            r = await wire.post(
                "/mcp",
                headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "get_solar_generation"},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "get_solar_generation",
                        "arguments": ARGS,
                        "_meta": metadata,
                    },
                },
            )
            assert r.status_code == 200
            result = r.json()["result"]["structuredContent"]
            assert result["metadata"]["record_count"] == 4 and result["metadata"]["unit"] == "MW"


@pytest.mark.parametrize("json_response", [True, False])
async def test_response_modes_and_concurrent_calls(json_response):
    async with http_client(Provider(), json_response) as remote:
        solar, price = await asyncio.gather(
            remote.call_tool("get_solar_generation", ARGS),
            remote.call_tool("get_imbalance_prices", ARGS),
        )
        assert not solar.is_error and not price.is_error
        assert solar.structured_content["metadata"]["unit"] == "MW"
        assert price.structured_content["metadata"]["unit"] == "EUR/MWh"


async def test_cancelled_http_request_closes_provider_and_lifespan():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingTransport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def aclose(self):
            self.closed = True

    transport = BlockingTransport()
    app = create_http_app(transport=transport)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as wire:
            task = asyncio.create_task(
                wire.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-11-25",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "get_load", "arguments": ARGS},
                    },
                )
            )
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    # Legacy stateless dispatch may finish cleanup at lifespan shutdown. Workers
    # run this lifespan per request, rather than retaining a process-wide session.
    await asyncio.wait_for(cancelled.wait(), 1)
    assert transport.closed


async def test_worker_constructs_independent_apps_and_fails_closed(monkeypatch):
    fake_workers = types.ModuleType("workers")
    fake_workers.WorkerEntrypoint = type("WorkerEntrypoint", (), {})

    class WorkerResponse:
        def __init__(self, body, *, status):
            self.body, self.status = body, status

    apps = []

    async def bridge(app, request, env, ctx):
        apps.append(app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://localhost"
            ) as wire:
                return await wire.get("/health")

    fake_workers.Response = WorkerResponse
    fake_workers.asgi = types.SimpleNamespace(fetch=bridge)
    monkeypatch.setitem(sys.modules, "workers", fake_workers)
    path = Path(__file__).parents[1] / "deploy/cloudflare/src/entry.py"
    spec = importlib.util.spec_from_file_location("worker_entry_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    worker = module.Default()
    worker.ctx = object()
    worker.env = types.SimpleNamespace()
    assert (await worker.fetch(object())).status == 503
    worker.env = types.SimpleNamespace(MCP_ALLOWED_HOSTS="localhost", MCP_ALLOWED_ORIGINS="")
    for _ in range(2):
        response = await worker.fetch(object())
        assert response.status_code == 200
    assert len(apps) == 2 and apps[0] is not apps[1]


async def test_temporary_admission_protection_preserves_health_and_rejects_before_provider():
    attempts = []

    async def reject():
        attempts.append(True)
        return False

    app = create_http_app(admission=reject)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as wire:
        assert (await wire.get("/health")).status_code == 200
        assert (await wire.get("/mcp")).status_code == 405
        assert (
            await wire.post("/mcp", headers={"Origin": "https://bad.invalid"})
        ).status_code == 403
        response = await wire.post("/mcp", content=b"not parsed or forwarded")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        assert response.json() == {"error": "temporarily_rate_limited"}
    assert attempts == [True]


@pytest.mark.parametrize(
    "host",
    [
        "*",
        "*.workers.dev",
        "https://worker.example",
        "user@worker.example",
        "worker.example/path",
        "worker.example:bad",
    ],
)
def test_host_configuration_fails_closed(host):
    with pytest.raises(ValueError):
        host_allowlist(host)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://*.example",
        "https://user@worker.example",
        "https://worker.example/path",
    ],
)
def test_origin_configuration_fails_closed(origin):
    with pytest.raises(ValueError):
        origin_allowlist(origin)
