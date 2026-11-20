"""Universal Multi-Channel Remote Notification Gateway (Core Framework).

Provides provider-agnostic notification dispatching for Human-in-the-Loop review requests,
alerts, and approval events. Supports declarative channel configuration with zero-cost
freeware defaults (Webhook, Telegram, Console, Mock).
"""

from abc import ABC, abstractmethod
from enum import Enum
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import re
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


_THREAD_HASH_REGISTRY: dict[str, str] = {}


def register_thread_hash(thread_id: str, hash_prefix: Optional[str] = None) -> str:
    """Register thread_id in memory and return its SHA-256 hash prefix."""
    full_hash = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    prefix = hash_prefix or full_hash[:16]
    _THREAD_HASH_REGISTRY[prefix] = thread_id
    _THREAD_HASH_REGISTRY[full_hash[:16]] = thread_id
    return prefix


def lookup_thread_by_hash(hash_prefix: str) -> Optional[str]:
    """Look up a thread_id from the in-memory registry by its hash prefix."""
    if hash_prefix in _THREAD_HASH_REGISTRY:
        return _THREAD_HASH_REGISTRY[hash_prefix]
    for key, tid in _THREAD_HASH_REGISTRY.items():
        if key.startswith(hash_prefix) or hash_prefix.startswith(key):
            return tid
    return None


def safe_utf8_truncate(text: str, max_bytes: int = 64) -> str:
    """Truncate a string to at most max_bytes when UTF-8 encoded without corrupting multi-byte characters."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def encode_telegram_callback_data(
    thread_id: str,
    action_id: str,
    max_bytes: int = 64,
) -> str:
    """Format and byte-bound callback_data for Telegram inline buttons (max 64 UTF-8 bytes).

    If f"{thread_id}:{action_id}" fits within max_bytes, returns it as-is.
    If it exceeds max_bytes, hashes the thread_id with SHA-256 to guarantee the action
    is preserved without truncation (preventing logic inversion bugs).
    """
    raw = f"{thread_id}:{action_id}"
    if len(raw.encode("utf-8")) <= max_bytes:
        return raw

    tid_hash = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:16]
    register_thread_hash(thread_id, tid_hash)
    callback_data = f"h:{tid_hash}:{action_id}"

    if len(callback_data.encode("utf-8")) <= max_bytes:
        return callback_data
    return safe_utf8_truncate(callback_data, max_bytes)


def expand_env_vars(text: str) -> str:
    """Expand environment variables in text using ${VAR}, ${VAR:-default}, or $VAR syntax.

    Unset variables without a default value expand to an empty string to prevent
    unresolved literal placeholders (e.g. '${TELEGRAM_BOT_TOKEN}') from being treated
    as truthy strings by config loaders.
    """
    pattern = re.compile(
        r"\$\{(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)"
    )

    def _replace(match: re.Match) -> str:
        var_name = match.group("var") or match.group("bare")
        default_val = match.group("default")
        val = os.environ.get(var_name)
        if val is not None:
            return val
        if default_val is not None:
            return default_val
        return ""

    return pattern.sub(_replace, text)


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

        # Format Telegram HTML message text with safe entity escaping
        score_text = f" ({payload.confidence_score * 100:.0f}% confidence)" if payload.confidence_score is not None else ""
        escaped_title = html.escape(payload.title)
        escaped_thread = html.escape(payload.thread_id)
        text_lines = [
            "<b>🔔 Human-in-the-Loop Review Required</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"<b>Thread:</b> <code>{escaped_thread}</code>",
            f"<b>Title:</b> {escaped_title}{score_text}",
        ]
        if payload.recipient:
            text_lines.append(f"<b>Recipient:</b> <code>{html.escape(payload.recipient)}</code>")
        if payload.subject:
            text_lines.append(f"<b>Subject:</b> {html.escape(payload.subject)}")
        if payload.body_preview:
            preview = payload.body_preview[:280] + ("..." if len(payload.body_preview) > 280 else "")
            text_lines.append(f"\n<b>Draft Preview:</b>\n<i>{html.escape(preview)}</i>")

        # Build inline keyboard buttons
        inline_buttons: list[dict[str, str]] = []
        for action in payload.actions:
            icon = "✅ " if action.action_id == "approve" else ("❌ " if action.action_id == "reject" else "✏️ ")
            if action.callback_payload:
                callback_data = safe_utf8_truncate(action.callback_payload, 64)
            else:
                callback_data = encode_telegram_callback_data(payload.thread_id, action.action_id, 64)
            inline_buttons.append({
                "text": f"{icon}{action.label}",
                "callback_data": callback_data,
            })

        telegram_payload = {
            "chat_id": self.chat_id,
            "text": "\n".join(text_lines),
            "parse_mode": "HTML",
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

        def _clean_val(val: Any) -> Any:
            if isinstance(val, str) and "$" in val:
                return expand_env_vars(val)
            return val

        # Webhook configuration
        webhook_cfg = channel_configs.get("webhook")
        if webhook_cfg:
            target_url = _clean_val(webhook_cfg.get("target_url")) or os.environ.get("NOTIFICATION_WEBHOOK_URL", "")
            auth_header = _clean_val(webhook_cfg.get("auth_header")) or os.environ.get("NOTIFICATION_WEBHOOK_AUTH")
            timeout_raw = _clean_val(webhook_cfg.get("timeout_seconds", 10.0))
            timeout = float(timeout_raw) if timeout_raw else 10.0
            channels["webhook"] = WebhookChannel(
                target_url=target_url,
                auth_header=auth_header,
                timeout_seconds=timeout,
            )

        # Telegram configuration
        telegram_cfg = channel_configs.get("telegram")
        if telegram_cfg:
            bot_token = _clean_val(telegram_cfg.get("bot_token")) or os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = _clean_val(telegram_cfg.get("chat_id")) or os.environ.get("TELEGRAM_CHAT_ID", "")
            api_base = _clean_val(telegram_cfg.get("api_base")) or os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")
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
        """Load configuration from a YAML file with environment variable expansion."""
        import yaml
        cfg_path = Path(path)
        if not cfg_path.exists():
            logger.warning(f"Notification config '{path}' not found. Using default console gateway.")
            return cls()

        with open(cfg_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        expanded_text = expand_env_vars(raw_text)
        data = yaml.safe_load(expanded_text) or {}
        return cls.from_dict(data)

