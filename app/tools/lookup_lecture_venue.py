"""Tool 1: lookup_lecture_venue (read-only, public)."""

from app.tools.common import ToolSpec


def handler(args, session, store):
    rows = store.find_lectures(args["course_code"], args.get("day"))
    return {
        "count": len(rows),
        "matches": [
            {k: r[k] for k in ("course_code", "course_name", "day", "start", "end", "venue")} for r in rows
        ],
        "source": "synthetic-dev-timetable",
    }


SPEC = ToolSpec(
    name="lookup_lecture_venue",
    purpose=(
        "Look up the lecture venue and time slots for a CoCIS course from the approved timetable. "
        "Use when a student asks where or when a lecture takes place. Returns an empty list if the "
        "course is not in the timetable; never guess a venue."
    ),
    input_schema={
        "type": "object", "additionalProperties": False, "required": ["course_code"],
        "properties": {
            "course_code": {"type": "string", "pattern": r"^[A-Z]{3}\d{4}$",
                            "description": "Course code in capitals, e.g. BSE4104"},
            "day": {"type": "string", "enum": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                    "description": "Optional weekday filter"},
        },
    },
    output_schema={
        "type": "object", "additionalProperties": False, "required": ["count", "matches", "source"],
        "properties": {
            "count": {"type": "integer", "minimum": 0},
            "source": {"type": "string"},
            "matches": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["course_code", "course_name", "day", "start", "end", "venue"],
                "properties": {k: {"type": "string"} for k in
                               ["course_code", "course_name", "day", "start", "end", "venue"]},
            }},
        },
    },
    handler=handler, auth="public", side_effect="read", max_attempts=2,
    failure_behaviour={
        "INVALID_ARGUMENTS": "Not executed. Model is told which field is wrong and asks the student for the course code.",
        "SERVICE_UNAVAILABLE": "Retried once (safe: read-only). If still down, student is pointed to the official timetable.",
        "UNEXPECTED_RESPONSE": "Result discarded; student gets a generic 'could not retrieve' message.",
    },
)
