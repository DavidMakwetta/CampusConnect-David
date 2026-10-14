"""Tool 4: submit_support_request (higher-impact write: notifies staff, needs human approval)."""

from app.tools.common import CASE_REF, REQUEST_OUT, ToolSpec, public_request
from app.tools.errors import Code, ToolFailure


def handler(args, session, store):
    row = store.get_request(args["case_ref"])
    if row is None:
        raise ToolFailure(Code.NOT_FOUND, f"No support request with reference {args['case_ref']} was found.")
    if row["student_id"] != session.student_id:
        raise ToolFailure(Code.NOT_AUTHORIZED, "You can only submit support requests that you created.")
    if row["status"] != "DRAFT":
        raise ToolFailure(Code.CONFLICT, f"Request {row['case_ref']} is already {row['status']} and cannot be submitted again.")
    return public_request(store.submit_request(args["case_ref"]))


SPEC = ToolSpec(
    name="submit_support_request",
    purpose=(
        "Submit an existing DRAFT support request so that it is sent to CoCIS support staff. "
        "HIGHER IMPACT: requires explicit human approval before it runs."
    ),
    input_schema={"type": "object", "additionalProperties": False, "required": ["case_ref"],
                  "properties": {"case_ref": CASE_REF}},
    output_schema=REQUEST_OUT,
    handler=handler, auth="student", side_effect="high_impact_write", requires_approval=True,
    failure_behaviour={
        "APPROVAL_REQUIRED": "Execution paused. Student sees what will be sent and must confirm.",
        "APPROVAL_DENIED": "Not executed. Request stays a DRAFT; student is told nothing was sent.",
        "NOT_AUTHORIZED": "Draft belongs to another student; refused.",
        "CONFLICT": "Request already submitted; student is told its current status.",
        "SERVICE_UNAVAILABLE": "Not retried automatically (avoids duplicate staff notifications). Student is told nothing was sent.",
    },
)
