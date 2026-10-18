
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.campusconnect import SYSTEM_PROMPT
from app.models import GeminiModelClient
from app.agent_graph import CampusConnectAgent
from app.tools import Executor, Session, Store


def main():
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY was not found. Check your .env file."
        )

    # Use the existing CampusConnect database and real Gemini model.
    store = Store("data/campusconnect.db")
    executor = Executor(store)

    model = GeminiModelClient(
        model="gemini-3.8-flash",
        api_key=api_key,
    )

    # Ask for a decision only if the agent requests human approval.
    def request_approval(question):
        print("\nHuman approval required:")
        print(question)
        choice = input("Approve this action? (yes/no): ").strip().lower()
        return choice in {"yes", "y"}

    assistant = CampusConnectAgent(
        model=model,
        executor=executor,
        approver=request_approval,
        base_prompt=SYSTEM_PROMPT,
    )

    session = Session(student_id="demo-student", role="student")

    print("CampusConnect — Live Gemini Trace Capture")
    print("Enter the request you want to test.")
    question = input("\nYour request: ").strip()

    if not question:
        print("No request entered. Exiting.")
        return

    # Run the real agent and collect events recorded by its implementation.
    answer = assistant.handle(question, session, [])

    trace = assistant.trace

    output = Path(
        "evidence/week5/execution_trace/failure_recovery.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "scenario": "live_gemini_execution",
        "test_type": "live_model_execution",
        "model": "gemini-3.8-flash",
        "user_request": question,
        "final_answer": answer,
        "trace": trace,
    }

    output.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nFinal answer:")
    print(answer)
    print(f"\nTrace events captured: {len(trace)}")
    print(f"Trace saved to: {output.resolve()}")

    if not trace:
        print(
            "WARNING: The agent returned no trace events. "
            "Check the agent's trace implementation before using this evidence."
        )


if __name__ == "__main__":
    main()
