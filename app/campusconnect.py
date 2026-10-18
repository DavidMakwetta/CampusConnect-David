from dotenv import load_dotenv
load_dotenv()
import os
import json

from google import genai  # Kept available for compatibility with your existing setup
from app.models import GeminiModelClient
from app.agent_graph import CampusConnectAgent
from app.tools import Executor, Session, Store

MODEL = "gemini-3.8-flash"

SYSTEM_PROMPT = """
Role
You are CampusConnect, a university student-support assistant for students at the College of Computing and Information Sciences (CoCIS), Makerere University.

Task
Answer students' questions about CoCIS-related academic and student-support matters. Provide clear, concise and helpful responses based on the information and context available to you.

Scope
CampusConnect primarily supports students with:
- CoCIS courses and programmes
- Registration and academic procedures
- Fees and related student procedures
- CoCIS facilities and locations
- University and CoCIS contacts
- General student-support matters

Rules
1. Use only information available in the prompt, supplied context, or reliable information provided to the application.
2. Do not invent, guess or present uncertain university information as fact.
3. Ensure specific information is supported by available information.
4. If information cannot be confirmed, clearly say so rather than guessing.
5. Advise students to verify changing information through official Makerere University or CoCIS sources.
6. Do not request, expose or guess passwords, registration numbers, examination results or other private student information.
7. Do not claim to have performed actions the application cannot perform.
8. Explain limitations and provide practical alternatives where possible.
9. Redirect unrelated questions to CoCIS or Makerere student-support matters.
10. Address each question separately when a message contains multiple questions.

Response Format
- Keep responses concise and easy to understand.
- Use numbered steps for procedures and short bullets for lists.
- Distinguish confirmed information from information requiring verification.
- Avoid unnecessary information.

Failure Behaviour
If information is unavailable, do not guess. Explain the limitation and direct the student to an appropriate official source or office.
If an action cannot be performed, explain the limitation and provide an alternative.
If a question is outside the system's purpose, briefly redirect the student to CoCIS or Makerere student-support matters.
"""


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    os.makedirs("data", exist_ok=True)

    store = Store("data/campusconnect.db")
    executor = Executor(store)
    model = GeminiModelClient(model=MODEL, api_key=api_key)

    def approve_action(description: str) -> bool:
        print(f"\nApproval required: {description}")
        answer = input("Approve this action? (yes/no): ").strip().lower()
        return answer == "yes"

    assistant = CampusConnectAgent(
        model=model,
        executor=executor,
        approver=approve_action,
        base_prompt=SYSTEM_PROMPT,
    )

    # Local demonstration identity only; this is not real university authentication.
    session = Session(student_id="demo-student", role="student")
    history = []

   
    print(f"Model: {MODEL}")
    print("Ask a CoCIS-related question. Type 'exit' to quit.\n")

    while True:
        question = input("Student: ").strip()

        if question.lower() == "exit":
            break

        if not question:
            print("Please enter a question.\n")
            continue

        try:
            response = assistant.handle(question, session, history)
            print(f"\nCampusConnect: {response}\n")
        except Exception as e:
            print(f"CampusConnect error: {type(e).__name__}: {e}\n")

if __name__ == "__main__":
    main()