"""Toolkit tools. Each returns a message a tester can act on."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from ipbuilding_debug.buffer import clamp_timeout
from ipbuilding_debug.decode import decode_frame, parse_frame
from ipbuilding_debug.dialect import present_decode, present_event
from ipbuilding_debug.errors import (
    KIND_NOT_AVAILABLE,
    KIND_NO_ADDRESS,
    KIND_OTHER,
    KIND_UNREACHABLE,
    MSG_GATEWAY_TOO_OLD,
    MSG_LOGS_USE_ADDON_TAB,
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_REMOTE_DEBUGGING_OFF,
    SWITCH_NAME,
    PLANNED_CAPABILITIES,
    ClassifiedError,
    gate_feature,
    msg_connected,
    msg_log_level_applied,
    msg_mdns_loopback,
    msg_not_available,
)
from ipbuilding_debug.redact import collect_tokens, redact_payload, redact_text
from ipbuilding_debug.session import GatewaySession

RAW_SEND_PATH = "/api/v1/debug/raw-send"
SHARING_WARNING = (
    "Namen, adressen en apparaat-ids zijn weggehaald. "
    "Deel dit verslag pas nadat je het zelf hebt nagelezen."
)
RAW_LOCAL_WARNING = (
    "Ruwe sessie, alleen om lokaal te kijken. "
    "Er staan adressen en namen in. Deel deze tekst niet."
)

# Relay and dimmer ``channel`` is the wire digit (0-7). Buttons keep the
# module's own index and are not renumbered.
CHANNEL_NUMBERING = (
    "Relay- en dimmerkanalen tellen vanaf 0: het eerste kanaal is 0, "
    "hetzelfde cijfer als op de veldbus (0 tot en met 7). "
    "Een knop toont de index die de module zelf meldt; dat nummer wordt niet omgenummerd."
)

COMMAND_WARNING = (
    "De gateway geeft ok: true zodra het commando is verstuurd, "
    "ook als de module niet antwoordt. "
    "Dat bewijst niet dat de lamp veranderde. "
    "Kijk fysiek, of later via frames. Er is geen ruw pakket verstuurd."
)

DEVICE_ACTIONS = ("ON", "OFF", "PULSE", "TOGGLE", "DIM", "DIM_START", "DIM_STOP")

BUFFER_EVENT_TYPES = (
    "state_changed",
    "button_event",
    "device_added",
    "device_removed",
    "device_ip_changed",
    "device_firmware_changed",
)

_ADDRESS_LABELS = {
    "config_default": "standaardadres uit de bundel (homeassistant.local)",
    "manual": "handmatig ingevuld",
    "mdns": "adres uit mDNS",
    "mdns_hostname": "hostnaam uit mDNS",
}

# Tools that stay registered, and the capability they need before they can run.
GATED_TOOLS = (
    ("read_logs", "log_stream"),
    ("capture_frames", "udp_frame"),
    ("send_raw", "raw_send"),
)

_LOG_RANK = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}


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


REASON_UNSUPPORTED = "Deze gateway-versie kan dit nog niet."
REASON_SWITCH_OFF = (
    f"De schakelaar '{SWITCH_NAME}' staat uit. "
    "Dit werkt pas als die aan staat."
)
REASON_SWITCH_OFF_LOGS = (
    f"De schakelaar '{SWITCH_NAME}' staat uit. "
    "Logregels komen dan niet binnen. Knoppen en statuswijzigingen blijven wel binnenkomen."
)
REASON_UNKNOWN = "De gateway meldt niet of dit nu werkt."
REASON_UNREACHABLE = "De gateway is niet bereikbaar, dus dit is niet te controleren."

# A timestamp the gateway put on the event itself. Device fields such as
# last_seen describe the module, not the moment this event was emitted.
_GATEWAY_TIME_KEYS = ("ts", "timestamp", "time")


def _capabilities(status: dict[str, Any] | None) -> list[str]:
    return [
        name
        for name, record in _capability_records(status).items()
        if record.get("supported", True)
    ]


def _capability_records(status: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """What ``/status.capabilities`` actually says, per name.

    A string means the version supports it. An object may also carry
    ``supported`` and ``active`` when the gateway sends them.
    """
    if not isinstance(status, dict):
        return {}
    caps = status.get("capabilities")
    if not isinstance(caps, list):
        return {}
    records: dict[str, dict[str, Any]] = {}
    for item in caps:
        if isinstance(item, str) and item:
            records[item] = {"supported": True}
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("id")
        if not isinstance(name, str) or not name:
            continue
        record: dict[str, Any] = {"supported": True}
        if isinstance(item.get("supported"), bool):
            record["supported"] = item["supported"]
        if isinstance(item.get("active"), bool):
            record["active"] = item["active"]
        if isinstance(item.get("reason"), str) and item["reason"].strip():
            record["reason"] = item["reason"].strip()
        records[name] = record
    return records


def _feature_rows(
    status: dict[str, Any] | None,
    *,
    remote: bool | None,
    probed: bool | None,
    reachable: bool,
) -> list[dict[str, Any]]:
    """``supported`` is the gateway version. ``active`` means it works now."""
    records = _capability_records(status)
    rows: list[dict[str, Any]] = []
    for name in PLANNED_CAPABILITIES:
        record = records.get(name, {})
        supported = bool(record.get("supported", False))
        if not reachable:
            rows.append(
                {
                    "name": name,
                    "supported": False,
                    "active": False,
                    "reason": REASON_UNREACHABLE,
                }
            )
            continue
        if not supported:
            rows.append(
                {
                    "name": name,
                    "supported": False,
                    "active": False,
                    "reason": REASON_UNSUPPORTED,
                }
            )
            continue
        if isinstance(record.get("active"), bool):
            active = bool(record["active"])
            reason = str(record.get("reason") or "")
            if not active and not reason:
                reason = _inactive_reason(name)
            rows.append(
                {
                    "name": name,
                    "supported": True,
                    "active": active,
                    "reason": reason if not active else "",
                }
            )
            continue
        if remote is True or probed is True:
            rows.append({"name": name, "supported": True, "active": True, "reason": ""})
            continue
        if remote is False or probed is False:
            rows.append(
                {
                    "name": name,
                    "supported": True,
                    "active": False,
                    "reason": _inactive_reason(name),
                }
            )
            continue
        rows.append(
            {
                "name": name,
                "supported": True,
                "active": False,
                "reason": REASON_UNKNOWN,
            }
        )
    return rows


def _inactive_reason(name: str) -> str:
    if name == "log_stream":
        return REASON_SWITCH_OFF_LOGS
    return REASON_SWITCH_OFF


def _needs_switch_probe(status: dict[str, Any] | None, remote: bool | None) -> bool:
    """Probe only when a supported feature has no reported on/off state."""
    if isinstance(remote, bool):
        return False
    records = _capability_records(status)
    for name in PLANNED_CAPABILITIES:
        record = records.get(name)
        if not record or not record.get("supported", False):
            continue
        if isinstance(record.get("active"), bool):
            continue
        return True
    return False


async def connection_status(
    session: GatewaySession,
    *,
    log_level: str | None = None,
) -> ToolResult:
    """Reachability, health, capabilities, and where the address came from."""
    error = await session.refresh_status()
    status = session.status if error is None else None
    where = _endpoint(session)
    if error is not None and error.kind in (KIND_UNREACHABLE, KIND_NO_ADDRESS):
        message = error.message
        if session.mdns_loopback:
            message = msg_mdns_loopback(loopback=session.mdns_loopback, tried=session.tried)
        blocked = unavailable_tools([], None)
        return ToolResult(
            message,
            {
                "ok": False,
                "connected": False,
                "kind": error.kind,
                "connection": session.state,
                "buffer": _buffer_summary(session),
                "missing_capabilities": list(PLANNED_CAPABILITIES),
                "capability_status": _feature_rows(
                    None, remote=None, probed=None, reachable=False
                ),
                "unavailable_tools": blocked,
                "log_level": session.log_level_status(),
                **where,
            },
        )
    if error is not None and status is None:
        return _from_error(
            error,
            connected=False,
            connection=session.state,
            buffer=_buffer_summary(session),
            **where,
        )

    remote = status.get("remote_debugging") if isinstance(status, dict) else None
    if not isinstance(remote, bool):
        remote = None
    status_dict = status if isinstance(status, dict) else None
    probed: bool | None = None
    if _needs_switch_probe(status_dict, remote):
        probed = await session.probe_remote_debugging()
    effective = remote if isinstance(remote, bool) else probed
    caps = _capabilities(status_dict)
    features = _feature_rows(
        status_dict, remote=remote, probed=probed, reachable=True
    )
    missing = [row["name"] for row in features if not row["supported"]]
    message, kind = _connected_message(
        remote=effective, capabilities=caps, missing=missing
    )
    # The gateway answered. ``ok`` stays false only when the debug switch
    # itself is off, not merely because a capability is absent.
    ok = effective is not False
    log_note = ""
    if log_level:
        gated = gate_feature(status_dict, "log_stream")
        if gated is None and effective is False:
            gated = gate_feature(
                {"remote_debugging": False, "capabilities": caps},
                "log_stream",
            )
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
            elif outcome == "applied" and session.log_level_info:
                log_note = msg_log_level_applied(session.log_level_info)
                message = f"{message} {log_note}"
            else:
                log_note = "Logniveau gevraagd."
        else:
            log_note = gated.message
    blocked = unavailable_tools(caps, effective)
    note = _unavailable_note(blocked)
    if note and message not in (MSG_REMOTE_DEBUGGING_OFF, MSG_LOG_LEVEL_RATE_LIMITED):
        message = f"{message} {note}"
    return ToolResult(
        message,
        {
            "ok": ok,
            "connected": True,
            "kind": kind,
            "connection": session.state,
            "version": (status or {}).get("version"),
            "remote_debugging": remote,
            "capabilities": caps,
            "missing_capabilities": missing,
            "capability_status": features,
            "switch_active": effective,
            "hub_role": (status or {}).get("hub_role"),
            "health": _health_view(status if isinstance(status, dict) else None),
            "buffer": _buffer_summary(session),
            "log_level_note": log_note,
            "log_level": session.log_level_status(),
            "unavailable_tools": blocked,
            **where,
        },
    )


async def gateway_health(session: GatewaySession) -> ToolResult:
    """Health, subsystems, issues, uptime, and the local buffer from /status."""
    error = await session.refresh_status()
    if error is not None and error.kind in (KIND_UNREACHABLE, KIND_NO_ADDRESS):
        return _from_error(error, connected=False, **_endpoint(session))
    if error is not None and session.status is None:
        return _from_error(error, connected=False, **_endpoint(session))
    status = session.status or {}
    health = _health_view(status)
    issues = health.get("issues") if isinstance(health.get("issues"), list) else []
    uptime = health.get("uptime_seconds")
    uptime_text = f" Looptijd {uptime} seconden." if isinstance(uptime, int) else ""
    state = health.get("status") or "onbekend"
    message = (
        f"Gateway-status: {state}.{uptime_text} "
        f"{len(issues)} openstaande melding(en)."
    )
    return ToolResult(
        message,
        {
            "ok": True,
            "connected": True,
            "kind": "health",
            "health": health,
            "buffer": _buffer_summary(session),
            **_endpoint(session),
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


async def list_devices(session: GatewaySession) -> ToolResult:
    """Channel inventory from GET /modules and GET /devices."""
    error = await session.refresh_status()
    if error is not None and error.kind in (KIND_UNREACHABLE, KIND_NO_ADDRESS):
        return _from_error(error, connected=False)
    modules_body, modules_error = await session.get_json("/api/v1/modules")
    devices_body, devices_error = await session.get_json(
        "/api/v1/devices?include_inactive=true"
    )
    if modules_error is not None and modules_error.kind == KIND_UNREACHABLE:
        return _from_error(modules_error)
    if devices_error is not None and devices_error.kind == KIND_UNREACHABLE:
        return _from_error(devices_error)
    modules = _list_of(modules_body, "modules")
    devices = _list_of(devices_body, "devices")
    by_module = {str(module.get("id")): module for module in modules if module.get("id")}
    rows = [_device_row(device, by_module) for device in devices]
    lines = [_device_line(row) for row in rows]
    if not lines:
        lines.append("De gateway heeft geen kanalen teruggegeven.")
    message = " ".join(lines) + " " + CHANNEL_NUMBERING
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "devices",
            "channel_numbering": CHANNEL_NUMBERING,
            "devices": rows,
            "modules": [_module_reachability(module) for module in modules],
            "modules_error": modules_error.message if modules_error else "",
            "devices_error": devices_error.message if devices_error else "",
        },
    )


async def recent_events(
    session: GatewaySession,
    *,
    limit: int = 50,
) -> ToolResult:
    """State changes and button events already in the local buffer.

    Works without ``udp_frame``. Does not read the add-on log.
    """
    limit = max(1, min(int(limit), 200))
    wanted = set(BUFFER_EVENT_TYPES)
    events = [
        present_event(event)
        for event in session.buffer.snapshot()
        if event.get("type") in wanted
    ][-limit:]
    presses = [
        event
        for event in events
        if event.get("type") == "button_event"
    ]
    changes = [event for event in events if event.get("type") == "state_changed"]
    if not events:
        message = (
            "De buffer heeft nog geen statuswijzigingen of knopgebeurtenissen. "
            "Druk op de knop of verander een lamp, en lees daarna opnieuw."
        )
    else:
        message = (
            f"{len(changes)} statuswijziging(en) en {len(presses)} knopgebeurtenis(sen) "
            "in de buffer (state_changed, button_event: press, single_press, release "
            "en wat de gateway verder stuurde)."
        )
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "events",
            "events": events,
            "buffer": _buffer_summary(session),
        },
    )


async def read_logs(
    session: GatewaySession,
    *,
    seconds: float = 15,
    since: str = "",
    level: str = "info",
    limit: int = 50,
    redact: bool = True,
) -> ToolResult:
    """Live gateway logs. Needs capability ``log_stream``.

    ``seconds`` is how long to wait and, when ``since`` is empty, the lookback.
    ``since`` is an ISO timestamp. ``level`` is the minimum (debug, info, warning, error).
    """
    error = await session.refresh_status()
    if error is not None:
        return _from_error(error, capability="log_stream")
    gated = gate_feature(session.status, "log_stream")
    if gated is not None:
        message = gated.message
        if gated.kind == KIND_NOT_AVAILABLE:
            message = f"{gated.message} {MSG_LOGS_USE_ADDON_TAB}"
        return _from_error(gated, capability="log_stream") if gated.kind != KIND_NOT_AVAILABLE else ToolResult(
            message,
            {"ok": False, "kind": gated.kind, "capability": "log_stream", "lines": []},
        )

    minimum = (level or "info").strip().lower()
    if minimum not in _LOG_RANK:
        return ToolResult(
            "Onbekend logniveau. Gebruik debug, info, warning of error.",
            {"ok": False, "kind": KIND_OTHER, "lines": []},
        )
    seconds = clamp_timeout(seconds if seconds > 0 else 0.1)
    limit = max(1, min(int(limit), 200))
    cursor = await session.ensure_log_subscription(minimum, timeout=3)
    if cursor is None:
        return ToolResult(
            "De gateway antwoordt, maar de live-verbinding staat nog niet. "
            "Probeer het zo meteen opnieuw.",
            {"ok": False, "kind": "connecting", "lines": []},
        )
    lines = await _collect_logs(
        session,
        cursor,
        seconds=seconds,
        since=since,
        minimum=minimum,
        limit=limit,
    )
    if redact:
        lines = _redact_logs(session, lines)
    if not lines:
        message = "Geen logregels in dit venster."
    else:
        message = f"{len(lines)} logregel(s)."
    if not redact:
        message = f"{message} Ruwe tekst, alleen lokaal. Deel deze tekst niet."
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "logs",
            "redacted": redact,
            "level": minimum,
            "seconds": seconds,
            "since": since,
            "lines": lines,
        },
    )


async def discover(session: GatewaySession, *, confirmed: bool = False) -> ToolResult:
    """POST /api/v1/discover after an explicit yes, then diff the inventory."""
    before_modules, before_devices, fetch_error = await _inventory(session)
    if fetch_error is not None:
        return _from_error(fetch_error, sent=False)
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "sent": False,
        "before": _inventory_counts(before_modules, before_devices),
    }
    if not confirmed:
        return ToolResult(
            (
                "Nog niet gestart. Dit vraagt de gateway om te scannen "
                "(POST /api/v1/discover). Nieuwe modules kunnen in de lijst komen. "
                f"Nu: {len(before_modules)} module(s), {len(before_devices)} apparaat/apparaten. "
                "Vraag de tester expliciet of de scan mag. "
                "Roep discover daarna opnieuw aan met confirmed=true."
            ),
            preview,
        )
    body, call_error = await session.post_json(
        "/api/v1/discover",
        {},
        timeout=120,
    )
    if call_error is not None:
        return _from_error(call_error, **preview)
    after_modules, after_devices, after_error = await _inventory(session)
    if after_error is not None:
        return _from_error(after_error, sent=True, gateway=body if isinstance(body, dict) else {})
    diff = _inventory_diff(before_modules, before_devices, after_modules, after_devices)
    gateway_result = body if isinstance(body, dict) else {}
    message = (
        "Scan uitgevoerd. "
        f"Modules {len(before_modules)} naar {len(after_modules)}. "
        f"Apparaten {len(before_devices)} naar {len(after_devices)}. "
        + _diff_sentence(diff)
    )
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "discover",
            "sent": True,
            "before": _inventory_counts(before_modules, before_devices),
            "after": _inventory_counts(after_modules, after_devices),
            "diff": diff,
            "gateway": {
                key: gateway_result.get(key)
                for key in (
                    "ok",
                    "added",
                    "changed",
                    "firmware_changed",
                    "removed",
                    "skipped_unidentified",
                    "duration_ms",
                    "schema_version",
                )
                if key in gateway_result
            },
        },
    )


async def device_command(
    session: GatewaySession,
    *,
    device_id: str,
    action: str,
    value: int | None = None,
    confirmed: bool = False,
) -> ToolResult:
    """Switch or dim one device via POST /devices/{id}/command."""
    device_id = (device_id or "").strip()
    action_name = (action or "").strip().upper()
    if not device_id:
        return ToolResult(
            "Er is geen apparaat opgegeven. Gebruik het id uit list_devices.",
            {"ok": False, "kind": KIND_OTHER, "sent": False},
        )
    if action_name not in DEVICE_ACTIONS:
        return ToolResult(
            "Onbekende actie. Gebruik ON, OFF, PULSE, TOGGLE, DIM, DIM_START of DIM_STOP.",
            {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
        )
    if action_name == "DIM" and value is None:
        return ToolResult(
            "DIM heeft een waarde nodig van 0 tot en met 100. Nog niet verstuurd.",
            {"ok": False, "kind": "confirmation_required", "sent": False, "action": action_name},
        )
    if value is not None:
        value = int(value)
        if action_name == "DIM" and not 0 <= value <= 100:
            return ToolResult(
                "DIM-waarde moet tussen 0 en 100 liggen. Nog niet verstuurd.",
                {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
            )
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "sent": False,
        "device_id": device_id,
        "action": action_name,
        "value": value,
    }
    if not confirmed:
        level = f" naar {value}" if value is not None else ""
        return ToolResult(
            (
                f"Nog niet verstuurd. Dit zet apparaat {device_id} op {action_name}{level} "
                "via het gewone commando van de gateway. "
                "Een lamp kan aan, uit of anders van helderheid gaan. "
                "Vraag de tester expliciet of dit mag. "
                "Roep device_command daarna opnieuw aan met confirmed=true. "
                + COMMAND_WARNING
            ),
            preview,
        )
    path = f"/api/v1/devices/{quote(device_id, safe='')}/command"
    payload: dict[str, Any] = {"action": action_name}
    if value is not None:
        payload["value"] = value
    body, call_error = await session.post_json(path, payload)
    if call_error is not None:
        return _from_error(call_error, **preview)
    gateway_ok = isinstance(body, dict) and body.get("ok") is True
    return ToolResult(
        COMMAND_WARNING,
        {
            "ok": gateway_ok,
            "kind": "command",
            "sent": True,
            "device_id": device_id,
            "action": action_name,
            "value": value,
            "warning": COMMAND_WARNING,
            "gateway": body if isinstance(body, dict) else {},
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
    decoded = present_decode(decode_frame(data))
    if decoded["matched"]:
        names = ", ".join(item["decoder"] for item in decoded["matches"])
        message = f"Het frame past bij: {names}."
        cities = [
            str(item.get("name"))
            for item in decoded.get("dialects") or []
            if item.get("name")
        ]
        if cities:
            message = f"{message} Dialect: {', '.join(cities)}."
    else:
        message = "Geen enkele decoder herkent dit frame."
    return ToolResult(message, {"ok": True, "kind": "decode", **decoded})


def _parse_gateway_time(event: dict[str, Any]) -> datetime | None:
    for key in _GATEWAY_TIME_KEYS:
        parsed = _parse_log_ts(event.get(key))
        if parsed is not None:
            return parsed
    return None


def _format_local(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().isoformat(timespec="seconds")


def _stamp_event(event: dict[str, Any], received_at: datetime) -> dict[str, Any]:
    """Local ISO time with offset, plus whether the clock was the gateway's."""
    item = present_event(event)
    gateway_time = _parse_gateway_time(item)
    if gateway_time is not None:
        item["local_time"] = _format_local(gateway_time)
        item["time_source"] = "gateway"
    else:
        item["local_time"] = _format_local(received_at)
        item["time_source"] = "received"
    return item


