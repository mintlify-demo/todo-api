"""The :class:`TodoClient`."""
from __future__ import annotations

from typing import Any, Iterator, Optional

import httpx

from .errors import AuthenticationError, NotFoundError, PermissionDeniedError, TodoApiError, ValidationError
from .models import Todo, TodoPage

# TODO(hosting): switch to the hosted Todo API URL once it exists.
DEFAULT_BASE_URL = "http://localhost:8000"
"""Where the client sends requests by default: the API running locally (``uvicorn main:app``)."""

_ERRORS = {401: AuthenticationError, 403: PermissionDeniedError, 404: NotFoundError, 422: ValidationError}


class TodoClient:
    """A client for the Todo API.

    :param api_key: Your API key, sent as ``X-API-Key``. The demo key is ``demo-key``;
        ``enterprise-demo-key`` also unlocks :meth:`bulk_create`.
    :param base_url: Where the API runs. Defaults to :data:`DEFAULT_BASE_URL` (``http://localhost:8000``).
    :param timeout: Request timeout in seconds.
    :param http_client: An existing ``httpx.Client`` to send requests with (useful in tests).

    Use it as a context manager to close the connection pool when you're done::

        with TodoClient(api_key="demo-key") as todos:
            todos.create("Write the docs")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(base_url=base_url, timeout=timeout)
        self._headers = {"X-API-Key": api_key}

    # -- lifecycle ---------------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "TodoClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- endpoints ---------------------------------------------------------------------------

    def list(self, *, page: int = 1, page_size: int = 10, completed: Optional[bool] = None) -> TodoPage:
        """List one page of todos, oldest first (``GET /todos``).

        :param page: Page number, starting at 1.
        :param page_size: Items per page, 1 to 100.
        :param completed: Only return todos with this completed state.
        :returns: A :class:`~todo_client.TodoPage`.
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if completed is not None:
            params["completed"] = str(completed).lower()
        return TodoPage.from_json(self._request("GET", "/todos", params=params))

    def iter_all(self, *, page_size: int = 100, completed: Optional[bool] = None) -> Iterator[Todo]:
        """Iterate over every todo, fetching pages as needed.

        :param page_size: How many todos to fetch per request.
        :param completed: Only yield todos with this completed state.
        """
        page = 1
        while True:
            result = self.list(page=page, page_size=page_size, completed=completed)
            yield from result.items
            if not result.has_next:
                return
            page += 1

    def get(self, todo_id: int) -> Todo:
        """Get one todo (``GET /todos/{todo_id}``).

        :raises NotFoundError: If there's no todo with that id.
        """
        return Todo.from_json(self._request("GET", f"/todos/{todo_id}"))

    def create(self, title: str, *, completed: bool = False, **fields: Any) -> Todo:
        """Create a todo (``POST /todos``).

        :param title: What needs doing, 1 to 200 characters.
        :param completed: Whether it's already done.
        :param fields: Extra fields supported by newer API versions, sent as-is.
        """
        body = {"title": title, "completed": completed, **fields}
        return Todo.from_json(self._request("POST", "/todos", json=body))

    def bulk_create(self, titles: list[str]) -> list[Todo]:
        """Create up to 100 todos in one request (``POST /todos/bulk``). **Enterprise plan only.**

        :raises PermissionDeniedError: If your API key isn't an enterprise key.
        """
        body = {"items": [{"title": t} for t in titles]}
        return [Todo.from_json(t) for t in self._request("POST", "/todos/bulk", json=body)]

    def update(self, todo_id: int, *, title: Optional[str] = None, completed: Optional[bool] = None) -> Todo:
        """Change a todo's title and/or completed state (``PATCH /todos/{todo_id}``).

        Arguments you leave as ``None`` are not changed.
        """
        body = {k: v for k, v in {"title": title, "completed": completed}.items() if v is not None}
        return Todo.from_json(self._request("PATCH", f"/todos/{todo_id}", json=body))

    def complete(self, todo_id: int) -> Todo:
        """Mark a todo as done. Shorthand for ``update(todo_id, completed=True)``."""
        return self.update(todo_id, completed=True)

    def delete(self, todo_id: int) -> None:
        """Delete a todo (``DELETE /todos/{todo_id}``).

        :raises NotFoundError: If there's no todo with that id.
        """
        self._request("DELETE", f"/todos/{todo_id}")

    # -- internals ---------------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, headers=self._headers, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise _ERRORS.get(response.status_code, TodoApiError)(response.status_code, str(detail))
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
