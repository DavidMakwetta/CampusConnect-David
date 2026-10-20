# CAMPUSCONNECT — AGENT TASK CONTRACT

## 1. Goal

Help CoCIS freshers with student-support tasks by interpreting their requests, retrieving relevant evidence, and selecting appropriate registered tools. Depending on the request, the agent may look up lecture venue information, check an existing support request, or create a draft support request.

Where submission is required, the agent must verify the relevant tool results, request explicit human approval, and submit only when approval is granted. After each action, the agent must use the result to decide whether to continue, take a safe alternative action, or stop with a clear explanation.

The agent operates within defined execution limits and must not perform actions outside its registered tools, available information, or permitted safety boundaries.

## 2. Approved Tools

The agent may use the following registered tools:

- `lookup_lecture_venue` — retrieve lecture venue information when relevant to a student's request.
- `get_support_request_status` — check the status of a support request belonging to the signed-in student.
- `create_support_request_draft` — create a draft support request for the signed-in student.
- `submit_support_request` — submit a support request after explicit human approval.

The agent must use only tools exposed through the application's tool declarations and validated by the tool executor. It must select tools according to the user's request and the information available, rather than invoking tools unnecessarily.

Tool results must be examined before the agent determines its next action. A tool call must not be treated as successful unless its result confirms success.

## 3. Agent State

The agent maintains information required to process the student's request and manage the workflow. This includes:

- The student's request and session information.
- Conversation history and previous model decisions.
- Retrieved CoCIS evidence and source filenames.
- The current tool call and its arguments.
- Tool results, errors, and relevant status information.
- The number of decision iterations completed.
- Approval decisions and execution trace events.
- The current workflow outcome and final response.

This state supports multi-step execution by allowing the agent to use the outcome of one action when determining what to do next. For example, the result of checking a support request can inform whether the agent should proceed to another action or explain that the request cannot be found.

Approval information must be associated with the specific action being authorised. The agent must not interpret approval for one operation as permission to perform unrelated operations.

## 4. Workflow

### 4.1 Workflow Overview

CampusConnect follows a bounded, multi-step workflow implemented using LangGraph. The workflow is organised around four nodes: `sense`, `decide`, `act`, and `stop`.

The general execution cycle is:

**Receive Request → Sense/Context → Decide → Act/Tool → Observe Result → Stop or Re-plan**

This structure allows the agent to handle requests that require more than one operation. Instead of producing an answer immediately after receiving a request, it can select a relevant tool, inspect the result, and determine whether another action is necessary.

The workflow is bounded by a maximum of five model decision iterations (`MAX_STEPS = 5`). This limits repeated decision-making and provides a defined stopping boundary.

### 4.2 Sense and Context Gathering

The workflow begins when a student submits a request through the application. The agent receives the request and identifies the information or action required to address it.

Where relevant, the system retrieves supporting information from the CampusConnect knowledge base. The retrieved evidence may contain information from CoCIS documents, including prospectuses, departmental information, and other approved institutional sources.

The agent uses the request and available context to determine what information is already available and whether a tool operation is needed. Retrieved documents provide supporting evidence for responses, while registered tools perform specific operations such as checking a support request or creating a draft.

The agent must not invent institutional procedures, contacts, or other details that cannot be supported by the available evidence. When information cannot be confirmed, it should communicate that limitation clearly.

### 4.3 Decision-Making and Tool Selection

After gathering the relevant context, the workflow proceeds to the `decide` node. The configured Gemini model, `gemini-3.8-flash`, determines the next appropriate action using the user's request, available evidence, previous decisions, and tool results.

The agent may select a tool when the request requires an operation that cannot be completed through a response alone. For example:

- A request for lecture venue information may require `lookup_lecture_venue`.
- A request to check an existing support request may require `get_support_request_status`.
- A request to prepare a new support request may require `create_support_request_draft`.
- A request to submit a prepared support request requires the approval-controlled `submit_support_request` operation.

Tool selection must remain within the registered tools and their intended purposes. The model's decision does not itself establish that an operation has succeeded; the actual tool result determines the outcome.

### 4.4 Action Execution

When the agent selects a tool, the workflow proceeds to the `act` node. The selected operation is passed to the tool executor, which validates and executes the tool call according to the application's rules.

The operation may return a successful result, a status value, or an error. For example, a successful draft-creation operation can return a support-request reference and a DRAFT status. A status lookup may instead return `NOT_FOUND` if the supplied reference does not correspond to an existing request.

The agent must examine the returned result before proceeding. It must not claim that a request has been created or submitted unless the corresponding tool confirms that outcome.

### 4.5 Observation and Re-planning

