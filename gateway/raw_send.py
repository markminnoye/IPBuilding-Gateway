"""Send one raw field-bus payload and collect replies in a short window.

The bus socket stays in the gateway. This module does not open a socket
and does not decode status. ``GatewayAPI`` is the only wiring point.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from gateway.reachability import confirmation_ms

log = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 64
DEFAULT_WINDOW_MS = 2000
MAX_WINDOW_MS = 3000
MAX_REPLIES = 8
_CLIENT_LIMIT = 5
_CLIENT_WINDOW_S = 60.0
_GLOBAL_LIMIT = 10
_GLOBAL_WINDOW_S = 60.0
_MAX_CLIENTS = 32


class RawSendError(Exception):
    """Rejected raw send. ``status`` is the REST status."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class SendPolicy:
    """Targets this gateway may send to, read at request time."""

    known_ips: frozenset[str]
    subnet: str | None
    hub_port: int


class RawSend:
    """One in-flight send, a capped reply list, and a per-client rate limit."""

    def __init__(
        self,
        bus: Any,
        policy: Callable[[], SendPolicy],
        *,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._bus = bus
        self._policy = policy
        self._monotonic = monotonic or time.monotonic
        self._busy = False
        self._client_hits: dict[str, deque[float]] = {}
        self._global_hits: deque[float] = deque()

    def accepts(self, msg_type: object) -> bool:
        return msg_type == "raw_send"

    async def handle_ws(self, ws: Any, data: dict[str, Any]) -> None:
        """WebSocket ``raw_send``. The caller already checked the switch."""
        client = _client_label(f"ws:{id(ws)}")
        try:
            result = await self.send(data, client=client)
        except RawSendError as exc:
            await ws.send_json(
                {"type": "error", "error": exc.code, "message": exc.message}
            )
            return
        await ws.send_json({"type": "raw_send_result", **result})

    async def send(self, body: dict[str, Any], *, client: str) -> dict[str, Any]:
        """Send ``payload_hex`` and return every reply inside the window."""
        policy = self._policy()
        module_ip = _module_ip(body.get("module_ip"))
        port = _port(body.get("port"), policy.hub_port)
        payload = _payload(body.get("payload_hex"))
        window_ms = _window_ms(body.get("window_ms", DEFAULT_WINDOW_MS))
        if not _target_allowed(module_ip, policy):
            self._audit(client, module_ip, port, payload, "refused:target_not_allowed", 0)
            raise RawSendError(
                "target_not_allowed",
                "Target is not a known module and not in the module subnet.",
                422,
            )
        if self._busy:
            self._audit(client, module_ip, port, payload, "refused:raw_send_busy", 0)
            raise RawSendError(
                "raw_send_busy",
                "A raw send is already in progress.",
                429,
            )
        try:
            self._take_slot(client)
        except RawSendError:
            self._audit(client, module_ip, port, payload, "refused:raw_send_rate_limited", 0)
            raise

        self._busy = True
        sent_at = self._monotonic()
        try:
            hold = getattr(self._bus, "hold_status", None)
            if callable(hold):
                hold(module_ip, sent_at + window_ms / 1000.0)
            try:
                await self._bus.send_command(
                    module_ip,
                    payload,
                    port,
                    expect_reply=False,
                )
            except Exception:
                release = getattr(self._bus, "release_hold", None)
                if callable(release):
                    release(module_ip)
                self._audit(client, module_ip, port, payload, "error:send_failed", 0)
                log.warning("raw send failed for %s", module_ip, exc_info=True)
                raise RawSendError(
                    "send_failed",
                    "The field bus could not send the payload.",
                    503,
                ) from None
            packets, truncated = await self._bus.collect_replies(
                module_ip=module_ip,
                after_ts=sent_at,
                timeout_ms=window_ms,
                limit=MAX_REPLIES,
            )
        finally:
            self._busy = False

        replies = []
        for pkt in packets:
            delay = confirmation_ms(sent_at, pkt)
            replies.append({"hex": pkt.data.hex(), "delay_ms": delay})
        result = "ok" if not truncated else "truncated"
        self._audit(client, module_ip, port, payload, result, len(replies))
        return {
            "ok": True,
            "schema_version": 2,
            "sent_hex": payload.hex(),
            "module_ip": module_ip,
            "port": port,
            "window_ms": window_ms,
            "replies": replies,
            "truncated": truncated,
        }

    def _take_slot(self, client: str) -> None:
        now = self._monotonic()
        _prune(self._global_hits, now, _GLOBAL_WINDOW_S)
        if len(self._global_hits) >= _GLOBAL_LIMIT:
            raise RawSendError(
                "raw_send_rate_limited",
                "Too many raw sends. Wait and try again.",
                429,
            )
        hits = self._client_hits.setdefault(client, deque())
        _prune(hits, now, _CLIENT_WINDOW_S)
        if len(hits) >= _CLIENT_LIMIT:
            raise RawSendError(
                "raw_send_rate_limited",
                "Too many raw sends. Wait and try again.",
                429,
            )
        if len(self._client_hits) > _MAX_CLIENTS:
            oldest = min(
                self._client_hits,
                key=lambda key: self._client_hits[key][-1] if self._client_hits[key] else 0.0,
            )
            if oldest != client:
                self._client_hits.pop(oldest, None)
        hits.append(now)
        self._global_hits.append(now)

    def _audit(
        self,
        client: str,
        module_ip: str,
        port: int,
        payload: bytes,
        result: str,
        replies: int,
    ) -> None:
        log.info(
            "raw_send client=%s target=%s port=%s bytes=%s result=%s replies=%d",
            client,
            module_ip,
            port,
            payload.hex(),
            result,
            replies,
        )


def _prune(hits: deque[float], now: float, window_s: float) -> None:
    while hits and now - hits[0] >= window_s:
        hits.popleft()


def _client_label(client: str) -> str:
    text = " ".join(client.split())
    return text[:64] or "unknown"


def _module_ip(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RawSendError("invalid_target", "module_ip must be an IPv4 address.", 422)
    text = value.strip()
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        raise RawSendError("invalid_target", "module_ip must be an IPv4 address.", 422) from None
    if not isinstance(addr, ipaddress.IPv4Address):
        raise RawSendError("invalid_target", "module_ip must be an IPv4 address.", 422)
    if (
        addr.is_multicast
        or addr.is_unspecified
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr == ipaddress.IPv4Address("255.255.255.255")
    ):
        raise RawSendError("invalid_target", "module_ip must be an IPv4 address.", 422)
    return str(addr)


def _port(value: object, hub_port: int) -> int:
    if value is None:
        return hub_port
    if isinstance(value, bool) or not isinstance(value, int):
        raise RawSendError("invalid_port", "port must be the field-bus port.", 422)
    if value != hub_port:
        raise RawSendError("invalid_port", "port must be the field-bus port.", 422)
    return value


def _payload(value: object) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise RawSendError("invalid_payload", "payload_hex must be hex bytes.", 400)
    text = value.strip()
    if len(text) % 2 or any(c not in "0123456789abcdefABCDEF" for c in text):
        raise RawSendError("invalid_payload", "payload_hex must be hex bytes.", 400)
    try:
        payload = bytes.fromhex(text)
    except ValueError:
        raise RawSendError("invalid_payload", "payload_hex must be hex bytes.", 400) from None
    if not payload:
        raise RawSendError("invalid_payload", "payload_hex must be hex bytes.", 400)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise RawSendError(
            "payload_too_large",
            f"Payload is larger than {MAX_PAYLOAD_BYTES} bytes.",
            422,
        )
    return payload


def _window_ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RawSendError(
            "invalid_window",
            f"window_ms must be an integer from 1 to {MAX_WINDOW_MS}.",
            400,
        )
    if value < 1 or value > MAX_WINDOW_MS:
        raise RawSendError(
            "invalid_window",
            f"window_ms must be an integer from 1 to {MAX_WINDOW_MS}.",
            400,
        )
    return value


def _target_allowed(module_ip: str, policy: SendPolicy) -> bool:
    if module_ip in policy.known_ips:
        return True
    network = _subnet(policy.subnet)
    if network is None:
        return False
    addr = ipaddress.ip_address(module_ip)
    return (
        addr in network
        and addr != network.network_address
        and addr != network.broadcast_address
    )


def _subnet(subnet: str | None) -> ipaddress.IPv4Network | None:
    if not isinstance(subnet, str) or not subnet.strip():
        return None
    text = subnet.strip()
    try:
        if "/" in text:
            network = ipaddress.ip_network(text, strict=False)
        else:
            network = ipaddress.ip_network(f"{text}.0/24", strict=False)
    except ValueError:
        return None
    if not isinstance(network, ipaddress.IPv4Network):
        return None
    return network
