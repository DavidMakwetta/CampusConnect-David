"""Bounded, persistent memory for CampusConnect.

Stores only the student's active support-request reference.
Uses the existing SQLite Store implementation.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from app.store import Store
from app.tools.errors import ServiceUnavailable


RETENTION_DAYS = 30
CASE_REF_PATTERN = re.compile(r"^CC-\d{4}-\d{5}$")


class MemoryService:
    """Manage private, time-limited memory for each student."""

    def __init__(self, store: Store, retention_days: int = RETENTION_DAYS):
        self.store = store
        self.retention_days = retention_days
        self.audit_log = []

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def _record(self, action, student_id, key=None, result=None):
        """Record minimal metadata about memory operations."""
        self.audit_log.append({
            "timestamp": self._now().isoformat(),
            "action": action,
            "student_id": student_id,
            "key": key,
            "result": result,
        })

    def remember_active_case(self, student_id: str, case_ref: str) -> bool:
        """Store a valid support-request reference for 30 days."""
        if not student_id or not CASE_REF_PATTERN.fullmatch(case_ref or ""):
            self._record("memory_write", student_id, "active_case", "rejected")
            return False

        now = self._now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(days=self.retention_days)).isoformat()

        try:
            self.store.memory_put(
                student_id=student_id,
                key="active_case",
                value=case_ref,
                created_at=created_at,
                expires_at=expires_at,
            )
            self._record("memory_write", student_id, "active_case", "success")
            return True
        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError):
            self._record("memory_write", student_id, "active_case", "failed")
            return False

    def recall_active_case(self, student_id: str):
        """Return an unexpired case reference belonging to this student's memory."""
        if not student_id:
            return None

        try:
            record = self.store.memory_get(student_id, "active_case")

            if not record:
                self._record("memory_read", student_id, "active_case", "miss")
                return None

            case_ref = record.get("value")
            expires_at = record.get("expires_at")

            if not CASE_REF_PATTERN.fullmatch(case_ref or ""):
                self.store.memory_delete(student_id, "active_case")
                self._record("memory_read", student_id, "active_case", "invalid")
                return None

            if not expires_at:
                self.store.memory_delete(student_id, "active_case")
                self._record("memory_read", student_id, "active_case", "invalid")
                return None

            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            if expiry <= self._now():
                self.store.memory_delete(student_id, "active_case")
                self._record("memory_read", student_id, "active_case", "expired")
                return None

            self._record("memory_read", student_id, "active_case", "hit")
            return case_ref

        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError, AttributeError):
            self._record("memory_read", student_id, "active_case", "failed")
            return None

    def export(self, student_id: str) -> list[dict]:
        """List the student's stored memory for transparency."""
        try:
            records = self.store.memory_list(student_id)
            self._record("memory_export", student_id, result="success")
            return records
        except (sqlite3.Error, ServiceUnavailable, RuntimeError):
            self._record("memory_export", student_id, result="failed")
            return []

    def forget(self, student_id: str) -> bool:
        """Delete stored memory without deleting the support request itself."""
        try:
            self.store.memory_delete(student_id, "active_case")
            self._record("memory_forget", student_id, "active_case", "success")
            return True
        except (sqlite3.Error, ServiceUnavailable, RuntimeError):
            self._record("memory_forget", student_id, "active_case", "failed")
            return False

    def purge_expired(self) -> bool:
        """Remove expired entries from the memory table."""
        try:
            self.store.memory_purge(self._now().isoformat())
            return True
        except (sqlite3.Error, ServiceUnavailable, RuntimeError, ValueError):
            return False