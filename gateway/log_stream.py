"""Live gateway logs for remote-debugging subscribers.

A logging.Handler pushes each line onto the asyncio loop with
``call_soon_threadsafe`` (UDP code logs from other threads). Lines go
only to WebSocket clients that subscribed. A slow client gets
``log_dropped``; it never blocks the loop or other clients.

The handler also keeps a memory ring of the last ``BUFFER_SIZE`` lines
and the last ``BUFFER_MAX_AGE_S`` seconds, and only while it is
attached. Nothing is written to disk. ``detach`` drops the ring.

Temporary log levels are memory-only. They are not written to add-on
options or the environment. The most verbose active request wins, and
the root logger is never set quieter than the level from configuration.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

BUFFER_SIZE = 500
BUFFER_MAX_AGE_S = 300.0
QUEUE_SIZE = 100
MAX_TTL_S = 3600
RATE_LIMIT = 10
RATE_WINDOW_S = 60.0

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
_LEVEL_NAMES: dict[int, str] = {value: name for name, value in _LEVELS.items()}
_LEVEL_NAMES[logging.CRITICAL] = "critical"

_SKIP_PREFIXES = ("aiohttp", "websockets")

_BEARER = re.compile(r"(?i)\b(bearer\s+)\S+")
_SECRET_KV = re.compile(
    r"(?i)\b(password|passwd|token|secret|api_key|authorization)"
    r"\b(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


class LogStreamError(Exception):
    """Rejected log-stream request. ``status`` is the REST status."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def baseline_from_config(value: object) -> int:
    """Logging level from configuration. Non-strings (test doubles) are INFO."""
    if not isinstance(value, str):
        return logging.INFO
    parsed = logging.getLevelName(value.strip().upper())
    if not isinstance(parsed, int):
        return logging.INFO
    return parsed


def redact(message: str) -> str:
    """Hide token- and password-like values. Field-bus hex payloads stay."""
    message = _JWT.sub("[redacted]", message)
    message = _BEARER.sub(r"\1[redacted]", message)
    message = _SECRET_KV.sub(r"\1\2[redacted]", message)
    return message


def _level_no(name: str) -> int:
    if name == "critical":
        return logging.CRITICAL
    return _LEVELS.get(name, logging.INFO)


def _level_name(level: int) -> str:
    named = _LEVEL_NAMES.get(level)
    if named is not None:
        return named
    text = logging.getLevelName(level)
    if isinstance(text, str) and not text.startswith("Level "):
        return text.lower()
    return "info"


def _parse_level(value: object) -> int:
    if not isinstance(value, str):
        raise LogStreamError(
            "invalid_log_level",
            "level must be one of debug, info, warning, error.",
        )
    parsed = _LEVELS.get(value.strip().lower())
    if parsed is None:
        raise LogStreamError(
            "invalid_log_level",
            "level must be one of debug, info, warning, error.",
        )
    return parsed


def _parse_ttl(value: object, max_ttl_s: int) -> int:
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LogStreamError(
            "invalid_ttl",
            f"ttl must be an integer from 1 to {max_ttl_s} seconds.",
        )
    if value < 1 or value > max_ttl_s:
        raise LogStreamError(
            "invalid_ttl",
            f"ttl must be an integer from 1 to {max_ttl_s} seconds.",
        )
    return value


