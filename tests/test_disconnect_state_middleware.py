"""Unit tests for DisconnectStateMiddleware (#743).

Tests the middleware in isolation — direct ASGI invocation, no FastAPI or
HTTP client. Drives a fake inner app with a controlled `receive` callable
and asserts the namespaced scope flag transitions correctly.

The middleware exists because Starlette's `listen_for_disconnect` task wins
the receive-channel race against any peek-based watcher. By wrapping
`receive` passively, the middleware sees every message before any inner
consumer can possibly observe it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from findajob.web.middleware import SCOPE_KEY, DisconnectStateMiddleware


@pytest.fixture
def collected_messages() -> list[dict[str, Any]]:
    """Recorder for messages the inner app would see via its receive."""
    return []


def _make_inner_app(message_log: list[dict[str, Any]]):
    """Build a fake ASGI app that drains `receive` and records messages."""

    async def app(scope: dict, receive, send) -> None:
        # Drain receive until we observe a terminator-shaped message.
        # In real use, this is what listen_for_disconnect's tight loop does.
        while True:
            msg = await receive()
            message_log.append(msg)
            if msg.get("type") in {"http.disconnect", "_test.stop"}:
                break

    return app


def _make_scripted_receive(messages: list[dict[str, Any]]):
    """Build a `receive` callable that replays a scripted sequence of messages.

    After the script is exhausted it returns the last message indefinitely.
    """
    idx = [0]

    async def receive() -> dict[str, Any]:
        if idx[0] < len(messages):
            msg = messages[idx[0]]
            idx[0] += 1
        else:
            msg = messages[-1]
        return msg

    return receive


async def _record_send(message: dict[str, Any]) -> None:
    """No-op send — the middleware doesn't touch send."""


def test_http_disconnect_flips_scope_flag(collected_messages):
    """When http.disconnect comes through receive, scope[SCOPE_KEY] flips True."""
    inner_app = _make_inner_app(collected_messages)
    middleware = DisconnectStateMiddleware(inner_app)

    scope = {"type": "http", "method": "GET", "path": "/"}
    receive = _make_scripted_receive(
        [
            {"type": "http.request", "body": b"", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )

    # Sanity: flag absent before middleware runs.
    assert SCOPE_KEY not in scope

    asyncio.run(middleware(scope, receive, _record_send))

    # After the middleware sees http.disconnect, the flag must be True.
    assert scope[SCOPE_KEY] is True
    # Inner app saw both messages — the middleware passes them through, doesn't
    # consume them. (This is the defining property vs. peek-based approaches.)
    assert collected_messages == [
        {"type": "http.request", "body": b"", "more_body": False},
        {"type": "http.disconnect"},
    ]


def test_no_disconnect_leaves_flag_false(collected_messages):
    """When only http.request messages come through, flag stays False."""
    inner_app = _make_inner_app(collected_messages)
    middleware = DisconnectStateMiddleware(inner_app)

    scope = {"type": "http", "method": "POST", "path": "/api"}
    receive = _make_scripted_receive(
        [
            {"type": "http.request", "body": b"chunk1", "more_body": True},
            {"type": "http.request", "body": b"chunk2", "more_body": False},
            # Sentinel to break the inner app's loop without triggering disconnect.
            {"type": "_test.stop"},
        ]
    )

    asyncio.run(middleware(scope, receive, _record_send))

    assert scope[SCOPE_KEY] is False


def test_non_http_scope_passes_through_unchanged():
    """Non-http scopes (lifespan, websocket) bypass flag initialization entirely."""

    async def app(scope, receive, send) -> None:
        # Should be invoked, but should not see SCOPE_KEY injected.
        pass

    middleware = DisconnectStateMiddleware(app)

    scope = {"type": "lifespan"}

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    asyncio.run(middleware(scope, receive, _record_send))

    # No flag was added to the non-http scope.
    assert SCOPE_KEY not in scope


def test_scope_key_is_namespaced_not_inside_state():
    """The flag lives at scope[SCOPE_KEY], next to scope["state"], not inside it.

    `request.state` is a Starlette wrapper around `scope["state"]`; the namespaced
    flag intentionally lives parallel to that, not inside it, to avoid State()
    wrapper semantics. Verifies the contract route closures rely on:
    `request.scope.get(SCOPE_KEY)` is the legitimate read.
    """
    assert SCOPE_KEY == "findajob.client_disconnected"
    # Namespaced — not a top-level "state" key.
    assert "." in SCOPE_KEY
    assert not SCOPE_KEY.startswith("state")


def test_flag_is_idempotent_under_multiple_disconnects(collected_messages):
    """Multiple http.disconnect messages don't break the flag (latches True)."""

    async def inner(scope, receive, send) -> None:
        # Drain three messages; each should be observable.
        for _ in range(3):
            msg = await receive()
            collected_messages.append(msg)

    middleware = DisconnectStateMiddleware(inner)
    scope = {"type": "http", "method": "GET", "path": "/"}
    receive = _make_scripted_receive(
        [
            {"type": "http.disconnect"},
            {"type": "http.disconnect"},
            {"type": "http.disconnect"},
        ]
    )

    asyncio.run(middleware(scope, receive, _record_send))

    assert scope[SCOPE_KEY] is True