def _stamp_note(note: dict[str, Any]) -> dict[str, Any]:
    item = dict(note)
    parsed = _parse_log_ts(item.get("at"))
    item["local_time"] = _format_local(parsed or datetime.now().astimezone())
    item["time_source"] = "received"
    return item


async def export_session(
    session: GatewaySession,
    *,
    note: str = "",
    marker: str = "",
    redact: bool = True,
) -> ToolResult:
    """Bundle the session. Names and addresses are removed unless redact is false."""
    if note or marker:
        await session.annotate(note or marker, marker=marker)
    exported = [
        _stamp_event(entry.event, entry.received_at)
        for entry in session.buffer.entries()
        if entry.event.get("type")
        in {
            "gap",
            "note",
            "udp_frame",
            "log",
            "log_dropped",
            "state_changed",
            "button_event",
            "device_added",
            "device_removed",
            "device_ip_changed",
            "device_firmware_changed",
        }
    ]
    status = session.status or {}
    body: dict[str, Any] = {
        "gateway": {
            "version": status.get("version"),
            "remote_debugging": status.get("remote_debugging"),
            "capabilities": _capabilities(status),
            "connection": session.state,
            "address": session.host,
        },
        "notes": [_stamp_note(note) for note in session.notes],
        "gaps": [event for event in exported if event.get("type") == "gap"],
        "events": exported[-500:],
        "buffer": _buffer_summary(session),
    }
    if redact:
        body = redact_payload(body)
        message = "Sessie gebundeld. " + SHARING_WARNING
        sharing = SHARING_WARNING
    else:
        message = RAW_LOCAL_WARNING
        sharing = RAW_LOCAL_WARNING
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "export",
            "redacted": redact,
            "sharing": sharing,
            **body,
        },
    )


