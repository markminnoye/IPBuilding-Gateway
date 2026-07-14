"""Asyncio UDP/1001 field bus client with polling loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from gateway.config import GatewayConfig

log = logging.getLogger(__name__)

ReplyCallback = Callable[["UDPPacket"], None]

# Steady-state poll payloads per module type (RE Sprint 1-5).
# Relay: P0000 keepalive (pulse echo only). Per-channel status at startup uses
# I<CH>00 sweep via gateway.state_poll (not the poll loop).
_POLL_RELAY = b"P0000"
_POLL_DIMMER = b"I9900"
_POLL_INPUT = b"I0000"

_MODULE_POLL: dict[str, bytes] = {
    "relay": _POLL_RELAY,
    "dimmer": _POLL_DIMMER,
    "input": _POLL_INPUT,
}

# Bound correlate_reply buffering during command waits (drop oldest on overflow).
_CORRELATE_QUEUE_MAX = 64
# Recent inbound packets for correlate_reply after synchronous send_command.
_RECENT_PACKETS_MAX = 128


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
        self._simulated_replies: dict[bytes, bytes] = {}
        self._listeners: list[ReplyCallback] = []
        self._recent_packets: deque[UDPPacket] = deque(maxlen=_RECENT_PACKETS_MAX)
        self._poll_task: asyncio.Task[None] | None = None
        self._next_poll_ts: dict[str, float] = {}
        self.last_send_ts: float = 0.0  # monotonic ts of last send_command

    def add_listener(self, cb: ReplyCallback) -> None:
        """Register a callback invoked for every inbound packet."""
        self._listeners.append(cb)

    def remove_listener(self, cb: ReplyCallback) -> None:
        self._listeners.remove(cb)

    def _notify_listeners(self, pkt: UDPPacket) -> None:
        self._recent_packets.append(pkt)
        for cb in self._listeners:
            try:
                cb(pkt)
            except Exception:
                log.exception("Listener callback error")

    def _match_reply(
        self,
        pkt: UDPPacket,
        *,
        module_ip: str,
        after_ts: float,
        predicate: Callable[[bytes], bool] | None,
    ) -> bool:
        if pkt.src_ip != module_ip:
            return False
        if pkt.monotonic_ts < after_ts:
            return False
        if predicate and not predicate(pkt.data):
            return False
        return True

    def _find_recent_reply(
        self,
        *,
        module_ip: str,
        after_ts: float,
        predicate: Callable[[bytes], bool] | None,
    ) -> UDPPacket | None:
        for pkt in reversed(self._recent_packets):
            if self._match_reply(
                pkt,
                module_ip=module_ip,
                after_ts=after_ts,
                predicate=predicate,
            ):
                return pkt
        return None

    async def start(self) -> None:
        if not self.config.simulated_mode:
            loop = asyncio.get_running_loop()
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self._notify_listeners),
                local_addr=(self.config.bind_ip, 0),
            )
        self._poll_task = asyncio.create_task(self._poll_loop())
        if self.config.installation:
            modules_list = [f"{mc.type.value}:{mc.ip}" for mc in self.config.installation.modules]
        else:
            modules_list = [f"{k}:{v}" for k, v in self.config.field_modules.items()]
        log.info(
            "UDPBus started  input_poll=%.1fs  actuator_poll=%.1fs  modules=%s  simulated=%s",
            self.config.poll_interval_s,
            self.config.actuator_poll_interval_s,
            modules_list,
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

    def _interval_for_type(self, module_type: str) -> float:
        if module_type == "input":
            return self.config.poll_interval_s
        return self.config.actuator_poll_interval_s

    def _poll_tick_s(self) -> float:
        return min(self.config.poll_interval_s, self.config.actuator_poll_interval_s)

    async def _poll_loop(self) -> None:
        """Background task: poll modules on per-type schedules (IPBox cadence)."""
        try:
            while True:
                await self._poll_due_modules(time.monotonic())
                await asyncio.sleep(self._poll_tick_s())
        except asyncio.CancelledError:
            log.info("Poll loop cancelled")
            raise

    async def _poll_due_modules(self, now: float) -> None:
        due_types: set[str] = set()
        for module_type in _MODULE_POLL:
            if now >= self._next_poll_ts.get(module_type, 0.0):
                due_types.add(module_type)
                self._next_poll_ts[module_type] = now + self._interval_for_type(module_type)

        if not due_types:
            return

        if self.config.installation:
            for mc in self.config.installation.modules:
                module_type = mc.type.value
                if module_type not in due_types:
                    continue
                if module_type == "input" and not self.config.claims_input_modules:
                    continue
                poll_payload = _MODULE_POLL.get(module_type)
                if not poll_payload:
                    continue
                try:
                    await self.send_command(mc.ip, poll_payload)
                except Exception:
                    log.warning("Poll failed for %s (%s)", module_type, mc.ip, exc_info=True)
        else:
            for module_type, module_ip in self.config.field_modules.items():
                if module_type not in due_types:
                    continue
                if module_type == "input" and not self.config.claims_input_modules:
                    continue
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
                self.last_send_ts = time.monotonic()
                self._notify_listeners(pkt)
            return
        if not self._transport:
            raise RuntimeError("UDPBus not started")
        self._transport.sendto(payload, (module_ip, dst_port))
        self.last_send_ts = time.monotonic()

    async def listen_for_replies(self) -> AsyncIterator[UDPPacket]:
        queue: asyncio.Queue[UDPPacket] = asyncio.Queue(maxsize=_CORRELATE_QUEUE_MAX)

        def collect(pkt: UDPPacket) -> None:
            try:
                queue.put_nowait(pkt)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(pkt)

        self.add_listener(collect)
        try:
            while True:
                yield await queue.get()
        finally:
            self.remove_listener(collect)

    async def correlate_reply(
        self,
        *,
        module_ip: str,
        after_ts: float,
        timeout_ms: int | None = None,
        predicate: Callable[[bytes], bool] | None = None,
    ) -> UDPPacket | None:
        """Wait for first reply from module_ip after after_ts."""
        wait_queue: asyncio.Queue[UDPPacket] = asyncio.Queue(maxsize=_CORRELATE_QUEUE_MAX)

        def collect(pkt: UDPPacket) -> None:
            try:
                wait_queue.put_nowait(pkt)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    wait_queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    wait_queue.put_nowait(pkt)

        self.add_listener(collect)
        try:
            matched = self._find_recent_reply(
                module_ip=module_ip,
                after_ts=after_ts,
                predicate=predicate,
            )
            if matched is not None:
                return matched

            deadline = time.monotonic() + (timeout_ms or self.config.reply_timeout_ms) / 1000.0

            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    pkt = await asyncio.wait_for(wait_queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if self._match_reply(
                    pkt,
                    module_ip=module_ip,
                    after_ts=after_ts,
                    predicate=predicate,
                ):
                    return pkt
            return None
        finally:
            self.remove_listener(collect)


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, notify: Callable[[UDPPacket], None]) -> None:
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
        self._notify(pkt)
