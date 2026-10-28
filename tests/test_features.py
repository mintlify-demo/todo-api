"""Tests for the plan-tier keys, the enterprise-only endpoint, GraphQL, and the WebSocket events."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from events import EVENT_TYPES
from main import app, reset_store
from todo_graphql import schema

DOCS = Path(__file__).parent.parent / "docs"


@pytest.fixture()
def client():
    reset_store()
    return TestClient(app, headers={"X-API-Key": "demo-key"})


# ---- plan keys and the enterprise-only endpoint ------------------------------------------


@pytest.mark.parametrize("key", ["demo-key", "partner-demo-key", "enterprise-demo-key"])
def test_every_plan_key_works(client, key):
    assert client.get("/todos", headers={"X-API-Key": key}).status_code == 200


def test_bulk_create_needs_an_enterprise_key(client):
    body = {"items": [{"title": "a"}, {"title": "b", "completed": True}]}
    assert client.post("/todos/bulk", json=body).status_code == 403
    assert client.post("/todos/bulk", json=body, headers={"X-API-Key": "partner-demo-key"}).status_code == 403
    r = client.post("/todos/bulk", json=body, headers={"X-API-Key": "enterprise-demo-key"})
    assert r.status_code == 201
    assert [t["title"] for t in r.json()] == ["a", "b"]
    assert client.get("/todos").json()["total"] == 2


def test_bulk_create_is_enterprise_only_in_the_docs():
    op = app.openapi()["paths"]["/todos/bulk"]["post"]
    assert op["x-mint"] == {"groups": ["enterprise"]}



def test_graphql_and_websocket_stay_out_of_the_openapi_spec():
    paths = app.openapi()["paths"]
    assert not any(p.startswith(("/graphql", "/ws")) for p in paths)


# ---- GraphQL --------------------------------------------------------------------------------


def gql(client, query, variables=None, **kw):
    return client.post("/graphql", json={"query": query, "variables": variables or {}}, **kw).json()


def test_graphql_create_and_list(client):
    created = gql(client, 'mutation { createTodo(input: {title: "Write the docs"}) { id title completed } }')
    assert created["data"]["createTodo"] == {"id": 1, "title": "Write the docs", "completed": False}
    page = gql(client, "{ todos(pageSize: 5) { total pageSize items { id title } } }")["data"]["todos"]
    assert page == {"total": 1, "pageSize": 5, "items": [{"id": 1, "title": "Write the docs"}]}
    # same store as REST
    assert client.get("/todos/1").json()["title"] == "Write the docs"


def test_graphql_update_and_delete(client):
    client.post("/todos", json={"title": "x"})
    upd = gql(client, "mutation { updateTodo(id: 1, input: {completed: true}) { completed title } }")
    assert upd["data"]["updateTodo"] == {"completed": True, "title": "x"}
    assert gql(client, "mutation { deleteTodo(id: 1) }")["data"]["deleteTodo"] is True
    assert gql(client, "mutation { deleteTodo(id: 1) }")["data"]["deleteTodo"] is False
    assert gql(client, "{ todo(id: 1) { id } }")["data"]["todo"] is None


def test_graphql_needs_an_api_key(client):
    out = gql(client, "{ todos { total } }", headers={"X-API-Key": "nope"})
    assert out["data"] is None and "API key" in out["errors"][0]["message"]


def test_committed_graphql_schema_is_up_to_date():
    """If this fails, run `make spec` and commit docs/schema.graphql."""
    assert (DOCS / "schema.graphql").read_text() == schema.as_str() + "\n"


# ---- WebSocket events -----------------------------------------------------------------------


def test_websocket_streams_rest_and_graphql_changes(client):
    with client.websocket_connect("/ws/events?api_key=partner-demo-key") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "connection.ready" and ready["plan"] == "partner"
        client.post("/todos", json={"title": "Write the docs"})
        created = ws.receive_json()
        assert created["type"] == "todo.created" and created["data"]["title"] == "Write the docs"
        assert created["timestamp"].endswith("Z")
        client.patch("/todos/1", json={"completed": True})
        updated = ws.receive_json()
        assert updated["type"] == "todo.updated" and updated["data"]["completed"] is True
        gql(client, "mutation { deleteTodo(id: 1) }")
        deleted = ws.receive_json()
        assert deleted["type"] == "todo.deleted" and deleted["data"] == {"id": 1}


def test_websocket_ping_and_subscribe(client):
    with client.websocket_connect("/ws/events?api_key=demo-key") as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
        ws.send_json({"type": "subscribe", "events": ["todo.deleted"]})
        assert ws.receive_json()["events"] == ["todo.deleted"]
        client.post("/todos", json={"title": "not sent: filtered out"})
        client.delete("/todos/1")
        msg = ws.receive_json()
        assert msg["type"] == "todo.deleted" and msg["data"] == {"id": 1}


def test_websocket_rejects_a_bad_key(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/events?api_key=nope") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_asyncapi_spec_matches_the_server():
    spec = yaml.safe_load((DOCS / "asyncapi.yaml").read_text())
    assert spec["asyncapi"].startswith("3.0")
    assert spec["channels"]["todoEvents"]["address"] == "/ws/events"
    names = {m["name"] for m in spec["components"]["messages"].values()}
    assert set(EVENT_TYPES) <= names
