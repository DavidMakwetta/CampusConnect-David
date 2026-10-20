"""Explicit workflow state for the CampusConnect support agent.

Workflow state tracks the current task. Persistent student memory is
managed separately by app.memory.MemoryService.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Phase(str, Enum):
    IDLE = "IDLE"
    DRAFT_CREATED = "DRAFT_CREATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


TRANSITIONS = {
    Phase.IDLE: {
        Phase.DRAFT_CREATED,
        Phase.FAILED,
    },
    Phase.DRAFT_CREATED: {
        Phase.AWAITING_APPROVAL,
        Phase.SUBMITTED,
        Phase.FAILED,
    },
    Phase.AWAITING_APPROVAL: {
        Phase.SUBMITTED,
        Phase.DRAFT_CREATED,
        Phase.FAILED,
    },
    Phase.SUBMITTED: {
        Phase.DRAFT_CREATED,
        Phase.FAILED,
    },
    Phase.FAILED: {
        Phase.IDLE,
        Phase.DRAFT_CREATED,
        Phase.FAILED,
    },
}


@dataclass
class WorkflowState:
    """Tracks one student's current support workflow."""

    student_id: str
    phase: Phase = Phase.IDLE
    active_case_ref: Optional[str] = None
    last_tool: Optional[str] = None
    last_stop_reason: str = ""
    turns: int = 0
    memory_used: bool = False

    def fire(self, new_phase: Phase) -> None:
        """Move to a valid workflow phase or reject an invalid transition."""
        if not isinstance(new_phase, Phase):
            new_phase = Phase(new_phase)

        if new_phase == self.phase:
            return

        allowed = TRANSITIONS.get(self.phase, set())

        if new_phase not in allowed:
            raise ValueError(
                f"Invalid workflow transition: "
                f"{self.phase.value} -> {new_phase.value}"
            )

        self.phase = new_phase

    def on_tool_result(
        self,
        tool: str,
        ok: bool,
        data: Optional[dict] = None,
    ) -> None:
        """Update workflow state after a tool returns a result."""
        self.last_tool = tool
        data = data or {}

        if not ok:
            self.fire(Phase.FAILED)
            self.last_stop_reason = f"Tool failed: {tool}"
            return

        case_ref = data.get("case_ref")
        if case_ref:
            self.active_case_ref = case_ref

        if tool == "create_support_request_draft":
            self.fire(Phase.DRAFT_CREATED)
            self.last_stop_reason = ""

        elif tool == "submit_support_request":
            self.fire(Phase.SUBMITTED)
            self.last_stop_reason = ""

        elif tool == "request_approval":
            self.fire(Phase.AWAITING_APPROVAL)
            self.last_stop_reason = "Awaiting human approval"

    def mark_memory_used(self) -> None:
        """Record that stored memory contributed to the current task."""
        self.memory_used = True

    def record_turn(self) -> None:
        """Count a user interaction in the current workflow."""
        self.turns += 1

    def snapshot(self) -> dict:
        """Return a serialisable representation of the workflow state."""
        return {
            "student_id": self.student_id,
            "phase": self.phase.value,
            "active_case_ref": self.active_case_ref,
            "last_tool": self.last_tool,
            "last_stop_reason": self.last_stop_reason,
            "turns": self.turns,
            "memory_used": self.memory_used,
        }