After an action is executed, the agent observes the result and uses it to determine the next step. If the operation succeeds, the agent may continue with another required action or provide the user with the result.

If a tool operation fails, the agent must assess whether a safe and supported recovery path exists. It may provide an explanation, request clarification, or stop when further action cannot proceed safely. It must not repeatedly invoke a failed operation without justification or invent a successful result.

For example, when a support-request lookup returns `NOT_FOUND`, the agent can explain that the reference was not found and advise the user to verify the reference or contact CoCIS administration. It must not create a replacement request unless the user requests that action and the workflow permits it.

This stage is important because it makes the agent's next action dependent on the actual outcome of the previous operation rather than on an assumption that the operation succeeded.

### 4.6 Human Approval and Submission

Submitting a support request is a consequential action because it sends the request beyond the draft stage. Therefore, the agent must obtain explicit human approval before submission.

Where submission is required, the agent must ensure that the relevant support request has been identified and that the required information is available. It then presents the specific submission action for approval.

If approval is granted, the agent may proceed with the submission operation, subject to the application's validation and authorisation checks. It must then inspect the tool result and report the actual outcome.

If approval is denied, the agent must not bypass the decision or automatically retry submission. The workflow must stop the submission process and inform the user that the request remains unsubmitted.

Approval applies only to the specific action and arguments presented for confirmation. It must not be reused as general permission for unrelated operations.

### 4.7 Stopping Conditions

The workflow proceeds to the `stop` node when the task is complete or when further execution is not permitted or cannot proceed safely.

The agent must stop when:

1. The requested task has been completed and the result has been confirmed.
2. The user denies approval for a submission.
3. A tool operation fails and no safe recovery path is available.
4. Required information is missing and cannot be obtained safely.
5. The maximum decision-iteration limit is reached.
6. The request cannot be handled within the registered tools and safety boundaries.

When stopping because of a failure or denied approval, the agent should explain what happened and identify any appropriate next steps. It must distinguish between an operation that was attempted and one that was confirmed successful.

The execution trace records the events associated with the workflow, allowing the decisions, tool operations, results, and stopping behaviour to be reviewed.

## 5. Limits and Safety Boundaries

The agent must operate within the following limits:

- The maximum number of model decision iterations is controlled by `MAX_STEPS`, currently set to five.
- Only registered tools may be invoked.
- Tool arguments must pass the application's validation checks.
- Student-specific operations must respect authentication and authorisation requirements.
- A support request must not be submitted without explicit human approval.
- Approval applies to the specific action and arguments presented for approval.
- A denied approval must not be bypassed or automatically retried.
- The agent must not claim that a draft or submission succeeded unless the tool result confirms it.
- Retrieved evidence must not be treated as proof of information it does not contain.
- A tool error must not be reported as a successful operation.
- If a failure cannot be recovered from safely, the agent must stop and explain the limitation.
- The agent must not create or submit an additional support request merely because an existing request cannot be found.

These boundaries are intended to keep the agent's actions controlled, traceable, and consistent with the user's instructions.

## 6. Stop Conditions

The agent must terminate the current workflow when any of the following conditions is met:

1. **Task completion:** The requested operation has completed, and its result has been confirmed.
2. **Approval denied:** The user declines permission to submit a support request.
3. **Unrecoverable tool failure:** A tool operation fails and no safe, supported recovery is available.
4. **Insufficient information:** Required information is missing and cannot be obtained safely.
5. **Execution limit reached:** The maximum number of decision iterations is reached.
6. **Boundary violation risk:** The requested action cannot be performed within the registered tools, validation rules, or safety boundaries.

The final response must accurately communicate whether the task was completed, left as a draft, stopped because approval was denied, or could not proceed because of an error.

## 7. Evaluation Evidence

The bounded agent workflow is evaluated using execution traces captured from live Gemini model executions. Each trace records the user's request, retrieved evidence, model decisions, tool calls, tool results, stopping behaviour, and final response. Approval-related events are also recorded when applicable.

The three currently captured traces are:

1. **Draft creation — `draft_creation.json`:** The agent created support request `CC-2026-00003` for a course-registration problem involving missing courses. The request remained in DRAFT status and was not submitted.

2. **Failure handling — `failure_recovery.json`:** The agent attempted to check the deliberately invalid reference `CC-9999-99999`. The `get_support_request_status` tool returned `NOT_FOUND`. The agent explained that the request could not be found and provided next steps without creating or submitting another request.

3. **Approval denied — `live_session.json`:** The agent checked support request `CC-2026-00002`, selected the submission operation, and requested explicit approval. The user denied approval, the tool returned `APPROVAL_DENIED`, and the agent stopped without submitting the request.

These traces provide evidence of draft creation, tool failure handling, and approval-controlled stopping.

