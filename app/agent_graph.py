
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

        state["trace"].append({
            "event": "model_decision",
            "iteration": state["iterations"] + 1,
            "requested_tools": [c.name for c in turn.tool_calls],
        })

        return {
            "turn": turn,
            "history": history,
            "iterations": state["iterations"] + 1,
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
                call.name, call.args, state["session"]
            )

            if result.error_code == Code.APPROVAL_REQUIRED:
                approval = self.executor.gate.request(
                    state["session"], call.name, call.args
                )

                question = describe_action(
                    call.name, call.args, self.executor.store
                )
                granted = self.approver(question)

                self.executor.gate.decide(
                    approval.approval_id, granted
                )

                state["trace"].append({
                    "event": "approval",
                    "question": question,
                    "granted": granted,
                })

                if granted:
                    result = self.executor.execute(
                        call.name, call.args, state["session"]
                    )
                else:
                    result = self.executor._fail(
                        call.name,
                        Code.APPROVAL_DENIED,
                        "The student declined. Nothing was sent. Do not retry.",
                    )

            model_result = result.for_model()

            state["trace"].append({
                "event": "tool_result",
                "result": model_result,
            })

            results.append({
                "name": call.name,
                "response": model_result,
            })

        history = list(state["history"])
        history.append({"role": "tool", "results": results})

        return {"history": history}

    def route_after_action(self, state: AgentState) -> str:
        if state["iterations"] >= MAX_STEPS:
            return "stop"
        return "decide"

    def stop(self, state: AgentState) -> dict:
        turn = state.get("turn")

        if turn is not None and not turn.tool_calls:
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

        state["trace"].append({
            "event": "assistant",
            "text": answer,
            "sources": state["sources"],
        })

        return {"answer": answer}

    def handle(
        self,
        user_text: str,
        session: Session,
        history: list[dict] | None = None,
    ) -> str:
        self.trace = []

        result = self.graph.invoke({
            "user_text": user_text,
            "session": session,
            "history": list(history or []),
            "evidence": "",
            "sources": [],
            "iterations": 0,
            "turn": None,
            "answer": "",
            "trace": self.trace,
        })

        self.trace = result["trace"]

        if history is not None:
            history.extend(result["history"][len(history):])

        return result["answer"]
