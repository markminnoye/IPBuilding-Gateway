"""In-memory ring buffer of gateway events. Lost when the MCP process exits."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

# Tools must not block a desktop client longer than this.
MAX_WAIT_SECONDS = 30.0


def clamp_timeout(seconds: float) -> float:
    """Cap a wait at 30 seconds. Negative values wait nothing."""
    if seconds < 0:
        return 0.0
    if seconds > MAX_WAIT_SECONDS:
        return MAX_WAIT_SECONDS
    return seconds


@dataclass(frozen=True)
class BufferEntry:
    seq: int
    event: dict[str, Any]
    received_at: datetime


class RingBuffer:
    """Bounded event log. Readers poll; nothing is pushed to the model."""

    def __init__(self, maxlen: int = 2000) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be at least 1")
        self.maxlen = maxlen
        self._items: deque[BufferEntry] = deque()
        self._seq = 0
        self.dropped = 0
        self._cond = asyncio.Condition()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def latest_seq(self) -> int:
        return self._seq

    async def append(self, event: dict[str, Any]) -> int:
        async with self._cond:
            self._seq += 1
            if len(self._items) >= self.maxlen:
                self._items.popleft()
                self.dropped += 1
            self._items.append(
                BufferEntry(self._seq, event, datetime.now().astimezone())
            )
            self._cond.notify_all()
            return self._seq

    def since(
        self,
        seq: int,
        *,
        types: set[str] | None = None,
    ) -> list[BufferEntry]:
        found: list[BufferEntry] = []
        for item in self._items:
            if item.seq <= seq:
                continue
            if types is not None and item.event.get("type") not in types:
                continue
            found.append(item)
        return found

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.event for item in self._items]

    def entries(self) -> list[BufferEntry]:
        return list(self._items)

    async def wait_until(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float,
        since_seq: int,
    ) -> BufferEntry | None:
        """Return the next matching event, or None when the (capped) timeout ends."""
        timeout = clamp_timeout(timeout)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with self._cond:
            while True:
                for item in self._items:
                    if item.seq > since_seq and predicate(item.event):
                        return item
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return None