def unavailable_tools(
    capabilities: list[str], remote: bool | None
) -> list[dict[str, Any]]:
    """Why a still-registered tool cannot run on this gateway."""
    blocked: list[dict[str, Any]] = []
    for tool, capability in GATED_TOOLS:
        if capability not in capabilities:
            blocked.append(
                {
                    "tool": tool,
                    "available": False,
                    "missing": capability,
                    "reason": (
                        f"{tool} is niet te gebruiken: capability {capability} ontbreekt "
                        "in deze gateway-versie."
                    ),
                }
            )
        elif remote is False:
            blocked.append(
                {
                    "tool": tool,
                    "available": False,
                    "missing": "remote_debugging",
                    "reason": (
                        f"{tool} is niet te gebruiken: de schakelaar "
                        f"{SWITCH_NAME} staat uit."
                    ),
                }
            )
    return blocked


def _unavailable_note(items: list[dict[str, Any]]) -> str:
    return " ".join(str(item.get("reason") or "") for item in items if item.get("reason"))


def _endpoint(session: GatewaySession) -> dict[str, Any]:
    return {
        "address": session.host,
        "port": session.port,
        "address_source": session.address_source,
        "address_source_label": _ADDRESS_LABELS.get(
            session.address_source, session.address_source
        ),
        "tried": list(session.tried),
        "mdns_loopback": list(session.mdns_loopback),
    }


