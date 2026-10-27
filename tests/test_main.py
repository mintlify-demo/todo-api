import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app, reset_store

AUTH = {"X-API-Key": "demo-key"}


@pytest.fixture()
def client():
    reset_store()
    return TestClient(app, headers=AUTH)


def make(client, title="Write the docs", **extra):
    return client.post("/todos", json={"title": title, **extra}).json()


def test_requires_api_key():
    anon = TestClient(app)
    assert anon.get("/todos").status_code == 401
    assert anon.get("/todos", headers={"X-API-Key": "nope"}).status_code == 401


def test_create_and_get(client):
    r = client.post("/todos", json={"title": "Write the docs"})
    assert r.status_code == 201
    todo = r.json()
    assert todo["id"] == 1 and todo["completed"] is False and "created_at" in todo
    assert client.get("/todos/1").json() == todo


def test_create_validates_title(client):
    assert client.post("/todos", json={"title": ""}).status_code == 422
    assert client.post("/todos", json={}).status_code == 422


def test_get_missing_is_404(client):
    r = client.get("/todos/99")
    assert r.status_code == 404
    assert r.json() == {"detail": "Todo not found"}


def test_patch_only_changes_sent_fields(client):
    make(client)
    r = client.patch("/todos/1", json={"completed": True})
    assert r.json()["completed"] is True
    assert r.json()["title"] == "Write the docs"


def test_delete(client):
    make(client)
    assert client.delete("/todos/1").status_code == 204
    assert client.get("/todos/1").status_code == 404
    assert client.delete("/todos/1").status_code == 404


def test_pagination(client):
    for i in range(25):
        make(client, f"todo {i}")
    page1 = client.get("/todos", params={"page_size": 10}).json()
    assert [t["title"] for t in page1["items"]][:2] == ["todo 0", "todo 1"]
    assert (page1["total"], page1["page"], page1["total_pages"]) == (25, 1, 3)
    page3 = client.get("/todos", params={"page": 3, "page_size": 10}).json()
    assert len(page3["items"]) == 5


def test_pagination_rejects_bad_params(client):
    assert client.get("/todos", params={"page": 0}).status_code == 422
    assert client.get("/todos", params={"page_size": 1000}).status_code == 422


def test_filter_by_completed(client):
    make(client, "a")
    make(client, "b", completed=True)
    done = client.get("/todos", params={"completed": True}).json()
    assert [t["title"] for t in done["items"]] == ["b"]
    assert done["total"] == 1


def test_deprecated_list_all_still_works(client):
    make(client, "a")
    make(client, "b")
    r = client.get("/todos/list-all")
    assert r.status_code == 200 and len(r.json()) == 2


def test_list_all_is_marked_deprecated_in_spec():
    assert app.openapi()["paths"]["/todos/list-all"]["get"]["deprecated"] is True


def test_priority_defaults_to_medium(client):
    assert make(client)["priority"] == "medium"


def test_create_with_priority_and_filter(client):
    make(client, "Low", priority="low")
    make(client, "High", priority="high")
    r = client.get("/todos", params={"priority": "high"})
    assert [t["title"] for t in r.json()["items"]] == ["High"]


def test_patch_priority(client):
    make(client)
    assert client.patch("/todos/1", json={"priority": "high"}).json()["priority"] == "high"


def test_invalid_priority_is_rejected(client):
    assert client.post("/todos", json={"title": "x", "priority": "urgent"}).status_code == 422


def test_due_date_round_trips(client):
    assert make(client, due_date="2026-11-15")["due_date"] == "2026-11-15"
    assert make(client, "No date")["due_date"] is None


def test_overdue_filter(client):
    make(client, "Late", due_date="2000-01-01")
    make(client, "Future", due_date="2999-01-01")
    make(client, "Done late", due_date="2000-01-01", completed=True)
    make(client, "No date")
    r = client.get("/todos", params={"overdue": True})
    assert [t["title"] for t in r.json()["items"]] == ["Late"]


def test_invalid_due_date_is_rejected(client):
    assert client.post("/todos", json={"title": "x", "due_date": "tomorrow"}).status_code == 422


def test_complete_endpoint(client):
    make(client)
    assert client.get("/todos/1").json()["completed_at"] is None
    r = client.post("/todos/1/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["completed"] is True and body["completed_at"] is not None
    # Idempotent: a second call keeps the original timestamp.
    assert client.post("/todos/1/complete").json()["completed_at"] == body["completed_at"]


def test_complete_missing_is_404(client):
    assert client.post("/todos/42/complete").status_code == 404


def test_committed_openapi_spec_is_up_to_date():
    """If this fails, run `make spec` and commit docs/openapi.json."""
    committed = json.loads((Path(__file__).parent.parent / "docs" / "openapi.json").read_text())
    assert committed == app.openapi()
