"""Structured tool errors, shared by REST and MCP."""
from __future__ import annotations

from typing import Any


class ToolError(Exception):
    status = 400

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFound(ToolError):
    status = 404


class Forbidden(ToolError):
    """Side-effect requested without an APPROVED proposal (or otherwise not allowed)."""

    status = 403


class Conflict(ToolError):
    status = 409


def require(cond: bool, code: str, message: str, **details: Any) -> None:
    if not cond:
        raise ToolError(code, message, **details)