def _connected_message(
    *,
    remote: bool | None,
    capabilities: list[str],
    missing: list[str],
) -> tuple[str, str]:
    if remote is False:
        return MSG_REMOTE_DEBUGGING_OFF, "remote_debugging_off"
    if missing and len(missing) == len(PLANNED_CAPABILITIES):
        return MSG_GATEWAY_TOO_OLD, "missing_capabilities"
    if remote is None:
        return msg_connected(remote_debugging=None, capabilities=capabilities), "connected"
    return msg_connected(remote_debugging=remote, capabilities=capabilities), "connected"


def _health_view(status: dict[str, Any] | None) -> dict[str, Any]:
    """Fields GET /api/v1/status actually carries. Absent keys stay absent."""
    if not isinstance(status, dict):
        return {}
    view: dict[str, Any] = {}
    for key in ("status", "uptime_seconds", "updated_at", "subsystems", "issues", "version"):
        if key in status:
            view[key] = status[key]
    return view


def _device_row(device: dict[str, Any], modules: dict[str, dict[str, Any]]) -> dict[str, Any]:
    module_id = device.get("module_id")
    module = modules.get(str(module_id), {}) if module_id else {}
    row: dict[str, Any] = {
        "id": device.get("id"),
        "module_id": module_id,
        "module_name": module.get("name"),
        "module_type": module.get("type"),
        "channel": device.get("channel"),
        "device_type": device.get("device_type"),
        "name": device.get("name"),
        "state": device.get("state") if "state" in device else None,
        "active": device.get("active"),
    }
    if "level" in device:
        row["level"] = device["level"]
    if "semantic_type" in device:
        row["semantic_type"] = device["semantic_type"]
    if "last_seen" in module:
        row["last_seen"] = module["last_seen"]
    else:
        row["last_seen"] = None
    if "last_seen_source" in module:
        row["last_seen_source"] = module["last_seen_source"]
    if "state" not in device:
        row["state_note"] = "geen status; knoppen geven alleen gebeurtenissen"
    return row


