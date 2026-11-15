"""Toolkit tools. Each returns a message a tester can act on."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ipbuilding_debug.buffer import clamp_timeout
from ipbuilding_debug.calibration import (
    DEFAULT_HOLD_SECONDS,
    DEFAULT_SWEEP_STEPS,
    DEFAULT_SYNC_OFF_SECONDS,
    DEFAULT_SYNC_ON_SECONDS,
    analyze_luma_series,
    extract_video_luma_async,
    fetch_module_dimmer_statuses,
    format_uitgang,
    parse_steps,
    save_module_dimmer_channel,
)
from ipbuilding_debug.decode import decode_frame, parse_frame
from ipbuilding_debug.dialect import (
    dialect_name,
    full_dialect_id,
    present_decode,
    present_event,
)
from ipbuilding_debug.errors import (
    KIND_NOT_AVAILABLE,
    KIND_NO_ADDRESS,
    KIND_REMOTE_DEBUGGING_OFF,
    KIND_OTHER,
    KIND_UNREACHABLE,
    MSG_GATEWAY_TOO_OLD,
    MSG_LOGS_USE_ADDON_TAB,
    MSG_LOG_LEVEL_NOT_REPORTED,
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_NOT_IN_THIS_GATEWAY_VERSION,
    MSG_REMOTE_DEBUGGING_OFF,
    SWITCH_NAME,
    SWITCH_NAME_NL,
    PLANNED_CAPABILITIES,
    ClassifiedError,
    gate_feature,
    msg_connected,
    msg_log_level_applied,
    msg_mdns_loopback,
    msg_not_available,
)
from ipbuilding_debug.installation_id import installation_id
from ipbuilding_debug.redact import (
    collect_display_names,
    collect_tokens,
    name_masks,
    redact_payload,
    redact_text,
    session_hosts,
)
from ipbuilding_debug.report import (
    disabled_message,
    email_body,
    intake_address,
    limit_export_events,
    mailto_link,
    offer_sentence,
    preview_message,
    render_report,
    report_send_enabled,
    section_map,
    sent_message,
    subject_line,
    unavailable_message,
)
from ipbuilding_debug.session import GatewaySession

RAW_SEND_PATH = "/api/v1/debug/raw-send"
_RAW_ERROR_TEXT = {
    "remote_debugging_disabled": (
        'Zet in de gateway "Bediening op afstand (voor debuggen)" aan.'
    ),
    "target_not_allowed": "Dit adres hoort niet bij een module van deze installatie.",
    "invalid_target": "Dit is geen geldig module-adres.",
    "invalid_port": "De poort moet 1001 zijn.",
    "payload_too_large": "Het pakket is te groot. Het maximum is 64 bytes.",
    "raw_send_rate_limited": (
        "Er zijn te veel testpakketten verstuurd. Wacht even en probeer het opnieuw."
    ),
    "raw_send_busy": "Er loopt nog een testpakket. Wacht tot dat venster klaar is.",
    "send_failed": "De gateway kon het pakket niet versturen.",
    "invalid_payload": "Dit pakket is niet geldig. Gebruik 1 tot 64 bytes hex.",
    "invalid_window": "Het venster moet tussen 1 en 3000 milliseconden liggen.",
    "invalid_json": "De gateway begreep het verzoek niet.",
}
SHARING_WARNING = (
    "Ruimte-, lamp- en knopnamen zijn gemaskeerd. "
    "Adressen en apparaat-ids zijn weggehaald. "
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
    "Vraag op het moment van schakelen wat de tester ziet, "
    "bijvoorbeeld of het traag reageerde. "
    "Er is geen ruw pakket verstuurd."
)

DEVICE_ACTIONS = ("ON", "OFF", "PULSE", "TOGGLE", "DIM", "DIM_START", "DIM_STOP")
RELAY_ACTIONS = frozenset({"ON", "OFF", "PULSE", "TOGGLE"})
DIMMER_ACTIONS = frozenset({"DIM", "TOGGLE", "DIM_START", "DIM_STOP"})
_DEVICE_KINDS = frozenset({"relay", "dimmer", "input"})

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
    f"De schakelaar '{SWITCH_NAME}' staat uit "
    f"(Nederlands: '{SWITCH_NAME_NL}'). "
    "Dit werkt pas als die aan staat."
)
REASON_SWITCH_OFF_LOGS = (
    f"De schakelaar '{SWITCH_NAME}' staat uit "
    f"(Nederlands: '{SWITCH_NAME_NL}'). "
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
                "connection": session.event_stream_state(),
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
            connection=session.event_stream_state(),
            buffer=_buffer_summary(session),
            **where,
        )

    # Let the snapshot land so connection matches the activiteitenlog.
    await session.wait_until_connected(2)
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
    if (
        not log_note
        and "log_stream" in caps
        and message not in (MSG_REMOTE_DEBUGGING_OFF, MSG_LOG_LEVEL_RATE_LIMITED)
    ):
        if session.log_level_status().get("reported") and session.log_level_info:
            level_sentence = msg_log_level_applied(session.log_level_info)
        else:
            level_sentence = MSG_LOG_LEVEL_NOT_REPORTED
        message = f"{message} {level_sentence}"
    blocked = unavailable_tools(caps, effective)
    note = _unavailable_note(blocked)
    if note and message not in (MSG_REMOTE_DEBUGGING_OFF, MSG_LOG_LEVEL_RATE_LIMITED):
        message = f"{message} {note}"
    live = session.event_stream_state()
    if live != "connected" and kind == "connected":
        kind = "connecting"
        message = f"{message} {_CONNECTION_WAIT}"
    return ToolResult(
        message,
        {
            "ok": ok,
            "connected": True,
            "kind": kind,
            "connection": live,
            "connection_note": _connection_note(live),
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
    """Health, subsystems, issues, uptime, and the activiteitenlog from /status."""
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
    await session.buffer.append(
        {
            "type": "decode_result",
            "received_at": _format_local(datetime.now().astimezone()),
            "matched": False,
            "source": "probe_generation",
            "message": dialect,
        }
    )
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
    # Remember names and rooms so a later report can redact them, including
    # text that never came back through the WebSocket snapshot.
    session.devices = {
        str(device.get("id")): device
        for device in devices
        if device.get("id") is not None
    }
    session.modules = {
        str(module.get("id")): module
        for module in modules
        if module.get("id") is not None
    }
    module_rows = [_module_reachability(module) for module in modules]
    timing = " ".join(
        str(row.get("reachability_sentence") or "")
        for row in module_rows
        if row.get("reachability_sentence")
    )
    message = " ".join(lines) + " " + CHANNEL_NUMBERING
    if timing:
        message = f"{message} {timing}"
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "devices",
            "channel_numbering": CHANNEL_NUMBERING,
            "devices": rows,
            "modules": module_rows,
            "modules_error": modules_error.message if modules_error else "",
            "devices_error": devices_error.message if devices_error else "",
        },
    )


async def recent_events(
    session: GatewaySession,
    *,
    limit: int = 50,
) -> ToolResult:
    """State changes and button events already in the activiteitenlog.

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
            "Het activiteitenlog heeft nog geen statuswijzigingen of knopgebeurtenissen. "
            "Druk op de knop of verander een lamp, en lees daarna opnieuw."
        )
    else:
        message = (
            f"{len(changes)} statuswijziging(en) en {len(presses)} knopgebeurtenis(sen) "
            "in het activiteitenlog (state_changed, button_event: press, single_press, release "
            "en wat de gateway verder stuurde)."
        )
    live = session.event_stream_state()
    if events and live == "connecting":
        message = f"{message} {_CONNECTION_WAIT}"
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "events",
            "connection": live,
            "connection_note": _connection_note(live),
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


def _device_kind(session: GatewaySession, device: dict[str, Any]) -> str:
    """relay, dimmer, or input from the device, else from its module."""
    raw = str(device.get("device_type") or "").strip().lower()
    if raw in _DEVICE_KINDS:
        return raw
    module_id = device.get("module_id")
    module = session.modules.get(str(module_id), {}) if module_id else {}
    if isinstance(module, dict):
        raw = str(module.get("type") or "").strip().lower()
        if raw in _DEVICE_KINDS:
            return raw
    return ""


async def _load_device(
    session: GatewaySession, device_id: str
) -> tuple[dict[str, Any] | None, ToolResult | None]:
    """Device from the session, or from list_devices when that id is missing."""
    current = session.devices.get(device_id)
    if isinstance(current, dict):
        return current, None
    loaded = await list_devices(session)
    current = session.devices.get(device_id)
    if isinstance(current, dict):
        return current, None
    if loaded.data.get("ok") is not True:
        return None, loaded
    return None, None


