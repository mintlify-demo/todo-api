"""Data returned by the Todo API."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Todo:
    """A todo item.

    :param id: Unique id, assigned by the server.
    :param title: What needs doing.
    :param completed: Whether the todo is done.
    :param created_at: When the todo was created (UTC).
    :param extra: Any fields the server returned that this SDK version doesn't know yet.
    """

    id: int
    title: str
    completed: bool
    created_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Todo":
        """Build a :class:`Todo` from an API response body."""
        known = {"id", "title", "completed", "created_at"}
        return cls(
            id=data["id"],
            title=data["title"],
            completed=data["completed"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            extra={k: v for k, v in data.items() if k not in known},
        )


@dataclass(frozen=True)
class TodoPage:
    """One page of todos from :meth:`TodoClient.list`.

    :param items: The todos on this page.
    :param total: Total todos matching the filter.
    :param page: The current page (starts at 1).
    :param page_size: Items per page.
    :param total_pages: How many pages there are.
    """

    items: list[Todo]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        """``True`` if there is another page after this one."""
        return self.page < self.total_pages

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TodoPage":
        """Build a :class:`TodoPage` from an API response body."""
        return cls(
            items=[Todo.from_json(t) for t in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
            total_pages=data["total_pages"],
        )
