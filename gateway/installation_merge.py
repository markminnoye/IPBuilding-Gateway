"""Merge engine for devices.json import (policy A).

Northbound fields on existing channels are never overwritten by import.
Network fields (ip, mac, firmware, model) are updated when import supplies
a value. Top-level ``buttons[]`` are preserved unless ``replace`` mode
explicitly passes ``"buttons": []``.
"""

from __future__ import annotations

import copy
from typing import Any

from gateway.installation import _normalize_mac

INSTALLATION_MODES = frozenset({
    "replace",
    "merge_modules",
    "append_modules",
    "import_channels",
})

NORTHBOUND_FIELDS = ("name", "room", "active", "max_watt", "semantic_type")
NETWORK_FIELDS = ("ip", "mac", "firmware", "model")


def _empty_dict() -> dict[str, Any]:
    return {"modules": [], "buttons": []}


def _module_key(mod: dict[str, Any]) -> tuple[str, str]:
    mac = mod.get("mac", "")
    if mac:
        return ("mac", _normalize_mac(mac))
    return ("ip", mod.get("ip", ""))


def _find_module_index(modules: list[dict[str, Any]], imported: dict[str, Any]) -> int | None:
    imp_mac = imported.get("mac", "")
    imp_ip = imported.get("ip", "")
    if imp_mac:
        norm = _normalize_mac(imp_mac)
        for i, mod in enumerate(modules):
            if mod.get("mac") and _normalize_mac(mod["mac"]) == norm:
                return i
    if imp_ip:
        for i, mod in enumerate(modules):
            if mod.get("ip") == imp_ip:
                return i
    return None


def _is_default_name(name: str | None, module_ip: str, ch: int) -> bool:
    if not name:
        return True
    if name == module_ip:
        return True
    return name == f"Ch {ch}"


def _is_default_room(room: str | None) -> bool:
    return not room or room == "Unconfigured"


def _find_channel_index(channels: list[dict[str, Any]], ch: int) -> int | None:
    for i, entry in enumerate(channels):
        if entry.get("ch") == ch:
            return i
    return None


def _merge_channel_network_and_shim(
    existing: dict[str, Any],
    imported: dict[str, Any],
    *,
    module_ip: str,
    is_new: bool,
) -> dict[str, Any]:
    out = copy.deepcopy(existing)
    ch = imported.get("ch", out.get("ch"))

    if is_new:
        out["ch"] = ch
        out["name"] = imported.get("name") or f"Ch {ch}"
        out["room"] = imported.get("room") or "Unconfigured"
        out["semantic_type"] = imported.get("semantic_type", "light")
        out["active"] = imported.get("active", False)
        out["max_watt"] = imported.get("max_watt", 0)
        if imported.get("ipbox_id") is not None:
            out["ipbox_id"] = imported["ipbox_id"]
        if imported.get("id"):
            out["id"] = imported["id"]
        return out

    # Policy A: preserve northbound on existing channels.
    if imported.get("ipbox_id") is not None and not out.get("ipbox_id"):
        out["ipbox_id"] = imported["ipbox_id"]
    if not out.get("id") and imported.get("id"):
        out["id"] = imported["id"]

    # Fill northbound only when existing value is empty/default.
    imp_name = imported.get("name")
    if imp_name and _is_default_name(out.get("name"), module_ip, ch):
        out["name"] = imp_name

    imp_room = imported.get("room")
    if imp_room and _is_default_room(out.get("room")):
        out["room"] = imp_room

    if out.get("max_watt", 0) == 0 and imported.get("max_watt"):
        out["max_watt"] = imported["max_watt"]

    imp_sem = imported.get("semantic_type")
    if imp_sem and (not out.get("semantic_type") or out.get("semantic_type") == "light"):
        if imp_sem != "light" or _is_default_name(out.get("name"), module_ip, ch):
            out["semantic_type"] = imp_sem

    return out


def _merge_module_network(existing: dict[str, Any], imported: dict[str, Any]) -> None:
    for field in NETWORK_FIELDS:
        val = imported.get(field)
        if not val:
            continue
        if field == "mac":
            existing["mac"] = _normalize_mac(val)
        else:
            existing[field] = val

    imp_name = imported.get("name")
    if imp_name and (not existing.get("name") or existing.get("name") == existing.get("ip")):
        existing["name"] = imp_name


