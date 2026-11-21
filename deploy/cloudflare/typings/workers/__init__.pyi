"""Small typing surface for the deployment-only, runtime-provided bridge.

Signatures mirror workers-runtime-sdk 1.9.6; no Worker implementation is vendored.
"""

from starlette.types import ASGIApp

class WorkerEntrypoint:
    env: object
    ctx: object

class Response:
    def __init__(self, body: str, *, status: int = ...) -> None: ...

class asgi:
    @staticmethod
    async def fetch(app: ASGIApp, request: object, env: object, ctx: object) -> object: ...
