"""Universal Multi-Channel Remote Notification Gateway (Core Framework).

Provides provider-agnostic notification dispatching for Human-in-the-Loop review requests,
alerts, and approval events. Supports declarative channel configuration with zero-cost
freeware defaults (Webhook, Telegram, Console, Mock).
"""

from abc import ABC, abstractmethod
from enum import Enum
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union
import urllib.error
import urllib.request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NotificationActionStyle(str, Enum):
    """Visual style hint for notification action buttons."""
    PRIMARY = "primary"      # e.g., Green / Approve
    DANGER = "danger"        # e.g., Red / Reject
    DEFAULT = "default"      # e.g., Grey / Edit or View


class NotificationAction(BaseModel):
    """Represents a clickable or selectable action (e.g. Approve, Edit, Reject)."""
    action_id: str = Field(..., description="Unique action identifier: 'approve', 'edit', 'reject'")
    label: str = Field(..., description="Human-readable button label")
    style: NotificationActionStyle = Field(default=NotificationActionStyle.DEFAULT)
    callback_payload: Optional[str] = Field(default=None, description="Optional opaque callback data")


class ReviewRequestPayload(BaseModel):
    """Standardized inter-agent notification contract for human approval boundaries."""
    thread_id: str = Field(..., description="LangGraph checkpoint thread identifier")
    title: str = Field(..., description="Notification headline")
    summary: str = Field(..., description="Short summary of proposed action")
    recipient: Optional[str] = Field(default=None, description="Action recipient (e.g. email or system)")
    subject: Optional[str] = Field(default=None, description="Action subject line or title")
    body_preview: Optional[str] = Field(default=None, description="Preview of proposed text or command")
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    critic_report: Optional[dict[str, Any]] = Field(default=None, description="Structured critique findings if evaluated")
    actions: list[NotificationAction] = Field(
        default_factory=lambda: [
            NotificationAction(action_id="approve", label="Approve", style=NotificationActionStyle.PRIMARY),
            NotificationAction(action_id="reject", label="Reject", style=NotificationActionStyle.DANGER),
        ],
        description="List of available actions for the human reviewer",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary workflow metadata")


class BaseNotificationChannel(ABC):
    """Abstract base class for all notification channel adapters."""

    @abstractmethod
    def send(self, payload: ReviewRequestPayload) -> bool:
        """Send a review request notification. Returns True if successful, False otherwise."""
        pass


class MockChannel(BaseNotificationChannel):
    """In-memory notification channel for hermetic $0-token unit and integration testing."""

    def __init__(self) -> None:
        self.sent_notifications: list[ReviewRequestPayload] = []

    def send(self, payload: ReviewRequestPayload) -> bool:
        self.sent_notifications.append(payload)
        logger.debug(f"[MockChannel] Captured notification for thread '{payload.thread_id}'")
        return True

    def clear(self) -> None:
        self.sent_notifications.clear()


class ConsoleChannel(BaseNotificationChannel):
    """ANSI-colored terminal card dispatcher for local offline review."""

    def __init__(self, color: bool = True) -> None:
        self.color = color

    def send(self, payload: ReviewRequestPayload) -> bool:
        c_cyan = "\033[96m" if self.color else ""
        c_green = "\033[92m" if self.color else ""
        c_yellow = "\033[93m" if self.color else ""
        c_bold = "\033[1m" if self.color else ""
        c_reset = "\033[0m" if self.color else ""

        bar = "=" * 65
        print(f"\n{c_cyan}{bar}{c_reset}")
        print(f"{c_bold}🔔 HUMAN-IN-THE-LOOP APPROVAL REQUIRED{c_reset}")
        print(f"{c_cyan}{bar}{c_reset}")
        print(f"{c_bold}Thread ID:{c_reset} {payload.thread_id}")
        print(f"{c_bold}Title:{c_reset}     {payload.title}")
        if payload.recipient:
            print(f"{c_bold}Recipient:{c_reset} {payload.recipient}")
        if payload.subject:
            print(f"{c_bold}Subject:{c_reset}   {payload.subject}")
        if payload.confidence_score is not None:
            print(f"{c_bold}Confidence:{c_reset}{c_yellow} {payload.confidence_score * 100:.1f}%{c_reset}")
        if payload.body_preview:
            print(f"\n{c_bold}Proposed Content Preview:{c_reset}")
            preview = payload.body_preview[:300] + ("..." if len(payload.body_preview) > 300 else "")
            print(f"  {preview}")

        action_labels = " | ".join(f"[{a.label}]" for a in payload.actions)
        print(f"\n{c_green}Available Actions: {action_labels}{c_reset}")
        print(f"{c_cyan}{bar}{c_reset}\n")
        return True


class WebhookChannel(BaseNotificationChannel):
    """Universal HTTP POST dispatcher delivering JSON payloads to any target URL.

    Compatible with local FastAPI approval servers, n8n, Zapier, Make, Slack Incoming Webhooks,
    Discord Webhooks, and custom enterprise notification backends.
    """

    def __init__(
        self,
        target_url: str,
        auth_header: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.target_url = target_url
        self.auth_header = auth_header
        self.timeout_seconds = timeout_seconds

    def send(self, payload: ReviewRequestPayload) -> bool:
        if not self.target_url:
            logger.warning("[WebhookChannel] Target URL is empty. Dispatch skipped.")
            return False

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AgenticNotificationGateway/1.0",
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        data = json.dumps(payload.model_dump()).encode("utf-8")
        req = urllib.request.Request(self.target_url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                status_code = response.getcode()
                if 200 <= status_code < 300:
                    logger.info(f"[WebhookChannel] Notification delivered to {self.target_url} (HTTP {status_code})")
                    return True
                else:
                    logger.warning(f"[WebhookChannel] Delivery failed with HTTP status {status_code}")
                    return False
        except urllib.error.HTTPError as e:
            logger.error(f"[WebhookChannel] HTTP error delivering notification to {self.target_url}: {e.code} {e.reason}")
            return False
        except Exception as e:
            logger.error(f"[WebhookChannel] Error delivering notification to {self.target_url}: {e}")
            return False


class TelegramChannel(BaseNotificationChannel):
    """Telegram Bot API dispatcher with inline keyboard callback buttons.

    Zero-cost mobile alerts with native [Approve] / [Reject] buttons.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        api_base: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def send(self, payload: ReviewRequestPayload) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("[TelegramChannel] bot_token or chat_id is missing. Dispatch skipped.")
            return False

        # Format Telegram MarkdownV2 message text
        score_text = f" ({payload.confidence_score * 100:.0f}% confidence)" if payload.confidence_score is not None else ""
        text_lines = [
            f"🔔 *Human-in-the-Loop Review Required*",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"*Thread:* `{payload.thread_id}`",
            f"*Title:* {payload.title}{score_text}",
        ]
        if payload.recipient:
            text_lines.append(f"*Recipient:* `{payload.recipient}`")
        if payload.subject:
            text_lines.append(f"*Subject:* {payload.subject}")
        if payload.body_preview:
            preview = payload.body_preview[:280] + ("..." if len(payload.body_preview) > 280 else "")
            text_lines.append(f"\n*Draft Preview:*\n_{preview}_")

        # Build inline keyboard buttons
        inline_buttons: list[dict[str, str]] = []
        for action in payload.actions:
            icon = "✅ " if action.action_id == "approve" else ("❌ " if action.action_id == "reject" else "✏️ ")
            callback_data = action.callback_payload or f"{payload.thread_id}:{action.action_id}"
            inline_buttons.append({
                "text": f"{icon}{action.label}",
                "callback_data": callback_data[:64],  # Telegram 64-byte callback_data limit
            })

        telegram_payload = {
            "chat_id": self.chat_id,
            "text": "\n".join(text_lines),
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [inline_buttons],
            },
        }

        url = f"{self.api_base}/bot{self.bot_token}/sendMessage"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(telegram_payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                status_code = response.getcode()
                if 200 <= status_code < 300:
                    logger.info(f"[TelegramChannel] Sent interactive review message for thread '{payload.thread_id}'")
                    return True
                return False
        except Exception as e:
            logger.error(f"[TelegramChannel] Failed to send Telegram notification: {e}")
            return False


class NotificationGateway:
    """Central notification dispatcher coordinating channel routing based on user configuration."""

    def __init__(
        self,
        default_channel: str = "console",
        channels: Optional[dict[str, BaseNotificationChannel]] = None,
        broadcast_all: bool = False,
    ) -> None:
        self.default_channel = default_channel
        self.channels: dict[str, BaseNotificationChannel] = channels or {
            "console": ConsoleChannel(),
            "mock": MockChannel(),
        }
        self.broadcast_all = broadcast_all

    def register_channel(self, name: str, channel: BaseNotificationChannel) -> None:
        """Register a new channel adapter by name."""
        self.channels[name] = channel

    def get_channel(self, name: str) -> Optional[BaseNotificationChannel]:
        """Retrieve a registered channel adapter."""
        return self.channels.get(name)

    def dispatch(
        self,
        payload: ReviewRequestPayload,
        channel: Optional[str] = None,
    ) -> bool:
        """Dispatch a notification to the specified channel, default channel, or all channels."""
        if self.broadcast_all:
            results = [ch.send(payload) for ch in self.channels.values()]
            return any(results)

        target_name = channel or self.default_channel
        target_ch = self.channels.get(target_name)
        if not target_ch:
            logger.warning(
                f"[NotificationGateway] Channel '{target_name}' not found. "
                f"Falling back to 'console'."
            )
            target_ch = self.channels.get("console", ConsoleChannel())

        return target_ch.send(payload)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "NotificationGateway":
        """Instantiate a NotificationGateway from a declarative configuration dictionary."""
        notif_cfg = config.get("notification", config)
        default_channel = notif_cfg.get("default_channel", "console")
        broadcast_all = bool(notif_cfg.get("broadcast_all", False))

        channels: dict[str, BaseNotificationChannel] = {
            "mock": MockChannel(),
            "console": ConsoleChannel(color=bool(notif_cfg.get("channels", {}).get("console", {}).get("color", True))),
        }

        channel_configs = notif_cfg.get("channels", {})

        # Webhook configuration
        webhook_cfg = channel_configs.get("webhook")
        if webhook_cfg:
            target_url = webhook_cfg.get("target_url") or os.environ.get("NOTIFICATION_WEBHOOK_URL", "")
            auth_header = webhook_cfg.get("auth_header") or os.environ.get("NOTIFICATION_WEBHOOK_AUTH")
            timeout = float(webhook_cfg.get("timeout_seconds", 10.0))
            channels["webhook"] = WebhookChannel(
                target_url=target_url,
                auth_header=auth_header,
                timeout_seconds=timeout,
            )

        # Telegram configuration
        telegram_cfg = channel_configs.get("telegram")
        if telegram_cfg:
            bot_token = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "")
            api_base = telegram_cfg.get("api_base", "https://api.telegram.org")
            channels["telegram"] = TelegramChannel(
                bot_token=bot_token,
                chat_id=chat_id,
                api_base=api_base,
            )

        return cls(
            default_channel=default_channel,
            channels=channels,
            broadcast_all=broadcast_all,
        )

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "NotificationGateway":
        """Load configuration from a YAML file."""
        import yaml
        cfg_path = Path(path)
        if not cfg_path.exists():
            logger.warning(f"Notification config '{path}' not found. Using default console gateway.")
            return cls()

        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

