"""Python client for the Todo API.

Quick start::

    from todo_client import TodoClient

    with TodoClient(api_key="demo-key") as todos:
        todo = todos.create("Write the docs")
        todos.complete(todo.id)
        for item in todos.iter_all():
            print(item.title)
"""
from .client import DEFAULT_BASE_URL, TodoClient
from .errors import AuthenticationError, NotFoundError, PermissionDeniedError, TodoApiError, ValidationError
from .models import Todo, TodoPage

__all__ = [
    "DEFAULT_BASE_URL",
    "TodoClient",
    "Todo",
    "TodoPage",
    "TodoApiError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
]
__version__ = "0.1.0"
