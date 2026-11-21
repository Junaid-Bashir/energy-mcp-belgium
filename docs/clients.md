# MCP clients

The server is model-provider independent. A host launches the installed executable, discovers the eight tools and decides how to interpret the user's request. Inspector is a developer aid, not a requirement for normal use.

## Installed stdio command

Install from production PyPI with `python -m pip install energy-mcp-belgium` in a virtual environment. Source checkouts also support `python -m pip install .`. Activate the installed environment before starting the host, or configure your own absolute installed CLI path. The server requires no working directory or LLM credentials.

```json
{"mcpServers":{"energy-belgium":{"command":"energy-mcp-belgium","args":[]}}}
```

This common JSON envelope is host-specific; the executable/arguments form the stdio contract. Use `Get-Command energy-mcp-belgium` in PowerShell or `command -v energy-mcp-belgium` in a POSIX shell to locate your installation. Both `energy-mcp-belgium` and `python -m energy_mcp_belgium` are supported; stdout is reserved for MCP traffic.

## MCP Inspector

Tested: official Inspector CLI **2.16.0** with Node **22.23.4**. Follow the [official CLI documentation](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md). Other versions have not been evaluated here; the GUI has not been tested.

With a supported Node runtime and the installed server on PATH:

```sh
npx --yes @modelcontextprotocol/inspector@2.16.0 --cli --config examples/inspector-config.json --server energy-belgium --method tools/list --format json
```

If your system Node is older, this command selects the specified runtime without replacing system Node:

```sh
npx --yes --package=node@22.23.4 --package=@modelcontextprotocol/inspector@2.16.0 mcp-inspector --cli --config examples/inspector-config.json --server energy-belgium --method tools/list --format json
```

Both commands download developer tooling if it is not cached. `tools/list` discovers schemas without requesting Elia records. For a bounded live call:

```sh
npx --yes @modelcontextprotocol/inspector@2.16.0 --cli energy-mcp-belgium --method tools/call --tool-name get_solar_generation --tool-arg start=2026-11-17T10:00:00Z --tool-arg end=2026-11-17T11:00:00Z --format json
```

The optional `examples/validate_inspector.py` runner requires explicit Node, Inspector, installed-command, working-directory and output paths; `--help` lists them. It makes fifteen bounded populated live calls, three invalid calls and one live no-data call, and stores output locally. Keep its output outside source control. It is not part of required CI.

## Remote Streamable HTTP

Endpoint: `https://energy-mcp-belgium.junaidbashir392.workers.dev/mcp`.

The hosted demo is best-effort and has no SLA. Runtime resource limits can cause HTTP 503 / Cloudflare 1102 errors; use local stdio if failures recur. See [service availability](remote-security.md#service-availability) and honor rate-limit retry guidance.

A concrete remote configuration depends on the client. With the supported Node runtime, use the official Inspector CLI:

```sh
npx --yes @modelcontextprotocol/inspector@2.16.0 --cli https://energy-mcp-belgium.junaidbashir392.workers.dev/mcp --transport http --method tools/list --format json
```

For ChatGPT, follow the [README connection steps](../README.md#use-with-chatgpt) and [current official OpenAI guide](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt). This server uses public-data access with no authentication. No universal remote `mcpServers` JSON format is assumed; use your client's documented Streamable HTTP URL setting, not an SSE-only transport.

## Reliable requests

Supply an explicit date, time range and timezone. Distinguish physical system imbalance in MW from settlement price in EUR/MWh. Ask for MWh energy to select calculate_energy; it fetches its own source. For generation-profile comparisons retrieve solar and wind records. Data-quality diagnostics require a named source and bounds. Host narration and tool selection may vary; [validation examples](validation.md) show the tested scope.
