"""Todo API: in-memory CRUD with API-key auth, pagination and a deprecated endpoint.

Everything lives in a Python dict, so data resets when the server restarts.

Auth:  send the header  X-API-Key: <key>.  The demo keys are public on purpose:
         demo-key             standard  (override with TODO_API_KEY)
         partner-demo-key     partner   (override with TODO_PARTNER_API_KEY)
         enterprise-demo-key  enterprise, unlocks POST /todos/bulk
                              (override with TODO_ENTERPRISE_API_KEY)

Also served: GraphQL at /graphql (todo_graphql.py) and a WebSocket stream of
todo events at /ws/events (events.py, documented in docs/asyncapi.yaml).

Run it:  uvicorn main:app --reload
"""
import math
import os
from datetime import datetime, timezone
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from events import EventedStore, events_app
from todo_graphql import graphql_app

# --------------------------------------------------------------------------- #
# Auth: one API key in a header
# --------------------------------------------------------------------------- #

API_KEY = os.environ.get("TODO_API_KEY", "demo-key")
PARTNER_API_KEY = os.environ.get("TODO_PARTNER_API_KEY", "partner-demo-key")
ENTERPRISE_API_KEY = os.environ.get("TODO_ENTERPRISE_API_KEY", "enterprise-demo-key")


def key_tier(key: str | None) -> str | None:
    """Map an API key to its plan: `standard`, `partner`, `enterprise`, or None if invalid."""
    return {API_KEY: "standard", PARTNER_API_KEY: "partner", ENTERPRISE_API_KEY: "enterprise"}.get(key or "")

# auto_error=False lets us return our own 401 (instead of FastAPI's default 403).
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description=(
        "Your API key. For the demo, use `demo-key`. Signed-in docs readers get their plan's key "
        "prefilled (`partner-demo-key` or `enterprise-demo-key`)."
    ),
)


def require_api_key(key: str | None = Security(api_key_header)) -> str:
    tier = key_tier(key)
    if tier is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return tier


def require_enterprise(tier: str = Depends(require_api_key)) -> None:
    if tier != "enterprise":
        raise HTTPException(status_code=403, detail="This endpoint needs an enterprise API key")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="What needs doing.", examples=["Write the docs"])
    completed: bool = Field(False, description="Whether the todo is already done.", examples=[False])
    priority: Priority = Field(
        Priority.medium, description="How important the todo is: `low`, `medium` (default), or `high`.", examples=["high"]
    )


class TodoUpdate(BaseModel):
    """Every field is optional. Only the fields you send are changed."""

    title: str | None = Field(None, min_length=1, max_length=200, description="New title.", examples=["Ship the docs"])
    completed: bool | None = Field(None, description="New completed state.", examples=[True])
    priority: Priority | None = Field(None, description="New priority.", examples=["low"])


class Todo(TodoCreate):
    id: int = Field(..., description="Unique id, assigned by the server.", examples=[1])
    created_at: datetime = Field(..., description="When the todo was created (UTC).", examples=["2026-01-15T09:30:00Z"])


class TodoPage(BaseModel):
    items: list[Todo] = Field(..., description="The todos on this page.")
    total: int = Field(..., description="Total todos matching the filter.", examples=[42])
    page: int = Field(..., description="The current page (starts at 1).", examples=[1])
    page_size: int = Field(..., description="Items per page.", examples=[10])
    total_pages: int = Field(..., description="How many pages there are.", examples=[5])


class Error(BaseModel):
    detail: str = Field(..., examples=["Todo not found"])


# --------------------------------------------------------------------------- #
# "Database": a dict of id -> Todo
# --------------------------------------------------------------------------- #

todos: dict[int, Todo] = EventedStore()  # a dict that broadcasts todo.* events on /ws/events
_next_id = 1


def reset_store() -> None:
    """Empty the store (used by the tests)."""
    global _next_id
    todos.clear()
    _next_id = 1


def get_or_404(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todos[todo_id]


# --------------------------------------------------------------------------- #
# The app. Every route below needs the API key.
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Todo API",
    version="1.0.0",
    summary="A tiny in-memory todo list with API-key auth.",
    description=(
        "Create, read, update and delete todos. Data is kept in memory and resets when the server restarts.\n\n"
        "All endpoints need an `X-API-Key` header. Use `demo-key` for the demo."
    ),
    servers=[{"url": "http://localhost:8000", "description": "Local development"}],
    dependencies=[Depends(require_api_key)],
    openapi_tags=[
        {"name": "Todos", "description": "Create, read, update and delete todos."},
    ],
)

