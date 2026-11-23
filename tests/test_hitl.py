import asyncio
from pathlib import Path
import sys
import time
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher, ToolExecutionResult
from core.hitl import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    HITLApprovalGate,
)
from core.notifications import MockChannel, NotificationGateway


@pytest.fixture
def mock_gateway():
    mock_ch = MockChannel()
    gateway = NotificationGateway(
        default_channel="mock",
        channels={"mock": mock_ch},
    )
    return gateway, mock_ch


# ==============================================================================
# 1. HITLApprovalGate Unit Tests
# ==============================================================================

@pytest.mark.anyio
async def test_hitl_auto_approve(mock_gateway):
    gateway, _ = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, auto_approve=True)

    req = await gate.request_approval(
        tool_name="delete_database",
        inputs={"db": "prod"},
    )

    assert req.is_approved is True
    assert req.status == ApprovalStatus.APPROVED
    assert "Auto-approved" in (req.reviewer_note or "")


@pytest.mark.anyio
async def test_hitl_programmatic_approval(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)

    async def resolver():
        # Wait until pending request appears
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        pending = gate.get_pending_requests()[0]
        gate.resolve(pending.request_id, ApprovalDecision.APPROVE, "Approved by admin")

    asyncio.create_task(resolver())

    req = await gate.request_approval(
        tool_name="transfer_funds",
        inputs={"amount": 5000, "to": "acct_999"},
    )

    assert req.is_approved is True
    assert req.status == ApprovalStatus.APPROVED
    assert req.reviewer_note == "Approved by admin"
    assert len(mock_ch.sent_notifications) == 1
    assert "transfer_funds" in mock_ch.sent_notifications[0].title


@pytest.mark.anyio
async def test_hitl_programmatic_rejection(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)

    async def resolver():
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        pending = gate.get_pending_requests()[0]
        gate.resolve(pending.request_id, ApprovalDecision.REJECT, "Operation too dangerous")

    asyncio.create_task(resolver())

    req = await gate.request_approval(
        tool_name="wipe_disk",
        inputs={"path": "/"},
    )

    assert req.is_approved is False
    assert req.is_rejected is True
    assert req.status == ApprovalStatus.REJECTED
    assert req.reviewer_note == "Operation too dangerous"


@pytest.mark.anyio
async def test_hitl_timeout(mock_gateway):
    gateway, _ = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=0.08)

    req = await gate.request_approval(
        tool_name="restart_cluster",
        inputs={"cluster_id": "us-east-1"},
    )

    assert req.is_approved is False
    assert req.status == ApprovalStatus.TIMED_OUT
    assert "timed out" in (req.reviewer_note or "").lower()


# ==============================================================================
# 2. AsyncToolDispatcher Integration Tests
# ==============================================================================

@pytest.mark.anyio
async def test_dispatcher_normal_tool_skips_approval(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway)
    dispatcher = AsyncToolDispatcher(approval_gate=gate)

    executed = False

    async def normal_tool(msg: str):
        nonlocal executed
        executed = True
        return f"Echo: {msg}"

    dispatcher.register_tool("normal_tool", normal_tool, require_approval=False)

    results = await dispatcher.dispatch([
        {"id": "call_1", "name": "normal_tool", "input": {"msg": "hello"}}
    ])

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].result == "Echo: hello"
    assert executed is True
    assert len(mock_ch.sent_notifications) == 0


@pytest.mark.anyio
async def test_dispatcher_sensitive_tool_approved(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)
    dispatcher = AsyncToolDispatcher(approval_gate=gate)

    tool_executed = False

    async def dangerous_tool(target: str):
        nonlocal tool_executed
        tool_executed = True
        return f"Destroyed: {target}"

    dispatcher.register_tool("dangerous_tool", dangerous_tool, require_approval=True)

    # Background task to approve
    async def auto_resolver():
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        req = gate.get_pending_requests()[0]
        gate.resolve(req.request_id, "approve", "User confirmed in modal")

    asyncio.create_task(auto_resolver())

    results = await dispatcher.dispatch([
        {"id": "call_danger", "name": "dangerous_tool", "input": {"target": "staging_db"}}
    ])

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.result == "Destroyed: staging_db"
    assert res.approval_status == "approved"
    assert tool_executed is True
    assert len(mock_ch.sent_notifications) == 1


