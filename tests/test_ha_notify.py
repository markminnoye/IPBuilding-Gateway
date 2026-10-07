"""Home Assistant persistent notification for remote debugging."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from gateway.ha_notify import (
    NOTIFICATION_ID,
    NOTIFICATION_MESSAGE,
    sync_remote_debugging_notification,
)


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _Session:
    def __init__(self, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.calls: list[dict[str, Any]] = []

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
    assert call["json"]["message"] == NOTIFICATION_MESSAGE
    assert call["headers"]["Authorization"] == "Bearer test-token"


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
