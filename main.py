"""Todo API: in-memory CRUD with API-key auth, pagination and a deprecated endpoint.

Everything lives in a Python dict, so data resets when the server restarts.

Auth:  send the header  X-API-Key: <key>.  The demo key is `demo-key`
       (override it with the TODO_API_KEY environment variable).

Run it:  uvicorn main:app --reload
"""
import math
import os
from datetime import date, datetime, timezone
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Auth: one API key in a header
# --------------------------------------------------------------------------- #

API_KEY = os.environ.get("TODO_API_KEY", "demo-key")

# auto_error=False lets us return our own 401 (instead of FastAPI's default 403).
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Your API key. For the demo, use `demo-key`.",
)


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


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
    due_date: date | None = Field(None, description="Optional date the todo is due (YYYY-MM-DD).", examples=["2026-11-15"])


class TodoUpdate(BaseModel):
    """Every field is optional. Only the fields you send are changed."""

    title: str | None = Field(None, min_length=1, max_length=200, description="New title.", examples=["Ship the docs"])
    completed: bool | None = Field(None, description="New completed state.", examples=[True])
    priority: Priority | None = Field(None, description="New priority.", examples=["low"])
    due_date: date | None = Field(None, description="New due date (YYYY-MM-DD). Send `null` to clear it.", examples=["2026-11-30"])


class Todo(TodoCreate):
    id: int = Field(..., description="Unique id, assigned by the server.", examples=[1])
    created_at: datetime = Field(..., description="When the todo was created (UTC).", examples=["2026-01-15T09:30:00Z"])
    completed_at: datetime | None = Field(
        None,
        description="When the todo was completed with `POST /todos/{todo_id}/complete` (UTC). `null` until then.",
        examples=["2026-01-16T17:05:00Z"],
    )


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

todos: dict[int, Todo] = {}
_next_id = 1


def reset_store() -> None:
    """Empty the store (used by the tests)."""
    global _next_id
    todos.clear()
    _next_id = 1


def is_overdue(todo: Todo) -> bool:
    """A todo is overdue when it is not done and its due date has passed."""
    today = datetime.now(timezone.utc).date()
    return not todo.completed and todo.due_date is not None and todo.due_date < today


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
        "All endpoints need an `X-API-Key` header. Use `demo-key` when running the demo locally."
    ),
    servers=[{"url": "http://localhost:8000", "description": "Local development"}],
    dependencies=[Depends(require_api_key)],
    openapi_tags=[
        {"name": "Todos", "description": "Create, read, update and delete todos."},
    ],
)

# Allow browsers to call the API from anywhere. The docs' "Try it" playground
# sends requests straight from your browser to http://localhost:8000, so it needs CORS.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UNAUTHORIZED = {401: {"model": Error, "description": "Missing or invalid API key."}}
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
    overdue: bool | None = Query(
        None, description="`true` returns only incomplete todos whose `due_date` is before today (UTC)."
    ),
) -> TodoPage:
    """Return one page of todos, oldest first. Filter with `completed`, `priority`, and `overdue`."""
    matching = [
        t
        for t in todos.values()
        if (completed is None or t.completed == completed)
        and (priority is None or t.priority == priority)
        and (overdue is None or is_overdue(t) == overdue)
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
    """Change a todo's `title`, `completed`, `priority`, and/or `due_date`. Fields you leave out are unchanged."""
    todo = get_or_404(todo_id)
    updated = todo.model_copy(update=body.model_dump(exclude_unset=True))
    todos[todo_id] = updated
    return updated


@app.post(
    "/todos/{todo_id}/complete",
    tags=["Todos"],
    operation_id="completeTodo",
    summary="Mark a todo as complete",
    response_model=Todo,
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def complete_todo(todo_id: int) -> Todo:
    """Mark a todo as done and record `completed_at`.

    Safe to call more than once: completing a todo that is already complete
    keeps its original `completed_at`.
    """
    todo = get_or_404(todo_id)
    if todo.completed and todo.completed_at is not None:
        return todo
    updated = todo.model_copy(update={"completed": True, "completed_at": datetime.now(timezone.utc)})
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
