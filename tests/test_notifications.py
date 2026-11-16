"""Unit tests for Multi-Channel Remote Notification Gateway (core/notifications.py)."""

import http.server
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any
import pytest

# Ensure projects/Agents is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.notifications import (
    ConsoleChannel,
    MockChannel,
    NotificationAction,
    NotificationActionStyle,
    NotificationGateway,
    ReviewRequestPayload,
    TelegramChannel,
    WebhookChannel,
    encode_telegram_callback_data,
    lookup_thread_by_hash,
    safe_utf8_truncate,
)


def test_review_request_payload_model():
    """Verify ReviewRequestPayload schema, defaults, and JSON serialization."""
    payload = ReviewRequestPayload(
        thread_id="thread_test_123",
        title="Approve Customer Outreach",
        summary="Agent drafted outreach for CISO",
        recipient="ciso@target.com",
        subject="Agentic Infrastructure Benchmarks",
        body_preview="Dear CISO, we benchmarked our agents...",
        confidence_score=0.95,
    )

    assert payload.thread_id == "thread_test_123"
    assert len(payload.actions) == 2
    assert payload.actions[0].action_id == "approve"
    assert payload.actions[1].action_id == "reject"
    assert payload.actions[0].style == NotificationActionStyle.PRIMARY

    dump = payload.model_dump()
    assert dump["recipient"] == "ciso@target.com"
    assert dump["confidence_score"] == 0.95


def test_mock_channel():
    """Verify MockChannel captures notifications in memory for offline testing."""
    mock_ch = MockChannel()
    payload = ReviewRequestPayload(
        thread_id="thread_mock",
        title="Test Notification",
        summary="A mock review request",
    )

    success = mock_ch.send(payload)
    assert success is True
    assert len(mock_ch.sent_notifications) == 1
    assert mock_ch.sent_notifications[0].thread_id == "thread_mock"

    mock_ch.clear()
    assert len(mock_ch.sent_notifications) == 0


def test_console_channel():
    """Verify ConsoleChannel prints review card without errors."""
    console_ch = ConsoleChannel(color=False)
    payload = ReviewRequestPayload(
        thread_id="thread_console",
        title="Terminal Review Card",
        summary="Testing terminal rendering",
        recipient="lead@corp.org",
        subject="Important Notice",
        body_preview="Sample draft body text.",
        confidence_score=0.92,
    )
    # Must return True without raising exception
    assert console_ch.send(payload) is True


