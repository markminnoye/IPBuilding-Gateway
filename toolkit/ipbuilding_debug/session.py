"""One WebSocket to the gateway, a ring buffer, and reconnect with backoff.

The process starts even when the gateway is down. Tools poll the buffer.
Nothing is written to stdout.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp

from ipbuilding_debug.buffer import MAX_WAIT_SECONDS, RingBuffer, clamp_timeout
from ipbuilding_debug.errors import (
    KIND_NO_ADDRESS,
    MSG_NO_ADDRESS,
    ClassifiedError,
    classify_http,
    classify_transport,
)

log = logging.getLogger("ipbuilding_debug")
log.addHandler(logging.NullHandler())

BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
DEFAULT_PORT = 8080

Sleeper = Callable[[float], Awaitable[None]]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_backoff(current: float, maximum: float = BACKOFF_MAX_S) -> float:
    return min(current * 2, maximum)


def parse_gateway_address(raw: str | None, *, default_port: int = DEFAULT_PORT) -> tuple[str, int]:
    """Host and port from a bundle setting. Scheme and path are ignored."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty")
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    host = parts.hostname
    if not host:
        raise ValueError("no-host")
    port = parts.port or default_port
    return host, port


def address_from_env() -> str:
    return (
        os.environ.get("IPBUILDING_GATEWAY_ADDRESS")
        or os.environ.get("IPBUILDING_GATEWAY")
        or ""
    ).strip()


