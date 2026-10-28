"""Run the SDK against the real app in-process (no network)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "sdk")]

from main import app, reset_store  # noqa: E402
from todo_client import NotFoundError, PermissionDeniedError, AuthenticationError, TodoClient  # noqa: E402


@pytest.fixture()
def todos():
    reset_store()
    return TodoClient(api_key="demo-key", http_client=TestClient(app))


def test_create_get_complete_delete(todos):
    todo = todos.create("Write the docs")
    assert todo.id == 1 and todo.completed is False
    assert todos.get(1).title == "Write the docs"
    assert todos.complete(1).completed is True
    todos.delete(1)
    with pytest.raises(NotFoundError):
        todos.get(1)


def test_iter_all_pages(todos):
    for i in range(7):
        todos.create(f"t{i}")
    assert [t.title for t in todos.iter_all(page_size=3)] == [f"t{i}" for i in range(7)]
    page = todos.list(page=3, page_size=3)
    assert page.total == 7 and not page.has_next and len(page.items) == 1


def test_bulk_create_needs_enterprise(todos):
    with pytest.raises(PermissionDeniedError):
        todos.bulk_create(["a"])
    ent = TodoClient(api_key="enterprise-demo-key", http_client=TestClient(app))
    assert [t.title for t in ent.bulk_create(["a", "b"])] == ["a", "b"]


def test_bad_key():
    with pytest.raises(AuthenticationError):
        TodoClient(api_key="nope", http_client=TestClient(app)).list()
