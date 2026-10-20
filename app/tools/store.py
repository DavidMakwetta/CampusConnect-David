"""SQLite-backed application data for CampusConnect.

Uses synthetic development data for timetable and support requests.
Includes bounded, persistent student memory for the Week 6 workflow.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

from app.tools.errors import ServiceUnavailable


SEED_TIMETABLE = [
    # course_code, course_name, day, start, end, venue
    ("BSE4104", "Emerging Trends in Software Engineering", "Mon",
     "14:00", "17:00", "Lab 3, CoCIS Block B"),
    ("BSE4105", "Software Integration and Deployment", "Tue",
     "09:00", "12:00", "Lab 1, CoCIS Block B"),
    ("BSE3101", "Software Architecture", "Wed",
     "14:00", "17:00", "Room 204, CoCIS Block A"),
    ("CSC2100", "Data Structures and Algorithms", "Thu",
     "08:00", "11:00", "Room 101, CoCIS Block A"),
    ("CSC2100", "Data Structures and Algorithms", "Fri",
     "08:00", "10:00", "Lab 2, CoCIS Block B"),
    ("IST1202", "Introduction to Databases", "Mon",
     "08:00", "11:00", "Room 105, CoCIS Block A"),
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS timetable (
    course_code TEXT,
    course_name TEXT,
    day TEXT,
    start TEXT,
    end TEXT,
    venue TEXT
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

CREATE TABLE IF NOT EXISTS student_memory (
    student_id TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (student_id, key)
);
"""


class Store:
    """SQLite persistence layer for CampusConnect tools and memory."""

    def __init__(
        self,
        path: str = ":memory:",
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._outage_calls_left = 0

        if self._db.execute(
            "SELECT COUNT(*) FROM timetable"
        ).fetchone()[0] == 0:
            self._db.executemany(
                "INSERT INTO timetable VALUES (?,?,?,?,?,?)",
                SEED_TIMETABLE,
            )
            self._db.commit()

    # ---- Fault injection used by tests and demonstrations -----------------

    def simulate_outage(self, calls: int) -> None:
        """Make the next `calls` guarded data operations raise ServiceUnavailable."""
        self._outage_calls_left = calls

    def _guard(self) -> None:
        if self._outage_calls_left > 0:
            self._outage_calls_left -= 1
            raise ServiceUnavailable("support database unreachable")

    def _now(self) -> str:
        """Return a UTC timestamp in a consistent ISO-like format."""
        return self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- Timetable --------------------------------------------------------

    def find_lectures(
        self,
        course_code: str,
        day: Optional[str] = None,
    ) -> list[dict]:
        self._guard()

        sql = "SELECT * FROM timetable WHERE course_code = ?"
        params = [course_code]

        if day:
            sql += " AND day = ?"
            params.append(day)

        sql += " ORDER BY day, start"

        return [
            dict(row)
            for row in self._db.execute(sql, params)
        ]

    # ---- Support requests -------------------------------------------------

    def _next_ref(self) -> str:
        count = self._db.execute(
            "SELECT COUNT(*) FROM support_requests"
        ).fetchone()[0] + 1

        return f"CC-{self._clock().year}-{count:05d}"

    def find_open_draft(
        self,
        student_id: str,
        category: str,
        summary: str,
    ) -> Optional[dict]:
        self._guard()

        row = self._db.execute(
            """
            SELECT * FROM support_requests
            WHERE student_id = ?
              AND category = ?
              AND summary = ?
              AND status = 'DRAFT'
            """,
            (student_id, category, summary),
        ).fetchone()

        return dict(row) if row else None

    def create_request(
        self,
        student_id: str,
        category: str,
        summary: str,
    ) -> dict:
        self._guard()

        case_ref = self._next_ref()
        now = self._now()

        self._db.execute(
            """
            INSERT INTO support_requests
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_ref,
                student_id,
                category,
                summary,
                "DRAFT",
                now,
                now,
            ),
        )
        self._db.commit()

        return self.get_request(case_ref)

    def get_request(self, case_ref: str) -> Optional[dict]:
        self._guard()

        row = self._db.execute(
            "SELECT * FROM support_requests WHERE case_ref = ?",
            (case_ref,),
        ).fetchone()

        return dict(row) if row else None

    def submit_request(self, case_ref: str) -> dict:
        """Change a request to SUBMITTED and create its outbox entry atomically."""
        self._guard()
        now = self._now()

        with self._db:
            self._db.execute(
                """
                UPDATE support_requests
                SET status = 'SUBMITTED', updated_at = ?
                WHERE case_ref = ?
                """,
                (now, case_ref),
            )

            self._db.execute(
                """
                INSERT INTO staff_outbox (case_ref, message, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    case_ref,
                    f"New student-support request {case_ref} awaiting triage",
                    now,
                ),
            )

        return self.get_request(case_ref)

    def outbox(self) -> list[dict]:
        return [
            dict(row)
            for row in self._db.execute(
                "SELECT * FROM staff_outbox ORDER BY id"
            )
        ]

    # ---- Persistent student memory: Week 6 -------------------------------
    #
    # Memory operations intentionally do not use _guard(). The fault-injection
    # counter is reserved for the existing support-data operations, so a
    # simulated support-service outage does not automatically consume it
    # through a memory operation.
    #
    # Memory values must be restricted by MemoryService. For this project,
    # the intended value is the student's active support-request reference.

    def memory_put(
        self,
        student_id: str,
        key: str,
        value: str,
        created_at: str,
        expires_at: str,
    ) -> None:
        """Insert or update a student's memory entry."""
        with self._db:
            self._db.execute(
                """
                INSERT INTO student_memory
                    (student_id, key, value, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(student_id, key)
                DO UPDATE SET
                    value = excluded.value,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    student_id,
                    key,
                    value,
                    created_at,
                    expires_at,
                ),
            )

    def memory_get(
        self,
        student_id: str,
        key: str,
    ) -> Optional[dict]:
        """Retrieve one memory entry belonging to the specified student."""
        row = self._db.execute(
            """
            SELECT student_id, key, value, created_at, expires_at
            FROM student_memory
            WHERE student_id = ? AND key = ?
            """,
            (student_id, key),
        ).fetchone()

        return dict(row) if row else None

    def memory_list(self, student_id: str) -> list[dict]:
        """List memory entries belonging only to the specified student."""
        rows = self._db.execute(
            """
            SELECT key, value, created_at, expires_at
            FROM student_memory
            WHERE student_id = ?
            ORDER BY key
            """,
            (student_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    def memory_delete(
        self,
        student_id: str,
        key: Optional[str] = None,
    ) -> int:
        """Delete one memory key or all memory belonging to a student."""
        if key is None:
            sql = "DELETE FROM student_memory WHERE student_id = ?"
            params = (student_id,)
        else:
            sql = (
                "DELETE FROM student_memory "
                "WHERE student_id = ? AND key = ?"
            )
            params = (student_id, key)

        with self._db:
            cursor = self._db.execute(sql, params)
            return cursor.rowcount

    def memory_purge(self, now_iso: str) -> int:
        """Delete memory entries whose expiry timestamp has passed."""
        with self._db:
            cursor = self._db.execute(
                """
                DELETE FROM student_memory
                WHERE expires_at <= ?
                """,
                (now_iso,),
            )
            return cursor.rowcount

    # ---- Resource cleanup -------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection."""
        self._db.close()