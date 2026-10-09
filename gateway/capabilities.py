"""Feature strings advertised on ``GET /api/v1/status``.

Append a name only when that feature is implemented.
"""

from __future__ import annotations

CAPABILITIES: tuple[str, ...] = (
    "log_stream",
    "udp_frame",
    "raw_send",
)