def _parse_since(value: object) -> datetime:
    """ISO 8601 cutoff. ``Z`` and offsets are accepted; naive values are UTC."""
    if not isinstance(value, str) or not value.strip():
        raise LogStreamError(
            "invalid_since",
            "since must be an ISO 8601 timestamp, for example 2026-10-08T12:00:00.000Z.",
        )
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise LogStreamError(
            "invalid_since",
            "since must be an ISO 8601 timestamp, for example 2026-10-08T12:00:00.000Z.",
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _entry_time(entry: dict[str, Any]) -> datetime | None:
    ts = entry.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return _parse_since(ts)
    except LogStreamError:
        return None


@dataclass
class _Subscriber:
    ws: Any
    min_level: int
    queue: asyncio.Queue[dict[str, Any]]
    dropped: int = 0
    task: asyncio.Task[None] | None = None


@dataclass
class _LevelRequest:
    level: int
    ttl: int
    handle: asyncio.TimerHandle | None = None


class _Handler(logging.Handler):
    """Forwards log records. Does not log, and ignores library loggers."""

    def __init__(self, stream: LogStream) -> None:
        super().__init__(level=logging.DEBUG)
        self._stream = stream
        self._busy = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._busy:
            return
        name = record.name or ""
        if name in _SKIP_PREFIXES or name.startswith(
            tuple(prefix + "." for prefix in _SKIP_PREFIXES)
        ):
            return
        self._busy = True
        try:
            entry = {
                "type": "log",
                "ts": datetime.fromtimestamp(record.created, timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": _level_name(record.levelno),
                "logger": name,
                "message": redact(record.getMessage()),
            }
            self._stream.offer(entry)
        except Exception:
            return
        finally:
            self._busy = False


class LogStream:
    """Ring buffer, per-subscriber queues, and temporary root log level."""

    def __init__(
        self,
        baseline_level: int = logging.INFO,
        *,
        buffer_size: int = BUFFER_SIZE,
        max_age_s: float = BUFFER_MAX_AGE_S,
        queue_size: int = QUEUE_SIZE,
        max_ttl_s: int = MAX_TTL_S,
        rate_limit: int = RATE_LIMIT,
        rate_window_s: float = RATE_WINDOW_S,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._baseline = baseline_level
        self._buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._max_age_s = max_age_s
        self._queue_size = queue_size
        self._max_ttl_s = max_ttl_s
        self._rate_limit = rate_limit
        self._rate_window_s = rate_window_s
        self._now = now or time.monotonic
        self._subs: dict[int, _Subscriber] = {}
        self._requests: dict[str, _LevelRequest] = {}
        self._rates: dict[str, deque[float]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handler: _Handler | None = None
        self._saved_level: int | None = None

    def attach(self) -> None:
        """Install the handler. Safe to call more than once."""
        if self._handler is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._handler = _Handler(self)
        logging.getLogger().addHandler(self._handler)

    def detach(self) -> None:
        """Remove the handler, cancel timers, and restore the root level."""
        root = logging.getLogger()
        if self._handler is not None:
            root.removeHandler(self._handler)
            self._handler = None
        for req in self._requests.values():
            if req.handle is not None:
                req.handle.cancel()
        self._requests.clear()
        for sub in self._subs.values():
            if sub.task is not None:
                sub.task.cancel()
        self._subs.clear()
        if self._saved_level is not None:
            root.setLevel(self._saved_level)
            self._saved_level = None
        self._loop = None
        self._buffer.clear()

    def offer(self, entry: dict[str, Any]) -> None:
        """Schedule ``entry`` on the loop. Called from any thread."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._on_entry, entry)
        except RuntimeError:
            return

    def _on_entry(self, entry: dict[str, Any]) -> None:
        if self._handler is None:
            return
        self._buffer.append(entry)
        self._prune()
        level_no = _level_no(entry["level"])
        for sub in self._subs.values():
            if level_no < sub.min_level:
                continue
            try:
                sub.queue.put_nowait(entry)
            except asyncio.QueueFull:
                sub.dropped += 1

    def history(
        self, min_level: object = None, since: object = None,
    ) -> dict[str, Any]:
        """Lines still in the ring, filtered by level and ``since``.

        ``since`` is an ISO 8601 timestamp. Lines at that time and later
        are returned. Omitted ``since`` returns everything the ring still
        holds. ``min_level`` defaults to info.
        """
        if min_level is None:
            level = logging.INFO
        else:
            level = _parse_level(min_level)
        cutoff = None if since is None else _parse_since(since)
        self._prune()
        lines: list[dict[str, Any]] = []
        for entry in self._buffer:
            if _level_no(entry["level"]) < level:
                continue
            if cutoff is not None:
                when = _entry_time(entry)
                if when is None or when < cutoff:
                    continue
            lines.append(dict(entry))
        return {
            "min_level": _level_name(level),
            "since": since,
            "lines": lines,
        }

    async def subscribe(
        self, ws: Any, min_level: object = None, since: object = None,
    ) -> None:
        """Replay the filtered ring, then live lines at ``min_level``."""
        snapshot = self.history(min_level, since)
        level = _parse_level(snapshot["min_level"])
        self.attach()
        key = id(ws)
        old = self._subs.pop(key, None)
        if old is not None and old.task is not None:
            old.task.cancel()
        sub = _Subscriber(
            ws=ws,
            min_level=level,
            queue=asyncio.Queue(self._queue_size),
        )
        self._subs[key] = sub
        replay = snapshot["lines"]
        for entry in replay:
            if not await self._try_send(ws, entry):
                self._subs.pop(key, None)
                return
        if not await self._try_send(
            ws,
            {
                "type": "logs_subscribed",
                "min_level": snapshot["min_level"],
                "since": since,
                "buffered": len(replay),
            },
        ):
            self._subs.pop(key, None)
            return
        sub.task = asyncio.create_task(self._drain(sub))

    async def unsubscribe(self, ws: Any) -> None:
        """Stop delivery and drop this client's temporary log level."""
        await self.disconnect(ws)
        await self._try_send(ws, {"type": "logs_unsubscribed"})

    async def disconnect(self, ws: Any) -> None:
        """Drop a client that went away. Does not send a reply."""
        sub = self._subs.pop(id(ws), None)
        if sub is not None and sub.task is not None:
            sub.task.cancel()
        if self._cancel_request(_ws_owner(ws)):
            self._apply_level()

    async def set_client_level(self, ws: Any, level: object, ttl: object) -> None:
        """One active level request per WebSocket client. Replaces the previous."""
        parsed = _parse_level(level)
        seconds = _parse_ttl(ttl, self._max_ttl_s)
        owner = _ws_owner(ws)
        self._consume_rate(owner)
        self.attach()
        self._replace_request(owner, parsed, seconds)
        effective = self._apply_level()
        await self._try_send(
            ws,
            {
                "type": "log_level",
                "ok": True,
                "level": _level_name(parsed),
                "ttl": seconds,
                "effective_level": _level_name(effective),
            },
        )

    async def set_rest_level(self, level: object, ttl: object) -> dict[str, Any]:
        """REST level change. Lives until its own TTL, even with no subscriber."""
        parsed = _parse_level(level)
        seconds = _parse_ttl(ttl, self._max_ttl_s)
        self._consume_rate("rest")
        self.attach()
        self._replace_request(f"rest:{uuid.uuid4().hex}", parsed, seconds)
        effective = self._apply_level()
        return {
            "ok": True,
            "level": _level_name(parsed),
            "ttl": seconds,
            "effective_level": _level_name(effective),
        }

    def _consume_rate(self, bucket: str) -> None:
        now = self._now()
        hist = self._rates.setdefault(bucket, deque())
        while hist and now - hist[0] >= self._rate_window_s:
            hist.popleft()
        if len(hist) >= self._rate_limit:
            raise LogStreamError(
                "log_level_rate_limited",
                "Too many log level changes. Wait and try again.",
                429,
            )
        hist.append(now)

    def _replace_request(self, owner: str, level: int, ttl: int) -> None:
        self._cancel_request(owner)
        handle = None
        loop = self._loop
        if loop is not None:
            handle = loop.call_later(ttl, self._on_expire, owner)
        self._requests[owner] = _LevelRequest(level=level, ttl=ttl, handle=handle)

    def _cancel_request(self, owner: str) -> bool:
        req = self._requests.pop(owner, None)
        if req is None:
            return False
        if req.handle is not None:
            req.handle.cancel()
        return True

    def _on_expire(self, owner: str) -> None:
        if not self._cancel_request(owner):
            return
        self._apply_level()

    def _effective_level(self) -> int:
        """Most verbose live request, never quieter than the configured baseline."""
        if not self._requests:
            return self._baseline
        requested = min(req.level for req in self._requests.values())
        return min(self._baseline, requested)

    def _apply_level(self) -> int:
        root = logging.getLogger()
        if self._saved_level is None:
            self._saved_level = root.level
        level = self._effective_level()
        root.setLevel(level)
        return level

    async def _drain(self, sub: _Subscriber) -> None:
        try:
            while True:
                entry = await sub.queue.get()
                if sub.dropped:
                    count = sub.dropped
                    sub.dropped = 0
                    if not await self._try_send(
                        sub.ws, {"type": "log_dropped", "count": count}
                    ):
                        self._subs.pop(id(sub.ws), None)
                        return
                if not await self._try_send(sub.ws, entry):
                    self._subs.pop(id(sub.ws), None)
                    return
        except asyncio.CancelledError:
            return

    def _prune(self) -> None:
        """Drop lines older than the time bound. The deque already caps the count."""
        cutoff = time.time() - self._max_age_s
        while self._buffer:
            when = _entry_time(self._buffer[0])
            if when is not None and when.timestamp() >= cutoff:
                break
            self._buffer.popleft()

    async def _try_send(self, ws: Any, payload: dict[str, Any]) -> bool:
        if getattr(ws, "closed", False):
            return False
        try:
            await ws.send_json(payload)
        except Exception:
            return False
        return True


def _ws_owner(ws: Any) -> str:
    return f"ws:{id(ws)}"
