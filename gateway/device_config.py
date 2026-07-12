"""Northbound field validation and devices.json mutation for PATCH /api/v1/devices.

Pure validation + mutation logic, kept separate from auto_discovery (discovery
scope) and installation.py (parsing/schema only).
"""

from __future__ import annotations

from gateway.installation import InstallationConfig

NORTHBOUND_CHANNEL_FIELDS = {"name", "room", "semantic_type", "active", "max_watt"}
NORTHBOUND_BUTTON_FIELDS = {"name", "room", "active"}
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


def validate_button_fields(fields: dict) -> dict:
    """Validate and normalize northbound button fields from a PATCH body."""
    unknown = set(fields.keys()) - NORTHBOUND_BUTTON_FIELDS
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


def apply_button_patch(
    installation: InstallationConfig,
    button_id: str,
    fields: dict,
) -> None:
    """Apply validated northbound fields to a button in-memory."""
    btn = installation.button_by_id(button_id)
    if btn is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Button {button_id!r} not found",
            {"device_id": button_id},
        )
    for key, value in fields.items():
        setattr(btn, key, value)


def installation_to_raw_dict(installation: InstallationConfig) -> dict:
    """Serialize installation to devices.json shape.

    Always includes ``buttons`` so PATCH writes never drop the top-level
    buttons array (regression guard for forced-discovery rewrite path).
    """
    return {
        "modules": [m.to_dict() for m in installation.modules],
        "buttons": [b.to_dict() for b in installation.buttons],
    }
