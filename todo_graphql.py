"""GraphQL API for todos, served at /graphql (GraphiQL in the browser at the same URL).

It reads and writes the same in-memory store as the REST API, so a todo created over
GraphQL shows up in GET /todos and on the /ws/events stream.

Auth: send `X-API-Key` like the REST API.
The SDL in docs/schema.graphql is generated from this file (`make spec`).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

import strawberry
from strawberry.asgi import GraphQL
from strawberry.permission import BasePermission
from strawberry.types import Info


class HasApiKey(BasePermission):
    message = "Invalid or missing API key. Send it in the X-API-Key header."

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        from main import key_tier

        return key_tier(info.context["request"].headers.get("x-api-key")) is not None


@strawberry.type(description="A todo item.")
class Todo:
    id: int = strawberry.field(description="Unique id, assigned by the server.")
    title: str = strawberry.field(description="What needs doing.")
    completed: bool = strawberry.field(description="Whether the todo is done.")
    created_at: datetime = strawberry.field(description="When the todo was created (UTC).")

    @classmethod
    def from_model(cls, todo) -> "Todo":
        return cls(id=todo.id, title=todo.title, completed=todo.completed, created_at=todo.created_at)


@strawberry.type(description="One page of todos.")
class TodoPage:
    items: list[Todo] = strawberry.field(description="The todos on this page.")
    total: int = strawberry.field(description="Total todos matching the filter.")
    page: int = strawberry.field(description="The current page (starts at 1).")
    page_size: int = strawberry.field(description="Items per page.")
    total_pages: int = strawberry.field(description="How many pages there are.")


@strawberry.input(description="Fields for a new todo.")
class CreateTodoInput:
    title: str = strawberry.field(description="What needs doing (1 to 200 characters).")
    completed: bool = strawberry.field(default=False, description="Whether the todo is already done.")


@strawberry.input(description="Fields to change. Fields you leave out are unchanged.")
class UpdateTodoInput:
    title: Optional[str] = strawberry.field(default=None, description="New title.")
    completed: Optional[bool] = strawberry.field(default=None, description="New completed state.")


def _get(todo_id: int):
    from main import todos

    return todos.get(todo_id)


@strawberry.type(description="Read todos.")
class Query:
    @strawberry.field(permission_classes=[HasApiKey], description="List todos, oldest first, one page at a time.")
    def todos(
        self,
        page: int = 1,
        page_size: int = 10,
        completed: Optional[bool] = None,
    ) -> TodoPage:
        from main import todos

        page, page_size = max(page, 1), min(max(page_size, 1), 100)
        matching = [t for t in todos.values() if completed is None or t.completed == completed]
        start = (page - 1) * page_size
        return TodoPage(
            items=[Todo.from_model(t) for t in matching[start : start + page_size]],
            total=len(matching),
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(len(matching) / page_size)),
        )

    @strawberry.field(permission_classes=[HasApiKey], description="Get one todo by id. Returns null if it doesn't exist.")
    def todo(self, id: int) -> Optional[Todo]:
        found = _get(id)
        return Todo.from_model(found) if found else None


@strawberry.type(description="Create, update and delete todos.")
class Mutation:
    @strawberry.mutation(permission_classes=[HasApiKey], description="Create a todo.")
    def create_todo(self, input: CreateTodoInput) -> Todo:
        from main import TodoCreate, create_todo

        return Todo.from_model(create_todo(TodoCreate(title=input.title, completed=input.completed)))

    @strawberry.mutation(permission_classes=[HasApiKey], description="Update a todo. Returns null if it doesn't exist.")
    def update_todo(self, id: int, input: UpdateTodoInput) -> Optional[Todo]:
        from main import todos

        found = todos.get(id)
        if found is None:
            return None
        changes = {k: v for k, v in {"title": input.title, "completed": input.completed}.items() if v is not None}
        todos[id] = found.model_copy(update=changes)
        return Todo.from_model(todos[id])

    @strawberry.mutation(permission_classes=[HasApiKey], description="Delete a todo. Returns true if it existed.")
    def delete_todo(self, id: int) -> bool:
        from main import todos

        if id not in todos:
            return False
        del todos[id]
        return True


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQL(schema)