def _device_line(row: dict[str, Any]) -> str:
    state = row["state"] if row.get("state") is not None else "geen status"
    seen = ""
    if row.get("last_seen"):
        source = row.get("last_seen_source") or "onbekend"
        seen = f" last_seen {row['last_seen']} ({source})"
    elif row.get("last_seen") is None:
        seen = " last_seen niet gemeld"
    return (
        f"{row.get('module_name') or row.get('module_id') or 'module'} "
        f"kanaal {row.get('channel')} "
        f"{row.get('device_type') or 'onbekend'} "
        f"{row.get('name') or row.get('id') or 'zonder naam'} "
        f"status {state}{seen}."
    )


def _module_reachability(module: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": module.get("id"),
        "type": module.get("type"),
        "model": module.get("model"),
        "name": module.get("name"),
    }
    if "firmware" in module:
        entry["firmware"] = module["firmware"]
    if "last_seen" in module:
        entry["last_seen"] = module["last_seen"]
    else:
        entry["last_seen"] = None
        entry["last_seen_note"] = "de gateway meldt geen last_seen voor deze module"
    if "last_seen_source" in module:
        entry["last_seen_source"] = module["last_seen_source"]
    return entry


async def _inventory(
    session: GatewaySession,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ClassifiedError | None]:
    modules_body, modules_error = await session.get_json("/api/v1/modules")
    if modules_error is not None and modules_error.kind == KIND_UNREACHABLE:
        return [], [], modules_error
    devices_body, devices_error = await session.get_json("/api/v1/devices?include_inactive=true")
    if devices_error is not None and devices_error.kind == KIND_UNREACHABLE:
        return [], [], devices_error
    error = modules_error or devices_error
    return _list_of(modules_body, "modules"), _list_of(devices_body, "devices"), error