class GatewaySession:
    """Lazy client. ``start`` returns before the socket connects."""

    def __init__(
        self,
        address: str,
        *,
        buffer_size: int = 2000,
        backoff_start: float = BACKOFF_START_S,
        backoff_max: float = BACKOFF_MAX_S,
        sleeper: Sleeper | None = None,
        log_level: str = "INFO",
    ) -> None:
        self.address = (address or "").strip()
        self.host = ""
        self.port = DEFAULT_PORT
        self.address_error = ""
        if not self.address:
            self.address_error = "empty"
        else:
            try:
                self.host, self.port = parse_gateway_address(self.address)
            except ValueError as exc:
                self.address_error = str(exc)
        self.buffer = RingBuffer(maxlen=buffer_size)
        self.backoff_start = backoff_start
        self.backoff_max = backoff_max
        self._sleeper = sleeper or asyncio.sleep
        self.log_level = log_level
        self.state = "idle"
        self.status: dict[str, Any] | None = None
        self.devices: dict[str, dict[str, Any]] = {}
        self.modules: dict[str, dict[str, Any]] = {}
        self.notes: list[dict[str, str]] = []
        self.want_frames = False
        self.last_error = ""
        self._http: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._session_up = False
        self._up = asyncio.Event()
        self._gap_from: str | None = None

    @classmethod
    def from_env(cls) -> GatewaySession:
        return cls(address_from_env())

    @property
    def base_http(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"

    async def ensure_started(self) -> None:
        """Start the reconnect loop if it is not running. Does not wait."""
        if self._task is not None and not self._task.done():
            return
        if self.address_error:
            self.state = "configuration"
            return
        self._stopped = asyncio.Event()
        await self._client()
        self._task = asyncio.create_task(self._ws_loop(), name="ipbuilding-gateway-ws")

    async def stop(self) -> None:
        self._stopped.set()
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._http is not None and not self._http.closed:
            await self._http.close()
        self._http = None
        self.state = "stopped"

    async def _client(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def refresh_status(self, *, timeout: float = 5.0) -> ClassifiedError | None:
        """GET /api/v1/status. Updates ``self.status`` on success."""
        if self.address_error:
            return ClassifiedError(KIND_NO_ADDRESS, MSG_NO_ADDRESS, self.address_error)
        await self.ensure_started()
        url = f"{self.base_http}/api/v1/status"
        try:
            client = await self._client()
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with client.get(url, timeout=client_timeout) as response:
                body = await _read_json(response)
                if response.status >= 400:
                    classified = classify_http(response.status, body)
                    self.last_error = classified.detail or classified.kind
                    return classified
                if not isinstance(body, dict):
                    classified = classify_http(response.status, body)
                    return classified
                self.status = body
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            classified = classify_transport(exc)
            self.last_error = classified.detail
            log.info("status fetch failed (%s)", classified.detail)
            return classified

    async def get_json(self, path: str, *, timeout: float = 8.0) -> tuple[Any, ClassifiedError | None]:
        if self.address_error:
            return None, ClassifiedError(KIND_NO_ADDRESS, MSG_NO_ADDRESS, self.address_error)
        url = f"{self.base_http}{path}"
        try:
            client = await self._client()
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with client.get(url, timeout=client_timeout) as response:
                body = await _read_json(response)
                if response.status >= 400:
                    return body, classify_http(response.status, body)
                return body, None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            return None, classify_transport(exc)

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float = 8.0,
    ) -> tuple[Any, ClassifiedError | None]:
        if self.address_error:
            return None, ClassifiedError(KIND_NO_ADDRESS, MSG_NO_ADDRESS, self.address_error)
        url = f"{self.base_http}{path}"
        try:
            client = await self._client()
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with client.post(url, json=payload, timeout=client_timeout) as response:
                body = await _read_json(response)
                if response.status >= 400:
                    return body, classify_http(response.status, body)
                return body, None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            return None, classify_transport(exc)

    async def wait_for_state(
        self,
        device_id: str,
        *,
        timeout: float = MAX_WAIT_SECONDS,
        state: str | None = None,
    ) -> dict[str, Any] | None:
        """Wait for a new ``state_changed`` for ``device_id``. Never longer than 30 s."""
        timeout = clamp_timeout(timeout)
        since = self.buffer.latest_seq

        def matches(event: dict[str, Any]) -> bool:
            if event.get("type") != "state_changed":
                return False
            if event.get("id") != device_id:
                return False
            if state is not None and event.get("state") != state:
                return False
            return True

        found = await self.buffer.wait_until(matches, timeout, since)
        if found is None:
            return None
        return found.event

    async def annotate(self, text: str, marker: str = "") -> dict[str, str]:
        item = {"at": utc_now(), "text": text, "marker": marker}
        self.notes.append(item)
        await self.buffer.append({"type": "note", **item})
        return item

    async def ensure_udp_subscription(self, timeout: float) -> int | None:
        """Send ``subscribe_udp_frames`` and return the buffer cursor just before it.

        Frames caused by this subscription have a higher sequence than the
        returned cursor. ``None`` means the subscribe was not sent in time.
        """
        cursor = self.buffer.latest_seq
        self.want_frames = True
        await self.ensure_started()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + clamp_timeout(timeout)
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            if not await self._wait_until_socket(remaining):
                return None
            if await self._send({"type": "subscribe_udp_frames"}):
                return cursor
            self._up.clear()
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                await asyncio.wait_for(self._up.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return None

    async def request_log_level(self, level: str, *, ttl_s: int = 900) -> str:
        """Ask the gateway to change its log level.

        Returns ``applied``, ``sent`` (no reply yet), ``not_connected``,
        ``rate_limited``, ``disabled``, or ``rejected``.
        """
        self.log_level = (level or "").strip().upper() or "INFO"
        try:
            ttl = int(ttl_s)
        except (TypeError, ValueError):
            ttl = 900
        ttl = max(1, min(ttl, 3600))
        await self.ensure_started()
        if not await self._wait_until_socket(3):
            return "not_connected"
        since = self.buffer.latest_seq
        await self._send({"type": "subscribe_logs", "min_level": self.log_level})
        if not await self._send(
            {"type": "set_log_level", "level": self.log_level, "ttl": ttl}
        ):
            return "not_connected"
        found = await self.buffer.wait_until(_log_level_reply, 3, since)
        if found is None:
            return "sent"
        event = found.event
        if event.get("type") == "log_level":
            return "applied"
        code = event.get("error")
        if code == "log_level_rate_limited":
            return "rate_limited"
        if code == "remote_debugging_disabled":
            return "disabled"
        return "rejected"

    async def wait_until_connected(self, timeout: float) -> bool:
        timeout = clamp_timeout(timeout)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if self._stopped.is_set():
                return False
            if self.state == "connected" and self._session_up:
                return True
            await asyncio.sleep(0.02)
        return self.state == "connected" and self._session_up

    def _socket_ready(self) -> bool:
        ws = self._ws
        return self._session_up and ws is not None and not ws.closed

    async def _wait_until_socket(self, timeout: float) -> bool:
        """Wait until a snapshot has been applied on an open socket."""
        timeout = clamp_timeout(timeout)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if self._stopped.is_set():
                return False
            if self._socket_ready():
                return True
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            # Drop a stale signal, then re-check so a snapshot that landed
            # in between is not lost.
            self._up.clear()
            if self._socket_ready():
                return True
            try:
                await asyncio.wait_for(self._up.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return self._socket_ready()

    def gap_events(self) -> list[dict[str, Any]]:
        return [event for event in self.buffer.snapshot() if event.get("type") == "gap"]

    async def _ws_loop(self) -> None:
        delay = self.backoff_start
        while not self._stopped.is_set():
            try:
                await self._one_connection()
                delay = self.backoff_start
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._note_disconnect()
                self.last_error = type(exc).__name__
                log.info("websocket closed (%s); retry in %.1fs", type(exc).__name__, delay)
                if self._stopped.is_set():
                    break
                try:
                    await self._sleeper(delay)
                except asyncio.CancelledError:
                    raise
                delay = next_backoff(delay, self.backoff_max)
            if self._stopped.is_set():
                break
            # A clean close (no exception) also backs off, unless we returned
            # because the task was cancelled.
            if self.state != "connected":
                continue

    async def _one_connection(self) -> None:
        if self.address_error:
            raise ConnectionError(self.address_error)
        client = await self._client()
        self.state = "connecting"
        log.info("websocket connecting")
        async with client.ws_connect(self.ws_url, heartbeat=20.0) as ws:
            self._ws = ws
            self.state = "connected"
            try:
                async for message in ws:
                    if self._stopped.is_set():
                        break
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._on_text(message.data)
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            finally:
                self._ws = None
                self._note_disconnect()
        raise ConnectionError("websocket closed")

    def _note_disconnect(self) -> None:
        if self._session_up and self._gap_from is None:
            self._gap_from = utc_now()
        self._session_up = False
        self._up.clear()
        if self.state != "stopped":
            self.state = "disconnected"

    async def _on_text(self, raw: str) -> None:
        import json

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await self.buffer.append({"type": "undecoded", "text": raw[:500]})
            return
        if not isinstance(payload, dict):
            await self.buffer.append({"type": "undecoded", "text": raw[:500]})
            return
        if payload.get("type") == "snapshot":
            await self._on_snapshot(payload)
            return
        if payload.get("type") == "gateway_status":
            self._apply_status(payload)
        await self.buffer.append(payload)

    async def _on_snapshot(self, payload: dict[str, Any]) -> None:
        if self._gap_from is not None:
            gap_to = utc_now()
            await self.buffer.append(
                {
                    "type": "gap",
                    "from": self._gap_from,
                    "to": gap_to,
                    "message": f"geen verbinding van {self._gap_from} tot {gap_to}",
                }
            )
            self._gap_from = None
        # Resync: the snapshot replaces local state. Stale devices are dropped.
        devices = payload.get("devices")
        modules = payload.get("modules")
        self.devices = {
            str(item["id"]): item
            for item in devices or []
            if isinstance(item, dict) and item.get("id") is not None
        }
        self.modules = {
            str(item["id"]): item
            for item in modules or []
            if isinstance(item, dict) and item.get("id") is not None
        }
        status = payload.get("gateway_status")
        if isinstance(status, dict):
            self._apply_status(status)
        self._session_up = True
        self.state = "connected"
        self._up.set()
        await self.buffer.append(payload)
        await self._resubscribe()

    def _apply_status(self, status: dict[str, Any]) -> None:
        merged = dict(self.status or {})
        merged.update(status)
        merged.pop("type", None)
        self.status = merged

    async def _resubscribe(self) -> None:
        """After each snapshot: logs, and frames when a tool asked for them."""
        status = self.status or {}
        caps = status.get("capabilities")
        if not isinstance(caps, list):
            return
        if "log_stream" in caps:
            await self._send({"type": "subscribe_logs", "min_level": self.log_level})
        if "udp_frame" in caps and self.want_frames:
            await self._send({"type": "subscribe_udp_frames"})

    async def _send(self, payload: dict[str, Any]) -> bool:
        ws = self._ws
        if ws is None or ws.closed:
            return False
        async with self._send_lock:
            if self._ws is None or self._ws.closed:
                return False
            try:
                await self._ws.send_json(payload)
            except (aiohttp.ClientError, ConnectionError, RuntimeError) as exc:
                log.info("websocket send failed (%s)", type(exc).__name__)
                return False
        return True


_LOG_LEVEL_ERRORS = frozenset(
    {
        "log_level_rate_limited",
        "remote_debugging_disabled",
        "invalid_log_level",
        "invalid_ttl",
    }
)


def _log_level_reply(event: dict[str, Any]) -> bool:
    kind = event.get("type")
    if kind == "log_level":
        return True
    return kind == "error" and event.get("error") in _LOG_LEVEL_ERRORS


async def _read_json(response: aiohttp.ClientResponse) -> Any:
    import json

    text = await response.text()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text[:180]}
