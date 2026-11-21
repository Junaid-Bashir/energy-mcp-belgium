"""Inspect local archives and verify a wheel in a fresh isolated environment.

Run after python -m build. Installs dependencies from configured pip indexes;
no provider data is requested and nothing is published.
"""

import json
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path


def run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    wheels, sdists = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("Require exactly one wheel and one sdist in dist/.")
    wheel, sdist = wheels[0], sdists[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        required = {
            "energy_mcp_belgium/server.py",
            "energy_mcp_belgium/py.typed",
            "energy_mcp_belgium/elia/client.py",
        }
        if (
            not required <= set(names)
            or not any(n.endswith("licenses/LICENSE") for n in names)
            or not any(n.endswith("licenses/THIRD_PARTY.md") for n in names)
        ):
            raise RuntimeError("Wheel is missing runtime files or license.")
        wheel_count = len(names)
    with tarfile.open(sdist) as archive:
        source_names = archive.getnames()
        for suffix in [
            "docs/elia-data.md",
            "tests/test_core.py",
            "THIRD_PARTY.md",
            ".github/workflows/ci.yml",
            "examples/verify_distribution.py",
            "SECURITY.md",
            "deploy/cloudflare/src/entry.py",
            "deploy/cloudflare/src/energy_mcp_http.py",
            "deploy/cloudflare/src/energy_mcp_security.py",
            "deploy/cloudflare/typings/workers/__init__.pyi",
            "deploy/cloudflare/wrangler.jsonc",
            "deploy/cloudflare/uv.lock",
        ]:
            if not any(n.endswith("/" + suffix) for n in source_names):
                raise RuntimeError(f"Sdist missing {suffix}")
    for name in [*names, *source_names]:
        parts = Path(name).parts
        if (
            {
                "__pycache__",
                ".local",
                ".integration",
                "node_modules",
                "python_modules",
                ".wrangler",
            }.intersection(parts)
            or name.endswith((".pyc", ".jsonl", ".log"))
            or any("venv" in p for p in parts)
            or Path(name).name
            in {"implementation-report.md", "acceptance-review.md", "client-integration.md"}
            or Path(name).name.startswith((".dev.vars", ".env"))
        ):
            raise RuntimeError(f"Unexpected build artifact: {name}")

    with tempfile.TemporaryDirectory(prefix="energy-mcp-wheel-") as directory:
        temp = Path(directory).resolve()
        environment = temp / "env"
        venv.create(environment, with_pip=True)
        bindir = environment / ("Scripts" if sys.platform == "win32" else "bin")
        python = bindir / ("python.exe" if sys.platform == "win32" else "python")
        entry = bindir / (
            "energy-mcp-belgium.exe" if sys.platform == "win32" else "energy-mcp-belgium"
        )
        run([str(python), "-m", "pip", "install", str(wheel)], temp)
        # The demo imports the installed package; the checkout src is absent from sys.path.
        demo = run([str(python), str(root / "examples" / "demo.py")], temp)
        if '"energy_mwh": 101.5' not in demo:
            raise RuntimeError("Installed-wheel mocked MCP demo failed.")
        guard = temp / "startup_guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import httpx\n"
            "async def blocked(*args, **kwargs):\n"
            "    raise RuntimeError('Provider network forbidden during startup/discovery')\n"
            "httpx.AsyncHTTPTransport.handle_async_request = blocked\n",
            encoding="utf-8",
        )
        script = """
import asyncio, json, sys
from pathlib import Path
import energy_mcp_belgium
from mcp import Client
from mcp.client.stdio import StdioServerParameters
assert "site-packages" in str(Path(energy_mcp_belgium.__file__))
async def main():
    for command, args in [(sys.executable, ["-m", "energy_mcp_belgium"]), (sys.argv[1], [])]:
        async with Client(StdioServerParameters(command=command, args=args, env={"PYTHONPATH": sys.argv[2]})) as c:
            tools = (await c.list_tools()).tools
            assert len(tools) == 8 and all(t.output_schema for t in tools)
            resource = await c.read_resource("energy://belgium/datasets")
            assert json.loads(resource.contents[0].text)["solar"]["provider"] == "elia"
            result = await c.call_tool("get_load", {"start":"2026-11-01T00:00:00Z", "end":"2026-11-01T00:00:00Z"})
            assert result.is_error
asyncio.run(main())
print("installed module and console stdio passed; startup/discovery provider network blocked")
"""
        print(run([str(python), "-c", script, str(entry), str(guard)], temp).strip())
    print(
        json.dumps(
            {
                "wheel_members": wheel_count,
                "sdist_members": len(source_names),
                "fresh_install": "passed",
                "mocked_mcp_demo": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
