"""Live field-bus frames for remote-debugging subscribers.

Each sent and received UDP payload can be forwarded as a ``udp_frame``
WebSocket event. Delivery uses a bounded per-client queue. A slow client
is told how many frames were dropped and never blocks the bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gateway.payloads.dimmer import decode_dimmer_payload
from gateway.payloads.input import decode_input_payload
from gateway.payloads.relay import decode_relay_payload
from gateway.udp_bus import UDPPacket

QUEUE_SIZE = 100

_DECODERS = (
    decode_input_payload,
    decode_dimmer_payload,
    decode_relay_payload,
)


def describe_payload(data: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort decode. Unknown payloads stay raw hex on the event."""
    for decoder in _DECODERS:
        try:
            parsed = decoder(data)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        dialect = parsed.get("dialect_id")
        dialect_id = dialect if isinstance(dialect, str) and dialect else None
        try:
            json.dumps(parsed)
        except (TypeError, ValueError):
            return None, dialect_id
        return parsed, dialect_id
    return None, None


def frame_event(direction: str, pkt: UDPPacket) -> dict[str, Any]:
    """One northbound ``udp_frame`` object."""
    decoded, dialect_id = describe_payload(pkt.data)
    return {
        "type": "udp_frame",
        "ts": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "direction": direction,
        "src": pkt.src_ip,
        "src_port": pkt.src_port,
        "dst": pkt.dst_ip,
        "dst_port": pkt.dst_port,
        "hex": pkt.data.hex(),
        "decoded": decoded,
        "dialect_id": dialect_id,
    }


@dataclass
class _Subscriber:
    ws: Any
    queue: asyncio.Queue[dict[str, Any]]
    dropped: int = 0
    task: asyncio.Task[None] | None = None


class UdpFrameHub:
    """Fan-out of field-bus frames to opted-in WebSocket clients."""

    def __init__(self, queue_size: int = QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subs: dict[int, _Subscriber] = {}

    def publish(self, direction: str, pkt: UDPPacket) -> None:
        """Queue one frame. Drops it for a full client queue. Never awaits."""
        if direction not in ("tx", "rx") or not self._subs:
            return
        entry = frame_event(direction, pkt)
        for sub in self._subs.values():
            try:
                sub.queue.put_nowait(entry)
            except asyncio.QueueFull:
                sub.dropped += 1

    async def subscribe(self, ws: Any) -> None:
        key = id(ws)
        old = self._subs.pop(key, None)
        if old is not None and old.task is not None:
            old.task.cancel()
        sub = _Subscriber(ws=ws, queue=asyncio.Queue(self._queue_size))
        self._subs[key] = sub
        if not await self._try_send(ws, {"type": "udp_frames_subscribed"}):
            self._subs.pop(key, None)
            return
        sub.task = asyncio.create_task(self._drain(sub))

    async def unsubscribe(self, ws: Any) -> None:
        await self.disconnect(ws)
        await self._try_send(ws, {"type": "udp_frames_unsubscribed"})

    async def disconnect(self, ws: Any) -> None:
        sub = self._subs.pop(id(ws), None)
        if sub is not None and sub.task is not None:
            sub.task.cancel()

    def close(self) -> None:
        for sub in self._subs.values():
            if sub.task is not None:
                sub.task.cancel()
        self._subs.clear()

    async def _drain(self, sub: _Subscriber) -> None:
        try:
            while True:
                entry = await sub.queue.get()
                if sub.dropped:
                    count = sub.dropped
                    sub.dropped = 0
                    if not await self._try_send(
                        sub.ws, {"type": "udp_frame_dropped", "dropped": count}
                    ):
                        self._subs.pop(id(sub.ws), None)
                        return
                if not await self._try_send(sub.ws, entry):
                    self._subs.pop(id(sub.ws), None)
                    return
        except asyncio.CancelledError:
            return

    async def _try_send(self, ws: Any, payload: dict[str, Any]) -> bool:
        if getattr(ws, "closed", False):
            return False
        try:
            await ws.send_json(payload)
        except Exception:
            logging.getLogger(__name__).debug("udp frame send failed")
            return False
        return True
