"""Exceptions raised by :class:`~todo_client.TodoClient`."""
from __future__ import annotations


class TodoApiError(Exception):
    """The API returned an error.

    :param status_code: The HTTP status code.
    :param detail: The ``detail`` message from the response body.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(TodoApiError):
    """``401``: the API key is missing or invalid."""


class PermissionDeniedError(TodoApiError):
    """``403``: your API key's plan can't use this endpoint (for example, bulk create needs Enterprise)."""


class NotFoundError(TodoApiError):
    """``404``: no todo with that id."""


class ValidationError(TodoApiError):
    """``422``: the request body or parameters were invalid."""
