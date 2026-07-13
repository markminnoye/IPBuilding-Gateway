"""Northbound field validation and devices.json mutation for PATCH /api/v1/devices.

Pure validation + mutation logic, kept separate from auto_discovery (discovery
scope) and installation.py (parsing/schema only).
"""

from __future__ import annotations

from gateway.installation import InstallationConfig, InstallationError

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


def validate_channel_fields(fields: dict) -> dict:
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


def installation_to_raw_dict(installation: InstallationConfig) -> dict:
    """Serialize installation to devices.json shape.

    No separate "buttons" key: each module's own to_dict() already carries
    its nested pushbuttons/detectors (or channels), so there is no write
    path left that can independently forget to include them.
    """
    return {
        "modules": [m.to_dict() for m in installation.modules],
    }
