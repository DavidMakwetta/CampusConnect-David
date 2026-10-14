"""Week 4 demo.

  python scripts/demo_week4.py            -> offline, deterministic (scripted model). Writes evidence/week4/demo-transcript.txt
  python scripts/demo_week4.py --live     -> real Gemini function calling (needs GEMINI_API_KEY), interactive, asks YOU to approve
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import GeminiModelClient, ModelTurn, ScriptedModelClient, ToolCall  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.tools import Executor, Session, Store  # noqa: E402

ALICE = Session("23/U/00001/EVE", "student")     # synthetic student
OUT = Path(__file__).resolve().parents[1] / "evidence" / "week4"


def call(name, **args):
    return ModelTurn(tool_calls=[ToolCall(name, args)])


def ref_from(h):
    return h[-1]["results"][0]["response"]["data"]["case_ref"]


def render(trace):
    lines = []
    for t in trace:
        e = t["event"]
        if e == "user":
            lines.append(f"\nSTUDENT : {t['text']}")
        elif e == "tool_call":
            lines.append(f"  -> model requests {t['tool']}({t['args']})")
        elif e == "approval":
            lines.append(f"  !! APPROVAL GATE: {t['question']}  ->  {'APPROVED' if t['granted'] else 'DENIED'}")
        elif e == "tool_result":
            lines.append(f"  <- executor returns {t['result']}")
        elif e == "assistant":
            lines.append(f"CAMPUSCONNECT: {t['text']}")
    return "\n".join(lines)


def offline():
    OUT.mkdir(parents=True, exist_ok=True)
    store = Store(":memory:")
    ex = Executor(store, audit_path=str(OUT / "audit-log.jsonl"))
    (OUT / "audit-log.jsonl").write_text("")
    answers = iter([True, False])
    script = [
        # 1. read tool
        call("lookup_lecture_venue", course_code="BSE4104"),
        ModelTurn(text="BSE4104 is on Monday 14:00-17:00 in Lab 3, CoCIS Block B (from the demo timetable)."),
        # 2. draft (low-risk write) then 3. submit (approval gate) - APPROVED
        call("create_support_request_draft", category="registration", summary="My course units do not show after registration"),
        ModelTurn(text="I've saved a draft (nothing has been sent to staff yet). Want me to submit it?"),
        lambda h: call("submit_support_request", case_ref=ref_from_last(h)),
        ModelTurn(text="Done - your request has been submitted to CoCIS support staff."),
        # 4. status
        lambda h: call("get_support_request_status", case_ref=ref_from_last(h)),
        ModelTurn(text="Your request is now SUBMITTED."),
        # 5. second draft, submit DENIED
        call("create_support_request_draft", category="fees", summary="I was charged twice for tuition this semester"),
        lambda h: call("submit_support_request", case_ref=ref_from_last(h)),
        ModelTurn(text="Okay - I haven't sent it. Your fees request is saved as a draft."),
    ]
    orch = Orchestrator(ScriptedModelClient(script), ex, approver=lambda q: next(answers))
    for msg in [
        "I have BSE4104 - where is the lecture?",
        "My course units are missing after registration, please log it.",
        "Yes, submit it.",
        "What's the status of that request?",
        "I was charged twice for tuition, log it and send it to staff.",
    ]:
        orch.handle(msg, ALICE, history=HISTORY)
    # failure demos straight through the executor (what the model could attempt)
    extra = [
        ("Missing parameter", "create_support_request_draft", {"summary": "Cannot see my results on the portal"}, ALICE),
        ("Unauthenticated", "get_support_request_status", {"case_ref": "CC-2026-00001"}, Session()),
        ("Other student's record", "get_support_request_status", {"case_ref": "CC-2026-00001"}, Session("23/U/00002/EVE", "student")),
        ("Spoofed identity argument", "create_support_request_draft", {"category": "fees", "summary": "Charge this to another student", "student_id": "23/U/00002/EVE"}, ALICE),
        ("Submit without approval", "submit_support_request", {"case_ref": "CC-2026-00002"}, ALICE),
    ]
    extra.append(("Service unavailable (read)", "lookup_lecture_venue", {"course_code": "BSE4104"}, Session()))
    lines = [render(orch.trace), "\n\n=== FAILURE / AUTHORIZATION CHECKS ==="]
    for label, tool, args, sess in extra:
        if label.startswith("Service unavailable"):
            store.simulate_outage(2)          # fail both the first attempt and the single retry
        r = ex.execute(tool, args, sess)
        lines.append(f"[{label}] {tool}({args}) -> {r.for_model()}")
    lines.append(f"\nStaff outbox: {store.outbox()}")
    text = "\n".join(lines)
    (OUT / "demo-transcript.txt").write_text(text, encoding="utf-8")
    print(text)


HISTORY: list = []


def ref_from_last(h):
    for m in reversed(h):
        if m["role"] == "tool":
            for r in m["results"]:
                d = (r["response"].get("data") or {})
                if "case_ref" in d:
                    return d["case_ref"]


def live():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.")
    from app.campusconnect import MODEL
    OUT.mkdir(parents=True, exist_ok=True)
    store = Store(":memory:")
    ex = Executor(store, audit_path=str(OUT / "live-audit-log.jsonl"))
    orch = Orchestrator(GeminiModelClient(MODEL, key), ex,
                        approver=lambda q: input(f"\n[APPROVAL NEEDED] {q} (y/n): ").strip().lower() == "y")
    print("CampusConnect Week 4 (live). Signed in as synthetic student 23/U/00001/EVE. Type 'exit' to quit.")
    hist: list = []
    while True:
        q = input("\nStudent: ").strip()
        if q.lower() == "exit":
            break
        print("CampusConnect:", orch.handle(q, ALICE, history=hist))
    (OUT / "live-transcript.txt").write_text(render(orch.trace), encoding="utf-8")


if __name__ == "__main__":
    live() if "--live" in sys.argv else offline()