def _ids(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("id")) for item in items if item.get("id")]


def _inventory_counts(
    modules: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "modules": len(modules),
        "devices": len(devices),
        "module_ids": _ids(modules),
        "device_ids": _ids(devices),
    }


def _inventory_diff(
    before_modules: list[dict[str, Any]],
    before_devices: list[dict[str, Any]],
    after_modules: list[dict[str, Any]],
    after_devices: list[dict[str, Any]],
) -> dict[str, list[str]]:
    def added(before: list[str], after: list[str]) -> list[str]:
        known = set(before)
        return [item for item in after if item not in known]

    def removed(before: list[str], after: list[str]) -> list[str]:
        kept = set(after)
        return [item for item in before if item not in kept]

    before_m, after_m = _ids(before_modules), _ids(after_modules)
    before_d, after_d = _ids(before_devices), _ids(after_devices)
    return {
        "modules_added": added(before_m, after_m),
        "modules_removed": removed(before_m, after_m),
        "devices_added": added(before_d, after_d),
        "devices_removed": removed(before_d, after_d),
    }


def _diff_sentence(diff: dict[str, list[str]]) -> str:
    parts = []
    for label, key in (
        ("nieuwe modules", "modules_added"),
        ("verdwenen modules", "modules_removed"),
        ("nieuwe apparaten", "devices_added"),
        ("verdwenen apparaten", "devices_removed"),
    ):
        values = diff.get(key) or []
        if values:
            parts.append(f"{label}: {', '.join(values)}")
    if not parts:
        return "Geen verschil in de lijst."
    return " ".join(parts) + "."


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


