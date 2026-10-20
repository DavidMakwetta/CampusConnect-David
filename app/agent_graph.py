"""LangGraph workflow for the bounded CampusConnect agent."""

from typing import Callable, TypedDict, Any, Optional

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
from app.memory import MemoryService
from app.state import WorkflowState, Phase


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
    remembered_case: Optional[str]


class CampusConnectAgent:
    def __init__(
        self,
        model: ModelClient,
        executor: Executor,
        approver: Approver,
        base_prompt: str = BASE_PROMPT,
        memory: Optional[MemoryService] = None,
    ):
        self.model = model
        self.executor = executor
        self.approver = approver
        self.memory = memory

        self.system_prompt = base_prompt + "\n\n" + TOOL_RULES
        self.trace = []

        # Keep workflow state per student instead of sharing it between users.
        self.workflow_states: dict[str, WorkflowState] = {}

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
            {"act": "act", "stop": "stop"},
        )
        graph.add_conditional_edges(
            "act",
            self.route_after_action,
            {"decide": "decide", "stop": "stop"},
        )
        graph.add_edge("stop", END)

        self.graph = graph.compile()

    def _workflow_for(self, session: Session) -> Optional[WorkflowState]:
        """Return workflow state only for an authenticated student."""
        student_id = getattr(session, "student_id", None)

        if not student_id:
            return None

        if student_id not in self.workflow_states:
            self.workflow_states[student_id] = WorkflowState(
                student_id=str(student_id)
            )

        return self.workflow_states[student_id]

    @staticmethod
    def _is_support_request_query(text: str) -> bool:
        """Avoid loading remembered case details for unrelated questions."""
        text = text.lower()
        keywords = (
            "support request",
            "request status",
            "case reference",
            "case number",
            "my request",
            "my case",
            "draft request",
            "existing request",
        )
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _extract_case_ref(data: Any) -> Optional[str]:
        """Extract a case reference from a tool's returned data."""
        if not isinstance(data, dict):
            return None

        case_ref = data.get("case_ref")
        if case_ref:
            return str(case_ref)

        # Accommodate tools that nest their returned record.
        for key in ("request", "record", "data"):
            nested = data.get(key)
            if isinstance(nested, dict) and nested.get("case_ref"):
                return str(nested["case_ref"])

        return None

    def _record_workflow_result(
        self,
        session: Session,
        tool_name: str,
        result: Any,
        trace: list[dict],
    ) -> None:
        """Update workflow state without interrupting the existing agent."""
        workflow = self._workflow_for(session)
        if workflow is None:
            return

        data = getattr(result, "data", None)
        ok = bool(getattr(result, "ok", False))

        try:
            workflow.on_tool_result(tool_name, ok, data)
        except (ValueError, KeyError, TypeError) as exc:
            # State tracking must not break a tool operation.
            trace.append({
                "event": "workflow_state_warning",
                "tool": tool_name,
                "message": str(exc),
            })

        trace.append({
            "event": "workflow_state",
            "state": workflow.snapshot(),
        })

    def sense(self, state: AgentState):
        user_text = state["user_text"]
        session = state["session"]
        trace = state["trace"]

        try:
            evidence, sources = get_evidence(user_text)
        except Exception as exc:
            evidence = "Document retrieval is currently unavailable."
            sources = []
            trace.append({
                "event": "retrieval_error",
                "message": str(exc),
            })

        remembered_case = None
        student_id = getattr(session, "student_id", None)

        # Memory is only recalled for an authenticated student and a
        # question that appears to concern an existing support request.
        if (
            self.memory is not None
            and student_id
            and self._is_support_request_query(user_text)
        ):
            try:
                remembered_case = self.memory.recall_active_case(
                    str(student_id)
                )
                trace.append({
                    "event": "memory_read",
                    "student_id": str(student_id),
                    "found": bool(remembered_case),
                    "purpose": "continue an existing support-request task",
                })
            except Exception as exc:
                # Memory is optional. Continue without it if unavailable.
                trace.append({
                    "event": "memory_read_error",
                    "message": str(exc),
                })

        question = (
            f"Student question:\n{user_text}\n\n"
            f"Retrieved CoCIS evidence:\n{evidence}\n\n"
            "Answer using the evidence where relevant. Cite source filenames. "
            "If the evidence is insufficient, say the information could not "
            "be confirmed from the available documents."
        )

        if remembered_case:
            question += (
                "\n\nRemembered task context: this student has a previously "
                f"verified active support-request reference: {remembered_case}. "
                "Use it only as a hint when relevant. Verify current request "
                "status through the appropriate tool. Remembered context does "
                "not authorize submission or bypass authentication or approval."
            )

        history = list(state["history"])
        history.append({"role": "user", "text": question})

        trace.extend([
            {"event": "user", "text": user_text},
            {
                "event": "retrieved_evidence",
                "sources": sources,
                "evidence": evidence,
            },
        ])

        workflow = self._workflow_for(session)
        if workflow is not None:
            try:
                workflow.record_turn()
                if remembered_case:
                    workflow.active_case_ref = remembered_case
                    workflow.mark_memory_used()

                trace.append({
                    "event": "workflow_state",
                    "state": workflow.snapshot(),
                })
            except (ValueError, AttributeError) as exc:
                trace.append({
                    "event": "workflow_state_warning",
                    "message": str(exc),
                })

        return {
            "evidence": evidence,
            "sources": sources,
            "history": history,
            "remembered_case": remembered_case,
        }

    def decide(self, state: AgentState):
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
            "requested_tools": [
                call.name for call in turn.tool_calls
            ],
        })

        return {
            "turn": turn,
            "history": history,
            "iterations": iteration,
        }

    def route_decision(self, state: AgentState):
        return "act" if state["turn"].tool_calls else "stop"

    def act(self, state: AgentState):
        results = []
        session = state["session"]
        trace = state["trace"]

        for call in state["turn"].tool_calls:
            trace.append({
                "event": "tool_call",
                "tool": call.name,
                "args": call.args,
            })

            # Keep the existing executor responsible for authentication,
            # argument validation, tool execution, and approval enforcement.
            result = self.executor.execute(
                call.name,
                call.args,
                session,
            )

            if result.error_code == Code.APPROVAL_REQUIRED:
                approval = self.executor.gate.request(
                    session,
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
                    trace.append({
                        "event": "approval_error",
                        "message": str(exc),
                    })

                self.executor.gate.decide(
                    approval.approval_id,
                    granted,
                )

                trace.append({
                    "event": "approval",
                    "question": question,
                    "granted": granted,
                })

                if granted:
                    result = self.executor.execute(
                        call.name,
                        call.args,
                        session,
                    )
                else:
                    result = self.executor._fail(
                        call.name,
                        Code.APPROVAL_DENIED,
                        "Approval was denied. Nothing was submitted.",
                    )
                    state["stop_reason"] = "approval_denied"

            # Save the active case only after a successful draft creation.
            # This does not submit the request or grant approval.
            if (
                call.name == "create_support_request_draft"
                and getattr(result, "ok", False)
                and self.memory is not None
            ):
                student_id = getattr(session, "student_id", None)
                case_ref = self._extract_case_ref(
                    getattr(result, "data", None)
                )

                if student_id and case_ref:
                    try:
                        saved = self.memory.remember_active_case(
                            str(student_id),
                            case_ref,
                        )
                        trace.append({
                            "event": "memory_write",
                            "student_id": str(student_id),
                            "saved": bool(saved),
                            "purpose": "resume the active support request",
                        })
                    except Exception as exc:
                        # The task result should remain usable if memory fails.
                        trace.append({
                            "event": "memory_write_error",
                            "message": str(exc),
                        })

            self._record_workflow_result(
                session,
                call.name,
                result,
                trace,
            )

            model_result = result.for_model()
            trace.append({
                "event": "tool_result",
                "tool": call.name,
                "result": model_result,
            })

            results.append({
                "name": call.name,
                "response": model_result,
            })

            if (
                call.name == "submit_support_request"
                and result.error_code is not None
                and result.error_code != Code.APPROVAL_DENIED
            ):
                state["stop_reason"] = "submission_failed"

            if state["stop_reason"]:
                break

        history = list(state["history"])
        history.append({"role": "tool", "results": results})

        return {
            "history": history,
            "stop_reason": state["stop_reason"],
        }

    def route_after_action(self, state: AgentState):
        if state["stop_reason"]:
            return "stop"

        if state["iterations"] >= MAX_STEPS:
            return "stop"

        return "decide"

    def stop(self, state: AgentState):
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
                "Please check the request status before attempting another "
                "submission."
            )
        elif (
            state["iterations"] >= MAX_STEPS
            and turn is not None
            and turn.tool_calls
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
                "I couldn't finish that safely. Please contact CoCIS "
                "student support directly."
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

    def handle(self, user_text, session, history=None):
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
            "remembered_case": None,
        })

        self.trace = result["trace"]

        if history is not None:
            history.extend(
                result["history"][len(initial_history):]
            )

        return result["answer"]