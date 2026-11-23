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

__all__ = [
    "AsyncToolDispatcher",
    "BaseNotificationChannel",
    "BasePayloadStore",
    "ConsoleChannel",
    "DataPointer",
    "LocalDiskPayloadStore",
    "MockChannel",
    "NotificationAction",
    "NotificationActionStyle",
    "NotificationGateway",
    "OpenAPIToolLoader",
    "OutputGuard",
    "OutputGuardMode",
    "OutputGuardResult",
    "ReviewRequestPayload",
    "TelegramChannel",
    "ToolExecutionResult",
    "ToolOutputTruncator",
    "TruncationResult",
    "WebhookChannel",
    "is_coroutine_callable",
    "to_async_tool",
]
