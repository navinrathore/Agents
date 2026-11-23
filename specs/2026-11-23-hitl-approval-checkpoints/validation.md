# Validation: Human-in-the-Loop (HITL) Execution Friction & Checkpoints

## Test Matrix

| Test Case | Component | Verification Criteria |
| :--- | :--- | :--- |
| **Non-Sensitive Tool Passthrough** | `AsyncToolDispatcher` | Regular tools execute immediately without prompting `HITLApprovalGate`. |
| **Approval Flow Execution** | `HITLApprovalGate` | Tool flagged with `require_approval=True` pauses, emits `ReviewRequestPayload`, resumes on `APPROVE`, and returns real tool result. |
| **Rejection Flow Blocking** | `HITLApprovalGate` | When rejected, underlying tool function is **never called**; returns informative rejection message in `ToolExecutionResult`. |
| **Timeout Auto-Rejection** | `HITLApprovalGate` | If no reviewer responds within `timeout_seconds`, request marks `TIMED_OUT` and aborts safely. |
| **Dynamic Risk Predicate** | `AsyncToolDispatcher` | Safe inputs pass automatically (e.g. `SELECT`), whereas dangerous inputs (e.g. `DROP TABLE`) trigger the approval gate. |
| **Remote Webhook Resolution** | `HITLApprovalGate` | `resolve(request_id, "approve")` wakes up the waiting async dispatcher task immediately. |
| **Order Preservation with Mixed Tools** | `AsyncToolDispatcher` | Batch dispatch preserving order when mix of approved, rejected, and un-gated tools are called. |