def _merge_module_channels(
    existing: dict[str, Any],
    imported: dict[str, Any],
    *,
    import_channels_only: bool,
) -> tuple[int, int]:
    """Merge channel lists; return (channels_added, channels_updated)."""
    module_ip = existing.get("ip", "")
    channels = existing.setdefault("channels", [])
    added = 0
    updated = 0

    for imp_ch in imported.get("channels", []):
        ch_num = imp_ch.get("ch")
        if not isinstance(ch_num, int):
            continue
        idx = _find_channel_index(channels, ch_num)
        if idx is None:
            channels.append(
                _merge_channel_network_and_shim(
                    {}, imp_ch, module_ip=module_ip, is_new=True,
                )
            )
            added += 1
        else:
            merged = _merge_channel_network_and_shim(
                channels[idx], imp_ch, module_ip=module_ip, is_new=False,
            )
            if merged != channels[idx]:
                updated += 1
            channels[idx] = merged

    if not import_channels_only:
        return added, updated
    return added, updated


def _prepare_new_module(imported: dict[str, Any]) -> dict[str, Any]:
    mod = copy.deepcopy(imported)
    if mod.get("mac"):
        mod["mac"] = _normalize_mac(mod["mac"])
    channels_out: list[dict[str, Any]] = []
    module_ip = mod.get("ip", "")
    for imp_ch in mod.get("channels", []):
        ch_num = imp_ch.get("ch")
        if not isinstance(ch_num, int):
            continue
        channels_out.append(
            _merge_channel_network_and_shim(
                {}, imp_ch, module_ip=module_ip, is_new=True,
            )
        )
    mod["channels"] = channels_out
    if "name" not in mod or not mod["name"]:
        mod["name"] = mod.get("model") or module_ip
    return mod


def merge_preview(
    current: dict[str, Any] | None,
    incoming: dict[str, Any],
    mode: str,
) -> dict[str, int]:
    """Count modules/channels that would change (for validate preview)."""
    merged = merge_installation(current, incoming, mode)
    cur = current or _empty_dict()
    cur_mods = { _module_key(m): m for m in cur.get("modules", []) }
    merged_mods = { _module_key(m): m for m in merged.get("modules", []) }

    modules_added = len(set(merged_mods) - set(cur_mods))
    modules_updated = 0
    for key in set(cur_mods) & set(merged_mods):
        if cur_mods[key] != merged_mods[key]:
            modules_updated += 1

    cur_ch = sum(len(m.get("channels", [])) for m in cur.get("modules", []))
    new_ch = sum(len(m.get("channels", [])) for m in merged.get("modules", []))
    channels_added = max(0, new_ch - cur_ch)

    return {
        "modules_added": modules_added,
        "modules_updated": modules_updated,
        "channels_added": channels_added,
    }


def merge_installation(
    current: dict[str, Any] | None,
    incoming: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Return merged devices.json dict without persisting."""
    if mode not in INSTALLATION_MODES:
        raise ValueError(f"Unknown installation mode: {mode!r}")

    base = copy.deepcopy(current) if current else _empty_dict()
    imp_modules = incoming.get("modules", [])

    if mode == "replace":
        out: dict[str, Any] = {
            "modules": copy.deepcopy(imp_modules),
        }
        if "buttons" in incoming:
            out["buttons"] = copy.deepcopy(incoming["buttons"])
        else:
            out["buttons"] = copy.deepcopy(base.get("buttons", []))
        return out

    modules = copy.deepcopy(base.get("modules", []))

    if mode == "append_modules":
        for imp_mod in imp_modules:
            if _find_module_index(modules, imp_mod) is not None:
                continue
            modules.append(_prepare_new_module(imp_mod))
        return {"modules": modules, "buttons": copy.deepcopy(base.get("buttons", []))}

    import_channels_only = mode == "import_channels"

    for imp_mod in imp_modules:
        idx = _find_module_index(modules, imp_mod)
        if idx is None:
            if import_channels_only:
                continue
            modules.append(_prepare_new_module(imp_mod))
            continue

        existing = modules[idx]
        if not import_channels_only:
            _merge_module_network(existing, imp_mod)
        _merge_module_channels(
            existing, imp_mod, import_channels_only=import_channels_only,
        )

    return {"modules": modules, "buttons": copy.deepcopy(base.get("buttons", []))}


def collect_warnings(raw: dict[str, Any]) -> list[str]:
    """Non-fatal validation warnings for operator feedback."""
    warnings: list[str] = []
    for mod in raw.get("modules", []):
        ip = mod.get("ip", "?")
        if not mod.get("mac"):
            warnings.append(f"module {ip}: no MAC address")
        if not mod.get("channels"):
            warnings.append(f"module {ip}: no channels")
    return warnings
