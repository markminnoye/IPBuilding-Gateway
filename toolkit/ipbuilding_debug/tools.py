"""The six v1 tools. Each returns a message a tester can act on."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from ipbuilding_debug.buffer import clamp_timeout
from ipbuilding_debug.decode import decode_frame, parse_frame
from ipbuilding_debug.errors import (
    KIND_NOT_AVAILABLE,
    KIND_NO_ADDRESS,
    KIND_OTHER,
    KIND_UNREACHABLE,
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_REMOTE_DEBUGGING_OFF,
    PLANNED_CAPABILITIES,
    ClassifiedError,
    gate_feature,
    msg_connected,
    msg_not_available,
)
from ipbuilding_debug.session import GatewaySession

RAW_SEND_PATH = "/api/v1/debug/raw-send"
SHARING_WARNING = (
    "Dit is voor deze sessie. Haal adressen, namen van mensen en namen van "
    "ruimtes weg voor je het ergens openbaar deelt."
)


@dataclass
class ToolResult:
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        payload = {"message": self.message, **self.data}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return f"{self.message}\n\n{text}"


def _from_error(error: ClassifiedError, **extra: Any) -> ToolResult:
    data = {"ok": False, **extra, "kind": error.kind}
    return ToolResult(error.message, data)


def _capabilities(status: dict[str, Any] | None) -> list[str]:
    if not isinstance(status, dict):
        return []
    caps = status.get("capabilities")
    if not isinstance(caps, list):
        return []
    return [str(item) for item in caps]


async def connection_status(
    session: GatewaySession,
    *,
    log_level: str | None = None,
) -> ToolResult:
    """Reachability, the debug switch, capabilities, and the local buffer."""
    error = await session.refresh_status()
    status = session.status if error is None else None
    if error is not None and error.kind in (KIND_UNREACHABLE, KIND_NO_ADDRESS):
        return _from_error(
            error,
            connection=session.state,
            buffer=_buffer_summary(session),
        )
    if error is not None and status is None:
        return _from_error(error, connection=session.state, buffer=_buffer_summary(session))

    remote = status.get("remote_debugging") if isinstance(status, dict) else None
    if not isinstance(remote, bool):
        remote = None
    caps = _capabilities(status if isinstance(status, dict) else None)
    message = msg_connected(remote_debugging=remote, capabilities=caps)
    kind = "remote_debugging_off" if remote is False else "connected"
    ok = remote is True
    log_note = ""
    if log_level:
        gated = gate_feature(status if isinstance(status, dict) else None, "log_stream")
        if gated is None:
            outcome = await session.request_log_level(log_level)
            if outcome == "rate_limited":
                message = MSG_LOG_LEVEL_RATE_LIMITED
                log_note = MSG_LOG_LEVEL_RATE_LIMITED
                kind = "log_level_rate_limited"
                ok = False
            elif outcome == "disabled":
                message = MSG_REMOTE_DEBUGGING_OFF
                log_note = MSG_REMOTE_DEBUGGING_OFF
                kind = "remote_debugging_off"
                ok = False
            elif outcome == "rejected":
                log_note = (
                    "De gateway nam het logniveau niet aan. "
                    "Gebruik debug, info, warning of error."
                )
            elif outcome == "not_connected":
                log_note = (
                    "Logniveau nog niet doorgegeven; de live-verbinding staat nog niet."
                )
            elif outcome == "applied":
                log_note = (
                    "Logniveau gevraagd. Het geldt tijdelijk en wordt niet opgeslagen."
                )
            else:
                log_note = "Logniveau gevraagd."
        else:
            log_note = gated.message
    return ToolResult(
        message,
        {
            "ok": ok,
            "kind": kind,
            "connection": session.state,
            "version": (status or {}).get("version"),
            "remote_debugging": remote,
            "capabilities": caps,
            "missing_capabilities": [
                name for name in PLANNED_CAPABILITIES if name not in caps
            ],
            "hub_role": (status or {}).get("hub_role"),
            "buffer": _buffer_summary(session),
            "log_level_note": log_note,
        },
    )


async def probe_generation(session: GatewaySession) -> ToolResult:
    """Installation inventory from the gateway API that already exists."""
    error = await session.refresh_status()
    if error is not None and error.kind in (KIND_UNREACHABLE, KIND_NO_ADDRESS):
        return _from_error(error)
    status = session.status or {}
    modules_body, modules_error = await session.get_json("/api/v1/modules")
    devices_body, devices_error = await session.get_json("/api/v1/devices")
    if modules_error is not None and modules_error.kind == KIND_UNREACHABLE:
        return _from_error(modules_error)
    modules = _list_of(modules_body, "modules")
    devices = _list_of(devices_body, "devices")
    summary = _module_summary(modules)
    hint = _generation_hint(modules)
    caps = _capabilities(status)
    dialect = (
        "Frames meelezen kan, dus het dialect kan met capture_frames en decode_test "
        "bevestigd worden."
        if "udp_frame" in caps
        else (
            "Het dialect (welke antwoorden de modules geven) is pas zeker als "
            "veldbusframes meelezen kan. "
            + msg_not_available("udp_frame")
        )
    )
    remote = status.get("remote_debugging") if isinstance(status.get("remote_debugging"), bool) else None
    parts = [
        f"Gateway-versie {status.get('version') or 'onbekend'}.",
        hint,
        dialect,
    ]
    if remote is False:
        parts.append(MSG_REMOTE_DEBUGGING_OFF)
    message = " ".join(parts)
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "inventory",
            "version": status.get("version"),
            "hub_role": status.get("hub_role"),
            "input_mode_label": status.get("input_mode_label"),
            "remote_debugging": remote,
            "capabilities": caps,
            "modules": summary,
            "device_count": len(devices),
            "devices_by_type": _count_by(devices, "device_type"),
            "modules_error": modules_error.message if modules_error else "",
            "devices_error": devices_error.message if devices_error else "",
        },
    )


async def capture_frames(
    session: GatewaySession,
    *,
    seconds: float = 5,
    direction: str = "both",
    module: str = "",
    pattern: str = "",
    limit: int = 50,
) -> ToolResult:
    """Live field-bus frames. Needs capability ``udp_frame``."""
    error = await session.refresh_status()
    if error is not None:
        return _from_error(error, capability="udp_frame")
    gated = gate_feature(session.status, "udp_frame")
    if gated is not None:
        return _from_error(gated, capability="udp_frame")

    seconds = clamp_timeout(seconds if seconds > 0 else 0.1)
    limit = max(1, min(int(limit), 200))
    direction = (direction or "both").lower()
    # Cursor is taken before subscribe, so a frame that is the reply to that
    # subscribe is inside the window. The wait below is only the upper bound.
    since = await session.ensure_udp_subscription(timeout=3)
    if since is None:
        return ToolResult(
            "De gateway antwoordt, maar de live-verbinding staat nog niet. "
            "Probeer het zo meteen opnieuw.",
            {"ok": False, "kind": "connecting", "frames": []},
        )
    frames = await _collect_frames(
        session,
        since,
        seconds=seconds,
        direction=direction,
        module=module,
        pattern=pattern,
        limit=limit,
    )
    if not frames:
        message = (
            "Er kwamen geen passende frames binnen in deze periode. "
            "Dat kan betekenen dat er niets gebeurde, of dat dit verkeer niet "
            "langs de gateway gaat."
        )
    else:
        message = f"{len(frames)} frame(s) ontvangen."
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "frames",
            "frames": frames,
            "seconds": seconds,
            "direction": direction,
        },
    )


async def send_raw(
    session: GatewaySession,
    *,
    target: str,
    payload_hex: str,
    port: int = 1001,
    window_ms: int = 2000,
    confirmed: bool = False,
) -> ToolResult:
    """Send raw bytes through the gateway. Requires an explicit second call."""
    try:
        hex_payload = _normalize_hex(payload_hex)
    except ValueError:
        return ToolResult(
            "Dit is geen geldig pakket. Gebruik hexadecimale tekens, twee per byte, "
            "bijvoorbeeld 5330303030.",
            {"ok": False, "kind": KIND_OTHER},
        )
    target = (target or "").strip()
    if not target:
        return ToolResult(
            "Er is geen module opgegeven. Zeg naar welke module het pakket moet.",
            {"ok": False, "kind": KIND_OTHER},
        )
    port = int(port)
    window_ms = max(100, min(int(window_ms), 5000))
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "target": target,
        "port": port,
        "payload_hex": hex_payload,
        "window_ms": window_ms,
        "sent": False,
    }
    if not confirmed:
        return ToolResult(
            (
                f"Nog niet verstuurd. Dit pakket gaat naar module {target} "
                f"op poort {port}: {hex_payload}. "
                "Het kan een lamp of een ander kanaal veranderen. "
                "Vraag de tester expliciet of dit verstuurd mag worden. "
                "Roep send_raw daarna opnieuw aan met confirmed=true."
            ),
            preview,
        )

    error = await session.refresh_status()
    if error is not None:
        return _from_error(error, **preview)
    gated = gate_feature(session.status, "raw_send")
    if gated is not None:
        return _from_error(gated, **preview)

    body, call_error = await session.post_json(
        RAW_SEND_PATH,
        {
            "target": target,
            "port": port,
            "payload_hex": hex_payload,
            "window_ms": window_ms,
        },
        timeout=max(8.0, window_ms / 1000 + 3),
    )
    if call_error is not None:
        if call_error.kind == KIND_NOT_AVAILABLE:
            call_error = ClassifiedError(
                KIND_NOT_AVAILABLE,
                msg_not_available("raw_send"),
                call_error.detail,
            )
        return _from_error(call_error, **preview)
    replies = []
    if isinstance(body, dict):
        raw_replies = body.get("replies") or []
        if isinstance(raw_replies, list):
            replies = raw_replies
    decoded = []
    for reply in replies:
        if isinstance(reply, dict) and isinstance(reply.get("hex"), str):
            item = dict(reply)
            item["local_decode"] = _safe_decode(reply["hex"])
            decoded.append(item)
        else:
            decoded.append(reply)
    return ToolResult(
        f"Pakket verstuurd naar {target} op poort {port}. {len(decoded)} antwoord(en) binnen het venster.",
        {
            "ok": True,
            "kind": "sent",
            "sent": True,
            "target": target,
            "port": port,
            "payload_hex": hex_payload,
            "window_ms": window_ms,
            "replies": decoded,
        },
    )


def decode_test(payload: str) -> ToolResult:
    """Local decode through the gateway payload decoders. No gateway needed."""
    try:
        data = parse_frame(payload)
    except ValueError:
        return ToolResult(
            "Dit is geen frame dat ik kan lezen. Plak hex of een korte ASCII-tekst.",
            {"ok": False, "kind": KIND_OTHER, "matched": False, "matches": []},
        )
    decoded = decode_frame(data)
    if decoded["matched"]:
        names = ", ".join(item["decoder"] for item in decoded["matches"])
        message = f"Het frame past bij: {names}."
    else:
        message = "Geen enkele decoder herkent dit frame."
    return ToolResult(message, {"ok": True, "kind": "decode", **decoded})


async def export_session(
    session: GatewaySession,
    *,
    note: str = "",
    marker: str = "",
) -> ToolResult:
    """Bundle notes, gap markers, and captured events for the session report."""
    if note or marker:
        await session.annotate(note or marker, marker=marker)
    events = session.buffer.snapshot()
    interesting = [
        event
        for event in events
        if event.get("type") in {"gap", "note", "udp_frame", "log", "log_dropped", "state_changed", "button_event"}
    ]
    status = session.status or {}
    message = (
        "Sessie gebundeld. "
        + SHARING_WARNING
    )
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "export",
            "sharing": SHARING_WARNING,
            "gateway": {
                "version": status.get("version"),
                "remote_debugging": status.get("remote_debugging"),
                "capabilities": _capabilities(status),
                "connection": session.state,
            },
            "notes": list(session.notes),
            "gaps": [event for event in events if event.get("type") == "gap"],
            "events": interesting[-500:],
            "buffer": _buffer_summary(session),
        },
    )


def _buffer_summary(session: GatewaySession) -> dict[str, Any]:
    gaps = session.gap_events()
    return {
        "count": len(session.buffer),
        "dropped": session.buffer.dropped,
        "gaps": len(gaps),
        "last_gap": gaps[-1] if gaps else None,
        "connection": session.state,
    }


def _list_of(body: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(body, dict) and isinstance(body.get(key), list):
        return [item for item in body[key] if isinstance(item, dict)]
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    return []


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        name = str(item.get(key) or "onbekend")
        counts[name] = counts.get(name, 0) + 1
    return counts


def _module_summary(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for module in modules:
        summary.append(
            {
                "id": module.get("id"),
                "type": module.get("type"),
                "model": module.get("model"),
                "firmware": module.get("firmware"),
                "name": module.get("name"),
            }
        )
    return summary


def _generation_hint(modules: list[dict[str, Any]]) -> str:
    models = [str(module.get("model") or "") for module in modules if module.get("model")]
    if not models:
        return "Er staan nog geen modules in de gateway."
    poe = [model for model in models if "poe" in model.lower()]
    if len(poe) == len(models):
        return "De module-namen wijzen op PoE-modules."
    if poe:
        return "Er zitten modules mét en zonder PoE in de naam tussen."
    return (
        "De module-namen bevatten geen PoE. "
        "Welk dialect de modules spreken is pas zeker als frames meelezen kan."
    )


def _frame_matches(event: dict[str, Any], *, direction: str, module: str, pattern: str) -> bool:
    if direction not in ("", "both") and str(event.get("direction") or "").lower() != direction:
        return False
    if module:
        blob = " ".join(
            str(event.get(key) or "")
            for key in ("src", "dst", "module", "module_ip", "target")
        )
        if module not in blob:
            return False
    if pattern:
        haystack = " ".join(
            str(event.get(key) or "") for key in ("hex", "raw", "ascii", "dialect_id")
        )
        if pattern.lower() not in haystack.lower():
            return False
    return True


def _normalize_hex(payload: str) -> str:
    compact = "".join((payload or "").split())
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if not compact or len(compact) % 2 or any(c not in "0123456789abcdefABCDEF" for c in compact):
        raise ValueError("hex")
    return compact.lower()


def _safe_decode(payload_hex: str) -> dict[str, Any] | None:
    try:
        return decode_frame(parse_frame(payload_hex))
    except (ValueError, Exception):
        return None


def _with_local_decode(event: dict[str, Any]) -> dict[str, Any]:
    item = dict(event)
    hex_payload = event.get("hex")
    if isinstance(hex_payload, str):
        item["local_decode"] = _safe_decode(hex_payload)
    return item


async def _collect_frames(
    session: GatewaySession,
    since: int,
    *,
    seconds: float,
    direction: str,
    module: str,
    pattern: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Frames after ``since``, until ``limit`` matches or ``seconds`` elapses."""

    def matching(event: dict[str, Any]) -> bool:
        return event.get("type") == "udp_frame" and _frame_matches(
            event, direction=direction, module=module, pattern=pattern
        )

    def gathered() -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for entry in session.buffer.since(since, types={"udp_frame"}):
            if not matching(entry.event):
                continue
            found.append(_with_local_decode(entry.event))
            if len(found) >= limit:
                break
        return found

    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    watched = since
    while True:
        frames = gathered()
        if len(frames) >= limit:
            return frames
        remaining = deadline - loop.time()
        if remaining <= 0:
            return frames
        nxt = await session.buffer.wait_until(matching, remaining, watched)
        if nxt is None:
            return gathered()
        watched = nxt.seq
