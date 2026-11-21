# Releasing Energy MCP Belgium

Version 0.1.0 is published on [production PyPI](https://pypi.org/project/energy-mcp-belgium/0.1.0/), using GitHub OIDC Trusted Publishing. Published artifacts are immutable; repository documentation and deployment updates do not replace them. The eight tools and six Elia contracts remain frozen. See the [getting started guide](getting-started.md) for installation.

The production publishing workflow is specific to the original v0.1.0 release and includes historical tag/commit guards. It is not a general-purpose workflow for republishing 0.1.0 or for a future version. Review and update those guards for any deliberately approved future release. Do not recreate a historical tag on a different source snapshot or publish a release merely to update documentation.

## Package identity and installation

Distribution and CLI: `energy-mcp-belgium`; import: `energy_mcp_belgium`; version: `0.1.0`; Python: 3.11+; software license: MIT. Elia data has separate terms in [third-party notices](../THIRD_PARTY.md).

Install from production PyPI:

```sh
python -m pip install energy-mcp-belgium
```

The installed command is `energy-mcp-belgium`; `python -m energy_mcp_belgium` starts the same stdio server. Python imports use:

```python
import energy_mcp_belgium
```

Configure a compatible host (with the installed environment on its PATH):

```json
{
  "mcpServers": {
    "energy-belgium": {"command": "energy-mcp-belgium", "args": []}
  }
}
```

The host chooses its model; the server requires no LLM API key. Runtime dependencies are MCP, HTTPX, Pydantic and Windows timezone data. The supported MCP range is `>=2.3,<3`, using the official SDK v2 API; 2.3.0 is the tested version, rather than an exact runtime pin. Earlier major/API versions are excluded; future v2 updates still need release verification.

## Owner-controlled TestPyPI setup

The workflow is prepared locally; it must be reviewed, committed and pushed before dispatch. No upload is implied by this document. Registry names must be rechecked immediately before publishing: a public 404 does not reserve a name.

1. Review the diff and run the quality gate below. Approve the exact source commit to publish.
2. In GitHub repository Settings → Environments, create `testpypi`. Restrict deployment to `main`, add a required reviewer, and prevent self-review where available. Do this before running the workflow; a workflow reference alone does not enable environment protection.
3. Authenticate directly at [TestPyPI](https://test.pypi.org/). Use Account settings → Publishing → Add a new pending publisher, at [the TestPyPI publishing settings](https://test.pypi.org/manage/account/publishing/).
4. Select GitHub and enter project `energy-mcp-belgium`, owner `Junaid-Bashir`, repository `energy-mcp-belgium`, workflow filename `publish-testpypi.yml`, environment `testpypi`. Do not include a path in the filename. Do not configure production PyPI here.
5. After explicit owner authorization, dispatch **Publish to TestPyPI** on `main`; review the exact commit and approve the environment deployment. Only the publish job receives `id-token: write`. Build/test jobs have no publishing permission. The endpoint is exclusively `https://test.pypi.org/legacy/`.
6. Inspect the resulting TestPyPI page, including README formatting, URLs, version, Python requirement and license. An existing immutable filename cannot be replaced; investigate a conflict rather than silently changing identity or version.

Never paste passwords, tokens, MFA or recovery codes into chat. [Official Trusted Publishing instructions](https://docs.pypi.org/trusted-publishers/using-a-publisher/) describe OIDC publishing without stored API tokens. [Pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) create the project on first upload and do not reserve its name.

## Exact remote artifact validation

Download only this distribution from TestPyPI, with no dependency resolution:

```sh
python -m pip download --index-url https://test.pypi.org/simple/ --no-deps --only-binary=:all: --dest downloaded energy-mcp-belgium==0.1.0
```

Compare the wheel's SHA-256 with `digests.sha256` from `https://test.pypi.org/pypi/energy-mcp-belgium/0.1.0/json` and the **same publishing run's** build artifact. A separate local build may differ if its source/build environment differs; investigate rather than treating matching version labels as proof of byte identity. Preserve the exact approved local candidate hash too.

Create a new environment outside the checkout, then install that downloaded wheel with dependencies from production PyPI only:

```sh
python -m venv registry-env
# Activate registry-env using your platform's activation command.
python -m pip install --index-url https://pypi.org/simple/ ./downloaded/energy_mcp_belgium-0.1.0-py3-none-any.whl
python -m pip check
python -c "import energy_mcp_belgium, importlib.metadata; print(energy_mcp_belgium.__file__); print(importlib.metadata.version('energy-mcp-belgium'))"
```

Verify site-packages origin, both launch forms, and exactly eight `tools/list` schemas with the official MCP client or [Inspector](clients.md). Compare complete names, descriptions, input and output schemas to the approved snapshot. Then run one bounded read-only Elia call, for example `get_imbalance_prices` over one historical hour. Check source, dataset, record count, timestamps, units and quality status. Keep raw evidence local. Do not mix TestPyPI with an extra dependency index.

## Local quality gate

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python examples/check_docs.py
python -m build
python -m twine check --strict dist/*
python examples/verify_distribution.py
```

Use a clean output directory with exactly one wheel and one sdist. Inspect both archives for private paths, credentials, local reports, environments, transcripts, caches and raw live output. Test synthetic integration (100 MW × four quarter-hours = 100 MWh), gaps, nulls, duplicates and coverage through the offline suite. The distribution verifier creates a fresh non-editable environment outside the checkout and checks module/console stdio startup with provider network blocked.

## Production publishing

Remote TestPyPI validation passed for commit `1138ac0`. The separate `publish-pypi.yml` workflow runs only for an intentional published GitHub Release named `v0.1.0`. It verifies package identity, frozen runtime source, tag ancestry and successful hosted CI on the exact release commit before building and verifying distributions. The protected `pypi` environment requires owner review; a separate production PyPI Trusted Publisher is tied to this workflow and environment. Only the publishing job receives OIDC permission. Ordinary pushes to `main` cannot publish.

Do not create or move a release tag until local checks and hosted CI pass. After upload, compare both production distribution hashes with the publishing run's artifacts, install from normal production PyPI in a new environment, and verify import origin, version, eight MCP tools, a bounded Elia call and deterministic analytics. Review the [release notes](release-notes-0.1.0.md) before publication. The tag must remain attached to the released commit; later installation-documentation changes belong in a separate commit.
