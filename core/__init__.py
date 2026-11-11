"""
Core Agent Framework package.
Contains provider-agnostic LLM client abstractions, configuration loaders, execution safety utilities,
and multi-channel remote notification gateway.
"""

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

__all__ = [
    "BaseNotificationChannel",
    "ConsoleChannel",
    "MockChannel",
    "NotificationAction",
    "NotificationActionStyle",
    "NotificationGateway",
    "ReviewRequestPayload",
    "TelegramChannel",
    "WebhookChannel",
]
