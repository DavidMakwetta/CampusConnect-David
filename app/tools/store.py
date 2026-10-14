"""SQLite-backed application data for the tools (synthetic data only, per the Project Charter)."""

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

from app.tools.errors import ServiceUnavailable

SEED_TIMETABLE = [
    # course_code, course_name, day, start, end, venue   (SYNTHETIC development data)
    ("BSE4104", "Emerging Trends in Software Engineering", "Mon", "14:00", "17:00", "Lab 3, CoCIS Block B"),
    ("BSE4105", "Software Integration and Deployment", "Tue", "09:00", "12:00", "Lab 1, CoCIS Block B"),
    ("BSE3101", "Software Architecture", "Wed", "14:00", "17:00", "Room 204, CoCIS Block A"),
    ("CSC2100", "Data Structures and Algorithms", "Thu", "08:00", "11:00", "Room 101, CoCIS Block A"),
    ("CSC2100", "Data Structures and Algorithms", "Fri", "08:00", "10:00", "Lab 2, CoCIS Block B"),
    ("IST1202", "Introduction to Databases", "Mon", "08:00", "11:00", "Room 105, CoCIS Block A"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS timetable (
    course_code TEXT, course_name TEXT, day TEXT, start TEXT, end TEXT, venue TEXT
);
CREATE TABLE IF NOT EXISTS support_requests (
    case_ref   TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    category   TEXT NOT NULL,
    summary    TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_ref TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str = ":memory:", clock: Optional[Callable[[], datetime]] = None):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._outage_calls_left = 0
        if self._db.execute("SELECT COUNT(*) FROM timetable").fetchone()[0] == 0:
            self._db.executemany("INSERT INTO timetable VALUES (?,?,?,?,?,?)", SEED_TIMETABLE)
            self._db.commit()

    # ---- fault injection used by the tests / demo -------------------------------------
    def simulate_outage(self, calls: int) -> None:
        """Make the next `calls` data-layer calls raise ServiceUnavailable."""
        self._outage_calls_left = calls

    def _guard(self) -> None:
        if self._outage_calls_left > 0:
            self._outage_calls_left -= 1
            raise ServiceUnavailable("support database unreachable")

    def _now(self) -> str:
        return self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- timetable ---------------------------------------------------------------------
    def find_lectures(self, course_code: str, day: Optional[str] = None) -> list[dict]:
        self._guard()
        sql, params = "SELECT * FROM timetable WHERE course_code = ?", [course_code]
        if day:
            sql += " AND day = ?"
            params.append(day)
        return [dict(r) for r in self._db.execute(sql + " ORDER BY day, start", params)]

    # ---- support requests --------------------------------------------------------------
    def _next_ref(self) -> str:
        n = self._db.execute("SELECT COUNT(*) FROM support_requests").fetchone()[0] + 1
        return f"CC-{self._clock().year}-{n:05d}"

    def find_open_draft(self, student_id: str, category: str, summary: str) -> Optional[dict]:
        self._guard()
        row = self._db.execute(
            "SELECT * FROM support_requests WHERE student_id=? AND category=? AND summary=? AND status='DRAFT'",
            (student_id, category, summary),
        ).fetchone()
        return dict(row) if row else None

    def create_request(self, student_id: str, category: str, summary: str) -> dict:
        self._guard()
        ref, now = self._next_ref(), self._now()
        self._db.execute(
            "INSERT INTO support_requests VALUES (?,?,?,?,?,?,?)",
            (ref, student_id, category, summary, "DRAFT", now, now),
        )
        self._db.commit()
        return self.get_request(ref)

    def get_request(self, case_ref: str) -> Optional[dict]:
        self._guard()
        row = self._db.execute("SELECT * FROM support_requests WHERE case_ref=?", (case_ref,)).fetchone()
        return dict(row) if row else None

    def submit_request(self, case_ref: str) -> dict:
        """DRAFT -> SUBMITTED and drop a notification into the (simulated) staff outbox, atomically."""
        self._guard()
        now = self._now()
        with self._db:
            self._db.execute(
                "UPDATE support_requests SET status='SUBMITTED', updated_at=? WHERE case_ref=?", (now, case_ref)
            )
            self._db.execute(
                "INSERT INTO staff_outbox (case_ref, message, created_at) VALUES (?,?,?)",
                (case_ref, f"New student-support request {case_ref} awaiting triage", now),
            )
        return self.get_request(case_ref)

    def outbox(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM staff_outbox ORDER BY id")]
