"""Error codes and result types shared by every CampusConnect tool."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Code(str, Enum):
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"      # missing / wrong-typed / extra parameters
    UNKNOWN_TOOL = "UNKNOWN_TOOL"                # model asked for a tool that is not registered
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"      # no signed-in student on the session
    NOT_AUTHORIZED = "NOT_AUTHORIZED"            # signed in, but not allowed to touch this record
    NOT_FOUND = "NOT_FOUND"                      # no such record
    CONFLICT = "CONFLICT"                        # record is in the wrong state for this action
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"      # higher-impact action needs a human decision
    APPROVAL_DENIED = "APPROVAL_DENIED"          # the human said no
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"  # backing service is down / timed out
    UNEXPECTED_RESPONSE = "UNEXPECTED_RESPONSE"  # tool output failed its output schema
    INTERNAL = "INTERNAL"                        # anything we did not anticipate


class ToolFailure(Exception):
    """Raised by a tool handler to return a controlled, expected failure."""

    def __init__(self, code: Code, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ServiceUnavailable(Exception):
    """Raised by the data layer when the backing store cannot be reached."""


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: Optional[dict] = None
    error_code: Optional[Code] = None
    message: str = ""
    retryable: bool = False
    extra: dict = field(default_factory=dict)

    def for_model(self) -> dict[str, Any]:
        """The only shape the language model ever sees. No stack traces, no internals."""
        if self.ok:
            return {"ok": True, "data": self.data}
        out = {
            "ok": False,
            "error_code": self.error_code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        out.update(self.extra)
        return out
