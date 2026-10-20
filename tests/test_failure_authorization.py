from app.tools.common import ToolSpec
from app.tools import Executor, Session, Store

passed = 0

def check(test_id, description, actual, expected):
    global passed
    success = actual == expected
    print(
        f"{test_id}: {'PASS' if success else 'FAIL'} | "
        f"{description} | Expected: {expected} | Actual: {actual}"
    )
    if success:
        passed += 1


store = Store()
executor = Executor(store)

# F1: Missing required course code
result = executor.execute("lookup_lecture_venue", {}, Session())
check("F1", "Missing course code",
      result.error_code.value if result.error_code else "OK",
      "INVALID_ARGUMENTS")

# F2: Unauthenticated student attempts to create a draft
result = executor.execute(
    "create_support_request_draft",
    {"category": "registration",
     "summary": "I need help with course registration"},
    Session(),
)
check("F2", "Unauthenticated draft creation",
      result.error_code.value if result.error_code else "OK",
      "NOT_AUTHENTICATED")

# F3: Another student attempts to view a request
owner = Session(student_id="student-A", role="student")
other = Session(student_id="student-B", role="student")

created = executor.execute(
    "create_support_request_draft",
    {"category": "registration",
     "summary": "I need help with course registration"},
    owner,
)

if created.ok:
    case_ref = created.data["case_ref"]
    result = executor.execute(
        "get_support_request_status",
        {"case_ref": case_ref},
        other,
    )
    check("F3", "Access another student's request",
          result.error_code.value if result.error_code else "OK",
          "NOT_AUTHORIZED")
else:
    check("F3", "Access another student's request",
          "SETUP_FAILED", "NOT_AUTHORIZED")

# F4: Simulate an unavailable database
store.simulate_outage(3)
result = executor.execute(
    "lookup_lecture_venue",
    {"course_code": "BSE4104"},
    Session(),
)
check("F4", "Unavailable database",
      result.error_code.value if result.error_code else "OK",
      "SERVICE_UNAVAILABLE")

# F5: Tool returns data that violates its output schema
bad_tool = ToolSpec(
    name="test_bad_output",
    purpose="Test output validation",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
    output_schema={
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    },
    handler=lambda args, session, store: {"unexpected": True},
    auth="public",
    side_effect="read",
)

bad_executor = Executor(store, tools={"test_bad_output": bad_tool})
result = bad_executor.execute("test_bad_output", {}, Session())
check("F5", "Unexpected tool response",
      result.error_code.value if result.error_code else "OK",
      "UNEXPECTED_RESPONSE")

print(f"\nResult: {passed}/5 tests passed.")