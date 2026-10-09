"""Home Assistant persistent notification for remote debugging."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from gateway.ha_notify import (
    NOTIFICATION_ID,
    sync_remote_debugging_notification,
)
from gateway.remote_debug_copy import TOOL_NAME, notification_message, notification_title


class _Response:
    def __init__(self, status: int, body: dict[str, Any] | None = None) -> None:
        self.status = status
        self.body = body or {}

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, content_type: str | None = None) -> dict[str, Any]:
        return self.body


class _Session:
    def __init__(
        self,
        status: int = 200,
        error: Exception | None = None,
        language: str = "en",
        language_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.language = language
        self.language_error = language_error
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        if self.language_error is not None:
            raise self.language_error
        return _Response(200, {"language": self.language})

    def post(self, url: str, **kwargs: Any) -> _Response:
        if self.error is not None:
            raise self.error
        self.calls.append({"url": url, **kwargs})
        return _Response(self.status)


@pytest.mark.asyncio
async def test_create_notification_when_enabled() -> None:
    session = _Session()
    await sync_remote_debugging_notification(True, token="test-token", session=session)
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"].endswith("/services/persistent_notification/create")
    assert call["json"]["notification_id"] == NOTIFICATION_ID
    assert call["json"]["title"] == notification_title("en")
    assert call["json"]["message"] == notification_message("en")
    assert call["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_create_notification_follows_dutch() -> None:
    session = _Session(language="nl")
    await sync_remote_debugging_notification(True, token="test-token", session=session)
    call = session.calls[0]
    assert call["json"]["title"] == notification_title("nl")
    assert call["json"]["message"] == notification_message("nl")
    assert TOOL_NAME["nl"] in call["json"]["message"]


@pytest.mark.asyncio
async def test_dismiss_notification_when_disabled() -> None:
    session = _Session()
    await sync_remote_debugging_notification(False, token="test-token", session=session)
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"].endswith("/services/persistent_notification/dismiss")
    assert call["json"] == {"notification_id": NOTIFICATION_ID}


@pytest.mark.asyncio
async def test_http_failure_logs_warning_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _Session(status=500)
    with caplog.at_level(logging.WARNING):
        await sync_remote_debugging_notification(
            True, token="test-token", session=session
        )
    assert any("HTTP 500" in rec.message for rec in caplog.records)
    assert all("test-token" not in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_language_lookup_failure_still_notifies_in_english(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _Session(language_error=OSError("config down"))
    with caplog.at_level(logging.WARNING):
        await sync_remote_debugging_notification(
            True, token="test-token", session=session
        )
    assert session.calls[0]["json"]["message"] == notification_message("en")
    assert any("language lookup failed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_connection_error_logs_warning_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _Session(error=OSError("supervisor unreachable"))
    with caplog.at_level(logging.WARNING):
        await sync_remote_debugging_notification(
            False, token="test-token", session=session
        )
    assert any("failed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_missing_token_skips_request(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    session = _Session()
    with caplog.at_level(logging.WARNING):
        await sync_remote_debugging_notification(True, token="", session=session)
    assert session.calls == []
    assert any("SUPERVISOR_TOKEN" in rec.message for rec in caplog.records)
