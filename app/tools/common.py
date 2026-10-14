"""Shared building blocks used by the individual tool modules."""

from dataclasses import dataclass, field
from typing import Callable

CATEGORIES = ["registration", "fees", "timetable", "accounts", "other"]
STATUSES = ["DRAFT", "SUBMITTED"]

CASE_REF = {
    "type": "string",
    "pattern": r"^CC-\d{4}-\d{5}$",
    "description": "Support request reference, e.g. CC-2026-00001",
}

REQUEST_OUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_ref", "category", "summary", "status", "created_at", "updated_at"],
    "properties": {
        "case_ref": CASE_REF,
        "category": {"type": "string", "enum": CATEGORIES},
        "summary": {"type": "string"},
        "status": {"type": "string", "enum": STATUSES},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}


@dataclass
class ToolSpec:
    name: str
    purpose: str                  # also sent to the model as the tool description
    input_schema: dict
    output_schema: dict
    handler: Callable             # (args: dict, session: Session, store: Store) -> dict
    auth: str                     # "public" | "student"
    side_effect: str              # "read" | "low_risk_write" | "high_impact_write"
    requires_approval: bool = False
    max_attempts: int = 1         # >1 only for idempotent reads
    failure_behaviour: dict = field(default_factory=dict)


def public_request(row: dict) -> dict:
    """The only fields of a support request that tools are allowed to return (no student ID)."""
    return {k: row[k] for k in ("case_ref", "category", "summary", "status", "created_at", "updated_at")}
