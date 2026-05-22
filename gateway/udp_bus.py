"""Asyncio UDP/1001 field bus client."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from gateway.config import GatewayConfig


@dataclass
class UDPPacket:
    data: bytes
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    monotonic_ts: float


class UDPBus:
    """Send commands to field modules and collect replies."""

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig.from_env()
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _UDPProtocol | None = None
        self._queue: asyncio.Queue[UDPPacket] = asyncio.Queue()
        self._simulated_replies: dict[bytes, bytes] = {}

    async def start(self) -> None:
        if self.config.simulated_mode:
            return
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._queue),
            local_addr=(self.config.bind_ip, 0),
        )

    async def stop(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None

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
    def __init__(self, queue: asyncio.Queue[UDPPacket]) -> None:
        self._queue = queue

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
