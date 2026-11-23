# Requirements: Human-in-the-Loop (HITL) Execution Friction & Checkpoints

## Overview
Autonomous agents executing high-risk or destructive tools (e.g., executing arbitrary SQL mutations, database drops, deleting files, sending external emails or payments) require deterministic security friction before execution occurs.

The `HITLApprovalGate` subsystem provides an execution boundary in `AsyncToolDispatcher`. When an agent attempts to execute a sensitive tool:
1. The dispatcher pauses execution for that tool call.
2. An approval request is recorded with a unique ID, metadata, and parameter preview.
3. A notification is dispatched via `NotificationGateway` (Console, Telegram, Webhook, Mock).
4. If **Approved**: execution proceeds normally and tool output is returned.
5. If **Rejected**: execution is blocked; a structured human rejection response is returned to the agent context (allowing the LLM to apologize or self-correct without crashing).
6. If **Timed Out**: execution fails safely with a timeout rejection (preventing infinite hanging).
7. If **Non-Blocking / Asynchronous Checkpoint**: the dispatcher can return a stateful checkpoint ticket (`[AWAITING_APPROVAL:req_id]`) allowing external webhooks to resume execution later.

---

## 1. Scope

### In-Scope
- **Sensitive Tool Registration**:
  - `dispatcher.register_tool(name, fn, require_approval=True)`
  - Mark specific tools as sensitive by name or tag.
  - Optional custom risk evaluator `risk_predicate(name, inputs) -> bool` to conditionally require approval only for dangerous inputs (e.g., `execute_sql` requires approval only if `DELETE`/`DROP`/`UPDATE` is detected).
- **Core Gate (`core/hitl.py`)**:
  - `ApprovalDecision`: `APPROVE`, `REJECT`
  - `ApprovalStatus`: `PENDING`, `APPROVED`, `REJECTED`, `TIMED_OUT`
  - `ApprovalRequest`: Thread ID, request ID, tool name, inputs, timestamp, status, reviewer notes.
  - `HITLApprovalGate`: Manages approval requests, resolves decisions, notifies channels via `NotificationGateway`.
- **Interactive & Programmatic Resolution**:
  - Interactive async resolver: waits up to `timeout_seconds` for a human or webhook response.
  - Programmatic resolution: `gate.resolve(request_id, decision, reason)` (for Telegram webhooks or REST API callbacks).
  - CLI console interactive prompt fallback (when running in terminal).
- **Dispatcher Integration (`core/dispatcher.py`)**:
  - Check `require_approval` before calling `tool_fn`.
  - Record approval status in `ToolExecutionResult`.
- **Zero-Token Hermetic Testing**:
  - Tests covering auto-approve, human rejection, timeout auto-rejection, predicate-based dynamic friction, and dispatcher execution.

### Out-of-Scope
- Building a full React/Vue web frontend UI (the gateway interfaces via standard `NotificationGateway`, Webhook, Telegram, and CLI Console).
