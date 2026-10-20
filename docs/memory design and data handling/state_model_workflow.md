CampusConnect 
Workflow State Model

1. Purpose

This document describes how CampusConnect agent tracks the progress of a student-support interaction. The workflow state records the current phase of an operation and relevant session information so the agent can respond consistently across turns.

The state model is implemented in app/state.py and used by the agent workflow in app/agent_graph.py.

2. Workflow State Diagram

flowchart TD
    A[IDLE] --> B[DRAFT_CREATED]
    B --> C[AWAITING_APPROVAL]
    C --> D[SUBMITTED]
    A --> E[FAILED]
    B --> E
    C --> E
    E --> A
    D --> A

The diagram presents the main workflow phases. A transition occurs when the application records the corresponding event or operation result. The exact transitions should remain consistent with the implementation.

3. State Descriptions

State	Description
IDLE	No active support-request operation is currently recorded.
DRAFT_CREATED	A student-support request draft has been created.
AWAITING_APPROVAL	The workflow is waiting for the required approval before proceeding with a protected operation.
SUBMITTED	The support request has been submitted successfully.
FAILED	An operation failed and the workflow records the failure.

4. State Transitions

Current state	Event or condition	Resulting state
IDLE	A support-request draft is created successfully	DRAFT_CREATED
DRAFT_CREATED	The workflow requires approval before proceeding	AWAITING_APPROVAL
AWAITING_APPROVAL	Submission succeeds after required checks	SUBMITTED
An active workflow state	A tool operation fails	FAILED
FAILED	A new interaction begins or the workflow is reset, where supported	IDLE
SUBMITTED	A new support-request workflow begins, where supported	IDLE

5. Session State

CampusConnect maintains workflow information associated with the current student session.

The WorkflowState structure includes the following fields:

Field	Purpose
student_id	Identifies the student associated with the workflow.
phase	Records the current workflow state.
active_case_ref	Holds the reference of the active support request, when available.
last_tool	Records the most recently executed tool.
last_stop_reason	Stores the reason the workflow stopped, where applicable.
turns	Tracks the number of recorded interaction turns.
memory_used	Indicates whether persistent memory was used during the current turn.

This information helps the agent track what has happened during an interaction without relying entirely on the language model to reconstruct the workflow from conversation history.

6. Relationship Between Workflow State and Persistent Memory

Workflow state and persistent memory serve different purposes.

Workflow state tracks the current interaction’s progress, including its phase, active request reference, last tool, and turn information.

Persistent memory stores a limited amount of information that can be retrieved during a later interaction. In CampusConnect, the intended use is to remember the reference of a student’s active support request.

When a reference is recalled, the application must verify that the request still exists and belongs to the relevant student. Memory does not replace authentication, authorisation, or approval.

7. Failure Handling and Approval

When a tool operation fails, the workflow records the failure and can retain a reason for stopping. The agent should communicate the result without inventing a successful outcome.

Approval is treated as a control boundary. The language model may identify an operation that requires approval, but it must not bypass the application’s approval mechanism or treat a student’s request in conversation as proof that an operation has been authorised.

8. Conclusion

The workflow state model provides a structured representation of CampusConnect’s student-support process. It separates workflow progress from persistent memory and keeps application-side validation and approval controls responsible for protected operations.