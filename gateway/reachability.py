"""Per-module field-bus reply timing.

The tracker only watches sends and replies the bus already makes. It does
not add polls. A command confirmation uses the same short reply window as
``correlate_reply``.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from gateway.payloads.dimmer import decode_dimmer_payload
from gateway.payloads.input import decode_input_payload
from gateway.payloads.relay import decode_relay_payload

# A reply slower than this is "slow". Faster is "ok". No reply is "none".
SLOW_REPLY_MS = 200
_AVG_SAMPLES = 20

_DECODERS = (
    decode_relay_payload,
    decode_dimmer_payload,
    decode_input_payload,
)


def empty_reachability() -> dict[str, Any]:
    return {
        "last_reply_at": None,
        "last_reply_ms": None,
        "avg_reply_ms": None,
        "missed_replies": 0,
    }


def reported_fields(data: bytes) -> dict[str, Any] | None:
    """State or level from a status reply. Unknown payloads stay null."""
    for decoder in _DECODERS:
        try:
            parsed = decoder(data)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        out: dict[str, Any] = {}
        state = parsed.get("state")
        if isinstance(state, str):
            out["state"] = state
        level = parsed.get("level_percent")
        if isinstance(level, int) and not isinstance(level, bool):
            out["level_percent"] = level
        if out:
            return out
    return None


def confirmation_ms(sent: float, reply: object) -> int | None:
    """Milliseconds from ``sent`` to a real reply timestamp, or None."""
    ts = getattr(reply, "monotonic_ts", None)
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    if isinstance(sent, bool) or not isinstance(sent, (int, float)):
        return None
    return max(0, int(round((float(ts) - float(sent)) * 1000)))


@dataclass
class _ModuleTiming:
    last_reply_at: str | None = None
    last_reply_ms: int | None = None
    missed_replies: int = 0
    pending_at: float | None = None
    samples: deque[int] = field(default_factory=lambda: deque(maxlen=_AVG_SAMPLES))


class ReachabilityTracker:
    """Last reply, last and average response time, and missed replies."""

    def __init__(
        self,
        timeout_s: float,
        *,
        slow_ms: int = SLOW_REPLY_MS,
        monotonic: Callable[[], float] | None = None,
        wall_clock: Callable[[], str] | None = None,
    ) -> None:
        self._timeout_s = timeout_s
        self.slow_ms = slow_ms
        self._monotonic = monotonic or time.monotonic
        self._wall_clock = wall_clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        self._modules: dict[str, _ModuleTiming] = {}

    def note_send(self, module_ip: str, sent_at: float) -> None:
        """Remember the latest send. An older unanswered send outside the window is a miss."""
        stats = self._modules.setdefault(module_ip, _ModuleTiming())
        if (
            stats.pending_at is not None
            and sent_at - stats.pending_at > self._timeout_s
        ):
            stats.missed_replies += 1
        stats.pending_at = sent_at

    def note_reply(self, module_ip: str, recv_at: float) -> int | None:
        """Record that ``module_ip`` answered. Returns the paired response time."""
        stats = self._modules.setdefault(module_ip, _ModuleTiming())
        if (
            stats.pending_at is not None
            and recv_at - stats.pending_at > self._timeout_s
        ):
            stats.missed_replies += 1
            stats.pending_at = None
        stats.last_reply_at = self._wall_clock()
        if stats.pending_at is None or recv_at < stats.pending_at:
            return None
        elapsed = max(0, int(round((recv_at - stats.pending_at) * 1000)))
        stats.pending_at = None
        stats.last_reply_ms = elapsed
        stats.samples.append(elapsed)
        return elapsed

    def note_timeout(self, module_ip: str, now: float) -> None:
        """Count a miss when the reply window for the latest send has closed."""
        stats = self._modules.get(module_ip)
        if stats is None or stats.pending_at is None:
            return
        if now - stats.pending_at >= self._timeout_s:
            stats.missed_replies += 1
            stats.pending_at = None

    def classify(self, reply_ms: int | None) -> str:
        if reply_ms is None:
            return "none"
        if reply_ms > self.slow_ms:
            return "slow"
        return "ok"

    def view(self, module_ip: str) -> dict[str, Any]:
        stats = self._modules.get(module_ip)
        if stats is None:
            return empty_reachability()
        avg = None
        if stats.samples:
            avg = int(round(sum(stats.samples) / len(stats.samples)))
        return {
            "last_reply_at": stats.last_reply_at,
            "last_reply_ms": stats.last_reply_ms,
            "avg_reply_ms": avg,
            "missed_replies": stats.missed_replies,
        }
