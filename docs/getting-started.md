# Getting started

Install Python 3.11+ and create/activate a virtual environment, then install from production PyPI:

```sh
python -m pip install energy-mcp-belgium
```

For development, clone the repository and install `python -m pip install -e ".[dev]"` from that checkout. The demonstration scripts below are included in the source repository.

## Generic stdio launch description

This common `mcpServers` JSON shape is illustrative: host configuration envelopes vary. The installed CLI below is the stdio subprocess interface; ensure its environment is on the host PATH.

```json
{"mcpServers":{"energy-belgium":{"command":"energy-mcp-belgium","args":[]}}}
```

No working directory or credentials are required after installation. If the host does not inherit your environment, replace the command with your own absolute installed CLI path. No host-specific undocumented settings are required.

## Demonstration

```sh
python examples/demo.py
python examples/demo.py --live
```

Default demo uses synthetic official-shaped data via an HTTP mock and the real official MCP client, server, validation, normalization and structured output path. `--live` retrieves one hour, two days ago. `pytest tests/test_live.py -k stdio` also checks a real subprocess without accessing Elia.

## Questions for your host

- Get Belgian solar generation for yesterday (the host resolves Belgian calendar bounds and splits ranges over 24h).
- Show Belgian wind generation between 08:00 and 12:00 UTC.
- What was the system imbalance during this period?
- Calculate the total solar energy over this period.
- Is this load series complete?

The host chooses tools and resolves natural-language dates. The server has no natural-language router.

For local MCP and official Inspector setup, see [client setup](clients.md). Bare “imbalance” requests need clarification between MW system imbalance and EUR/MWh prices. Ask for MWh energy to use calculate_energy, which fetches its own source data.
