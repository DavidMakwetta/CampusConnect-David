CampusConnect 
Memory Design and Data Handling Note

1. Purpose

CampusConnect uses limited persistent memory to help a student continue a support-request task across interactions. Instead of requiring the student to provide the same request reference every time, the system can recall the reference associated with the student’s active support request.

2. Data Stored

The persistent-memory component stores the following fields in the student_memory table in the CampusConnect SQLite database.

Field	Purpose
student_id	Associates the memory record with a student identity used by the application.
key	Identifies the memory item, currently active_case.
value	Stores the support-request reference.
created_at	Records when the memory item was created or updated.
expires_at	Specifies when the memory item expires.

3. Purpose and Justification

The selected memory use case addresses a practical student-support need: continuing a request-related task without repeatedly entering its reference.

The memory service verifies that the referenced request exists and belongs to the student before storing or returning the reference. Expired or invalid records are removed when encountered, and the implementation provides a method to purge expired records.

This is a bounded use of memory because it retains one justified task-related item rather than building a general-purpose profile of the student.

4. Access and Security Boundaries

Memory is accessed through the application’s MemoryService, which uses the same data store as the support-request tools.

The intended access boundary is the authenticated student’s own record. The service checks the student identity against the associated request before remembering or recalling its reference. The current command-line demonstration uses a fixed demonstration identity; this is not equivalent to production university authentication.

Memory is contextual information, not an authorization mechanism. Support-request submission remains subject to the existing tool executor, authentication checks, and approval gate. A remembered reference must not be treated as permission to submit a request.

5. Retention and Deletion

Memory records have a default retention period of 30 days. The service records creation and expiry timestamps and provides a purge operation for expired entries.

The implementation also provides a deletion operation that removes the student’s active-case memory. The demonstration interface exposes this operation through the forget command.

6. Workflow State and Memory

CampusConnect distinguishes workflow state from persistent memory.

Workflow state tracks information such as the current phase, active request reference, most recent tool, number of turns, and whether memory was used during the current turn. This state supports workflow visibility and debugging.

Persistent memory stores the active request reference beyond a single interaction. When a relevant request-related question is asked, the agent can recall the reference and provide it as contextual information to the model. The agent should still verify current request status through the appropriate tool.

7. Limitations

The current implementation is a project demonstration rather than a production university service. Its demonstration identity does not provide real student authentication. Production deployment would require a verified identity provider, database access controls, appropriate audit and retention policies, and testing of access restrictions.


8. Conclusion

CampusConnect implements a limited persistent-memory use case for retaining an active support-request reference. The design aims to improve continuity while limiting stored data, defining a retention period, providing a deletion operation, and preserving the existing authorization and approval boundaries.