def _prepare_device_action(
    kind: str, action_name: str, value: int | None
) -> tuple[str, int | None, str] | ToolResult:
    """Map a request onto the actions the gateway accepts for this type.

    A dimmer accepts DIM 0-100, TOGGLE, DIM_START, and DIM_STOP. ON becomes
    DIM 100 and OFF becomes DIM 0. PULSE is refused. A relay accepts ON, OFF,
    PULSE, and TOGGLE.
    """
    if kind == "dimmer":
        note = ""
        if action_name == "ON":
            action_name, value = "DIM", 100
            note = "ON op een dimmer wordt DIM 100."
        elif action_name == "OFF":
            action_name, value = "DIM", 0
            note = "OFF op een dimmer wordt DIM 0."
        elif action_name == "PULSE":
            return ToolResult(
                "PULSE werkt niet op een dimmer. "
                "Een dimmer neemt DIM met een waarde van 0 tot 100, TOGGLE, "
                "DIM_START of DIM_STOP. Nog niet verstuurd.",
                {"ok": False, "kind": KIND_OTHER, "sent": False, "action": "PULSE"},
            )
        elif action_name not in DIMMER_ACTIONS:
            return ToolResult(
                "Deze actie werkt niet op een dimmer. "
                "Gebruik DIM (0 tot 100), TOGGLE, DIM_START of DIM_STOP. "
                "Nog niet verstuurd.",
                {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
            )
        if action_name == "DIM" and value is None:
            return ToolResult(
                "DIM heeft een waarde nodig van 0 tot en met 100. Nog niet verstuurd.",
                {
                    "ok": False,
                    "kind": "confirmation_required",
                    "sent": False,
                    "action": action_name,
                },
            )
        if action_name == "DIM" and not 0 <= int(value) <= 100:
            return ToolResult(
                "DIM-waarde moet tussen 0 en 100 liggen. Nog niet verstuurd.",
                {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
            )
        return action_name, value, note
    if kind == "relay":
        if action_name not in RELAY_ACTIONS:
            return ToolResult(
                "Deze actie werkt niet op een relais. "
                "Gebruik ON, OFF, PULSE of TOGGLE. Nog niet verstuurd.",
                {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
            )
        return action_name, value, ""
    if kind == "input":
        return ToolResult(
            "Een input of knop neemt geen schakelcommando. Nog niet verstuurd.",
            {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
        )
    return ToolResult(
        "Het type van dit apparaat is niet bekend. "
        "Roep list_devices aan en gebruik het id en het type daaruit. "
        "Nog niet verstuurd.",
        {"ok": False, "kind": KIND_OTHER, "sent": False, "action": action_name},
    )


# Dimmer actions after which the tool reads the level back from the module.
_READBACK_ACTIONS = {"DIM", "TOGGLE", "DIM_STOP"}
# Pause before the read-back so the module has taken the command. Tests set 0.
READBACK_DELAY_S = 0.6
_READBACK_WINDOW_MS = 1500


def _readback_target(device: dict[str, Any]) -> tuple[str, int] | None:
    """Module address and channel 0-7 for a dimmer status read, or None."""
    module_ip = str(device.get("module_id") or "").strip()
    channel = device.get("channel")
    if _raw_module_ip(module_ip) is None:
        return None
    if type(channel) is not int or not 0 <= channel <= 7:
        return None
    return module_ip, channel


def _readback_level(replies: list[Any], channel: int) -> dict[str, Any] | None:
    """The first dimmer status reply for ``channel`` among the raw replies."""
    for reply in replies:
        if not isinstance(reply, dict) or not isinstance(reply.get("hex"), str):
            continue
        decoded = _safe_decode(reply["hex"])
        if not isinstance(decoded, dict):
            continue
        for match in decoded.get("matches") or []:
            if not isinstance(match, dict):
                continue
            fields = match.get("fields") if isinstance(match.get("fields"), dict) else {}
            if fields.get("family") != "dimmer_status_reply":
                continue
            if fields.get("channel") != channel:
                continue
            level = fields.get("level_percent")
            return {
                "level_percent": level if type(level) is int else None,
                "raw": str(fields.get("raw") or decoded.get("ascii") or reply["hex"]),
                "dialect_id": full_dialect_id(str(fields.get("dialect_id") or "")),
            }
    return None


async def _dimmer_readback(
    session: GatewaySession,
    device: dict[str, Any],
    *,
    action: str,
    value: int | None,
) -> dict[str, Any]:
    """Ask the dimmer for the live level of this channel with ``I{ch}000000``.

    This is a read. It changes no output. A module that only echoes the
    command proves it received the frame, not that the lamp moved; this
    read-back is the check. Needs ``raw_send``; without it the result says why.
    """
    target = _readback_target(device)
    if target is None:
        return {
            "available": False,
            "reason": "geen moduleadres of kanaal 0 tot 7 in de inventaris",
        }
    module_ip, channel = target
    error = await session.refresh_status()
    if error is not None:
        return {"available": False, "reason": error.message or error.kind}
    gated = gate_feature(session.status, "raw_send")
    if gated is not None:
        if gated.kind == KIND_REMOTE_DEBUGGING_OFF:
            reason = "de schakelaar Bediening op afstand (voor debuggen) staat uit"
        else:
            reason = "deze gatewayversie kan geen testpakket sturen"
        return {"available": False, "reason": reason}
    if READBACK_DELAY_S > 0:
        await asyncio.sleep(READBACK_DELAY_S)
    query = f"I{channel}000000"
    body, call_error = await session.post_json(
        RAW_SEND_PATH,
        {
            "module_ip": module_ip,
            "port": 1001,
            "payload_hex": query.encode("ascii").hex(),
            "window_ms": _READBACK_WINDOW_MS,
        },
        timeout=max(8.0, _READBACK_WINDOW_MS / 1000 + 3),
    )
    if call_error is not None:
        code = _raw_error_code(body)
        if code == "raw_send_rate_limited":
            reason = "te veel testpakketten in de laatste minuut; probeer zo meteen opnieuw"
        else:
            reason = code or call_error.message or call_error.kind
        return {"available": False, "query": query, "reason": reason}
    replies = body.get("replies") if isinstance(body, dict) else None
    found = _readback_level(replies if isinstance(replies, list) else [], channel)
    result: dict[str, Any] = {
        "available": True,
        "query": query,
        "channel": channel,
        "answered": found is not None,
    }
    expected = value if action == "DIM" else None
    if found is not None:
        result.update(found)
        if expected is not None and found.get("level_percent") is not None:
            result["expected_percent"] = expected
            result["matches_request"] = found["level_percent"] == expected
    return result


def _readback_sentence(readback: dict[str, Any] | None) -> str:
    """One or two sentences for the tool message. Empty when not attempted."""
    if not isinstance(readback, dict):
        return ""
    if not readback.get("available"):
        reason = readback.get("reason") or "onbekende reden"
        return f" Nalezen van de stand lukte niet: {reason}."
    if not readback.get("answered"):
        return (
            " Nalezen: de module gaf geen stand terug op de leesvraag. "
            "Vraag de tester wat de lamp doet."
        )
    level = readback.get("level_percent")
    shown = f"{level}%" if level is not None else "een onbekende stand"
    raw = readback.get("raw") or ""
    if readback.get("matches_request") is False:
        return (
            f" Nalezen: de module meldt nu {shown} ({raw}), niet de gevraagde "
            f"{readback.get('expected_percent')}%. Het commando is waarschijnlijk "
            "niet uitgevoerd. Vraag de tester wat de lamp doet."
        )
    return (
        f" Nalezen: de module meldt nu {shown} ({raw}). Vraag de tester of de "
        "lamp dat ook echt doet; een module kan een stand melden die de lamp niet volgt."
    )


def _is_echo_only_dialect(readback: dict[str, Any] | None) -> bool:
    if not isinstance(readback, dict):
        return False
    return "torhout" in str(readback.get("dialect_id") or "")


async def device_command(
    session: GatewaySession,
    *,
    device_id: str,
    action: str,
    value: int | None = None,
    fade: int | None = None,
    confirmed: bool = False,
    verify: bool = True,
) -> ToolResult:
    """Switch or dim one device via POST /devices/{id}/command.

    The device type comes from list_devices. Dimmers are translated before
    anything is sent: ON becomes DIM 100, OFF becomes DIM 0, and PULSE is refused.
    ``fade`` is optional for DIM, ON, and OFF: omit it or pass 0 for an instant
    change. 1–255 lengthens the ramp. A non-integer or a value outside 0–255
    is rejected. The module reports the end level before the lamp finishes.
    ``verify`` reads the live level back from a dimmer after DIM, TOGGLE, and
    DIM_STOP when ``raw_send`` is active. That read changes nothing.
    """
    device_id = (device_id or "").strip()
    requested = (action or "").strip().upper()
    if not device_id:
        return ToolResult(
            "Er is geen apparaat opgegeven. Gebruik het id uit list_devices.",
            {"ok": False, "kind": KIND_OTHER, "sent": False},
        )
    if requested not in DEVICE_ACTIONS:
        return ToolResult(
            "Onbekende actie. "
            "Een relais neemt ON, OFF, PULSE of TOGGLE. "
            "Een dimmer neemt DIM (0 tot 100), TOGGLE, DIM_START of DIM_STOP.",
            {"ok": False, "kind": KIND_OTHER, "sent": False, "action": requested},
        )
    if value is not None:
        value = int(value)
    device, load_error = await _load_device(session, device_id)
    if device is None:
        if load_error is not None:
            return load_error
        return ToolResult(
            "Dit apparaat staat niet in de inventaris. "
            "Roep list_devices aan en gebruik het id daaruit. Nog niet verstuurd.",
            {"ok": False, "kind": KIND_OTHER, "sent": False, "action": requested},
        )
    prepared = _prepare_device_action(_device_kind(session, device), requested, value)
    if isinstance(prepared, ToolResult):
        prepared.data["device_id"] = device_id
        prepared.data["requested_action"] = requested
        return prepared
    action_name, value, note = prepared
    if action_name == "DIM" and fade is not None:
        if isinstance(fade, bool) or not isinstance(fade, int) or not 0 <= fade <= 255:
            return ToolResult(
                "Fade moet een geheel getal van 0 tot en met 255 zijn. Nog niet verstuurd.",
                {
                    "ok": False,
                    "kind": KIND_OTHER,
                    "sent": False,
                    "device_id": device_id,
                    "action": action_name,
                },
            )
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "sent": False,
        "device_id": device_id,
        "action": action_name,
        "requested_action": requested,
        "value": value,
        "translated": bool(note),
    }
    if action_name == "DIM":
        preview["fade"] = 0 if fade is None else fade
    will_verify = (
        verify
        and _device_kind(session, device) == "dimmer"
        and action_name in _READBACK_ACTIONS
    )
    preview["verify"] = will_verify
    if not confirmed:
        level = f" naar {value}" if value is not None else ""
        lead = f"{note} " if note else ""
        check = (
            "Daarna vraagt de tool de dimmer naar zijn stand. Die leesvraag verandert niets. "
            if will_verify
            else ""
        )
        return ToolResult(
            (
                f"{lead}Nog niet verstuurd. Dit zet apparaat {device_id} op {action_name}{level} "
                "via het commando van de gateway. "
                "Een lamp kan aan, uit of anders van helderheid gaan. "
                f"{check}"
                "Vraag de tester op dat moment wat hij ziet, "
                "bijvoorbeeld of het traag reageerde. "
                "Roep device_command daarna opnieuw aan met confirmed=true. "
                + COMMAND_WARNING
            ),
            preview,
        )
    path = f"/api/v1/devices/{quote(device_id, safe='')}/command"
    payload: dict[str, Any] = {"action": action_name}
    if value is not None:
        payload["value"] = value
    if action_name == "DIM":
        payload["fade"] = 0 if fade is None else fade
    body, call_error = await session.post_json(path, payload)
    if call_error is not None:
        await _record_command_result(
            session,
            device_id=device_id,
            action=action_name,
            value=value,
            ok=False,
            error=call_error.detail or call_error.kind,
            module_confirmed=None,
            confirm_ms=None,
            reported=None,
            confirmation_available=False,
            note=note,
        )
        return _from_error(call_error, **preview)
    gateway_ok = isinstance(body, dict) and body.get("ok") is True
    confirmation = _command_confirmation(body, action_name)
    readback: dict[str, Any] | None = None
    if will_verify and gateway_ok:
        readback = await _dimmer_readback(session, device, action=action_name, value=value)
    await _record_command_result(
        session,
        device_id=device_id,
        action=action_name,
        value=value,
        ok=gateway_ok,
        error="" if gateway_ok else (_raw_error_code(body) or ""),
        module_confirmed=confirmation["module_confirmed"],
        confirm_ms=confirmation["confirm_ms"],
        reported=confirmation["reported"],
        confirmation_available=confirmation["available"],
        note=note,
        readback=readback,
    )
    message = confirmation["message"]
    if confirmation["module_confirmed"] and _is_echo_only_dialect(readback):
        message += (
            " Deze dimmer (Torhout) stuurt het commando alleen terug. "
            "Dat bevestigt dat hij het ontving, niet dat de lamp veranderde."
        )
    message += _readback_sentence(readback)
    if note:
        message = f"{note} {message}"
    result = {
        "ok": gateway_ok,
        "kind": "command",
        "sent": True,
        "device_id": device_id,
        "action": action_name,
        "requested_action": requested,
        "value": value,
        "translated": bool(note),
        "module_confirmed": confirmation["module_confirmed"],
        "confirm_ms": confirmation["confirm_ms"],
        "reported": confirmation["reported"],
        "confirmation_available": confirmation["available"],
        "warning": message,
        "gateway": body if isinstance(body, dict) else {},
        "readback": readback,
    }
    if "fade" in preview:
        result["fade"] = preview["fade"]
    return ToolResult(message, result)


async def _calibrated_sleeper(session: GatewaySession, seconds: float) -> None:
    if seconds <= 0:
        return
    sleeper = getattr(session, "_sleeper", None)
    if callable(sleeper):
        await sleeper(seconds)
    else:
        await asyncio.sleep(seconds)


async def _load_calibration_inventory(
    session: GatewaySession,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ToolResult | None]:
    modules, devices, error = await _inventory(session)
    if error is not None and not devices and not modules:
        return [], [], _from_error(error, mode="calibration")
    session.devices = {
        str(device.get("id")): device
        for device in devices
        if isinstance(device, dict) and device.get("id") is not None
    }
    session.modules = {
        str(module.get("id")): module
        for module in modules
        if isinstance(module, dict) and module.get("id") is not None
    }
    if error is not None and not devices:
        return modules, [], _from_error(error, mode="calibration")
    return modules, devices, None


def _dimmer_module_ip(device: dict[str, Any], modules: dict[str, dict[str, Any]]) -> str:
    direct = str(device.get("module_ip") or "").strip()
    if direct:
        return direct
    mod_id = str(device.get("module_id") or "").strip()
    mod = modules.get(mod_id, {})
    if isinstance(mod, dict):
        ip = str(mod.get("ip") or "").strip()
        if ip:
            return ip
    return mod_id


def _matching_dimmers(
    session: GatewaySession,
    devices: list[dict[str, Any]],
    modules_by_id: dict[str, dict[str, Any]],
    *,
    device_id: str,
    module_ip: str,
    channel: int | None,
) -> tuple[list[dict[str, Any]], ToolResult | None]:
    dimmers = [d for d in devices if isinstance(d, dict) and _device_kind(session, d) == "dimmer"]
    if device_id:
        for dev in devices:
            if str(dev.get("id") or "") == device_id:
                if _device_kind(session, dev) != "dimmer":
                    return [], ToolResult(
                        f"Apparaat {device_id} is geen dimmer maar '{_device_kind(session, dev) or 'onbekend'}'.",
                        {"ok": False, "kind": KIND_OTHER, "device_id": device_id},
                    )
                return [dev], None
        return [], ToolResult(
            f"Apparaat {device_id} staat niet in de inventaris. Roep list_devices aan.",
            {"ok": False, "kind": KIND_OTHER, "device_id": device_id},
        )

    filtered = dimmers
    if module_ip:
        filtered = [
            d
            for d in filtered
            if _dimmer_module_ip(d, modules_by_id) == module_ip
            or str(d.get("module_id") or "").strip() == module_ip
        ]
    if channel is not None:
        filtered = [d for d in filtered if d.get("channel") == channel]

    if (module_ip or channel is not None) and not filtered:
        return [], ToolResult(
            "Geen dimmer gevonden voor die module/kanaal-combinatie. Roep list_devices aan.",
            {
                "ok": False,
                "kind": KIND_OTHER,
                "module_ip": module_ip or None,
                "channel": channel,
            },
        )
    return filtered, None


def _validate_calibration_channel(channel: int | None) -> ToolResult | None:
    if channel is None:
        return None
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 7:
        return ToolResult(
            "Kanaal moet een geheel getal van 0 tot en met 7 zijn.",
            {"ok": False, "kind": KIND_OTHER, "channel": channel},
        )
    return None


def _validate_timing_bounds(
    *,
    hold_seconds: float,
    sync_on_seconds: float,
    sync_off_seconds: float,
    countdown_seconds: float = 0.0,
) -> ToolResult | None:
    for label, val in (
        ("hold_seconds", hold_seconds),
        ("sync_on_seconds", sync_on_seconds),
        ("sync_off_seconds", sync_off_seconds),
    ):
        if (
            isinstance(val, bool)
            or not isinstance(val, (int, float))
            or not math.isfinite(float(val))
            or not 0.5 <= float(val) <= 10.0
        ):
            return ToolResult(
                f"{label} moet tussen 0.5 en 10.0 seconden liggen.",
                {"ok": False, "kind": KIND_OTHER, "parameter": label, "value": val},
            )
    if (
        isinstance(countdown_seconds, bool)
        or not isinstance(countdown_seconds, (int, float))
        or not math.isfinite(float(countdown_seconds))
        or not 0.0 <= float(countdown_seconds) <= 30.0
    ):
        return ToolResult(
            "countdown_seconds moet tussen 0.0 en 30.0 seconden liggen.",
            {"ok": False, "kind": KIND_OTHER, "parameter": "countdown_seconds", "value": countdown_seconds},
        )
    return None


def _module_row_for_channel(rows: list[dict[str, Any]] | None, ch: int) -> dict[str, Any] | None:
    if not rows:
        return None
    for row in rows:
        try:
            if int(row.get("ch")) == ch:
                return row
        except (TypeError, ValueError):
            continue
    if 0 <= ch < len(rows) and isinstance(rows[ch], dict):
        return rows[ch]
    return None


async def _fetch_modules_map(module_ips: set[str]) -> dict[str, tuple[list[dict[str, Any]] | None, str | None]]:
    ips = sorted(ip for ip in module_ips if ip and not any(c.isspace() for c in ip))
    if not ips:
        return {}
    results = await asyncio.gather(
        *(fetch_module_dimmer_statuses(ip) for ip in ips),
        return_exceptions=False,
    )
    return dict(zip(ips, results))


async def calibrate_dimmer(
    session: GatewaySession,
    *,
    mode: str = "status",
    device_id: str = "",
    module_ip: str = "",
    channel: int | None = None,
    steps: str = "",
    hold_seconds: float = DEFAULT_HOLD_SECONDS,
    countdown_seconds: float = 0.0,
    sync_on_seconds: float = DEFAULT_SYNC_ON_SECONDS,
    sync_off_seconds: float = DEFAULT_SYNC_OFF_SECONDS,
    video_path: str = "",
    sweep_log_path: str = "",
    margin_min: int = 1,
    sat_threshold: float = 0.985,
    dim_min: int | None = None,
    dim_max: int | None = None,
    dim_gamma: float | None = None,
    default_fade: int | None = None,
    keep_raw: bool = False,
    confirmed: bool = False,
) -> ToolResult:
    """Calibrate an IP0300PoE dimmer channel (status, sweep, analyze, apply)."""
    norm_mode = (mode or "status").strip().lower()
    if norm_mode not in {"status", "sweep", "analyze", "apply"}:
        return ToolResult(
            "Ongeldige kalibratiemodus. Kies status, sweep, analyze of apply.",
            {"ok": False, "kind": KIND_OTHER, "mode": norm_mode},
        )

    device_id = (device_id or "").strip()
    module_ip = (module_ip or "").strip()
    ch_err = _validate_calibration_channel(channel)
    if ch_err is not None:
        return ch_err

    if norm_mode == "analyze":
        return await _calibrate_analyze(
            session,
            device_id=device_id,
            module_ip=module_ip,
            channel=channel,
            steps=steps,
            hold_seconds=hold_seconds,
            sync_on_seconds=sync_on_seconds,
            sync_off_seconds=sync_off_seconds,
            video_path=video_path,
            sweep_log_path=sweep_log_path,
            margin_min=margin_min,
            sat_threshold=sat_threshold,
        )

    modules, devices, inv_err = await _load_calibration_inventory(session)
    if inv_err is not None:
        return inv_err
    modules_by_id = {
        str(m.get("id")): m for m in modules if isinstance(m, dict) and m.get("id") is not None
    }
    matches, match_err = _matching_dimmers(
        session,
        devices,
        modules_by_id,
        device_id=device_id,
        module_ip=module_ip,
        channel=channel,
    )
    if match_err is not None:
        return match_err

    if norm_mode == "status":
        return await _calibrate_status(matches, modules_by_id)

    if not matches:
        return ToolResult(
            "Geen dimmers gevonden in de gateway-inventaris.",
            {"ok": False, "kind": KIND_OTHER, "mode": norm_mode},
        )
    if len(matches) > 1:
        options = [
            f"{d.get('id')} ({d.get('name') or 'zonder naam'}, kanaal {d.get('channel')})"
            for d in matches
        ]
        return ToolResult(
            "Meerdere dimmers gevonden; geef device_id of module_ip + channel op: "
            + ", ".join(options),
            {"ok": False, "kind": KIND_OTHER, "mode": norm_mode, "candidates": options},
        )

    target = matches[0]
    target_id = str(target.get("id") or "")
    target_ip = _dimmer_module_ip(target, modules_by_id)
    target_ch = target.get("channel")
    if isinstance(target_ch, bool) or not isinstance(target_ch, int) or not 0 <= target_ch <= 7:
        return ToolResult(
            f"Dimmer {target_id} heeft een ongeldig kanaalnummer ({target_ch}).",
            {"ok": False, "kind": KIND_OTHER, "mode": norm_mode, "device_id": target_id},
        )

    if norm_mode == "sweep":
        return await _calibrate_sweep(
            session,
            target=target,
            target_id=target_id,
            module_ip=target_ip,
            channel=target_ch,
            steps=steps,
            hold_seconds=hold_seconds,
            countdown_seconds=countdown_seconds,
            sync_on_seconds=sync_on_seconds,
            sync_off_seconds=sync_off_seconds,
            sweep_log_path=sweep_log_path,
            keep_raw=keep_raw,
            confirmed=confirmed,
        )

    return await _calibrate_apply(
        session,
        target=target,
        target_id=target_id,
        module_ip=target_ip,
        channel=target_ch,
        dim_min=dim_min,
        dim_max=dim_max,
        dim_gamma=dim_gamma,
        default_fade=default_fade,
        confirmed=confirmed,
    )


async def _calibrate_status(
    dimmers: list[dict[str, Any]],
    modules_by_id: dict[str, dict[str, Any]],
) -> ToolResult:
    ips = {_dimmer_module_ip(d, modules_by_id) for d in dimmers}
    mod_map = await _fetch_modules_map(ips)
    rows: list[dict[str, Any]] = []
    for dev in dimmers:
        ch = dev.get("channel")
        mod_ip = _dimmer_module_ip(dev, modules_by_id)
        statuses, mod_err = mod_map.get(mod_ip, (None, None))
        mod_row = (
            _module_row_for_channel(statuses, ch)
            if isinstance(ch, int) and not isinstance(ch, bool)
            else None
        )
        entry: dict[str, Any] = {
            "device_id": dev.get("id"),
            "name": dev.get("name"),
            "room": dev.get("room"),
            "module_ip": mod_ip,
            "channel": ch,
            "uitgang": (
                format_uitgang(mod_ip, ch)
                if mod_ip and isinstance(ch, int) and not isinstance(ch, bool)
                else None
            ),
            "active": dev.get("active"),
            "state": dev.get("state"),
            "level": dev.get("level"),
            "dim_gamma": dev.get("dim_gamma"),
            "default_fade": dev.get("default_fade"),
            "module_http_reachable": statuses is not None,
        }
        if mod_row is not None:
            entry["descr"] = mod_row.get("descr")
            entry["gr"] = mod_row.get("gr")
            entry["dim_min"] = mod_row.get("dimMin")
            entry["dim_max"] = mod_row.get("dimMax")
            entry["module_state"] = mod_row.get("state")
        elif mod_err:
            entry["module_http_error"] = mod_err
        rows.append(entry)

    unreachable_ips = sorted(ip for ip, (data, _) in mod_map.items() if data is None)
    note_http = (
        f" Directe module-uitlezing niet bereikbaar voor {', '.join(unreachable_ips)}; "
        "gateway-waarden zijn wel getoond."
        if unreachable_ips
        else ""
    )
    msg = (
        f"{len(rows)} dimmerkanaal/-kanalen gevonden. "
        "Kanalen tellen vanaf 0 (zelfde cijfer als op de module)."
        + note_http
    )
    return ToolResult(
        msg,
        {
            "ok": True,
            "kind": "dimmer_calibration",
            "mode": "status",
            "channels": rows,
            "module_http": {
                ip: {"reachable": data is not None, "error": err or ""}
                for ip, (data, err) in sorted(mod_map.items())
            },
        },
    )


async def _calibrate_sweep(
    session: GatewaySession,
    *,
    target: dict[str, Any],
    target_id: str,
    module_ip: str,
    channel: int,
    steps: str,
    hold_seconds: float,
    countdown_seconds: float,
    sync_on_seconds: float,
    sync_off_seconds: float,
    sweep_log_path: str,
    keep_raw: bool,
    confirmed: bool,
) -> ToolResult:
    try:
        parsed_steps = parse_steps(steps or None)
    except ValueError as exc:
        return ToolResult(
            f"Ongeldige sweep-stappen: {exc}",
            {"ok": False, "kind": KIND_OTHER, "mode": "sweep", "sent": False},
        )
    timing_err = _validate_timing_bounds(
        hold_seconds=hold_seconds,
        sync_on_seconds=sync_on_seconds,
        sync_off_seconds=sync_off_seconds,
        countdown_seconds=countdown_seconds,
    )
    if timing_err is not None:
        timing_err.data["mode"] = "sweep"
        return timing_err

    statuses, mod_err = await fetch_module_dimmer_statuses(module_ip)
    mod_row = _module_row_for_channel(statuses, channel)
    uitgang = format_uitgang(module_ip, channel)
    orig_gamma = target.get("dim_gamma")
    orig_min = mod_row.get("dimMin") if mod_row else None
    orig_max = mod_row.get("dimMax") if mod_row else None
    orig_descr = str(mod_row.get("descr") or target.get("name") or "") if mod_row else ""
    orig_gr = str(mod_row.get("gr") or target.get("room") or "") if mod_row else ""

    est_s = round(
        float(countdown_seconds)
        + float(sync_on_seconds)
        + float(sync_off_seconds)
        + len(parsed_steps) * float(hold_seconds)
        + 0.5,
        1,
    )
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "mode": "sweep",
        "sent": False,
        "device_id": target_id,
        "name": target.get("name"),
        "room": target.get("room"),
        "module_ip": module_ip,
        "channel": channel,
        "uitgang": uitgang,
        "steps": parsed_steps,
        "hold_seconds": float(hold_seconds),
        "sync_on_seconds": float(sync_on_seconds),
        "sync_off_seconds": float(sync_off_seconds),
        "countdown_seconds": float(countdown_seconds),
        "estimated_seconds": est_s,
        "keep_raw": bool(keep_raw),
        "module_http_reachable": mod_row is not None,
        "original": {
            "dim_gamma": orig_gamma,
            "dim_min": orig_min,
            "dim_max": orig_max,
        },
    }
    if not confirmed:
        mod_note = (
            f"Module dimMin/dimMax ({orig_min}..{orig_max}) gaat tijdelijk naar 0..100"
            if mod_row is not None
            else (
                "Directe module-HTTP is niet bereikbaar; alleen gateway dim_gamma gaat tijdelijk naar 1.0"
                + (f" ({mod_err})" if mod_err else "")
            )
        )
        return ToolResult(
            (
                f"Nog niet gestart. Kalibratiesweep op {target.get('name') or target_id} "
                f"(uitgang {uitgang}, kanaal {channel}): {len(parsed_steps)} stappen van "
                f"{parsed_steps[0]}% tot {parsed_steps[-1]}% (duur ~{est_s} s, sync-puls "
                f"{sync_on_seconds} s aan / {sync_off_seconds} s uit). {mod_note}. "
                "Verduister eerst de kamer, richt de smartphonecamera (SDR 1080p, AE/AF Lock) "
                "op een indirect verlichte muur of plafond en start de video-opname. "
                "Roep calibrate_dimmer opnieuw aan met confirmed=true zodra de opname loopt."
            ),
            preview,
        )

    if countdown_seconds > 0:
        await _calibrated_sleeper(session, float(countdown_seconds))

    patch_path = f"/api/v1/devices/{quote(target_id, safe='')}"
    cmd_path = f"/api/v1/devices/{quote(target_id, safe='')}/command"

    gateway_raw_applied = False
    module_raw_applied = False
    recorded_steps: list[dict[str, Any]] = []
    used_nominal_offsets = False
    t_sync_off = 0.0
    sweep_error: str | None = None
    restored = {"gateway_dim_gamma": False, "module_dim_min_max": False}

    try:
        if orig_gamma is not None and float(orig_gamma) != 1.0:
            _, p_err = await session.patch_json(patch_path, {"dim_gamma": 1.0})
            if p_err is not None:
                return _from_error(p_err, mode="sweep", device_id=target_id, sent=False)
            gateway_raw_applied = True

        if mod_row is not None and (orig_min, orig_max) != (0, 100):
            saved_ok, save_err = await save_module_dimmer_channel(
                module_ip,
                channel,
                descr=orig_descr,
                gr=orig_gr,
                dim_min=0,
                dim_max=100,
            )
            if not saved_ok:
                sweep_error = f"Kon module-schaal niet tijdelijk op 0..100 zetten: {save_err}"
                raise RuntimeError(sweep_error)
            module_raw_applied = True

        # Sync pulse: ON 100% -> OFF 0%
        _, c_err = await session.post_json(
            cmd_path, {"action": "DIM", "value": 100, "fade": 0}
        )
        if c_err is not None:
            return _from_error(c_err, mode="sweep", device_id=target_id, sent=True)
        await _calibrated_sleeper(session, float(sync_on_seconds))

        _, c_err = await session.post_json(
            cmd_path, {"action": "DIM", "value": 0, "fade": 0}
        )
        if c_err is not None:
            return _from_error(c_err, mode="sweep", device_id=target_id, sent=True)
        t_sync_off = time.monotonic()
        await _calibrated_sleeper(session, float(sync_off_seconds))

        for idx, pct in enumerate(parsed_steps):
            actual_offset = round(time.monotonic() - t_sync_off, 3)
            nominal_offset = round(float(sync_off_seconds) + idx * float(hold_seconds), 3)
            body, c_err = await session.post_json(
                cmd_path, {"action": "DIM", "value": pct, "fade": 0}
            )
            ok_step = c_err is None and isinstance(body, dict) and body.get("ok") is True
            recorded_steps.append(
                {
                    "level": pct,
                    "offset_s": actual_offset,
                    "nominal_offset_s": nominal_offset,
                    "ok": ok_step,
                }
            )
            if c_err is not None:
                sweep_error = c_err.message
                break
            await _calibrated_sleeper(session, float(hold_seconds))

        # Final OFF so the video shows a clear end state.
        await session.post_json(cmd_path, {"action": "DIM", "value": 0, "fade": 0})
        await _calibrated_sleeper(session, min(1.0, float(hold_seconds)))
    except RuntimeError:
        pass
    finally:
        if not keep_raw:
            if module_raw_applied and isinstance(orig_min, int) and isinstance(orig_max, int):
                if 0 <= orig_min < orig_max <= 100:
                    ok_rest, _ = await save_module_dimmer_channel(
                        module_ip,
                        channel,
                        descr=orig_descr,
                        gr=orig_gr,
                        dim_min=orig_min,
                        dim_max=orig_max,
                    )
                    restored["module_dim_min_max"] = ok_rest
            if gateway_raw_applied and orig_gamma is not None:
                _, r_err = await session.patch_json(patch_path, {"dim_gamma": orig_gamma})
                restored["gateway_dim_gamma"] = r_err is None

    if sweep_error is not None and not recorded_steps:
        return ToolResult(
            sweep_error,
            {
                "ok": False,
                "kind": KIND_OTHER,
                "mode": "sweep",
                "sent": False,
                "device_id": target_id,
                "restored": restored,
            },
        )

    step_offsets: list[float]
    if recorded_steps:
        measured_span = recorded_steps[-1]["offset_s"] - recorded_steps[0]["offset_s"]
        expected_span = max(0.0, (len(recorded_steps) - 1) * float(hold_seconds))
        if expected_span > 0.2 and measured_span < 0.05 * expected_span:
            step_offsets = [float(item["nominal_offset_s"]) for item in recorded_steps]
            used_nominal_offsets = True
        else:
            step_offsets = [float(item["offset_s"]) for item in recorded_steps]
    else:
        step_offsets = []

    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", target_id or f"ch{channel}")
    target_log = (
        Path(sweep_log_path).expanduser()
        if sweep_log_path.strip()
        else Path(tempfile.gettempdir()) / f"ipbuilding_dimmer_sweep_{safe_id}.json"
    )
    target_log.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "device_id": target_id,
        "name": target.get("name"),
        "room": target.get("room"),
        "module_ip": module_ip,
        "channel": channel,
        "uitgang": uitgang,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sync_on_seconds": float(sync_on_seconds),
        "sync_off_seconds": float(sync_off_seconds),
        "hold_seconds": float(hold_seconds),
        "steps": [int(item["level"]) for item in recorded_steps],
        "step_offsets_seconds": step_offsets,
        "used_nominal_offsets": used_nominal_offsets,
        "module_http_reachable": mod_row is not None,
    }
    target_log.write_text(
        json.dumps(log_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    await session.annotate(
        f"Dimmersweep {target.get('name') or target_id} (uitgang {uitgang}): "
        f"{len(recorded_steps)} stappen gelogd naar {target_log.name}",
        marker="calibrate_dimmer_sweep",
    )
    return ToolResult(
        (
            f"Sweep afgerond voor {target.get('name') or target_id} (uitgang {uitgang}, "
            f"{len(recorded_steps)} stappen). Log opgeslagen op {target_log}. "
            "Stop de video-opname en roep calibrate_dimmer(mode='analyze', "
            f"video_path=..., sweep_log_path='{target_log}') aan."
        ),
        {
            "ok": sweep_error is None,
            "kind": "dimmer_calibration",
            "mode": "sweep",
            "sent": True,
            "device_id": target_id,
            "uitgang": uitgang,
            "module_ip": module_ip,
            "channel": channel,
            "steps": log_payload["steps"],
            "hold_seconds": float(hold_seconds),
            "sync_on_seconds": float(sync_on_seconds),
            "sync_off_seconds": float(sync_off_seconds),
            "step_offsets_seconds": step_offsets,
            "sweep_log_path": str(target_log),
            "module_http_reachable": mod_row is not None,
            "keep_raw": bool(keep_raw),
            "restored": restored,
            "partial_error": sweep_error or "",
        },
    )


async def _calibrate_analyze(
    session: GatewaySession,
    *,
    device_id: str,
    module_ip: str,
    channel: int | None,
    steps: str,
    hold_seconds: float,
    sync_on_seconds: float,
    sync_off_seconds: float,
    video_path: str,
    sweep_log_path: str,
    margin_min: int,
    sat_threshold: float,
) -> ToolResult:
    if not video_path.strip():
        return ToolResult(
            "Geef video_path op om een kalibratievideo te analyseren.",
            {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
        )
    if isinstance(margin_min, bool) or not isinstance(margin_min, int) or margin_min < 0:
        return ToolResult(
            "margin_min moet een geheel getal >= 0 zijn.",
            {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
        )
    if (
        isinstance(sat_threshold, bool)
        or not isinstance(sat_threshold, (int, float))
        or not 0.5 <= float(sat_threshold) <= 1.0
    ):
        return ToolResult(
            "sat_threshold moet tussen 0.5 en 1.0 liggen.",
            {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
        )

    sweep_meta: dict[str, Any] = {}
    step_offsets: list[float] | None = None
    effective_hold = float(hold_seconds)
    effective_sync_on = float(sync_on_seconds)
    effective_sync_off = float(sync_off_seconds)
    raw_steps: str | list[int] | None = steps.strip() or None

    if sweep_log_path.strip():
        log_file = Path(sweep_log_path.strip()).expanduser()
        if not log_file.is_file():
            return ToolResult(
                f"Sweep-logbestand niet gevonden: {log_file}",
                {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
            )
        try:
            sweep_meta = json.loads(log_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ToolResult(
                f"Kon sweep-logbestand niet lezen: {exc}",
                {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
            )
        if not isinstance(sweep_meta, dict):
            return ToolResult(
                "Ongeldig JSON-formaat in sweep-logbestand.",
                {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
            )
        if raw_steps is None and isinstance(sweep_meta.get("steps"), list):
            raw_steps = sweep_meta["steps"]
        if isinstance(sweep_meta.get("step_offsets_seconds"), list):
            step_offsets = [float(x) for x in sweep_meta["step_offsets_seconds"]]
        if isinstance(sweep_meta.get("hold_seconds"), (int, float)):
            effective_hold = float(sweep_meta["hold_seconds"])
        if isinstance(sweep_meta.get("sync_on_seconds"), (int, float)):
            effective_sync_on = float(sweep_meta["sync_on_seconds"])
        if isinstance(sweep_meta.get("sync_off_seconds"), (int, float)):
            effective_sync_off = float(sweep_meta["sync_off_seconds"])
        device_id = device_id or str(sweep_meta.get("device_id") or "")
        module_ip = module_ip or str(sweep_meta.get("module_ip") or "")
        if channel is None and isinstance(sweep_meta.get("channel"), int):
            channel = sweep_meta["channel"]

    try:
        parsed_steps = parse_steps(raw_steps)
    except ValueError as exc:
        return ToolResult(
            f"Ongeldige stappen: {exc}",
            {"ok": False, "kind": KIND_OTHER, "mode": "analyze"},
        )

    timing_err = _validate_timing_bounds(
        hold_seconds=effective_hold,
        sync_on_seconds=effective_sync_on,
        sync_off_seconds=effective_sync_off,
    )
    if timing_err is not None:
        timing_err.data["mode"] = "analyze"
        return timing_err

    try:
        samples = await extract_video_luma_async(video_path.strip())
        analysis = analyze_luma_series(
            samples,
            parsed_steps,
            effective_hold,
            sync_on_seconds=effective_sync_on,
            sync_off_seconds=effective_sync_off,
            step_offsets_seconds=step_offsets,
            margin_min=margin_min,
            sat_threshold=float(sat_threshold),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return ToolResult(
            f"Video-analyse mislukt: {exc}",
            {"ok": False, "kind": KIND_OTHER, "mode": "analyze", "video_path": video_path},
        )

    await session.annotate(
        f"Video-analyse {device_id or sweep_meta.get('uitgang') or 'dimmer'}: "
        f"gemeten dimMin={analysis['measured_dim_min']}, "
        f"advies dimMin={analysis['recommended_dim_min']}, "
        f"dimMax={analysis['recommended_dim_max']}, "
        f"dim_gamma={analysis['recommended_dim_gamma']}",
        marker="calibrate_dimmer_analyze",
    )
    msg = (
        f"Analyse klaar: gemeten ontsteking op {analysis['measured_dim_min']}%. "
        f"Aanbevolen instelling: dimMin={analysis['recommended_dim_min']}, "
        f"dimMax={analysis['recommended_dim_max']}, "
        f"dim_gamma={analysis['recommended_dim_gamma']}. "
        "Toon de volledige staptabel aan de tester en vraag om bevestiging "
        "vóórdat je calibrate_dimmer(mode='apply', confirmed=true) aanroept."
    )
    return ToolResult(
        msg,
        {
            "ok": True,
            "kind": "dimmer_calibration",
            "mode": "analyze",
            "device_id": device_id or None,
            "module_ip": module_ip or None,
            "channel": channel,
            "uitgang": sweep_meta.get("uitgang")
            or (format_uitgang(module_ip, channel) if module_ip and channel is not None else None),
            "video_path": str(Path(video_path.strip()).expanduser()),
            "sweep_log_path": sweep_log_path.strip() or None,
            "frame_count": len(samples),
            **analysis,
        },
    )


async def _calibrate_apply(
    session: GatewaySession,
    *,
    target: dict[str, Any],
    target_id: str,
    module_ip: str,
    channel: int,
    dim_min: int | None,
    dim_max: int | None,
    dim_gamma: float | None,
    default_fade: int | None,
    confirmed: bool,
) -> ToolResult:
    if (
        dim_min is None
        and dim_max is None
        and dim_gamma is None
        and default_fade is None
    ):
        return ToolResult(
            "Geef minstens dim_min/dim_max, dim_gamma of default_fade op.",
            {"ok": False, "kind": KIND_OTHER, "mode": "apply", "sent": False},
        )

    want_module_curve = dim_min is not None or dim_max is not None
    if want_module_curve:
        for label, val in (("dim_min", dim_min), ("dim_max", dim_max)):
            if val is not None and (isinstance(val, bool) or not isinstance(val, int)):
                return ToolResult(
                    f"{label} moet een geheel getal zijn.",
                    {"ok": False, "kind": KIND_OTHER, "mode": "apply", "sent": False},
                )

    parsed_gamma: float | None = None
    if dim_gamma is not None:
        if (
            isinstance(dim_gamma, bool)
            or not isinstance(dim_gamma, (int, float))
            or not math.isfinite(float(dim_gamma))
            or not 1.0 <= float(dim_gamma) <= 3.5
        ):
            return ToolResult(
                "dim_gamma moet tussen 1.0 en 3.5 liggen.",
                {"ok": False, "kind": KIND_OTHER, "mode": "apply", "sent": False},
            )
        parsed_gamma = round(float(dim_gamma), 2)

    if default_fade is not None:
        if (
            isinstance(default_fade, bool)
            or not isinstance(default_fade, int)
            or not 0 <= default_fade <= 255
        ):
            return ToolResult(
                "default_fade moet een geheel getal van 0 tot en met 255 zijn.",
                {"ok": False, "kind": KIND_OTHER, "mode": "apply", "sent": False},
            )

    statuses, mod_err = await fetch_module_dimmer_statuses(module_ip)
    mod_row = _module_row_for_channel(statuses, channel)

    resolved_min: int | None = None
    resolved_max: int | None = None
    if want_module_curve:
        if mod_row is None:
            return ToolResult(
                "Kan dimMin/dimMax niet opslaan: directe HTTP-verbinding met de "
                f"dimmermodule ({module_ip}) lukte niet ({mod_err or 'onbereikbaar'}). "
                "Je kunt wel dim_gamma en default_fade via de gateway opslaan.",
                {
                    "ok": False,
                    "kind": KIND_OTHER,
                    "mode": "apply",
                    "sent": False,
                    "module_ip": module_ip,
                    "channel": channel,
                },
            )
        resolved_min = dim_min if dim_min is not None else mod_row.get("dimMin")
        resolved_max = dim_max if dim_max is not None else mod_row.get("dimMax")
        if (
            not isinstance(resolved_min, int)
            or not isinstance(resolved_max, int)
            or not 0 <= resolved_min < resolved_max <= 100
        ):
            return ToolResult(
                f"dim_min en dim_max moeten voldoen aan 0 <= dim_min < dim_max <= 100 "
                f"(kreeg {resolved_min}..{resolved_max}).",
                {"ok": False, "kind": KIND_OTHER, "mode": "apply", "sent": False},
            )

    uitgang = format_uitgang(module_ip, channel)
    orig_descr = str(mod_row.get("descr") or target.get("name") or "") if mod_row else ""
    orig_gr = str(mod_row.get("gr") or target.get("room") or "") if mod_row else ""
    before_state = {
        "dim_min": mod_row.get("dimMin") if mod_row else None,
        "dim_max": mod_row.get("dimMax") if mod_row else None,
        "dim_gamma": target.get("dim_gamma"),
        "default_fade": target.get("default_fade"),
    }
    after_state = {
        "dim_min": resolved_min if want_module_curve else before_state["dim_min"],
        "dim_max": resolved_max if want_module_curve else before_state["dim_max"],
        "dim_gamma": parsed_gamma if parsed_gamma is not None else before_state["dim_gamma"],
        "default_fade": default_fade if default_fade is not None else before_state["default_fade"],
    }

    if not confirmed:
        parts: list[str] = []
        if want_module_curve:
            parts.append(
                f"module dimMin/dimMax van {before_state['dim_min']}..{before_state['dim_max']} "
                f"naar {resolved_min}..{resolved_max} (met behoud van descr='{orig_descr}', gr='{orig_gr}')"
            )
        if parsed_gamma is not None:
            parts.append(f"gateway dim_gamma van {before_state['dim_gamma']} naar {parsed_gamma}")
        if default_fade is not None:
            parts.append(f"gateway default_fade van {before_state['default_fade']} naar {default_fade}")
        return ToolResult(
            (
                f"Nog niet opgeslagen. Voorgesteld voor {target.get('name') or target_id} "
                f"(uitgang {uitgang}, kanaal {channel}): "
                + "; ".join(parts)
                + ". Vraag bevestiging en roep calibrate_dimmer opnieuw aan met confirmed=true."
            ),
            {
                "ok": False,
                "kind": "confirmation_required",
                "mode": "apply",
                "sent": False,
                "device_id": target_id,
                "uitgang": uitgang,
                "module_ip": module_ip,
                "channel": channel,
                "before": before_state,
                "after": after_state,
            },
        )

    module_saved = False
    verified_module: dict[str, Any] | None = None
    if want_module_curve and resolved_min is not None and resolved_max is not None:
        ok_save, save_err = await save_module_dimmer_channel(
            module_ip,
            channel,
            descr=orig_descr,
            gr=orig_gr,
            dim_min=resolved_min,
            dim_max=resolved_max,
        )
        if not ok_save:
            return ToolResult(
                f"Opslaan op dimmermodule mislukt: {save_err}",
                {
                    "ok": False,
                    "kind": KIND_OTHER,
                    "mode": "apply",
                    "sent": False,
                    "device_id": target_id,
                },
            )
        module_saved = True
        fresh_statuses, _ = await fetch_module_dimmer_statuses(module_ip)
        fresh_row = _module_row_for_channel(fresh_statuses, channel)
        if fresh_row is not None:
            verified_module = {
                "dim_min": fresh_row.get("dimMin"),
                "dim_max": fresh_row.get("dimMax"),
                "descr": fresh_row.get("descr"),
                "gr": fresh_row.get("gr"),
            }

    gateway_patch: dict[str, Any] = {}
    if parsed_gamma is not None:
        gateway_patch["dim_gamma"] = parsed_gamma
    if default_fade is not None:
        gateway_patch["default_fade"] = default_fade

    gateway_body: Any = None
    if gateway_patch:
        patch_path = f"/api/v1/devices/{quote(target_id, safe='')}"
        gateway_body, patch_err = await session.patch_json(patch_path, gateway_patch)
        if patch_err is not None:
            return _from_error(
                patch_err,
                mode="apply",
                device_id=target_id,
                sent=module_saved,
                module_saved=module_saved,
                verified_module=verified_module,
            )

    await session.annotate(
        f"Kalibratie opgeslagen op {target.get('name') or target_id} (uitgang {uitgang}): "
        f"dimMin={after_state['dim_min']}, dimMax={after_state['dim_max']}, "
        f"dim_gamma={after_state['dim_gamma']}, default_fade={after_state['default_fade']}",
        marker="calibrate_dimmer_apply",
    )
    return ToolResult(
        (
            f"Kalibratie opgeslagen voor {target.get('name') or target_id} (uitgang {uitgang}): "
            f"dimMin={after_state['dim_min']}, dimMax={after_state['dim_max']}, "
            f"dim_gamma={after_state['dim_gamma']}, default_fade={after_state['default_fade']}. "
            "Test met de tester 1%, 50%, 100% en een fade aan/uit om te verifiëren."
        ),
        {
            "ok": True,
            "kind": "dimmer_calibration",
            "mode": "apply",
            "sent": True,
            "device_id": target_id,
            "uitgang": uitgang,
            "module_ip": module_ip,
            "channel": channel,
            "before": before_state,
            "after": after_state,
            "module_saved": module_saved,
            "verified_module": verified_module,
            "gateway": gateway_body if isinstance(gateway_body, dict) else {},
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
    include_polls: bool = False,
) -> ToolResult:
    """Live field-bus frames. Needs capability ``udp_frame``.

    ``seconds=0`` does not wait: it returns what arrived since the previous
    capture. Call it once to start, let the tester act, and call it again
    when the tester says done. Routine polls and keepalives are left out
    unless ``include_polls`` is true; the result counts them.
    """
    error = await session.refresh_status()
    if error is not None:
        return _from_error(error, capability="udp_frame")
    gated = gate_feature(session.status, "udp_frame")
    if gated is not None:
        return _from_error(gated, capability="udp_frame")

    seconds = clamp_timeout(seconds if seconds > 0 else 0.0)
    limit = max(1, min(int(limit), 200))
    direction = (direction or "both").lower()
    # The first capture takes its cursor before subscribe, so a frame that is
    # the reply to that subscribe is inside the window and frames from before
    # the call stay outside it. A later capture continues from the seq stored
    # at the end of the previous one, so the pause between calls is included
    # and frames already returned are not repeated. The wait stays capped.
    continued = session.frame_cursor is not None
    since = await session.ensure_udp_subscription(timeout=3)
    if since is None:
        return ToolResult(
            "De gateway antwoordt, maar de live-verbinding staat nog niet. "
            "Probeer het zo meteen opnieuw.",
            {"ok": False, "kind": "connecting", "frames": []},
        )
    if session.frame_cursor is not None:
        since = session.frame_cursor
    skipped: dict[str, int] = {"polls": 0}
    frames = await _collect_frames(
        session,
        since,
        seconds=seconds,
        direction=direction,
        module=module,
        pattern=pattern,
        limit=limit,
        include_polls=include_polls,
        skipped=skipped,
    )
    await _record_capture_decodes(session, frames)
    session.frame_cursor = session.buffer.latest_seq
    if not frames:
        message = (
            "Er kwamen geen passende frames binnen in deze periode. "
            "Dat kan betekenen dat er niets gebeurde, of dat dit verkeer niet "
            "langs de gateway gaat."
        )
    else:
        message = f"{len(frames)} frame(s) ontvangen."
    if skipped["polls"]:
        message += (
            f" {skipped['polls']} routinepoll(s) weggelaten; "
            "include_polls=true toont ze."
        )
    if len(frames) >= limit:
        message += (
            f" De limiet van {limit} frames is bereikt; er kan meer zijn. "
            "Roep de tool opnieuw aan met seconds=0 voor de rest."
        )
    if continued:
        message = (
            "Deze opname gaat verder waar de vorige stopte, "
            "inclusief wat tussendoor binnenkwam. "
            + message
        )
    elif seconds == 0:
        message = (
            "Meeluisteren loopt vanaf nu. Laat de tester drukken of kijken, en roep "
            "capture_frames opnieuw aan met seconds=0 zodra hij klaar zegt. "
            + message
        )
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "frames",
            "frames": frames,
            "seconds": seconds,
            "direction": direction,
            "continued": continued,
            "polls_skipped": skipped["polls"],
            "include_polls": include_polls,
        },
    )


async def send_raw(
    session: GatewaySession,
    *,
    module_ip: str,
    payload_hex: str,
    port: int = 1001,
    window_ms: int = 2000,
    confirmed: bool = False,
) -> ToolResult:
    """Send raw bytes through the gateway. Requires an explicit second call."""
    try:
        hex_payload = _normalize_hex(payload_hex)
    except ValueError:
        return _raw_rejected("invalid_payload")
    if not 1 <= len(hex_payload) // 2 <= 64:
        return _raw_rejected("invalid_payload")
    module_ip = (module_ip or "").strip()
    if _raw_module_ip(module_ip) is None:
        return _raw_rejected("invalid_target")
    if isinstance(port, bool) or not isinstance(port, int) or port != 1001:
        return _raw_rejected("invalid_port")
    if isinstance(window_ms, bool) or not isinstance(window_ms, int) or not 1 <= window_ms <= 3000:
        return _raw_rejected("invalid_window")
    preview = {
        "ok": False,
        "kind": "confirmation_required",
        "module_ip": module_ip,
        "port": port,
        "payload_hex": hex_payload,
        "window_ms": window_ms,
        "sent": False,
    }
    if not confirmed:
        return ToolResult(
            (
                f"Nog niet verstuurd. Dit pakket gaat naar module {module_ip} "
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
        if gated.kind == KIND_NOT_AVAILABLE:
            return ToolResult(
                "Een testpakket sturen is niet ondersteund in deze gatewayversie.",
                {**preview, "ok": False, "kind": KIND_NOT_AVAILABLE},
            )
        if gated.kind == KIND_REMOTE_DEBUGGING_OFF:
            return ToolResult(
                _RAW_ERROR_TEXT["remote_debugging_disabled"],
                {**preview, "ok": False, "kind": KIND_REMOTE_DEBUGGING_OFF},
            )
        return _from_error(gated, **preview)

    body, call_error = await session.post_json(
        RAW_SEND_PATH,
        {
            "module_ip": module_ip,
            "port": port,
            "payload_hex": hex_payload,
            "window_ms": window_ms,
        },
        timeout=max(8.0, window_ms / 1000 + 3),
    )
    if call_error is not None:
        code = _raw_error_code(body)
        if code in _RAW_ERROR_TEXT:
            return ToolResult(
                _RAW_ERROR_TEXT[code],
                {**preview, "ok": False, "kind": code},
            )
        if call_error.kind == KIND_NOT_AVAILABLE:
            return ToolResult(
                "Een testpakket sturen is niet ondersteund in deze gatewayversie.",
                {**preview, "ok": False, "kind": KIND_NOT_AVAILABLE},
            )
        return _from_error(call_error, **preview)
    replies: list[Any] = []
    truncated = False
    sent_hex = hex_payload
    reported_window = window_ms
    if isinstance(body, dict):
        raw_replies = body.get("replies") or []
        if isinstance(raw_replies, list):
            replies = raw_replies
        truncated = body.get("truncated") is True
        if isinstance(body.get("sent_hex"), str) and body.get("sent_hex"):
            sent_hex = body["sent_hex"]
        if type(body.get("window_ms")) is int:
            reported_window = body["window_ms"]
    decoded = []
    for reply in replies:
        if isinstance(reply, dict) and isinstance(reply.get("hex"), str):
            item = dict(reply)
            item["local_decode"] = _safe_decode(reply["hex"])
            decoded.append(item)
        else:
            decoded.append(reply)
    if decoded:
        summary = f"{len(decoded)} antwoord(en) binnen het venster."
    else:
        summary = "Geen antwoord binnen het venster. Dat is gelukt."
    if truncated:
        summary += " Er was nog een antwoord; de gateway bewaart er hoogstens 8."
    await _record_raw_send(session, module_ip=module_ip, sent_hex=sent_hex, replies=decoded)
    return ToolResult(
        f"Pakket verstuurd naar {module_ip} op poort {port}. {summary}",
        {
            "ok": True,
            "kind": "sent",
            "sent": True,
            "module_ip": module_ip,
            "port": port,
            "payload_hex": hex_payload,
            "sent_hex": sent_hex,
            "window_ms": reported_window,
            "replies": decoded,
            "truncated": truncated,
        },
    )


def _hex_as_text(hex_text: str) -> str:
    """Printable ASCII for a frame, else the hex itself."""
    try:
        data = bytes.fromhex(hex_text)
    except ValueError:
        return hex_text
    if data and all(32 <= byte < 127 for byte in data):
        return data.decode("ascii")
    return hex_text


def _reply_summary(reply: Any) -> str:
    if not isinstance(reply, dict):
        return "?"
    text = _hex_as_text(str(reply.get("hex") or ""))
    decoded = reply.get("local_decode")
    bits: list[str] = []
    if isinstance(decoded, dict):
        for match in decoded.get("matches") or []:
            fields = match.get("fields") if isinstance(match, dict) else None
            if not isinstance(fields, dict):
                continue
            family = fields.get("family")
            if family:
                bits.append(str(family))
            level = fields.get("level_percent")
            if type(level) is int:
                bits.append(f"{level}%")
            full = full_dialect_id(str(fields.get("dialect_id") or ""))
            if full:
                bits.append(full)
            break
    return f"{text} ({' '.join(bits)})" if bits else text


async def _record_raw_send(
    session: GatewaySession,
    *,
    module_ip: str,
    sent_hex: str,
    replies: list[Any],
) -> None:
    """Store one sent test packet and its replies for the report."""
    sent = _hex_as_text(sent_hex)
    if replies:
        answer = "antwoord " + "; ".join(_reply_summary(reply) for reply in replies)
    else:
        answer = "geen antwoord"
    await session.buffer.append(
        {
            "type": "raw_send_result",
            "received_at": _format_local(datetime.now().astimezone()),
            "module_ip": module_ip,
            "sent_hex": sent_hex,
            "reply_hex": [
                str(reply.get("hex") or "") for reply in replies if isinstance(reply, dict)
            ],
            "message": f"testpakket {sent} naar {module_ip}: {answer}",
        }
    )


async def decode_test(payload: str, session: GatewaySession | None = None) -> ToolResult:
    """Local decode through the gateway payload decoders. No gateway needed."""
    try:
        data = parse_frame(payload)
    except ValueError:
        result = ToolResult(
            "Dit is geen frame dat ik kan lezen. Plak hex of een korte ASCII-tekst.",
            {"ok": False, "kind": KIND_OTHER, "matched": False, "matches": []},
        )
        if session is not None:
            await session.buffer.append(_decode_result_event(None))
        return result
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
        elif any(item.get("decoder") == "relay" for item in decoded["matches"]):
            message += (
                " Het relaisformaat is herkend, maar deze decoder geeft er geen dialect-id aan."
                " Dat is geen Kessel-Lo en geen Torhout."
            )
    else:
        message = "Geen enkele decoder herkent dit frame."
    if session is not None:
        await session.buffer.append(_decode_result_event(decoded))
    return ToolResult(message, {"ok": True, "kind": "decode", **decoded})


def _parse_gateway_time(event: dict[str, Any]) -> datetime | None:
    for key in _GATEWAY_TIME_KEYS:
        parsed = _parse_log_ts(event.get(key))
        if parsed is not None:
            return parsed
    return None


# UTC in log text: a T or a space, a fraction with '.' or ',', then Z or +00:00.
_UTC_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:[Zz]|[+\-]00:?00)"
)
_TIME_FIELDS = ("ts", "timestamp", "time", "at", "from", "to")


def _format_local(moment: datetime) -> str:
    """ISO 8601 in the tester's timezone, with a numeric offset. Never a Z suffix."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().isoformat(timespec="seconds")


def _localise_utc_text(text: str) -> str:
    """Rewrite UTC timestamps in a report to local time with a numeric offset."""

    def replace(match: re.Match[str]) -> str:
        parsed = _parse_log_ts(match.group(0))
        if parsed is None:
            return match.group(0)
        return _format_local(parsed)

    return _UTC_STAMP.sub(replace, text)


def _localise_time_fields(item: dict[str, Any]) -> None:
    """Convert UTC clock fields on one event. Local offsets are left as they are."""
    for key in _TIME_FIELDS:
        raw = item.get(key)
        if not isinstance(raw, str) or _UTC_STAMP.fullmatch(raw.strip()) is None:
            continue
        parsed = _parse_log_ts(raw)
        if parsed is not None:
            item[key] = _format_local(parsed)
    for key in ("message", "text"):
        raw = item.get(key)
        if isinstance(raw, str) and _UTC_STAMP.search(raw):
            item[key] = _localise_utc_text(raw)


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
    _localise_time_fields(item)
    if item.get("type") == "udp_frame":
        decoded = _with_local_decode(item).get("local_decode")
        _remember_frame_dialects(item, decoded if isinstance(decoded, dict) else None)
    return item


def _stamp_note(note: dict[str, Any]) -> dict[str, Any]:
    item = dict(note)
    parsed = _parse_log_ts(item.get("at"))
    item["local_time"] = _format_local(parsed or datetime.now().astimezone())
    item["time_source"] = "received"
    _localise_time_fields(item)
    return item


def report_directory() -> Path:
    """Where a saved report goes: ``IPBUILDING_REPORT_DIR``, else Downloads, else home."""
    configured = os.environ.get("IPBUILDING_REPORT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    home = Path.home()
    downloads = home / "Downloads"
    return downloads if downloads.is_dir() else home


def _save_report_file(report: str, installatie_id: str) -> tuple[str, str]:
    """Write the filtered report. Returns (path, error); one of them is empty."""
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", installatie_id or "")[:16] or "sessie"
    folder = report_directory()
    path = folder / f"ipbuilding-rapport-{safe_id}-{stamp}.md"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    except OSError as exc:
        return "", f"{exc.__class__.__name__}: {exc.strerror or exc}"
    return str(path), ""


async def export_session(
    session: GatewaySession,
    *,
    note: str = "",
    marker: str = "",
    redact: bool = True,
    feedback: str = "",
    include_events: bool | None = None,
    vermoeden: str = "",
    open_vraag: str = "",
    save_file: bool = True,
) -> ToolResult:
    """Bundle the session. Names are masked and addresses removed unless redact is false.

    With ``save_file`` the filtered report is also written as a Markdown file
    (Downloads by default), so the tester can attach it unchanged. A raw
    report (``redact=false``) is never written to disk.
    """
    if note or marker:
        await session.annotate(note or marker, marker=marker)
    if feedback.strip():
        session.tool_feedback = feedback.strip()
    if vermoeden.strip():
        session.suspicion = vermoeden.strip()
    if open_vraag.strip():
        session.developer_question = open_vraag.strip()
    if include_events is not None:
        session.include_events = bool(include_events)
    body = _export_body(session)
    body["feedback"] = session.tool_feedback
    body["vermoeden"] = session.suspicion
    body["open_vraag"] = session.developer_question
    body["events_included"] = session.include_events
    hosts = session_hosts(session)
    inventory = _inventory_names(session)
    tokens = collect_tokens({"inventory": inventory, "session": body})
    masks = _report_name_masks(body, inventory, hosts) if redact else None
    if redact:
        body = redact_payload(body, tokens=tokens, hosts=hosts, masks=masks)
        sharing = SHARING_WARNING
    else:
        sharing = RAW_LOCAL_WARNING
    report, frontmatter = render_report(body)
    if redact:
        # Second pass: headings, feedback, and every other line of the report.
        report = redact_text(report, tokens, hosts, masks)
        frontmatter = redact_text(frontmatter, tokens, hosts, masks)
    report = _localise_utc_text(report)
    frontmatter = _localise_utc_text(frontmatter)
    message = f"{report}\n{sharing}"
    file_path = ""
    file_error = ""
    if save_file and redact:
        file_path, file_error = _save_report_file(
            report, str(body.get("installatie_id") or "")
        )
        if file_path:
            message += (
                f"\nHet volledige rapport staat ook als bestand: {file_path}. "
                "Laat de tester dat bestand ongewijzigd meesturen. "
                "Schrijf geen eigen samenvatting in de plaats ervan."
            )
        else:
            message += f"\nHet rapport kon niet als bestand bewaard worden ({file_error})."
    offer = offer_sentence()
    if offer:
        message = f"{message}\n{offer}"
    return ToolResult(
        message,
        {
            "ok": True,
            "kind": "export",
            "redacted": redact,
            "sharing": sharing,
            "report": report,
            "frontmatter": frontmatter,
            "file_path": file_path,
            "file_error": file_error,
            **body,
        },
    )


async def send_report(
    session: GatewaySession,
    *,
    confirmed: bool = False,
    korte_fout: str = "",
    feedback: str = "",
    include_events: bool | None = None,
    vermoeden: str = "",
    open_vraag: str = "",
) -> ToolResult:
    """Show the filtered report. After an explicit yes, show copyable text.

    Nothing is sent from this process. The tester copies the report, the
    address, and the masked subject into their own mail program. A mailto
    link is only an extra. Without an intake address the option is
    unavailable. With the feature flag off, only the local report remains.
    """
    if not report_send_enabled():
        return ToolResult(
            disabled_message(),
            {"ok": False, "kind": "report_disabled", "sent": False, "mailto": None},
        )
    address = intake_address()
    if not address:
        return ToolResult(
            unavailable_message(),
            {"ok": False, "kind": "report_unavailable", "sent": False, "mailto": None},
        )
    exported = await export_session(
        session,
        redact=True,
        feedback=feedback,
        include_events=include_events,
        vermoeden=vermoeden,
        open_vraag=open_vraag,
    )
    report = str(exported.data.get("report") or "")
    file_path = str(exported.data.get("file_path") or "")
    file_line = (
        f"\nHet rapport staat ook als bestand: {file_path}. "
        "Voeg dat bestand ongewijzigd toe als bijlage."
        if file_path
        else ""
    )
    if not confirmed:
        return ToolResult(
            preview_message(report) + file_line,
            {
                "ok": True,
                "kind": "report_preview",
                "confirmed": False,
                "sent": False,
                "mailto": None,
                "report": report,
                "file_path": file_path,
            },
        )
    frontmatter = str(exported.data.get("frontmatter") or "")
    # Same map as the report. The mapping itself is not returned.
    raw_body = _export_body(session)
    hosts = session_hosts(session)
    inventory = _inventory_names(session)
    tokens = collect_tokens({"inventory": inventory, "session": raw_body})
    masks = _report_name_masks(raw_body, inventory, hosts)
    subject = subject_line(
        str(exported.data.get("installatie_id") or ""),
        korte_fout,
        tokens=tokens,
        hosts=hosts,
        masks=masks,
    )
    link = mailto_link(
        address,
        subject,
        email_body(section_map(exported.data), frontmatter),
    )
    return ToolResult(
        sent_message(address, subject, report, link) + file_line,
        {
            "ok": True,
            "kind": "report_mailto",
            "confirmed": True,
            "sent": False,
            "mailto": link,
            "subject": subject,
            "address": address,
            "file_path": file_path,
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
                        f"'{SWITCH_NAME}' staat uit "
                        f"(Nederlands: '{SWITCH_NAME_NL}')."
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
    for key in ("level", "semantic_type", "module_ip", "room", "dim_gamma", "default_fade"):
        if key in device:
            row[key] = device[key]
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
    timing = _reply_timing(module)
    entry["reachability"] = timing["reachability"]
    entry["reachability_sentence"] = timing["sentence"]
    if timing["note"]:
        entry["reachability_note"] = timing["note"]
    return entry


def _optional_ms(value: Any) -> int | None:
    """A non-negative integer from the gateway. Booleans are not milliseconds."""
    if type(value) is int and value >= 0:
        return value
    return None


def _reply_timing(module: dict[str, Any]) -> dict[str, Any]:
    """Per-module reply timing. Present fields mean this gateway supports it."""
    raw = module.get("reachability")
    if "reachability" not in module or not isinstance(raw, dict):
        note = f"Bereikbaarheid is {MSG_NOT_IN_THIS_GATEWAY_VERSION}."
        return {"reachability": None, "note": note, "sentence": note}
    last_reply_at = raw.get("last_reply_at")
    if not isinstance(last_reply_at, str) or not last_reply_at.strip():
        last_reply_at = None
    else:
        last_reply_at = last_reply_at.strip()
    missed = raw.get("missed_replies")
    if type(missed) is not int or missed < 0:
        missed = None
    parsed = {
        "last_reply_at": last_reply_at,
        "last_reply_ms": _optional_ms(raw.get("last_reply_ms")),
        "avg_reply_ms": _optional_ms(raw.get("avg_reply_ms")),
        "missed_replies": missed,
    }
    return {
        "reachability": parsed,
        "note": "",
        "sentence": _reachability_sentence(module, parsed),
    }


def _reachability_sentence(module: dict[str, Any], parsed: dict[str, Any]) -> str:
    name = module.get("name") or module.get("id") or "deze module"
    quiet = (
        parsed["last_reply_at"] is None
        and parsed["last_reply_ms"] is None
        and parsed["avg_reply_ms"] is None
        and parsed["missed_replies"] in (0, None)
    )
    if quiet:
        return f"{name}: nog geen antwoord gemeten."
    bits: list[str] = []
    last_ms = parsed["last_reply_ms"]
    last_at = parsed["last_reply_at"]
    if last_ms is not None and last_at:
        bits.append(f"laatste antwoord {last_ms} ms om {last_at}")
    elif last_ms is not None:
        bits.append(f"laatste antwoord {last_ms} ms")
    elif last_at:
        bits.append(f"laatste antwoord om {last_at}")
    if parsed["avg_reply_ms"] is not None:
        bits.append(f"gemiddeld {parsed['avg_reply_ms']} ms")
    if parsed["missed_replies"] is not None:
        bits.append(f"{parsed['missed_replies']} keer geen antwoord")
    return f"{name}: " + ", ".join(bits) + "."


def _reported_sentence(reported: Any) -> str:
    if not isinstance(reported, dict):
        return ""
    bits: list[str] = []
    state = reported.get("state")
    if isinstance(state, str) and state.strip():
        bits.append(f"status {state.strip()}")
    level = reported.get("level_percent")
    if type(level) is int:
        bits.append(f"niveau {level}%")
    if not bits:
        return ""
    return " De module meldt " + " en ".join(bits) + "."


def _device_display_name(session: GatewaySession, device_id: str) -> str:
    record = session.devices.get(device_id)
    if isinstance(record, dict) and isinstance(record.get("name"), str):
        return record["name"].strip()
    return ""


def _command_result_line(
    *,
    action: str,
    value: int | None,
    name: str,
    device_id: str,
    ok: bool,
    error: str,
    module_confirmed: bool | None,
    confirm_ms: int | None,
    reported: dict[str, Any] | None,
) -> str:
    bits = [action]
    if value is not None:
        bits.append(str(value))
    if name:
        bits.append(name)
    if device_id:
        bits.append(device_id)
    if ok:
        bits.append("ok")
    elif error:
        bits.append(f"fout {error}")
    else:
        bits.append("fout")
    if module_confirmed is True:
        bits.append("bevestigd")
        if confirm_ms is not None:
            bits.append(f"{confirm_ms} ms")
    else:
        bits.append("niet bevestigd")
    if isinstance(reported, dict):
        state = reported.get("state")
        if isinstance(state, str) and state.strip():
            bits.append(f"status {state.strip()}")
        level = reported.get("level_percent")
        if type(level) is int:
            bits.append(f"niveau {level}%")
    return " ".join(bits)


async def _record_command_result(
    session: GatewaySession,
    *,
    device_id: str,
    action: str,
    value: int | None,
    ok: bool,
    error: str,
    module_confirmed: bool | None,
    confirm_ms: int | None,
    reported: dict[str, Any] | None,
    confirmation_available: bool,
    note: str = "",
    readback: dict[str, Any] | None = None,
) -> None:
    """Store one sent command. Previews never call this."""
    name = _device_display_name(session, device_id)
    message = _command_result_line(
        action=action,
        value=value,
        name=name,
        device_id=device_id,
        ok=ok,
        error=error,
        module_confirmed=module_confirmed,
        confirm_ms=confirm_ms,
        reported=reported,
    )
    if isinstance(readback, dict):
        if not readback.get("available"):
            message += f" nalezen niet gelukt ({readback.get('reason') or 'onbekend'})"
        elif not readback.get("answered"):
            message += " nalezen geen antwoord"
        else:
            level = readback.get("level_percent")
            message += f" nagelezen {level}% ({readback.get('raw') or ''})"
            if readback.get("matches_request") is False:
                message += " WIJKT AF van de gevraagde stand"
    if note:
        message = f"{note} {message}"
    event: dict[str, Any] = {
            "type": "command_result",
            "received_at": _format_local(datetime.now().astimezone()),
            "device_id": device_id,
            "action": action,
            "value": value,
            "ok": ok,
            "error": error,
            "module_confirmed": module_confirmed,
            "confirm_ms": confirm_ms,
            "reported": reported,
            "confirmation_available": confirmation_available,
            "message": message,
    }
    if note:
        event["translation"] = note
    if name:
        event["name"] = name
    if readback is not None:
        event["readback"] = readback
    await session.buffer.append(event)


_DECODE_FIELD_KEYS = ("family", "action", "channel", "state", "state_code", "dialect_id")


def _decode_result_event(decoded: dict[str, Any] | None) -> dict[str, Any]:
    """One decode, short enough for the report. No raw decoder dump."""
    matches: list[dict[str, Any]] = []
    dialect_ids: list[str] = []
    hex_text = ""
    matched = False
    if isinstance(decoded, dict):
        hex_text = str(decoded.get("hex") or "")
        matched = bool(decoded.get("matched"))
        for match in decoded.get("matches") or []:
            if not isinstance(match, dict):
                continue
            fields = match.get("fields") if isinstance(match.get("fields"), dict) else {}
            short: dict[str, Any] = {}
            decoder = match.get("decoder")
            if isinstance(decoder, str) and decoder:
                short["decoder"] = decoder
            for key in _DECODE_FIELD_KEYS:
                value = fields.get(key)
                if key == "dialect_id" and isinstance(value, str) and value:
                    full = full_dialect_id(value)
                    if full:
                        short[key] = full
                        if full not in dialect_ids:
                            dialect_ids.append(full)
                elif isinstance(value, str) and value:
                    short[key] = value
                elif type(value) is int:
                    short[key] = value
            if short:
                matches.append(short)
    dialect_id = dialect_ids[0] if dialect_ids else ""
    if not matched:
        line = f"{hex_text} niet herkend".strip()
    else:
        decoders = ", ".join(str(item.get("decoder")) for item in matches if item.get("decoder"))
        bits = [hex_text, "herkend", decoders]
        bits.append("dialect " + ", ".join(dialect_ids) if dialect_ids else "geen dialect-id")
        for item in matches:
            for key in ("action", "channel", "state"):
                if key in item:
                    bits.append(f"{key} {item[key]}")
        line = " ".join(bit for bit in bits if bit)
    event: dict[str, Any] = {
        "type": "decode_result",
        "received_at": _format_local(datetime.now().astimezone()),
        "hex": hex_text,
        "matched": matched,
        "fields": matches,
        "message": line,
    }
    if dialect_id:
        event["dialect_id"] = dialect_id
        event["dialect_ids"] = dialect_ids
    return event


def _command_confirmation(body: Any, action: str) -> dict[str, Any]:
    """Read module_confirmed from a command body. Missing fields are an older gateway."""
    if not isinstance(body, dict) or "module_confirmed" not in body:
        message = (
            f"{COMMAND_WARNING} "
            f"Of de module dat bevestigde is {MSG_NOT_IN_THIS_GATEWAY_VERSION}."
        )
        return {
            "available": False,
            "module_confirmed": None,
            "confirm_ms": None,
            "reported": None,
            "message": message,
        }
    confirmed = body.get("module_confirmed") is True
    confirm_ms = _optional_ms(body.get("confirm_ms"))
    reported = body.get("reported") if isinstance(body.get("reported"), dict) else None
    if action == "DIM_START" and not confirmed:
        message = (
            "DIM_START is verstuurd. Die actie wacht niet op een antwoord, "
            "dus de module bevestigt niets."
        )
    elif confirmed:
        when = f" in {confirm_ms} ms" if confirm_ms is not None else ""
        message = f"De module heeft geantwoord{when}.{_reported_sentence(reported)}"
    else:
        message = (
            "De gateway heeft het commando verstuurd. "
            "De module heeft niet geantwoord."
        )
    return {
        "available": True,
        "module_confirmed": confirmed,
        "confirm_ms": confirm_ms if confirmed else None,
        "reported": reported,
        "message": message,
    }


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


_CONNECTION_WAIT = (
    "De live-verbinding is connecting. "
    "connected op de gateway betekent dat hij antwoordt, niet dat gebeurtenissen al binnenkomen. "
    "Zeg connected pas als connection connected is. Dat is hetzelfde woord als bij de gebeurtenissen."
)


def _connection_note(live: str) -> str:
    if live == "connected":
        return "connection is connected, hetzelfde woord als bij de gebeurtenissen."
    if live == "connecting":
        return _CONNECTION_WAIT
    return f"connection is {live}."


def _buffer_summary(session: GatewaySession) -> dict[str, Any]:
    gaps = session.gap_events()
    live = session.event_stream_state()
    return {
        "count": len(session.buffer),
        "dropped": session.buffer.dropped,
        "gaps": len(gaps),
        "last_gap": gaps[-1] if gaps else None,
        "connection": live,
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


def _inventory_names(session: GatewaySession) -> dict[str, list[dict[str, Any]]]:
    """Device and module records whose names and rooms must leave the report."""
    return {
        "devices": [item for item in session.devices.values() if isinstance(item, dict)],
        "modules": [item for item in session.modules.values() if isinstance(item, dict)],
    }


_EXPORT_TYPES = {
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
    "command_result",
    "decode_result",
    "raw_send_result",
}


_POLL_MARKERS = ("idle", "keepalive", "poll")
_SESSION_GRACE = timedelta(seconds=5)


def _fields_are_poll(fields: dict[str, Any]) -> bool:
    family = str(fields.get("family") or "")
    if family == "relay_reply_candidate":
        return True
    blob = " ".join(
        str(fields.get(key) or "") for key in ("family", "action", "dialect_id")
    ).lower()
    return any(marker in blob for marker in _POLL_MARKERS)


def _frame_kind(decoded: dict[str, Any] | None) -> str:
    """``poll``, ``confirming``, or ``other``.

    A frame that confirms something stays confirming even when another match
    is a poll. An unrecognized frame is ``other``.
    """
    if not isinstance(decoded, dict) or not decoded.get("matched"):
        return "other"
    saw_confirming = False
    saw_poll = False
    for match in decoded.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fields = match.get("fields") if isinstance(match.get("fields"), dict) else {}
        if _fields_are_poll(fields):
            saw_poll = True
        else:
            saw_confirming = True
    if saw_confirming:
        return "confirming"
    if saw_poll:
        return "poll"
    return "other"


def _full_ids_from_decode(decoded: dict[str, Any] | None) -> list[str]:
    found: list[str] = []
    if not isinstance(decoded, dict):
        return found
    for match in decoded.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fields = match.get("fields") if isinstance(match.get("fields"), dict) else {}
        full = full_dialect_id(str(fields.get("dialect_id") or ""))
        if full and full not in found:
            found.append(full)
    return found


def _remember_frame_dialects(item: dict[str, Any], decoded: dict[str, Any] | None) -> None:
    """Copy full dialect ids onto the frame. Not the raw decode, not the city name.

    The decode can carry module addresses. The report only needs the full
    dialect id, so a confirming frame and the frontmatter can name it.
    """
    item["frame_kind"] = _frame_kind(decoded)
    found = _full_ids_from_decode(decoded)
    own = item.get("dialect_id")
    if isinstance(own, str):
        full = full_dialect_id(own)
        if full and full not in found:
            found.insert(0, full)
    for raw in item.get("dialect_ids") or []:
        if not isinstance(raw, str):
            continue
        full = full_dialect_id(raw)
        if full and full not in found:
            found.append(full)
    if not found:
        item.pop("dialect_id", None)
        item.pop("dialect_ids", None)
        item.pop("dialect_name", None)
        return
    item["dialect_ids"] = found
    item["dialect_id"] = found[0]
    name = dialect_name(found[0])
    if name:
        item["dialect_name"] = name
    else:
        item.pop("dialect_name", None)


def _within_session(event: dict[str, Any], received_at: datetime, started_at: datetime) -> bool:
    """True when the event belongs to this toolkit session.

    A gateway clock (``ts``, ``timestamp``, ``time``) wins, so a log line
    replayed from last night stays out even though it arrived just now.
    Live events without that clock use the moment the toolkit stored them.
    """
    moment = _parse_gateway_time(event) or received_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    start = started_at if started_at.tzinfo is not None else started_at.replace(tzinfo=timezone.utc)
    return moment >= start - _SESSION_GRACE


async def _record_capture_decodes(session: GatewaySession, frames: list[dict[str, Any]]) -> None:
    """One determination per full dialect id, plus at most one miss and one plain match."""
    seen: set[str] = set()
    plain = False
    miss = False
    for frame in frames:
        decoded = frame.get("local_decode")
        event = _decode_result_event(decoded if isinstance(decoded, dict) else None)
        ids = [item for item in event.get("dialect_ids") or [] if isinstance(item, str)]
        if ids:
            fresh = [item for item in ids if item not in seen]
            if not fresh:
                continue
            seen.update(fresh)
            event["dialect_id"] = fresh[0]
            event["dialect_ids"] = fresh
            event["source"] = "capture_frames"
            await session.buffer.append(event)
            continue
        if event.get("matched"):
            if plain:
                continue
            plain = True
        else:
            if miss:
                continue
            miss = True
        event["source"] = "capture_frames"
        await session.buffer.append(event)


def _export_body(session: GatewaySession) -> dict[str, Any]:
    started = session.started_at
    exported = [
        _stamp_event(entry.event, entry.received_at)
        for entry in session.buffer.entries()
        if entry.event.get("type") in _EXPORT_TYPES
        and _within_session(entry.event, entry.received_at, started)
    ]
    kept, note = limit_export_events(exported)
    status = session.status or {}
    return {
        "gateway": {
            "version": status.get("version"),
            "hub_role": status.get("hub_role"),
            "remote_debugging": status.get("remote_debugging"),
            "capabilities": _capabilities(status),
            "connection": session.event_stream_state(),
            "address": session.host,
        },
        # Random local id. The gateway instance id is a different value and
        # is not copied into the report.
        "installatie_id": installation_id(),
        "modules": _export_modules(session),
        "notes": [_stamp_note(note) for note in session.notes],
        "gaps": [event for event in kept if event.get("type") == "gap"],
        "events": kept,
        "appendix_note": note,
        "buffer": _buffer_summary(session),
    }


def _report_name_masks(
    body: dict[str, Any],
    inventory: dict[str, Any],
    hosts: set[str],
) -> dict[str, str]:
    """Masks for this report. Not included in the tool result."""
    names = collect_display_names({"inventory": inventory, "session": body}, hosts)
    return name_masks(names, _report_appearance(body, inventory))


def _report_appearance(body: dict[str, Any], inventory: dict[str, Any]) -> str:
    """Notes, then events, then inventory. First whole-word hit wins."""
    chunks: list[str] = []
    for note in body.get("notes") or []:
        if isinstance(note, dict) and isinstance(note.get("text"), str):
            chunks.append(note["text"])
    for event in body.get("events") or []:
        if not isinstance(event, dict):
            continue
        for key in ("message", "text", "name", "room", "descr", "gr", "module_name", "action"):
            value = event.get(key)
            if isinstance(value, str) and value:
                chunks.append(value)
    chunks.extend(_name_field_text(inventory))
    chunks.extend(_name_field_text(body.get("modules")))
    return "\n".join(chunks)


def _name_field_text(node: Any) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"descr", "gr", "module_name", "name", "room"} and isinstance(item, str):
                    found.append(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return found


def _export_modules(session: GatewaySession) -> list[dict[str, Any]]:
    """Type and model for the report. The name is included so redaction can drop it."""
    modules = []
    for module in session.modules.values():
        if not isinstance(module, dict):
            continue
        modules.append(
            {
                "type": module.get("type"),
                "model": module.get("model"),
                "name": module.get("name"),
            }
        )
    return modules


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


def _raw_rejected(code: str) -> ToolResult:
    return ToolResult(
        _RAW_ERROR_TEXT[code],
        {"ok": False, "kind": code, "sent": False},
    )


def _raw_error_code(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("error", "code"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return ""


def _raw_module_ip(value: str) -> str | None:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    if not isinstance(addr, ipaddress.IPv4Address):
        return None
    if (
        addr.is_multicast
        or addr.is_unspecified
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr == ipaddress.IPv4Address("255.255.255.255")
    ):
        return None
    return str(addr)


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
    text = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
    if len(text) >= 11 and text[10] == " ":
        text = text[:10] + "T" + text[11:]
    if "T" in text:
        text = text.replace(",", ".", 1)
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
    hosts = session_hosts(session)
    cleaned: list[dict[str, Any]] = []
    for line in lines:
        item = dict(line)
        message = item.get("message")
        if isinstance(message, str):
            item["message"] = redact_text(message, tokens, hosts)
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
    include_polls: bool = True,
    skipped: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Frames after ``since``, until ``limit`` matches or ``seconds`` elapses.

    Without ``include_polls`` a routine poll or keepalive is counted in
    ``skipped["polls"]`` and not returned.
    """

    def matching(event: dict[str, Any]) -> bool:
        return event.get("type") == "udp_frame" and _frame_matches(
            event, direction=direction, module=module, pattern=pattern
        )

    def gathered() -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        polls = 0
        for entry in session.buffer.since(since, types={"udp_frame"}):
            if not matching(entry.event):
                continue
            item = _with_local_decode(entry.event)
            if not include_polls and _frame_kind(item.get("local_decode")) == "poll":
                polls += 1
                continue
            found.append(item)
            if len(found) >= limit:
                break
        if skipped is not None:
            skipped["polls"] = polls
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