class MockHTTPServer(http.server.HTTPServer):
    """Local mock HTTP server capturing incoming requests."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.received_requests: list[dict[str, Any]] = []


class MockHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8")
        self.server.received_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(post_body) if post_body else {},
        })

        if self.path == "/error":
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
        pass  # Silence stderr request logging during tests


@pytest.fixture
def mock_server():
    server = MockHTTPServer(("127.0.0.1", 0), MockHTTPHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()
    server.server_close()


def test_webhook_channel_success(mock_server):
    """Verify WebhookChannel delivers JSON POST request to target HTTP endpoint."""
    server, port = mock_server
    target_url = f"http://127.0.0.1:{port}/api/review-endpoint"

    webhook_ch = WebhookChannel(
        target_url=target_url,
        auth_header="Bearer secret_token_xyz",
    )

    payload = ReviewRequestPayload(
        thread_id="thread_webhook_success",
        title="Webhook Test Alert",
        summary="Testing webhook dispatch",
        recipient="cfo@fin.com",
    )

    success = webhook_ch.send(payload)
    assert success is True
    assert len(server.received_requests) == 1

    req = server.received_requests[0]
    assert req["path"] == "/api/review-endpoint"
    auth_val = req["headers"].get("Authorization") or req["headers"].get("authorization")
    assert auth_val == "Bearer secret_token_xyz"
    assert req["body"]["thread_id"] == "thread_webhook_success"
    assert req["body"]["recipient"] == "cfo@fin.com"


def test_webhook_channel_error_handling(mock_server):
    """Verify WebhookChannel handles HTTP 500 error and unreachable host gracefully."""
    server, port = mock_server
    # 1. Server returns 500
    webhook_error = WebhookChannel(target_url=f"http://127.0.0.1:{port}/error")
    payload = ReviewRequestPayload(thread_id="t1", title="Title", summary="Summary")
    assert webhook_error.send(payload) is False

    # 2. Host unreachable / bad port
    webhook_bad_host = WebhookChannel(target_url="http://127.0.0.1:59999/unreachable")
    assert webhook_bad_host.send(payload) is False

    # 3. Empty URL
    webhook_empty = WebhookChannel(target_url="")
    assert webhook_empty.send(payload) is False


def test_telegram_channel_dispatch(mock_server):
    """Verify TelegramChannel formats message and inline keyboard buttons correctly."""
    server, port = mock_server
    api_base = f"http://127.0.0.1:{port}"

    telegram_ch = TelegramChannel(
        bot_token="test_bot_token_123",
        chat_id="chat_98765",
        api_base=api_base,
    )

    payload = ReviewRequestPayload(
        thread_id="thread_tg_001",
        title="Executive Outreach Approval",
        summary="Approval required for CEO outreach",
        recipient="ceo@startup.co",
        subject="Zero Trust Mesh",
        body_preview="Hello CEO, our architecture ensures zero trust.",
        confidence_score=0.96,
        actions=[
            NotificationAction(action_id="approve", label="Approve", style=NotificationActionStyle.PRIMARY),
            NotificationAction(action_id="reject", label="Reject", style=NotificationActionStyle.DANGER),
        ],
    )

    success = telegram_ch.send(payload)
    assert success is True
    assert len(server.received_requests) == 1

    req = server.received_requests[0]
    assert req["path"] == "/bottest_bot_token_123/sendMessage"
    body = req["body"]
    assert body["chat_id"] == "chat_98765"
    assert body["parse_mode"] == "HTML"
    assert "thread_tg_001" in body["text"]
    assert "Executive Outreach Approval" in body["text"]

    # Verify inline keyboard buttons
    keyboard = body["reply_markup"]["inline_keyboard"][0]
    assert len(keyboard) == 2
    assert "Approve" in keyboard[0]["text"]
    assert keyboard[0]["callback_data"] == "thread_tg_001:approve"
    assert "Reject" in keyboard[1]["text"]
    assert keyboard[1]["callback_data"] == "thread_tg_001:reject"


def test_telegram_channel_missing_credentials():
    """Verify TelegramChannel returns False gracefully if token or chat_id is missing."""
    ch = TelegramChannel(bot_token="", chat_id="")
    payload = ReviewRequestPayload(thread_id="t_missing", title="T", summary="S")
    assert ch.send(payload) is False


def test_telegram_channel_html_escaping(mock_server):
    """Verify dynamic fields with HTML and Markdown characters are safely HTML-escaped."""
    server, port = mock_server
    telegram_ch = TelegramChannel(
        bot_token="test_token",
        chat_id="chat_123",
        api_base=f"http://127.0.0.1:{port}",
    )

    payload = ReviewRequestPayload(
        thread_id="thread_<danger>&_001",
        title="Alert: <Critical> & High_Priority *Action*",
        summary="Summary test",
        recipient="user_name<test@example.com>",
        subject="Re: Q3_Financial_Plan & Audit <Confidential>",
        body_preview="Body with <b>raw HTML tags</b> & 'quotes' + _underscores_ & *stars*.",
    )

    assert telegram_ch.send(payload) is True
    assert len(server.received_requests) == 1

    body = server.received_requests[0]["body"]
    assert body["parse_mode"] == "HTML"
    text = body["text"]

    # Assert dynamic content was escaped safely
    assert "thread_&lt;danger&gt;&amp;_001" in text
    assert "&lt;Critical&gt; &amp; High_Priority *Action*" in text
    assert "user_name&lt;test@example.com&gt;" in text
    assert "Re: Q3_Financial_Plan &amp; Audit &lt;Confidential&gt;" in text
    assert "&lt;b&gt;raw HTML tags&lt;/b&gt; &amp; &#x27;quotes&#x27;" in text or "&lt;b&gt;raw HTML tags&lt;/b&gt; &amp; 'quotes'" in text
    assert "_underscores_" in text  # Underscores preserved literally without causing Markdown entity errors

    # Assert structural HTML tags are present
    assert "<b>🔔 Human-in-the-Loop Review Required</b>" in text
    assert "<code>thread_&lt;danger&gt;&amp;_001</code>" in text
    assert "<b>Subject:</b>" in text
    assert "<i>" in text and "</i>" in text


def test_safe_utf8_truncate():
    """Verify safe_utf8_truncate strictly bounds UTF-8 bytes without splitting multibyte characters."""
    # 1. Plain ASCII <= 64 bytes
    assert safe_utf8_truncate("hello world", 64) == "hello world"

    # 2. Plain ASCII > 64 bytes
    long_ascii = "a" * 80
    truncated_ascii = safe_utf8_truncate(long_ascii, 64)
    assert len(truncated_ascii.encode("utf-8")) == 64
    assert truncated_ascii == "a" * 64

    # 3. Multibyte characters (e.g. 4-byte emoji 🚀)
    # 15 emojis * 4 bytes = 60 bytes. 16 emojis = 64 bytes.
    emojis = "🚀" * 20  # 80 bytes
    truncated_emoji = safe_utf8_truncate(emojis, 64)
    assert len(truncated_emoji.encode("utf-8")) <= 64
    assert len(truncated_emoji.encode("utf-8")) % 4 == 0  # No partial emoji
    assert truncated_emoji == "🚀" * 16

    # 4. Multibyte with awkward boundary
    # 'a' * 62 (62 bytes) + '🚀' (4 bytes) = 66 bytes
    awkward = ("a" * 62) + "🚀"
    res = safe_utf8_truncate(awkward, 64)
    assert len(res.encode("utf-8")) == 62
    assert res == "a" * 62


def test_encode_telegram_callback_data_and_registry():
    """Verify callback_data preserves action without truncation or logic inversion."""
    # 1. Short thread fits within 64 bytes as f"{thread}:{action}"
    short_tid = "thread_short_01"
    res_short = encode_telegram_callback_data(short_tid, "approve", 64)
    assert res_short == f"{short_tid}:approve"
    assert len(res_short.encode("utf-8")) <= 64

    # 2. Long thread (>64 bytes) uses SHA-256 digest prefix 'h:{hash}:{action}'
    long_tid = "thread_enterprise_security_compliance_audit_2026_q4_defense_in_depth_policy"
    res_long = encode_telegram_callback_data(long_tid, "approve", 64)
    assert res_long.startswith("h:")
    assert res_long.endswith(":approve")
    assert len(res_long.encode("utf-8")) <= 64

    # 3. Original thread is recoverable from registry
    hash_slice = res_long.split(":")[1]
    recovered = lookup_thread_by_hash(hash_slice)
    assert recovered == long_tid


def test_telegram_channel_long_thread_hashing(mock_server):
    """Verify TelegramChannel generates bounded callback_data with intact action for long thread IDs."""
    server, port = mock_server
    telegram_ch = TelegramChannel(
        bot_token="test_token",
        chat_id="chat_123",
        api_base=f"http://127.0.0.1:{port}",
    )

    long_tid = "thread_enterprise_security_compliance_audit_2026_q4_defense_in_depth_policy_extended"
    payload = ReviewRequestPayload(
        thread_id=long_tid,
        title="Long Thread Compliance Review",
        summary="Testing callback data hashing",
        actions=[
            NotificationAction(action_id="approve", label="Approve", style=NotificationActionStyle.PRIMARY),
            NotificationAction(action_id="reject", label="Reject", style=NotificationActionStyle.DANGER),
        ],
    )

    assert telegram_ch.send(payload) is True
    assert len(server.received_requests) == 1

    body = server.received_requests[0]["body"]
    keyboard = body["reply_markup"]["inline_keyboard"][0]

    # Verify both buttons are <= 64 UTF-8 bytes and actions are preserved
    btn_approve = keyboard[0]
    btn_reject = keyboard[1]

    assert len(btn_approve["callback_data"].encode("utf-8")) <= 64
    assert len(btn_reject["callback_data"].encode("utf-8")) <= 64

    assert btn_approve["callback_data"].startswith("h:")
    assert btn_approve["callback_data"].endswith(":approve")

    assert btn_reject["callback_data"].startswith("h:")
    assert btn_reject["callback_data"].endswith(":reject")


def test_notification_gateway_routing_and_fallback():
    """Verify NotificationGateway routes to preferred channel and falls back gracefully."""
    mock_ch = MockChannel()
    gateway = NotificationGateway(
        default_channel="mock",
        channels={"mock": mock_ch},
    )

    payload = ReviewRequestPayload(thread_id="t_gate", title="Gateway Test", summary="Testing gateway")

    # 1. Dispatch to default ('mock')
    assert gateway.dispatch(payload) is True
    assert len(mock_ch.sent_notifications) == 1

    # 2. Unknown channel falls back to console
    assert gateway.dispatch(payload, channel="non_existent") is True


def test_notification_gateway_from_dict_and_yaml(tmp_path: Path):
    """Verify loading NotificationGateway configuration from dictionary and YAML file."""
    config_dict = {
        "notification": {
            "default_channel": "webhook",
            "channels": {
                "webhook": {
                    "target_url": "http://example.com/webhook",
                    "auth_header": "Bearer token123",
                },
                "telegram": {
                    "bot_token": "tg_token_xyz",
                    "chat_id": "123456",
                },
                "console": {
                    "color": False,
                },
            },
        }
    }

    # 1. Load from dict
    gw = NotificationGateway.from_dict(config_dict)
    assert gw.default_channel == "webhook"
    assert isinstance(gw.get_channel("webhook"), WebhookChannel)
    assert isinstance(gw.get_channel("telegram"), TelegramChannel)
    assert isinstance(gw.get_channel("console"), ConsoleChannel)

    # 2. Load from YAML file
    import yaml
    yaml_file = tmp_path / "notif_config.yaml"
    with open(yaml_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    gw_yaml = NotificationGateway.from_yaml(yaml_file)
    assert gw_yaml.default_channel == "webhook"
    assert gw_yaml.get_channel("webhook").target_url == "http://example.com/webhook"
