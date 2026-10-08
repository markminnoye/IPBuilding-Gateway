"""Feature strings advertised on ``GET /api/v1/status``.

Append a name only when that feature is implemented. Planned follow-ups
(not listed until they exist): ``raw_send``.
"""

from __future__ import annotations

CAPABILITIES: tuple[str, ...] = (
    "log_stream",
    "udp_frame",
    "module_reachability",
)
