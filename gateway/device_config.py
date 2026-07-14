"""Northbound field validation and devices.json mutation for PATCH /api/v1/devices.

Pure validation + mutation logic, kept separate from auto_discovery (discovery
scope) and installation.py (parsing/schema only).
"""

from __future__ import annotations

from gateway.installation import InstallationConfig, InstallationError, PushbuttonConfig
from gateway.module_metadata import (
    ModuleMetadataCache,
    extract_pushbuttons_from_getbuttons,
    normalize_button_hardware_id,
)
from gateway.types import DeviceType

NORTHBOUND_CHANNEL_FIELDS = {"name", "room", "semantic_type", "active", "max_watt"}
NORTHBOUND_PUSHBUTTON_FIELDS = {"name", "room", "active"}
SEMANTIC_TYPES = {"light", "fan", "cover", "switch", "plug"}


class DeviceConfigError(Exception):
    """Raised when PATCH body validation or mutation fails."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def validate_channel_fields(
    fields: dict,
    module_type: DeviceType | None = None,
) -> dict:
    """Validate and normalize northbound channel fields from a PATCH body."""
    unknown = set(fields.keys()) - NORTHBOUND_CHANNEL_FIELDS
    if unknown:
        raise DeviceConfigError(
            "unknown_field",
            f"Unknown field(s): {', '.join(sorted(unknown))}",
            {"fields": sorted(unknown)},
        )

    result: dict = {}
    for key, value in fields.items():
        if key == "name":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "name must be a string")
            result["name"] = value
        elif key == "room":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "room must be a string")
            result["room"] = value
        elif key == "semantic_type":
            if not isinstance(value, str) or value not in SEMANTIC_TYPES:
                raise DeviceConfigError(
                    "validation",
                    f"semantic_type must be one of {sorted(SEMANTIC_TYPES)}",
                    {"allowed": sorted(SEMANTIC_TYPES)},
                )
            if module_type == DeviceType.DIMMER and value != "light":
                raise DeviceConfigError(
                    "validation",
                    "dimmer channels only support semantic_type 'light'",
                    {"allowed": ["light"]},
                )
            result["semantic_type"] = value
        elif key == "active":
            if not isinstance(value, bool):
                raise DeviceConfigError("validation", "active must be a boolean")
            result["active"] = value
        elif key == "max_watt":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DeviceConfigError(
                    "validation",
                    "max_watt must be a non-negative integer",
                )
            result["max_watt"] = value
    return result


def validate_pushbutton_fields(fields: dict) -> dict:
    """Validate and normalize northbound pushbutton fields from a PATCH body."""
    unknown = set(fields.keys()) - NORTHBOUND_PUSHBUTTON_FIELDS
    if unknown:
        raise DeviceConfigError(
            "unknown_field",
            f"Unknown field(s): {', '.join(sorted(unknown))}",
            {"fields": sorted(unknown)},
        )

    result: dict = {}
    for key, value in fields.items():
        if key == "name":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "name must be a string")
            result["name"] = value
        elif key == "room":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "room must be a string")
            result["room"] = value
        elif key == "active":
            if not isinstance(value, bool):
                raise DeviceConfigError("validation", "active must be a boolean")
            result["active"] = value
    return result


def validate_devices_document(raw: object) -> dict:
    """Validate a full devices.json document for import (POST /api/v1/devices/import).

    Runs it through InstallationConfig._parse — the same code the gateway uses
    at boot — so "if it imports, the gateway boots with it". Returns ``raw``
    unchanged on success. Raises DeviceConfigError (matching the PATCH error
    model) on any structural problem: not a dict, invalid module type,
    duplicate MAC/IP/device id, or the old flat top-level "buttons" format.
    """
    if not isinstance(raw, dict):
        raise DeviceConfigError(
            "invalid_devices_file", "Document must be a JSON object"
        )
    try:
        InstallationConfig._parse(raw)
    except InstallationError as exc:
        raise DeviceConfigError("invalid_devices_file", str(exc)) from exc
    return raw


def apply_channel_patch(
    installation: InstallationConfig,
    module_ip: str,
    ch: int,
    fields: dict,
) -> None:
    """Apply validated northbound fields to a channel in-memory."""
    mc = installation.module_by_ip(module_ip)
    if mc is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Module {module_ip!r} not found",
            {"module_ip": module_ip},
        )
    ch_cfg = next((c for c in mc.channels if c.ch == ch), None)
    if ch_cfg is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Channel {ch} not found on module {module_ip}",
            {"module_ip": module_ip, "channel": ch},
        )
    for key, value in fields.items():
        setattr(ch_cfg, key, value)


def apply_pushbutton_patch(
    installation: InstallationConfig,
    button_id: str,
    fields: dict,
) -> None:
    """Apply validated northbound fields to a pushbutton in-memory."""
    btn = installation.pushbutton_by_id(button_id)
    if btn is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Pushbutton {button_id!r} not found",
            {"device_id": button_id},
        )
    for key, value in fields.items():
        setattr(btn, key, value)


def sync_input_pushbuttons_from_cache(
    installation: InstallationConfig,
    meta_cache: ModuleMetadataCache,
    module_mac: str | None = None,
) -> int:
    """Merge cached getButtons data into input modules in *installation*.

    Preserves operator-edited ``name``, ``room``, ``active``, and
    ``hold_threshold_s`` on existing pushbuttons. Fills missing ``channel``,
    ``name``, and ``room`` from wire data. Appends newly discovered button
    ids without removing entries absent from the wire.

    Rebuilds the flat ``installation.pushbuttons`` index. Returns the
    number of input modules that had cached button data applied.
    """
    target_mac = module_mac.lower() if module_mac else None
    updated = 0

    for mc in installation.modules:
        if mc.type != DeviceType.INPUT:
            continue
        mac = mc.mac.lower()
        if target_mac is not None and mac != target_mac:
            continue
        meta = meta_cache.get(mac)
        if meta is None or not meta.buttons:
            continue

        wire_buttons = extract_pushbuttons_from_getbuttons(mac, meta.buttons)
        wire_by_id = {btn.id: btn for btn in wire_buttons}

        merged: list[PushbuttonConfig] = []
        seen_ids: set[str] = set()

        for existing in mc.pushbuttons:
            canonical_id = normalize_button_hardware_id(existing.id)
            wire = wire_by_id.get(canonical_id)
            if wire is not None:
                merged.append(
                    PushbuttonConfig(
                        id=canonical_id,
                        module_id=mac,
                        channel=(
                            existing.channel
                            if existing.channel is not None
                            else wire.channel
                        ),
                        name=existing.name or wire.name,
                        room=existing.room or wire.room,
                        active=existing.active,
                        hold_threshold_s=existing.hold_threshold_s,
                    )
                )
            else:
                merged.append(
                    PushbuttonConfig(
                        id=canonical_id,
                        module_id=mac,
                        channel=existing.channel,
                        name=existing.name,
                        room=existing.room,
                        active=existing.active,
                        hold_threshold_s=existing.hold_threshold_s,
                    )
                )
            seen_ids.add(canonical_id)

        for wire in wire_buttons:
            if wire.id in seen_ids:
                continue
            merged.append(wire)
            seen_ids.add(wire.id)

        mc.pushbuttons = merged
        updated += 1

    all_buttons: list[PushbuttonConfig] = []
    pushbuttons_by_id: dict[str, PushbuttonConfig] = {}
    for mc in installation.modules:
        if mc.type != DeviceType.INPUT:
            continue
        for btn in mc.pushbuttons:
            all_buttons.append(btn)
            pushbuttons_by_id[btn.id.lower()] = btn

    installation.pushbuttons = all_buttons
    installation._pushbuttons_by_id = pushbuttons_by_id
    return updated


def installation_to_raw_dict(installation: InstallationConfig) -> dict:
    """Serialize installation to devices.json shape.

    No separate "buttons" key: each module's own to_dict() already carries
    its nested pushbuttons/detectors (or channels), so there is no write
    path left that can independently forget to include them.
    """
    return {
        "modules": [m.to_dict() for m in installation.modules],
    }
