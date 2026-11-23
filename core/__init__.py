"""
Core Agent Framework package.
Contains provider-agnostic LLM client abstractions, configuration loaders, execution safety utilities,
and multi-channel remote notification gateway.
"""

from core.dispatcher import (
    AsyncToolDispatcher,
    ToolExecutionResult,
    is_coroutine_callable,
    to_async_tool,
)
from core.hitl import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    HITLApprovalGate,
)
from core.notifications import (
    BaseNotificationChannel,
    ConsoleChannel,
    MockChannel,
    NotificationAction,
    NotificationActionStyle,
    NotificationGateway,
    ReviewRequestPayload,
    TelegramChannel,
    WebhookChannel,
)
from core.openapi_loader import OpenAPIToolLoader
from core.output_guard import (
    BasePayloadStore,
    DataPointer,
    LocalDiskPayloadStore,
    OutputGuard,
    OutputGuardMode,
    OutputGuardResult,
    ToolOutputTruncator,
    TruncationResult,
)
from core.pointer_tools import PointerToolSuite, normalize_pointer_id
from core.skills import (
    SkillManager,
    SkillMetadata,
    SkillPackage,
    SkillRegistry,
    SkillRouter,
    generate_tool_schema,
    parse_skill_md,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
    "AsyncToolDispatcher",
    "BaseNotificationChannel",
    "BasePayloadStore",
    "ConsoleChannel",
    "DataPointer",
    "HITLApprovalGate",
    "LocalDiskPayloadStore",
    "MockChannel",
    "NotificationAction",
    "NotificationActionStyle",
    "NotificationGateway",
    "OpenAPIToolLoader",
    "OutputGuard",
    "OutputGuardMode",
    "OutputGuardResult",
    "PointerToolSuite",
    "ReviewRequestPayload",
    "SkillManager",
    "SkillMetadata",
    "SkillPackage",
    "SkillRegistry",
    "SkillRouter",
    "TelegramChannel",
    "ToolExecutionResult",
    "ToolOutputTruncator",
    "TruncationResult",
    "WebhookChannel",
    "generate_tool_schema",
    "is_coroutine_callable",
    "normalize_pointer_id",
    "parse_skill_md",
    "to_async_tool",
]