@pytest.mark.anyio
async def test_dispatcher_sensitive_tool_rejected(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)
    dispatcher = AsyncToolDispatcher(approval_gate=gate)

    tool_executed = False

    async def destructive_tool(filepath: str):
        nonlocal tool_executed
        tool_executed = True
        return f"Deleted {filepath}"

    dispatcher.register_tool("destructive_tool", destructive_tool, require_approval=True)

    # Background task to reject
    async def auto_rejecter():
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        req = gate.get_pending_requests()[0]
        gate.resolve(req.request_id, "reject", "Deletion forbidden on prod files")

    asyncio.create_task(auto_rejecter())

    results = await dispatcher.dispatch([
        {"id": "call_del", "name": "destructive_tool", "input": {"filepath": "/etc/passwd"}}
    ])

    assert len(results) == 1
    res = results[0]
    # Tool function must NEVER have been called!
    assert tool_executed is False
    assert res.success is False
    assert res.approval_status == "rejected"
    assert "Execution Blocked" in res.result
    assert "Deletion forbidden on prod files" in res.result


@pytest.mark.anyio
async def test_dispatcher_dynamic_risk_predicate(mock_gateway):
    gateway, mock_ch = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)

    # Risk predicate: only queries with DROP, DELETE, or TRUNCATE need approval
    def sql_risk_predicate(tool_name: str, inputs: dict) -> bool:
        if tool_name == "execute_sql":
            query = inputs.get("query", "").upper()
            return any(word in query for word in ["DROP", "DELETE", "TRUNCATE"])
        return False

    dispatcher = AsyncToolDispatcher(
        approval_gate=gate,
        risk_predicate=sql_risk_predicate,
    )

    async def execute_sql(query: str):
        return f"SQL executed: {query}"

    dispatcher.register_tool("execute_sql", execute_sql)

    # 1. Safe query: passes without approval
    res_safe = await dispatcher.dispatch([
        {"id": "c1", "name": "execute_sql", "input": {"query": "SELECT * FROM users"}}
    ])
    assert res_safe[0].success is True
    assert res_safe[0].result == "SQL executed: SELECT * FROM users"
    assert len(mock_ch.sent_notifications) == 0

    # 2. Risky query: triggers gate
    async def reject_drop():
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        req = gate.get_pending_requests()[0]
        gate.resolve(req.request_id, "reject", "DROP TABLE not allowed")

    asyncio.create_task(reject_drop())

    res_risky = await dispatcher.dispatch([
        {"id": "c2", "name": "execute_sql", "input": {"query": "DROP TABLE accounts"}}
    ])
    assert res_risky[0].success is False
    assert res_risky[0].approval_status == "rejected"
    assert "DROP TABLE not allowed" in res_risky[0].result
    assert len(mock_ch.sent_notifications) == 1


@pytest.mark.anyio
async def test_dispatcher_mixed_batch_with_approval_preserves_order(mock_gateway):
    gateway, _ = mock_gateway
    gate = HITLApprovalGate(gateway=gateway, default_timeout=5.0)
    dispatcher = AsyncToolDispatcher(approval_gate=gate, parallel_execution=True)

    async def tool_a(val: str):
        return f"A: {val}"

    async def sensitive_tool(val: str):
        return f"B: {val}"

    async def tool_c(val: str):
        return f"C: {val}"

    dispatcher.register_tool("tool_a", tool_a)
    dispatcher.register_tool("sensitive_tool", sensitive_tool, require_approval=True)
    dispatcher.register_tool("tool_c", tool_c)

    async def approve_all():
        while not gate.get_pending_requests():
            await asyncio.sleep(0.01)
        req = gate.get_pending_requests()[0]
        gate.resolve(req.request_id, "approve", "Batch approved")

    asyncio.create_task(approve_all())

    tool_calls = [
        {"id": "c1", "name": "tool_a", "input": {"val": "1"}},
        {"id": "c2", "name": "sensitive_tool", "input": {"val": "2"}},
        {"id": "c3", "name": "tool_c", "input": {"val": "3"}},
    ]

    results = await dispatcher.dispatch(tool_calls)

    assert len(results) == 3
    assert results[0].tool_call_id == "c1"
    assert results[0].result == "A: 1"

    assert results[1].tool_call_id == "c2"
    assert results[1].result == "B: 2"
    assert results[1].approval_status == "approved"

    assert results[2].tool_call_id == "c3"
    assert results[2].result == "C: 3"
