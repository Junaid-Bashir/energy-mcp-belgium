# Contributing

## Development setup

Python 3.11+ from a checkout:

```sh
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python examples/check_docs.py
python -m build
python examples/verify_distribution.py
```

CI is configured for Linux and Windows, Python 3.11–3.14. Local validation was performed on Windows Python 3.12; a configured matrix is not a claim that remote jobs have already passed. Build and installation may contact package indexes. Offline tests require neither Elia nor an external model/client application.

## Tests and live checks

Default tests use small synthetic official-shaped responses through httpx.MockTransport and block unmarked provider HTTP. tests/test_core.py contains the fixture factory: field/dimension structure follows verified Elia metadata, while values are invented. Do not commit bulk provider downloads, raw host transcripts or credentials.

For ten opt-in one-hour Elia checks, enable the environment variable explicitly:

```powershell
$env:ENERGY_MCP_LIVE = "1"
python -m pytest tests/test_live.py -m live -s
Remove-Item Env:ENERGY_MCP_LIVE
```

In a POSIX shell: `ENERGY_MCP_LIVE=1 python -m pytest tests/test_live.py -m live -s`. Calls cover the six documented datasets, both wind subtypes and both analytics tools, two days before the run. Do not enable live tests in ordinary CI.

## Contracts and tools

To update a source, follow [contract maintenance](docs/elia-data.md): inspect official metadata, dimension values, units, interval semantics and source notices; update provider mappings, documentation and synthetic regressions together. Run tiny opt-in live checks when provider-facing behavior changes. Never substitute forecasts, fill missing values with zero or silently discard duplicate keys.

A tool change needs precise scope/units, typed input/output schemas, bounded requests and MCP-level tests using the official client. Keep Elia-specific field names inside the provider package. Update the tool reference and schema snapshot deliberately when the public contract changes. Do not add external mutations, arbitrary fetch/file/code tools, conversation storage or forecasting to v0.1.

## Optional Inspector validation

Inspector is developer tooling, not a runtime dependency. Follow the [tested client setup](docs/clients.md) to discover tools with examples/inspector-config.json. For bounded live checks, `python examples/validate_inspector.py --help` describes the separate Node/Inspector/installed-server paths and local output directory. This runner contacts Elia and writes raw local output; keep that directory ignored. It is not required in CI.

## Distribution and public content

Build wheel/sdist and run the fresh-install verifier before proposing a release. Check relative links with examples/check_docs.py. Keep documentation focused on users, contributors and maintainers. Audit publication candidates for secrets and machine paths. Software is MIT licensed; Elia data has separate terms. Publication requires an explicit owner decision.
