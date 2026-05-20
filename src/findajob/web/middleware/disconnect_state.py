"""ASGI middleware that records client-disconnect into scope state.

Follow-up to #743. Starlette's `StreamingResponse.__call__` spawns its own
`listen_for_disconnect` task that sits in `while True: await receive()`. A
naive watcher task polling `request.is_disconnected()` loses the
receive-channel race to that listener — by the time the watcher peeks,
Starlette has already consumed the disconnect message and the channel is
empty. The reverted attempt in commit 228a6ef proved this empirically.

This middleware wraps `receive` so every `http.disconnect` message is
recorded into `scope["findajob.client_disconnected"]` BEFORE being passed
downstream. Any inner caller — Starlette's listener, a route handler, a
streaming generator's `is_cancelled` callback — can read the flag
synchronously from `request.scope[SCOPE_KEY]` without competing for the
receive channel.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

SCOPE_KEY = "findajob.client_disconnected"


class DisconnectStateMiddleware:
    """Wraps `receive` to record `http.disconnect` into `scope[SCOPE_KEY]`.

    The flag latches to True on first disconnect and is never reset. HTTP/1.1
    treats disconnect as terminal for the scope, so a reconnect within the
    same scope is not a thing we need to model.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        scope[SCOPE_KEY] = False

        async def wrapped_receive() -> MutableMapping[str, Any]:
            message = await receive()
            if message.get("type") == "http.disconnect":
                scope[SCOPE_KEY] = True
            return message

        await self.app(scope, wrapped_receive, send)
