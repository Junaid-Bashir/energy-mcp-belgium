# Package releases

The production package is [energy-mcp-belgium](https://pypi.org/project/energy-mcp-belgium/). Published versions are immutable: documentation or deployment updates do not replace package archives. See [installation](getting-started.md) and [release notes](release-notes-0.1.0.md).

## Package identity

| Setting | Value |
|---|---|
| Distribution and CLI | `energy-mcp-belgium` |
| Python import | `energy_mcp_belgium` |
| Python requirement | 3.11+ |
| Software license | MIT |
| Repository | https://github.com/Junaid-Bashir/energy-mcp-belgium |

Elia data has separate [license and attribution terms](../THIRD_PARTY.md). Keep provider contracts, units and public schemas consistent with the version being released.

## Release checks

Run from a clean checkout of the intended release commit:

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python examples/check_docs.py
python -m build
python -m twine check --strict dist/*
python examples/verify_distribution.py
```

Use a clean build directory containing exactly one wheel and one sdist. Inspect both for source/license completeness and the absence of credentials, private paths, environments, transcripts, caches and local output. The distribution verifier installs the wheel outside the checkout and checks console/module stdio discovery with provider networking blocked. Hosted CI must pass on the exact source commit.

## Registry publishing

GitHub OIDC Trusted Publishing avoids long-lived upload tokens. Configure the publisher for the exact repository owner/name, workflow filename and environment; see [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/). Protect the `testpypi` and `pypi` environments with appropriate branch/reviewer controls. Build/test jobs need no upload permission; only publishing jobs receive `id-token: write`.

The repository has two distinct workflows:

- `publish-testpypi.yml`: manually dispatched on `main`, targeting TestPyPI through the `testpypi` environment.
- `publish-pypi.yml`: triggered by a published GitHub Release, targeting production PyPI through the `pypi` environment. Its version/tag/commit guards are specific to v0.1.0. Review and update those guards before using the workflow for another version; it is not a general-purpose publishing template.

Release maintainers must review the version, artifact identity, workflow conditions and environment approval before publishing. Never republish an existing version, reuse a version label for different archives, or move a published release tag to different source. Documentation-only changes do not require a package release. Ordinary pushes to `main` do not publish to either registry.

TestPyPI and production PyPI are separate services. Configure and approve their publishers separately. Check package-name availability directly; a public 404 does not reserve a name. Pending publishers create the project on first upload; see [the official pending-publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Verify registry artifacts

Download the intended version without resolving dependencies from TestPyPI. For example, to inspect 0.1.0:

```sh
python -m pip download --index-url https://test.pypi.org/simple/ --no-deps --only-binary=:all: --dest downloaded energy-mcp-belgium==0.1.0
```

Compare the downloaded SHA-256 with the registry's `digests.sha256` and the same publishing run's build artifact. Matching version labels alone do not establish byte identity; different build environments can produce different archives.

Install the downloaded wheel into a fresh environment outside the source checkout, using production PyPI for dependencies:

```sh
python -m venv registry-env
# Activate registry-env using your platform's activation command.
python -m pip install --index-url https://pypi.org/simple/ ./downloaded/energy_mcp_belgium-0.1.0-py3-none-any.whl
python -m pip check
python -c "import energy_mcp_belgium, importlib.metadata; print(energy_mcp_belgium.__file__); print(importlib.metadata.version('energy-mcp-belgium'))"
```

Check site-packages origin, both stdio launch forms, and all eight tool schemas with the official MCP client or [Inspector](clients.md). Make one bounded Elia query and verify source, dataset, UTC timestamps, units and quality status. Confirm deterministic analytics and coverage using synthetic data. Do not combine TestPyPI with an extra dependency index or publish raw authenticated logs.

After a production upload, repeat hash, clean-install, schema and bounded-query checks against production PyPI. Keep software versioning separate from hosted deployment configuration and provider-data revisions.