# Allow browsers to call the API from anywhere. The docs' "Try it" playground
# sends requests straight from your browser to the API, so it needs CORS.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# GraphQL and the WebSocket event stream are mounted sub-apps, so they stay out of
# the OpenAPI spec (they have their own: docs/schema.graphql and docs/asyncapi.yaml).
app.mount("/graphql", graphql_app)
app.mount("/ws", events_app)

UNAUTHORIZED = {401: {"model": Error, "description": "Missing or invalid API key."}}
FORBIDDEN = {403: {"model": Error, "description": "Your API key's plan can't use this endpoint."}}
NOT_FOUND = {404: {"model": Error, "description": "No todo with that id."}}


@app.get(
    "/todos",
    tags=["Todos"],
    operation_id="listTodos",
    summary="List todos",
    response_model=TodoPage,
    responses=UNAUTHORIZED,
)
def list_todos(
    page: int = Query(1, ge=1, description="Page number, starting at 1."),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (1 to 100)."),
    completed: bool | None = Query(None, description="Only return todos with this completed state."),
    priority: Priority | None = Query(None, description="Only return todos with this priority."),
) -> TodoPage:
    """Return one page of todos, oldest first. Filter with `completed` and `priority`."""
    matching = [
        t
        for t in todos.values()
        if (completed is None or t.completed == completed) and (priority is None or t.priority == priority)
    ]
    start = (page - 1) * page_size
    return TodoPage(
        items=matching[start : start + page_size],
        total=len(matching),
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(len(matching) / page_size)),
    )


# NOTE: declared before /todos/{todo_id} so "list-all" is not parsed as an id.
@app.get(
    "/todos/list-all",
    tags=["Todos"],
    operation_id="listAllTodos",
    summary="List all todos (deprecated)",
    response_model=list[Todo],
    responses=UNAUTHORIZED,
    deprecated=True,
)
def list_all_todos() -> list[Todo]:
    """**Deprecated.** Returns every todo in one unpaginated response.

    Use `GET /todos` with `page` and `page_size` instead. This endpoint will
    be removed in a future version.
    """
    return list(todos.values())


@app.post(
    "/todos",
    tags=["Todos"],
    operation_id="createTodo",
    summary="Create a todo",
    response_model=Todo,
    status_code=status.HTTP_201_CREATED,
    responses=UNAUTHORIZED,
)
def create_todo(body: TodoCreate) -> Todo:
    """Create a todo. The server assigns the `id` and `created_at`."""
    global _next_id
    todo = Todo(id=_next_id, created_at=datetime.now(timezone.utc), **body.model_dump())
    todos[todo.id] = todo
    _next_id += 1
    return todo


class BulkCreate(BaseModel):
    items: list[TodoCreate] = Field(..., min_length=1, max_length=100, description="Up to 100 todos to create.")


@app.post(
    "/todos/bulk",
    tags=["Todos"],
    operation_id="bulkCreateTodos",
    summary="Bulk create todos (Enterprise)",
    response_model=list[Todo],
    status_code=status.HTTP_201_CREATED,
    responses={**UNAUTHORIZED, **FORBIDDEN},
    dependencies=[Depends(require_enterprise)],
    # Mintlify: only readers in the `enterprise` group see this endpoint in the docs.
    openapi_extra={"x-mint": {"groups": ["enterprise"]}},
)
def bulk_create_todos(body: BulkCreate) -> list[Todo]:
    """Create up to 100 todos in one request. **Enterprise plan only:** send an enterprise API key
    (`enterprise-demo-key` in the demo), or the API returns `403`."""
    return [create_todo(item) for item in body.items]


@app.get(
    "/todos/{todo_id}",
    tags=["Todos"],
    operation_id="getTodo",
    summary="Get a todo",
    response_model=Todo,
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def get_todo(todo_id: int) -> Todo:
    """Fetch one todo by id."""
    return get_or_404(todo_id)


@app.patch(
    "/todos/{todo_id}",
    tags=["Todos"],
    operation_id="updateTodo",
    summary="Update a todo",
    response_model=Todo,
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def update_todo(todo_id: int, body: TodoUpdate) -> Todo:
    """Change a todo's `title`, `completed`, and/or `priority`. Fields you leave out are unchanged."""
    todo = get_or_404(todo_id)
    updated = todo.model_copy(update=body.model_dump(exclude_unset=True))
    todos[todo_id] = updated
    return updated


@app.delete(
    "/todos/{todo_id}",
    tags=["Todos"],
    operation_id="deleteTodo",
    summary="Delete a todo",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def delete_todo(todo_id: int) -> Response:
    """Delete a todo. Returns `204` with no body."""
    get_or_404(todo_id)
    del todos[todo_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)
