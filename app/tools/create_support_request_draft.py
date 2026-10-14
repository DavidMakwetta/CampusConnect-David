"""Tool 3: create_support_request_draft (low-risk simulated write: a draft nobody else can see)."""

from app.tools.common import CATEGORIES, REQUEST_OUT, ToolSpec, public_request


def handler(args, session, store):
    existing = store.find_open_draft(session.student_id, args["category"], args["summary"])
    row = existing or store.create_request(session.student_id, args["category"], args["summary"])
    out = public_request(row)
    out["duplicate_of_existing_draft"] = existing is not None
    return out


_OUTPUT = {
    **REQUEST_OUT,
    "properties": {**REQUEST_OUT["properties"], "duplicate_of_existing_draft": {"type": "boolean"}},
    "required": REQUEST_OUT["required"] + ["duplicate_of_existing_draft"],
}

SPEC = ToolSpec(
    name="create_support_request_draft",
    purpose=(
        "Create a DRAFT support request for the signed-in student after the student has described their "
        "problem. A draft is not visible to staff and nothing is sent. Submitting is a separate step."
    ),
    input_schema={
        "type": "object", "additionalProperties": False, "required": ["category", "summary"],
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "summary": {"type": "string", "minLength": 10, "maxLength": 500,
                        "description": "Plain-language description of the problem. No passwords or ID numbers."},
        },
    },
    output_schema=_OUTPUT,
    handler=handler, auth="student", side_effect="low_risk_write",
    failure_behaviour={
        "INVALID_ARGUMENTS": "Not executed. Model asks the student for the missing detail (category or a longer summary).",
        "NOT_AUTHENTICATED": "Not executed. Student is asked to sign in.",
        "SERVICE_UNAVAILABLE": "Not retried automatically. Student is told NO draft was created.",
    },
)
