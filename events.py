"""Real-time todo events over a WebSocket: ws://<host>/ws/events?api_key=<key>.

The store in main.py is an `EventedStore`, a dict that publishes an event whenever
a todo is written or deleted, so every REST or GraphQL change is broadcast without
touching the endpoint code.

Messages the server sends (all JSON, documented in docs/asyncapi.yaml):

    {"type": "connection.ready", "plan": "standard", "timestamp": "..."}
    {"type": "todo.created", "data": {<Todo>}, "timestamp": "..."}
    {"type": "todo.updated", "data": {<Todo>}, "timestamp": "..."}
    {"type": "todo.deleted", "data": {"id": 1}, "timestamp": "..."}
    {"type": "pong", "timestamp": "..."}

Messages a client can send:

    {"type": "ping"}
    {"type": "subscribe", "events": ["todo.created", "todo.deleted"]}   # filter
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

EVENT_TYPES = ("todo.created", "todo.updated", "todo.deleted")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventBus:
    """Fan out events to every connected WebSocket. Safe to call from any thread."""

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()

    def subscribe(self) -> tuple[asyncio.AbstractEventLoop, asyncio.Queue]:
        sub = (asyncio.get_running_loop(), asyncio.Queue())
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub) -> None:
        self._subscribers.discard(sub)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        message = {"type": event_type, "data": data, "timestamp": _now()}
        for loop, queue in list(self._subscribers):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:  # loop closed
                self._subscribers.discard((loop, queue))


bus = EventBus()


class EventedStore(dict):
    """A dict of id -> Todo that publishes todo.created / todo.updated / todo.deleted."""

    def __setitem__(self, key, value) -> None:
        event = "todo.updated" if key in self else "todo.created"
        super().__setitem__(key, value)
        bus.publish(event, value.model_dump(mode="json"))

    def __delitem__(self, key) -> None:
        super().__delitem__(key)
        bus.publish("todo.deleted", {"id": key})


events_app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


@events_app.websocket("/events")
async def todo_events(websocket: WebSocket) -> None:
    from main import key_tier  # late import: main imports this module

    key = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    plan = key_tier(key)
    if plan is None:
        # 1008 = policy violation. Browsers can't send headers on a WebSocket, so use ?api_key=.
        await websocket.close(code=1008, reason="Invalid or missing API key")
        return
    await websocket.accept()
    sub = bus.subscribe()
    wanted = set(EVENT_TYPES)
    await websocket.send_json({"type": "connection.ready", "plan": plan, "timestamp": _now()})

    async def pump() -> None:
        while True:
            message = await sub[1].get()
            if message["type"] in wanted:
                await websocket.send_json(message)

    sender = asyncio.create_task(pump())
    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("type") if isinstance(msg, dict) else None
            if kind == "ping":
                await websocket.send_json({"type": "pong", "timestamp": _now()})
            elif kind == "subscribe":
                requested = [e for e in msg.get("events") or [] if e in EVENT_TYPES]
                wanted = set(requested or EVENT_TYPES)
                await websocket.send_json({"type": "subscribed", "events": sorted(wanted), "timestamp": _now()})
            else:
                await websocket.send_json({"type": "error", "message": "Unknown message type", "timestamp": _now()})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        sender.cancel()
        bus.unsubscribe(sub)
