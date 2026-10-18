"""LangGraph workflow for the bounded CampusConnect agent."""

from typing import Callable, TypedDict, Any

from langgraph.graph import StateGraph, START, END

from app.models import ModelClient
from app.orchestrator import (
    BASE_PROMPT,
    TOOL_RULES,
    MAX_STEPS,
    get_evidence,
    tool_declarations,
    describe_action,
)
from app.tools import Executor, Session
from app.tools.errors import Code


Approver = Callable[[str], bool]


class AgentState(TypedDict):
    user_text: str
    session: Session
    history: list[dict]
    evidence: str
    sources: list[str]
    iterations: int
    turn: Any
    answer: str
    stop_reason: str
    trace: list[dict]


class CampusConnectAgent:
    def __init__(
        self,
        model: ModelClient,
        executor: Executor,
        approver: Approver,
        base_prompt: str = BASE_PROMPT,
    ):
        self.model = model
        self.executor = executor
        self.approver = approver
        self.system_prompt = base_prompt + "\n\n" + TOOL_RULES
        self.trace: list[dict] = []

        graph = StateGraph(AgentState)

        graph.add_node("sense", self.sense)
        graph.add_node("decide", self.decide)
        graph.add_node("act", self.act)
        graph.add_node("stop", self.stop)

        graph.add_edge(START, "sense")
        graph.add_edge("sense", "decide")

        graph.add_conditional_edges(
            "decide",
            self.route_decision,
            {
                "act": "act",
                "stop": "stop",
            },
        )

        graph.add_conditional_edges(
            "act",
            self.route_after_action,
            {
                "decide": "decide",
                "stop": "stop",
            },
        )

        graph.add_edge("stop", END)
        self.graph = graph.compile()

    def sense(self, state: AgentState) -> dict:
        try:
            evidence, sources = get_evidence(state["user_text"])
        except Exception as exc:
            evidence = "Document retrieval is currently unavailable."
            sources = []

            state["trace"].append({
                "event": "retrieval_error",
                "message": str(exc),
            })

        question = (
            f"Student question:\n{state['user_text']}\n\n"
            f"Retrieved CoCIS evidence:\n{evidence}\n\n"
            "Answer using the evidence where relevant. Cite source filenames. "
            "If the evidence is insufficient, say the information could not "
            "be confirmed from the available documents."
        )

        history = list(state["history"])
        history.append({"role": "user", "text": question})

        state["trace"].extend([
            {"event": "user", "text": state["user_text"]},
            {
                "event": "retrieved_evidence",
                "sources": sources,
                "evidence": evidence,
            },
        ])

        return {
            "evidence": evidence,
            "sources": sources,
            "history": history,
        }

    def decide(self, state: AgentState) -> dict:
        turn = self.model.generate(
            self.system_prompt,
            state["history"],
            tool_declarations(),
        )

        history = list(state["history"])
        history.append({
            "role": "model",
            "text": turn.text,
            "raw": turn.raw,
        })

        iteration = state["iterations"] + 1

        state["trace"].append({
            "event": "model_decision",
            "iteration": iteration,
            "requested_tools": [c.name for c in turn.tool_calls],
        })

        return {
            "turn": turn,
            "history": history,
            "iterations": iteration,
        }

    def route_decision(self, state: AgentState) -> str:
        if state["turn"].tool_calls:
            return "act"
        return "stop"

    def act(self, state: AgentState) -> dict:
        results = []

        for call in state["turn"].tool_calls:
            state["trace"].append({
                "event": "tool_call",
                "tool": call.name,
                "args": call.args,
            })

            result = self.executor.execute(
                call.name,
                call.args,
                state["session"],
            )

            # Actions requiring approval must not proceed without it.
            if result.error_code == Code.APPROVAL_REQUIRED:
                approval = self.executor.gate.request(
                    state["session"],
                    call.name,
                    call.args,
                )

                question = describe_action(
                    call.name,
                    call.args,
                    self.executor.store,
                )

                try:
                    granted = self.approver(question)
                except Exception as exc:
                    granted = False
                    state["trace"].append({
                        "event": "approval_error",
                        "message": str(exc),
                    })

                self.executor.gate.decide(
                    approval.approval_id,
                    granted,
                )

                state["trace"].append({
                    "event": "approval",
                    "question": question,
                    "granted": granted,
                })

                if granted:
                    result = self.executor.execute(
                        call.name,
                        call.args,
                        state["session"],
                    )
                else:
                    result = self.executor._fail(
                        call.name,
                        Code.APPROVAL_DENIED,
                        "Approval was denied. Nothing was submitted.",
                    )

                    state["stop_reason"] = "approval_denied"

            model_result = result.for_model()

            state["trace"].append({
                "event": "tool_result",
                "tool": call.name,
                "result": model_result,
            })

            results.append({
                "name": call.name,
                "response": model_result,
            })

            # Do not retry a submission automatically after an error.
            # Its final outcome may need to be checked before trying again.
            if (
                call.name == "submit_support_request"
                and result.error_code is not None
                and result.error_code != Code.APPROVAL_DENIED
            ):
                state["stop_reason"] = "submission_failed"

            # Stop processing further calls after a safety boundary is hit.
            if state["stop_reason"]:
                break

        history = list(state["history"])
        history.append({
            "role": "tool",
            "results": results,
        })

        return {
    "history": history,
    "stop_reason": state["stop_reason"],
}

    def route_after_action(self, state: AgentState) -> str:
        if state["stop_reason"]:
            return "stop"

        if state["iterations"] >= MAX_STEPS:
            return "stop"

        return "decide"

    def stop(self, state: AgentState) -> dict:
        turn = state.get("turn")
        reason = state.get("stop_reason", "")

        if reason == "approval_denied":
            answer = (
                "The submission was not approved, so the support request "
                "was not submitted."
            )

        elif reason == "submission_failed":
            answer = (
                "The submission did not return a successful result. "
                "Please check the request status before attempting "
                "another submission."
            )

        elif state["iterations"] >= MAX_STEPS and (
            turn is not None and turn.tool_calls
        ):
            answer = (
                "I reached the maximum number of decision steps before "
                "completing the task. Please check the current request "
                "status before continuing."
            )
            reason = "iteration_limit"

        elif turn is not None and not turn.tool_calls:
            answer = turn.text

            if state["sources"]:
                source_list = "\n".join(
                    f"- {source}" for source in state["sources"]
                )
                answer += f"\n\nSources:\n{source_list}"

        else:
            answer = (
                "I couldn't finish that safely. "
                "Please contact CoCIS student support directly."
            )
            reason = reason or "unable_to_continue"

        state["trace"].append({
            "event": "stop",
            "reason": reason or "final_answer",
        })

        state["trace"].append({
            "event": "assistant",
            "text": answer,
            "sources": state["sources"],
        })

        return {
            "answer": answer,
            "stop_reason": reason,
        }

    def handle(
        self,
        user_text: str,
        session: Session,
        history: list[dict] | None = None,
    ) -> str:
        self.trace = []

        initial_history = list(history or [])

        result = self.graph.invoke({
            "user_text": user_text,
            "session": session,
            "history": initial_history,
            "evidence": "",
            "sources": [],
            "iterations": 0,
            "turn": None,
            "answer": "",
            "stop_reason": "",
            "trace": self.trace,
        })

        self.trace = result["trace"]

        if history is not None:
            history.extend(result["history"][len(initial_history):])

        return result["answer"]