def _log_rank(level: str) -> int:
    return _LOG_RANK.get((level or "").lower(), _LOG_RANK["info"])


def _parse_log_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _log_in_window(event: dict[str, Any], start: datetime | None) -> bool:
    if start is None:
        return True
    moment = _parse_log_ts(event.get("ts"))
    if moment is None:
        return True
    return moment >= start


def _inventory_tokens(session: GatewaySession) -> set[str]:
    blob: dict[str, Any] = {
        "devices": list(session.devices.values()),
        "modules": list(session.modules.values()),
    }
    return collect_tokens(blob)


def _redact_logs(
    session: GatewaySession, lines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    tokens = _inventory_tokens(session) | collect_tokens(lines)
    cleaned: list[dict[str, Any]] = []
    for line in lines:
        item = dict(line)
        message = item.get("message")
        if isinstance(message, str):
            item["message"] = redact_text(message, tokens)
        cleaned.append(item)
    return cleaned


async def _collect_logs(
    session: GatewaySession,
    since_seq: int,
    *,
    seconds: float,
    since: str,
    minimum: str,
    limit: int,
) -> list[dict[str, Any]]:
    start = _parse_log_ts(since) if since else None
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    floor = _log_rank(minimum)

    def matching(event: dict[str, Any]) -> bool:
        if event.get("type") != "log":
            return False
        if _log_rank(str(event.get("level") or "")) < floor:
            return False
        return _log_in_window(event, start)

    def gathered() -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for entry in session.buffer.since(since_seq, types={"log"}):
            if not matching(entry.event):
                continue
            found.append(dict(entry.event))
            if len(found) >= limit:
                break
        return found

    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    watched = since_seq
    while True:
        lines = gathered()
        if len(lines) >= limit:
            return lines
        remaining = deadline - loop.time()
        if remaining <= 0:
            return lines
        nxt = await session.buffer.wait_until(matching, remaining, watched)
        if nxt is None:
            return gathered()
        watched = nxt.seq


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
