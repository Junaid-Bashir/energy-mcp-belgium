"""Hosted protections: real SDK dispatch and mocked provider/binding boundaries."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import httpx
import pytest
from energy_mcp_http import create_http_app
from energy_mcp_security import GuardedEliaTransport, ProtectionUnavailable
from test_remote_transport import http_client
from transport_fixtures import ARGS, Provider

from energy_mcp_belgium.elia.client import EliaClient
from energy_mcp_belgium.errors import EnergyError

URL = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods001/records"


async def test_all_pages_and_retries_consume_upstream_budget(monkeypatch, capsys):
    from energy_mcp_belgium.elia import client as module

    charged, offsets, sleeps = [], [], []

    async def admit():
        charged.append(True)
        return True

    async def sleep(seconds):
        sleeps.append(seconds)

    def provider(request):
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        if len(offsets) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "total_count": 250,
                "results": [{"test": i} for i in range(offset, min(offset + 100, 250))],
            },
        )

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    guard = GuardedEliaTransport(admit, httpx.MockTransport(provider))
    async with httpx.AsyncClient(transport=guard) as wire:
        assert len(await EliaClient(wire).records("ods001", "private-query-marker")) == 250
    assert offsets == [0, 0, 100, 200] and len(charged) == 4 and sleeps == [0.25]
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["status"] for e in logs] == [503, 200, 200, 200]
    assert all(e["event"] == "elia_attempt" and e["attempted"] for e in logs)
    assert "private-query-marker" not in json.dumps(logs)


@pytest.mark.parametrize("broken", [False, True])
async def test_exhausted_or_broken_upstream_budget_fails_closed_without_core_retry(broken, capsys):
    calls = []

    async def admit():
        calls.append(True)
        if broken:
            raise RuntimeError("private-binding-secret C:/internal/path")
        return False

    def provider(request):
        pytest.fail("Denied admission must not send an Elia request")

    async with httpx.AsyncClient(
        transport=GuardedEliaTransport(admit, httpx.MockTransport(provider))
    ) as wire:
        with pytest.raises(EnergyError) as caught:
            await EliaClient(wire).records("ods001", "ignored")
    assert len(calls) == 1
    assert caught.value.code == (
        "remote_protection_unavailable" if broken else "remote_capacity_limited"
    )
    output = capsys.readouterr().out
    assert "private-binding-secret" not in str(caught.value) + output
    assert "internal/path" not in str(caught.value) + output
    assert not json.loads(output)["attempted"]


async def test_budget_exhaustion_stops_a_provider_retry_storm(monkeypatch):
    from energy_mcp_belgium.elia import client as module

    admissions, sent = [], []

    async def admit():
        admissions.append(True)
        return len(admissions) == 1

    async def sleep(seconds):
        pass

    def provider(request):
        sent.append(request)
        return httpx.Response(503)

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(
        transport=GuardedEliaTransport(admit, httpx.MockTransport(provider))
    ) as wire:
        with pytest.raises(EnergyError, match="remote_capacity_limited"):
            await EliaClient(wire).records("ods001", "ignored")
    assert len(sent) == 1 and len(admissions) == 2


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", URL),
        ("GET", "http://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods001/records"),
        ("GET", "https://attacker.example/records"),
        ("GET", URL.replace("ods001", "unapproved")),
        ("GET", URL.replace("opendata.elia.be", "opendata.elia.be:8443")),
        ("GET", URL.replace("opendata.elia.be", "user:secret@opendata.elia.be")),
    ],
)
async def test_hosted_transport_is_not_an_arbitrary_proxy(method, url):
    async def admit():
        pytest.fail("Disallowed destination must not consume upstream budget")

    def provider(request):
        pytest.fail("Disallowed destination reached provider")

    async with httpx.AsyncClient(
        transport=GuardedEliaTransport(admit, httpx.MockTransport(provider))
    ) as wire:
        with pytest.raises(EnergyError, match="not allowed"):
            await wire.request(method, url)


async def test_telemetry_observes_real_tool_outcomes_without_values(capsys, caplog):
    async with http_client(Provider()) as client:
        ok = await client.call_tool("get_load", ARGS)
        bad = await client.call_tool("get_load", {**ARGS, "start": "private-prompt-secret"})
        assert ok.structured_content["metadata"]["record_count"] == 4
        assert bad.is_error and "invalid_request" in bad.content[0].text
        assert "private-prompt-secret" not in bad.content[0].text
        assert "pydantic" not in bad.content[0].text
        unknown = await client.call_tool("private-tool-secret", {})
        assert unknown.is_error and "private-tool-secret" not in unknown.content[0].text
    output = capsys.readouterr().out
    assert all(
        marker not in output + caplog.text
        for marker in [
            "private-prompt-secret",
            "private-tool-secret",
            ARGS["start"],
            "total_load_mw",
        ]
    )
    events = [json.loads(line) for line in output.splitlines()]
    calls = [e for e in events if e["event"] == "mcp_request" and e["method"] == "tools/call"]
    assert calls[0]["outcome"] == "success" and calls[0]["record_count"] == 4
    assert calls[1]["outcome"] == "tool_error" and calls[1]["error_code"] == "invalid_request"
    assert calls[2]["tool"] is None and calls[2]["outcome"] == "tool_error"


async def test_provider_failure_is_distinct_from_http_success_in_telemetry(capsys, monkeypatch):
    from energy_mcp_belgium.elia import client as module

    async def sleep(seconds):
        pass

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    async with http_client(Provider("unavailable")) as client:
        assert (await client.call_tool("get_load", ARGS)).is_error
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(e.get("tool") == "get_load" and e["outcome"] == "provider_error" for e in events)
    assert any(e["event"] == "http_request" and e["status"] == 200 for e in events)


async def test_http_failure_boundary_never_exposes_binding_exception_or_probe_path(capsys):
    async def broken():
        raise ProtectionUnavailable("private-binding-error C:/internal/path")

    app = create_http_app(admission=broken)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as wire:
        r = await wire.post("/mcp", content=b"private-body-secret")
        assert r.status_code == 503 and r.headers["retry-after"] == "60"
        assert r.json() == {"error": "service_temporarily_unavailable"}
        assert (await wire.get("/private-probe-secret")).status_code == 404
        assert (await wire.get("/health")).json() == {
            "status": "ok",
            "service": "energy-mcp-belgium",
        }
    output = capsys.readouterr().out
    assert all(
        s not in output + r.text
        for s in [
            "private-binding-error",
            "internal/path",
            "private-body-secret",
            "private-probe-secret",
        ]
    )


async def test_worker_requires_all_bindings_and_health_does_not_charge(monkeypatch):
    fake = types.ModuleType("workers")
    fake.WorkerEntrypoint = type("WorkerEntrypoint", (), {})

    class Response:
        def __init__(self, body, *, status):
            self.body, self.status = body, status

    class Binding:
        def __init__(self):
            self.keys = []

        async def limit(self, options):
            self.keys.append(options["key"])
            return types.SimpleNamespace(success=False)

    async def bridge(app, request, env, ctx):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://localhost"
            ) as wire:
                return await wire.request(request.method, request.path)

    fake.Response = Response
    fake.asgi = types.SimpleNamespace(fetch=bridge)
    monkeypatch.setitem(sys.modules, "workers", fake)
    path = Path(__file__).parents[1] / "deploy/cloudflare/src/entry.py"
    spec = importlib.util.spec_from_file_location("hardened_entry_test", path)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    worker = entry.Default()
    worker.ctx = object()
    worker.env = types.SimpleNamespace(
        MCP_PROTECTION_REQUIRED="true", MCP_ALLOWED_HOSTS="localhost"
    )
    request = types.SimpleNamespace(
        method="GET", path="/health", headers={"CF-Connecting-IP": "203.0.113.7"}
    )
    assert (await worker.fetch(request)).status == 503
    bindings = [Binding() for _ in range(4)]
    for name, binding in zip(
        ["MCP_INGRESS", "MCP_AGGREGATE", "ELIA_BURST", "ELIA_BUDGET"], bindings, strict=True
    ):
        setattr(worker.env, name, binding)
    assert (await worker.fetch(request)).status_code == 200
    assert not any(b.keys for b in bindings)
    request.method, request.path = "POST", "/mcp"
    assert (await worker.fetch(request)).status_code == 429
    assert len(bindings[0].keys) == 1 and len(bindings[0].keys[0]) == 64
    assert "203.0.113.7" not in bindings[0].keys[0]
    assert not any(b.keys for b in bindings[1:])
