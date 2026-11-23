# Plan: Human-in-the-Loop (HITL) Execution Friction & Checkpoints

## Proposed Architecture

```
                      Agent Emits Tool Call
                                │
                                ▼
                   AsyncToolDispatcher.dispatch
                                │
                   Is tool sensitive / risky?
                   (require_approval or predicate)
                               / \
                            NO     YES
                            │       │
                            │       ▼
                            │   ┌──────────────────────────────┐
                            │   │       HITLApprovalGate       │
                            │   │ 1. Record ApprovalRequest    │
                            │   │ 2. Send Review Notification  │
                            │   │ 3. Await Decision / Callback │
                            │   └──────────────┬───────────────┘
                            │                  │
                            │         Decision Outcome?
                            │         ├── APPROVED ──► Proceed with tool execution
                            │         ├── REJECTED ──► Return "Action rejected by user"
                            │         └── TIMEOUT  ──► Return "Approval timed out"
                            │
                            ▼
               Execute Tool Function (tool_fn)
                            │
                            ▼
               OutputGuard / Truncator (if output > threshold)
                            │
                            ▼
                   Return ToolExecutionResult
```

---

## Phased Implementation Plan

### Phase 1: Core Approval Engine (`projects/Agents/core/hitl.py`)
1. Data models:
   - `ApprovalStatus` (PENDING, APPROVED, REJECTED, TIMED_OUT)
   - `ApprovalDecision` (APPROVE, REJECT)
   - `ApprovalRequest` (request_id, tool_name, inputs, status, created_at, resolved_at, reviewer_note)
2. `HITLApprovalGate`:
   - Configurable timeout (default 30.0s).
   - In-memory registry of active `asyncio.Future` or `asyncio.Event` waiters indexed by `request_id`.
   - `request_approval(tool_name, inputs, thread_id) -> ApprovalRequest`:
     - Dispatches notification to `NotificationGateway`.
     - Waits for resolution future or times out.
   - `resolve(request_id, decision, note) -> bool`:
     - Resolves the waiter future and updates status.
   - Interactive CLI mode for interactive terminal sessions (prompting `[y/N]`).

### Phase 2: Dispatcher Integration (`projects/Agents/core/dispatcher.py`)
1. In `AsyncToolDispatcher`:
   - `approval_gate: Optional[HITLApprovalGate] = None`
   - `sensitive_tools: Set[str]`
   - `risk_predicate: Optional[Callable[[str, Dict[str, Any]], bool]] = None`
   - In `register_tool`: add `require_approval: bool = False`.
2. In `_execute_single_tool`:
   - Before executing `tool_fn`, check if approval is required.
   - If required, request approval from `approval_gate`.
   - If rejected, skip execution and return structured cancellation result.
   - If approved, execute normally.

### Phase 3: Comprehensive Test Suite (`projects/Agents/tests/test_hitl.py`)
1. Unit tests for `HITLApprovalGate` (approval, rejection, timeout, note tracking).
2. Dynamic risk predicate tests.
3. Integration with `AsyncToolDispatcher` (verifying approved tools run, rejected tools are blocked, and normal tools pass directly).
