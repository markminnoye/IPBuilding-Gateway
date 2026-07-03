"""Shared validate/apply path for devices.json (API + discovery)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from gateway.installation import InstallationConfig, InstallationError
from gateway.installation_merge import (
    INSTALLATION_MODES,
    collect_warnings,
    merge_installation,
    merge_preview,
)

log = logging.getLogger(__name__)


def validate_installation_body(
    body: dict[str, Any],
    current: InstallationConfig | None,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    """Dry-run merge + schema parse. Does not write to disk."""
    mode = mode or body.get("mode", "merge_modules")
    if mode not in INSTALLATION_MODES:
        return {
            "ok": False,
            "errors": [f"Unknown mode {mode!r}"],
            "warnings": [],
        }

    current_dict = current.to_dict() if current else None
    try:
        merged = merge_installation(current_dict, body, mode)
        InstallationConfig._parse(merged)
    except InstallationError as exc:
        return {
            "ok": False,
            "errors": [str(exc)],
            "warnings": [],
        }
    except ValueError as exc:
        return {
            "ok": False,
            "errors": [str(exc)],
            "warnings": [],
        }

    warnings = collect_warnings(merged)
    preview = merge_preview(current_dict, body, mode)
    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "preview": preview,
    }


def apply_installation_body(
    body: dict[str, Any],
    current: InstallationConfig | None,
    *,
    mode: str | None = None,
    writer: Any,
    devices_file: str,
    on_installation_changed: Callable[[InstallationConfig], None] | None = None,
) -> dict[str, Any]:
    """Merge, validate, atomically write, reload, and invoke callback."""
    mode = mode or body.get("mode", "merge_modules")
    validation = validate_installation_body(body, current, mode=mode)
    if not validation["ok"]:
        return {
            "ok": False,
            "errors": validation["errors"],
            "warnings": validation.get("warnings", []),
            "reload": False,
        }

    current_dict = current.to_dict() if current else None
    merged = merge_installation(current_dict, body, mode)
    module_count = len(merged.get("modules", []))
    channel_count = sum(len(m.get("channels", [])) for m in merged.get("modules", []))

    if not writer.write(merged):
        return {
            "ok": False,
            "errors": ["Failed to acquire lock on devices.json"],
            "warnings": validation.get("warnings", []),
            "reload": False,
        }

    try:
        new_inst = InstallationConfig.load(devices_file)
    except InstallationError as exc:
        log.error(
            "apply_installation: devices.json written (%d modules) but reload failed: %s",
            module_count,
            exc,
        )
        return {
            "ok": False,
            "errors": [f"Reload failed after write: {exc}"],
            "warnings": validation.get("warnings", []),
            "reload": False,
        }

    if on_installation_changed is not None:
        try:
            on_installation_changed(new_inst)
        except Exception:
            log.exception("apply_installation: on_installation_changed callback failed")

    log.info(
        "applied installation: %d modules, %d channels (mode=%s)",
        module_count,
        channel_count,
        mode,
    )
    return {
        "ok": True,
        "applied": {"modules": module_count, "channels": channel_count},
        "warnings": validation.get("warnings", []),
        "reload": True,
    }
