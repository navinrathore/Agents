"""
Human-in-the-Loop (HITL) Execution Friction & Checkpoint Subsystem.

Provides deterministic security gates for sensitive, high-risk, or destructive tool execution.
Pauses dispatcher execution, dispatches review notifications via NotificationGateway (Console,
Telegram, Webhook, Mock), and resumes upon human or programmatic approval or rejection.
"""

import asyncio
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

from core.notifications import (
    ConsoleChannel,
    MockChannel,
    NotificationAction,
    NotificationActionStyle,
    NotificationGateway,
    ReviewRequestPayload,
)

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """Reviewer decision on a sensitive tool execution request."""
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalStatus(str, Enum):
    """Lifecycle status of a tool approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class ApprovalRequest:
    """Represents an active or historic tool approval request."""

    def __init__(
        self,
        request_id: str,
        tool_name: str,
        inputs: Dict[str, Any],
        thread_id: str = "default_thread",
        status: ApprovalStatus = ApprovalStatus.PENDING,
        created_at: Optional[float] = None,
        resolved_at: Optional[float] = None,
        reviewer_note: Optional[str] = None,
    ):
        self.request_id = request_id
        self.tool_name = tool_name
        self.inputs = inputs
        self.thread_id = thread_id
        self.status = status
        self.created_at = created_at if created_at is not None else time.time()
        self.resolved_at = resolved_at
        self.reviewer_note = reviewer_note

    @property
    def is_approved(self) -> bool:
        return self.status == ApprovalStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status in (ApprovalStatus.REJECTED, ApprovalStatus.TIMED_OUT)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "inputs": self.inputs,
            "thread_id": self.thread_id,
            "status": self.status.value,
            "created_at": round(self.created_at, 4),
            "resolved_at": round(self.resolved_at, 4) if self.resolved_at else None,
            "reviewer_note": self.reviewer_note,
        }


class HITLApprovalGate:
    """
    Stateful execution friction gate that intercepts sensitive tool calls.
    Emits review notifications, holds async execution futures, and enforces timeouts.
    """

    def __init__(
        self,
        gateway: Optional[NotificationGateway] = None,
        default_timeout: float = 30.0,
        auto_approve: bool = False,
        interactive_cli: bool = False,
    ):
        self.gateway = gateway or NotificationGateway(
            default_channel="console",
            channels={"console": ConsoleChannel(color=True), "mock": MockChannel()},
        )
        self.default_timeout = default_timeout
        self.auto_approve = auto_approve
        self.interactive_cli = interactive_cli
        self._requests: Dict[str, ApprovalRequest] = {}
        self._waiters: Dict[str, asyncio.Future[tuple[ApprovalDecision, Optional[str]]]] = {}

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    def get_pending_requests(self) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def _format_body_preview(self, tool_name: str, inputs: Dict[str, Any]) -> str:
        lines = [f"Tool Invocation: {tool_name}()", "Arguments:"]
        for k, v in inputs.items():
            str_v = str(v)
            if len(str_v) > 200:
                str_v = str_v[:197] + "..."
            lines.append(f"  - {k}: {str_v}")
        return "\n".join(lines)

    async def request_approval(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        thread_id: str = "default_thread",
        timeout: Optional[float] = None,
        summary: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Pauses and waits for approval on a sensitive tool invocation.
        Returns the resolved ApprovalRequest with final status (APPROVED, REJECTED, TIMED_OUT).
        """
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        effective_timeout = timeout if timeout is not None else self.default_timeout

        req = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            inputs=inputs,
            thread_id=thread_id,
            status=ApprovalStatus.PENDING,
            created_at=time.time(),
        )
        self._requests[request_id] = req

        # Fast path: auto_approve toggle (for automated pipelines/testing)
        if self.auto_approve:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.reviewer_note = "Auto-approved by configuration."
            return req

        # Build notification payload
        notification_summary = summary or f"Sensitive tool execution requested: '{tool_name}'"
        payload = ReviewRequestPayload(
            thread_id=f"{thread_id}:{request_id}",
            title=f"Security Approval: {tool_name}",
            summary=notification_summary,
            body_preview=self._format_body_preview(tool_name, inputs),
            actions=[
                NotificationAction(
                    action_id="approve",
                    label="Approve Execution",
                    style=NotificationActionStyle.PRIMARY,
                    callback_payload=f"{request_id}:approve",
                ),
                NotificationAction(
                    action_id="reject",
                    label="Reject Execution",
                    style=NotificationActionStyle.DANGER,
                    callback_payload=f"{request_id}:reject",
                ),
            ],
            metadata={"request_id": request_id, "tool_name": tool_name},
        )

        # Dispatch notification
        try:
            self.gateway.dispatch(payload)
        except Exception as exc:
            logger.error(f"[HITLApprovalGate] Failed to dispatch review notification: {exc}")

        # Interactive CLI mode prompt (if enabled)
        if self.interactive_cli:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._prompt_cli_input, request_id)

        # Create async waiter future
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[ApprovalDecision, Optional[str]]] = loop.create_future()
        self._waiters[request_id] = future

        try:
            decision, note = await asyncio.wait_for(future, timeout=effective_timeout)
            req.resolved_at = time.time()
            req.reviewer_note = note
            if decision == ApprovalDecision.APPROVE:
                req.status = ApprovalStatus.APPROVED
            else:
                req.status = ApprovalStatus.REJECTED
        except asyncio.TimeoutError:
            req.status = ApprovalStatus.TIMED_OUT
            req.resolved_at = time.time()
            req.reviewer_note = f"Approval timed out after {effective_timeout}s."
            logger.warning(f"[HITLApprovalGate] Approval request '{request_id}' timed out after {effective_timeout}s.")
        finally:
            self._waiters.pop(request_id, None)

        return req

    def resolve(
        self,
        request_id: str,
        decision: Union[ApprovalDecision, str],
        note: Optional[str] = None,
    ) -> bool:
        """
        Resolves an active pending approval request.
        Can be called by webhooks, Telegram callbacks, or programmatic test fixtures.
        """
        if isinstance(decision, str):
            decision = ApprovalDecision(decision.lower())

        req = self._requests.get(request_id)
        if not req or req.status != ApprovalStatus.PENDING:
            return False

        future = self._waiters.get(request_id)
        if future and not future.done():
            future.set_result((decision, note))
            return True

        # Fallback if waiter not active but request exists
        req.resolved_at = time.time()
        req.reviewer_note = note
        req.status = ApprovalStatus.APPROVED if decision == ApprovalDecision.APPROVE else ApprovalStatus.REJECTED
        return True

    def _prompt_cli_input(self, request_id: str) -> None:
        """Synchronous terminal prompt executed in separate thread."""
        try:
            choice = input(f"Approve execution for {request_id}? [y/N]: ").strip().lower()
            if choice in ("y", "yes"):
                self.resolve(request_id, ApprovalDecision.APPROVE, "Approved via CLI prompt")
            else:
                self.resolve(request_id, ApprovalDecision.REJECT, "Rejected via CLI prompt")
        except Exception:
            self.resolve(request_id, ApprovalDecision.REJECT, "CLI input failed or aborted")
