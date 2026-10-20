"""Bounded, persistent memory for the CampusConnect agent.

Only the active support-request reference is stored.
Memory never authorizes a support-request submission.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from app.tools.store import Store
from app.tools.errors import ServiceUnavailable


RETENTION_DAYS = 30
ACTIVE_CASE_KEY = "active_case"
CASE_REF_PATTERN = re.compile(r"^CC-\d{4}-\d{5}$")


class MemoryService:
    """Manage student-specific, time-limited application memory."""

    def __init__(
        self,
        store: Store,
        retention_days: int = RETENTION_DAYS,
    ):
        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")

        self.store = store
        self.retention_days = retention_days
        self.audit_log: list[dict] = []

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _record(
        self,
        action: str,
        student_id: str,
        result: str,
        key: str = ACTIVE_CASE_KEY,
    ) -> None:
        """Record minimal memory-operation metadata, not request contents."""
        self.audit_log.append({
            "timestamp": self._now().isoformat(),
            "action": action,
            "student_id": student_id,
            "key": key,
            "result": result,
        })

    def remember_active_case(
        self,
        student_id: str,
        case_ref: str,
    ) -> bool:
        """Remember a case only if it exists and belongs to this student."""
        if (
            not student_id
            or not CASE_REF_PATTERN.fullmatch(case_ref or "")
        ):
            self._record("memory_write", student_id or "", "rejected")
            return False

        try:
            request = self.store.get_request(case_ref)

            if (
                not request
                or request.get("student_id") != student_id
            ):
                self._record("memory_write", student_id, "ownership_check_failed")
                return False

            now = self._now()
            self.store.memory_put(
                student_id=student_id,
                key=ACTIVE_CASE_KEY,
                value=case_ref,
                created_at=now.isoformat(),
                expires_at=(
                    now + timedelta(days=self.retention_days)
                ).isoformat(),
            )

            self._record("memory_write", student_id, "success")
            return True

        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError):
            self._record("memory_write", student_id, "failed")
            return False

    def recall_active_case(self, student_id: str) -> str | None:
        """Recall a valid, unexpired case owned by the requesting student."""
        if not student_id:
            return None

        try:
            entry = self.store.memory_get(
                student_id,
                ACTIVE_CASE_KEY,
            )

            if not entry:
                self._record("memory_read", student_id, "miss")
                return None

            case_ref = entry.get("value")
            expires_at = entry.get("expires_at")

            if not CASE_REF_PATTERN.fullmatch(case_ref or ""):
                self.store.memory_delete(student_id, ACTIVE_CASE_KEY)
                self._record("memory_read", student_id, "invalid_reference")
                return None

            if not expires_at:
                self.store.memory_delete(student_id, ACTIVE_CASE_KEY)
                self._record("memory_read", student_id, "missing_expiry")
                return None

            expiry = datetime.fromisoformat(expires_at)

            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            if expiry <= self._now():
                self.store.memory_delete(student_id, ACTIVE_CASE_KEY)
                self._record("memory_read", student_id, "expired")
                return None

            # Verify the case still exists and belongs to this student.
            request = self.store.get_request(case_ref)

            if (
                not request
                or request.get("student_id") != student_id
            ):
                self.store.memory_delete(student_id, ACTIVE_CASE_KEY)
                self._record("memory_read", student_id, "ownership_check_failed")
                return None

            self._record("memory_read", student_id, "hit")
            return case_ref

        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError):
            self._record("memory_read", student_id, "failed")
            return None

    def export(self, student_id: str) -> list[dict]:
        """Return memory entries for the student's transparency command."""
        if not student_id:
            return []

        try:
            entries = self.store.memory_list(student_id)
            self._record("memory_export", student_id, "success")
            return entries
        except (sqlite3.Error, ServiceUnavailable, RuntimeError):
            self._record("memory_export", student_id, "failed")
            return []

    def forget(self, student_id: str) -> bool:
        """Delete the student's stored memory, not the support request."""
        if not student_id:
            return False

        try:
            self.store.memory_delete(student_id, ACTIVE_CASE_KEY)
            self._record("memory_forget", student_id, "success")
            return True
        except (sqlite3.Error, ServiceUnavailable, RuntimeError):
            self._record("memory_forget", student_id, "failed")
            return False

    def purge_expired(self) -> int:
        """Delete expired memory entries and return the number removed."""
        try:
            removed = self.store.memory_purge(self._now().isoformat())
            self._record(
                "memory_purge",
                "*",
                f"removed_{removed}",
            )
            return removed
        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError):
            self._record("memory_purge", "*", "failed")
            return 0