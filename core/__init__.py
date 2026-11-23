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

__all__ = [
    "AsyncToolDispatcher",
    "BaseNotificationChannel",
    "ConsoleChannel",
    "MockChannel",
    "NotificationAction",
    "NotificationActionStyle",
    "NotificationGateway",
    "OpenAPIToolLoader",
    "ReviewRequestPayload",
    "TelegramChannel",
    "ToolExecutionResult",
    "WebhookChannel",
    "is_coroutine_callable",
    "to_async_tool",
]
