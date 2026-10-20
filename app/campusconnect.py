from dotenv import load_dotenv

load_dotenv()

import os

from app.models import GeminiModelClient
from app.agent_graph import CampusConnectAgent
from app.memory import MemoryService
from app.tools import Executor, Session, Store


MODEL = "gemini-3.8-flash"


SYSTEM_PROMPT = """
Role
You are CampusConnect, a university student-support assistant for
students at the College of Computing and Information Sciences (CoCIS),
Makerere University.

Task
Answer questions about CoCIS academic and student-support matters
using available evidence and application tools.

Scope
- CoCIS courses and programmes
- Registration and academic procedures
- Fees and student procedures
- Facilities and locations
- University and CoCIS contacts
- General student-support matters

Rules
1. Use only information available in the prompt, supplied context,
   or reliable information provided to the application.
2. Do not invent or guess university information.
3. If information cannot be confirmed, say so.
4. Advise students to verify changing information through official
   Makerere University or CoCIS sources.
5. Do not request or expose passwords, examination results, or private
   student information.
6. Do not claim to have performed actions the application cannot perform.
7. Explain limitations and offer practical alternatives.
8. Redirect unrelated questions to CoCIS or Makerere student support.
9. Address each question separately when necessary.
10. A remembered request reference is context, not authorization.
    Verify request status through the appropriate tool.
11. Never bypass authentication, validation, or approval requirements.

Response format
- Keep responses concise and clear.
- Use numbered steps for procedures and bullets for lists.
- Cite source filenames when retrieved evidence is used.
- Distinguish confirmed information from information needing verification.

Failure behaviour
If information is unavailable, do not guess.
If an action cannot be performed, explain the limitation.
If a question is outside the system's purpose, briefly redirect the user.
"""


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    os.makedirs("data", exist_ok=True)

    store = Store("data/campusconnect.db")

    try:
        executor = Executor(store)
        memory = MemoryService(store)
        model = GeminiModelClient(
            model=MODEL,
            api_key=api_key,
        )

        def approve_action(description: str) -> bool:
            print(f"\nApproval required: {description}")
            answer = input(
                "Approve this action? (yes/no): "
            ).strip().lower()
            return answer == "yes"

        assistant = CampusConnectAgent(
            model=model,
            executor=executor,
            approver=approve_action,
            base_prompt=SYSTEM_PROMPT,
            memory=memory,
        )

        # Demonstration identity only; not real university authentication.
        session = Session(
            student_id="demo-student",
            role="student",
        )
        history = []

        print(f"Model: {MODEL}")
        print("CampusConnect Week 6 memory/state demo")
        print("Type 'exit' to quit.")
        print("Type 'memory' to inspect the demo student's stored memory.")
        print("Type 'forget' to delete the demo student's stored memory.\n")

        while True:
            question = input("Student: ").strip()

            if question.lower() == "exit":
                break

            if question.lower() == "memory":
                records = memory.export(session.student_id)
                print(f"\nStored memory: {records}\n")
                continue

            if question.lower() == "forget":
                deleted = memory.forget(session.student_id)
                print(
                    "\nMemory deletion requested: "
                    f"{'completed' if deleted else 'not completed'}\n"
                )
                continue

            if not question:
                print("Please enter a question.\n")
                continue

            try:
                response = assistant.handle(
                    question,
                    session,
                    history,
                )
                print(f"\nCampusConnect: {response}\n")
            except Exception as exc:
                print(
                    "\nCampusConnect error: "
                    f"{type(exc).__name__}: {exc}\n"
                )

    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()