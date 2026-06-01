"""Asyncio UDP/1001 field bus client with polling loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from gateway.config import GatewayConfig

log = logging.getLogger(__name__)

ReplyCallback = Callable[["UDPPacket"], None]

# Poll payloads per module type (confirmed in RE Sprint 1-5)
_POLL_RELAY = b"P0000"
_POLL_DIMMER = b"I9900"
_POLL_INPUT = b"I0000"

_MODULE_POLL: dict[str, bytes] = {
    "relay": _POLL_RELAY,
    "dimmer": _POLL_DIMMER,
    "input": _POLL_INPUT,
}


@dataclass
class UDPPacket:
    data: bytes
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    monotonic_ts: float


class UDPBus:
    """Send commands to field modules, poll for state, and collect replies."""

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig.from_env()
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _UDPProtocol | None = None
        self._queue: asyncio.Queue[UDPPacket] = asyncio.Queue()
        self._simulated_replies: dict[bytes, bytes] = {}
        self._listeners: list[ReplyCallback] = []
        self._poll_task: asyncio.Task[None] | None = None

    def add_listener(self, cb: ReplyCallback) -> None:
        """Register a callback invoked for every inbound packet."""
        self._listeners.append(cb)

    def remove_listener(self, cb: ReplyCallback) -> None:
        self._listeners.remove(cb)

    def _notify_listeners(self, pkt: UDPPacket) -> None:
        for cb in self._listeners:
            try:
                cb(pkt)
            except Exception:
                log.exception("Listener callback error")

    async def start(self) -> None:
        if not self.config.simulated_mode:
            loop = asyncio.get_running_loop()
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self._queue, self._notify_listeners),
                local_addr=(self.config.bind_ip, 0),
            )
        self._poll_task = asyncio.create_task(self._poll_loop())
        log.info(
            "UDPBus started  poll_interval=%.1fs  modules=%s  simulated=%s",
            self.config.poll_interval_s,
            list(self.config.field_modules.keys()),
            self.config.simulated_mode,
        )

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._transport:
            self._transport.close()
            self._transport = None
        log.info("UDPBus stopped")

    async def _poll_loop(self) -> None:
        """Background task: poll all modules at fixed interval."""
        try:
            while True:
                await self._poll_all_modules()
                await asyncio.sleep(self.config.poll_interval_s)
        except asyncio.CancelledError:
            log.info("Poll loop cancelled")
            raise

    async def _poll_all_modules(self) -> None:
        for module_type, module_ip in self.config.field_modules.items():
            poll_payload = _MODULE_POLL.get(module_type)
            if not poll_payload:
                continue
            try:
                await self.send_command(module_ip, poll_payload)
            except Exception:
                log.warning("Poll failed for %s (%s)", module_type, module_ip, exc_info=True)

    def register_simulated_reply(self, command: bytes, reply: bytes) -> None:
        self._simulated_replies[command] = reply

    async def send_command(self, module_ip: str, payload: bytes, port: int | None = None) -> None:
        dst_port = port or self.config.hub_port
        if self.config.simulated_mode:
            reply = self._simulated_replies.get(payload)
            if reply:
                pkt = UDPPacket(
                    data=reply,
                    src_ip=module_ip,
                    src_port=dst_port,
                    dst_ip=self.config.bind_ip,
                    dst_port=0,
                    monotonic_ts=time.monotonic(),
                )
                await self._queue.put(pkt)
                self._notify_listeners(pkt)
            return
        if not self._transport:
            raise RuntimeError("UDPBus not started")
        self._transport.sendto(payload, (module_ip, dst_port))

    async def listen_for_replies(self) -> AsyncIterator[UDPPacket]:
        while True:
            yield await self._queue.get()

    async def correlate_reply(
        self,
        *,
        module_ip: str,
        after_ts: float,
        timeout_ms: int | None = None,
        predicate: Callable[[bytes], bool] | None = None,
    ) -> UDPPacket | None:
        """Wait for first reply from module_ip after after_ts."""
        deadline = time.monotonic() + (timeout_ms or self.config.reply_timeout_ms) / 1000.0

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                pkt = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if pkt.src_ip != module_ip:
                continue
            if pkt.monotonic_ts < after_ts:
                continue
            if predicate and not predicate(pkt.data):
                continue
            return pkt
        return None


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        queue: asyncio.Queue[UDPPacket],
        notify: Callable[[UDPPacket], None],
    ) -> None:
        self._queue = queue
        self._notify = notify

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        pkt = UDPPacket(
            data=data,
            src_ip=addr[0],
            src_port=addr[1],
            dst_ip="",
            dst_port=0,
            monotonic_ts=time.monotonic(),
        )
        self._queue.put_nowait(pkt)
        self._notify(pkt)
