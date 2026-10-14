"""Deterministic tool executor. The language model can only *request* a call; this layer decides.

Pipeline for every request:
  1 known tool? -> 2 arguments valid? -> 3 authenticated/authorized? -> 4 approved (if high impact)?
  -> 5 run handler (bounded retries for reads) -> 6 output matches schema? -> 7 audit log
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from jsonschema import Draft202012Validator

from app.tools.definitions import TOOLS, ToolSpec
from app.tools.errors import Code, ServiceUnavailable, ToolFailure, ToolResult
from app.tools.store import Store


@dataclass(frozen=True)
class Session:
    """Identity comes from the application session, never from model-supplied arguments."""
    student_id: Optional[str] = None
    role: str = "anonymous"   # "anonymous" | "student"


@dataclass
class Approval:
    approval_id: str
    tool: str
    args: dict
    fingerprint: str
    status: str = "PENDING"   # PENDING | GRANTED | DENIED | CONSUMED
    created: float = field(default_factory=time.time)


class ApprovalGate:
    """One-time, argument-bound approvals. An approval for A cannot be used to run B."""

    def __init__(self, ttl_seconds: int = 300, clock: Callable[[], float] = time.time):
        self._items: dict[str, Approval] = {}
        self._ttl, self._clock = ttl_seconds, clock

    @staticmethod
    def fingerprint(session: Session, tool: str, args: dict) -> str:
        blob = json.dumps({"s": session.student_id, "t": tool, "a": args}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def request(self, session: Session, tool: str, args: dict) -> Approval:
        a = Approval(uuid.uuid4().hex[:8], tool, dict(args), self.fingerprint(session, tool, args), created=self._clock())
        self._items[a.approval_id] = a
        return a

    def decide(self, approval_id: str, granted: bool) -> None:
        self._items[approval_id].status = "GRANTED" if granted else "DENIED"

    def consume(self, session: Session, tool: str, args: dict) -> bool:
        fp = self.fingerprint(session, tool, args)
        for a in self._items.values():
            fresh = self._clock() - a.created <= self._ttl
            if a.status == "GRANTED" and a.fingerprint == fp and fresh:
                a.status = "CONSUMED"          # single use
                return True
        return False


class Executor:
    def __init__(self, store: Store, tools: dict[str, ToolSpec] | None = None,
                 gate: ApprovalGate | None = None, audit_path: str | None = None):
        self.store, self.tools = store, tools or TOOLS
        self.gate = gate or ApprovalGate()
        self.audit: list[dict] = []
        self._audit_path = audit_path

    # ------------------------------------------------------------------ audit
    def _log(self, tool: str, session: Session, args, result: ToolResult, note: str = "") -> ToolResult:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": tool, "student": session.student_id,
            "args": args if isinstance(args, dict) else repr(args)[:200],
            "outcome": "OK" if result.ok else result.error_code.value, "note": note,
        }
        self.audit.append(entry)
        if self._audit_path:
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return result

    @staticmethod
    def _fail(tool, code: Code, msg: str, retryable=False, **extra) -> ToolResult:
        return ToolResult(False, tool, error_code=code, message=msg, retryable=retryable, extra=extra)

    # ------------------------------------------------------------------ main entry
    def execute(self, tool_name: str, args, session: Session) -> ToolResult:
        spec = self.tools.get(tool_name)
        if spec is None:                                                              # 1
            return self._log(tool_name, session, args, self._fail(
                tool_name, Code.UNKNOWN_TOOL, "That tool does not exist. Use only the tools you were given."))

        if not isinstance(args, dict):                                                # 2
            return self._log(tool_name, session, args, self._fail(
                tool_name, Code.INVALID_ARGUMENTS, "Arguments must be a JSON object."))
        errors = sorted(Draft202012Validator(spec.input_schema).iter_errors(args), key=lambda e: list(e.path))
        if errors:
            problems = [
                {"field": ".".join(map(str, e.path)) or "(root)", "problem": e.message[:160]} for e in errors
            ]
            missing = [e.message.split("'")[1] for e in errors if e.validator == "required"]
            return self._log(tool_name, session, args, self._fail(
                tool_name, Code.INVALID_ARGUMENTS,
                "Arguments are invalid. Do not retry with guessed values; ask the student for what is missing.",
                problems=problems, missing=missing))

        if spec.auth == "student":                                                    # 3
            if session.role != "student" or not session.student_id:
                return self._log(tool_name, session, args, self._fail(
                    tool_name, Code.NOT_AUTHENTICATED, "The student is not signed in. Ask them to sign in first."))

        if spec.requires_approval and not self.gate.consume(session, tool_name, args):  # 4
            return self._log(tool_name, session, args, self._fail(
                tool_name, Code.APPROVAL_REQUIRED,
                "This action needs the student's explicit approval before it can run.",
                tool_args=args), note="paused for approval")

        result = self._run_handler(spec, args, session)                               # 5, 6
        return self._log(tool_name, session, args, result)

    # ------------------------------------------------------------------ handler + output checks
    def _run_handler(self, spec: ToolSpec, args: dict, session: Session) -> ToolResult:
        last: Optional[Exception] = None
        for attempt in range(1, spec.max_attempts + 1):
            try:
                data = spec.handler(args, session, self.store)
                break
            except ToolFailure as tf:                      # expected, controlled failure
                return self._fail(spec.name, tf.code, tf.message)
            except ServiceUnavailable as exc:
                last = exc                                  # retry only if the spec allows it (reads)
            except Exception:                              # unexpected: log detail, hide it from the model
                return self._fail(spec.name, Code.INTERNAL, "Something went wrong while running the tool.")
        else:
            writes = spec.side_effect != "read"
            return self._fail(
                spec.name, Code.SERVICE_UNAVAILABLE,
                "The service is unavailable right now." + (" Nothing was saved or sent." if writes else ""),
                retryable=not writes)

        problems = list(Draft202012Validator(spec.output_schema).iter_errors(data))
        if problems:                                        # never forward malformed / over-sharing output
            return self._fail(spec.name, Code.UNEXPECTED_RESPONSE,
                              "The tool returned data in an unexpected format, so it was discarded.")
        return ToolResult(True, spec.name, data=data)
