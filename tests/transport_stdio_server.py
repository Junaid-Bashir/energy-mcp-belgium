"""Test-only subprocess; never imported by the installed CLI or Worker."""

import sys

from transport_fixtures import Provider

from energy_mcp_belgium.server import create_server

if __name__ == "__main__":
    create_server(Provider(sys.argv[1] if len(sys.argv) > 1 else "complete").transport()).run(
        transport="stdio"
    )
