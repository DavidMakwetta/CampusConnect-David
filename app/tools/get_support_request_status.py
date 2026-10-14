"""Tool 2: get_support_request_status (read-only, owner only)."""

from app.tools.common import CASE_REF, REQUEST_OUT, ToolSpec, public_request
from app.tools.errors import Code, ToolFailure


def handler(args, session, store):
    row = store.get_request(args["case_ref"])
    if row is None:
        raise ToolFailure(Code.NOT_FOUND, f"No support request with reference {args['case_ref']} was found.")
    if row["student_id"] != session.student_id:
        raise ToolFailure(Code.NOT_AUTHORIZED, "You can only view support requests that you created.")
    return public_request(row)


SPEC = ToolSpec(
    name="get_support_request_status",
    purpose=(
        "Retrieve the current status of a support request that the signed-in student created, "
        "using its case reference. Read-only."
    ),
    input_schema={"type": "object", "additionalProperties": False, "required": ["case_ref"],
                  "properties": {"case_ref": CASE_REF}},
    output_schema=REQUEST_OUT,
    handler=handler, auth="student", side_effect="read", max_attempts=2,
    failure_behaviour={
        "NOT_AUTHENTICATED": "Not executed. Student is asked to sign in.",
        "NOT_AUTHORIZED": "Request belongs to another student. Nothing is revealed beyond the refusal.",
        "NOT_FOUND": "Student is told no request has that reference; no status is invented.",
        "SERVICE_UNAVAILABLE": "Retried once; then student is told status cannot be checked right now.",
    },
)
