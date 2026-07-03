"""Parse legacy IPBuilding central mobile UI HTML into devices.json schema."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

_TOGGLE_RE = re.compile(
    r"protocolToggleItem[^\"']*?(?:ip=|')(\d+\.\d+\.\d+\.\d+)[^\"']*?(?:ch=|')(\d+)",
    re.IGNORECASE,
)
_DIM_RE = re.compile(
    r"protocolSetDimValue[^\"']*?(?:ip=|')(\d+\.\d+\.\d+\.\d+)[\"']?[^\"']*?(?:ch=|')(\d+)",
    re.IGNORECASE,
)
_ADRES_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)-(\d{2})")

_ITEM_RE = re.compile(
    r'<div[^>]*onclick="([^"]*(?:protocolToggleItem|protocolSetDimValue)[^"]*)"[^>]*>'
    r".*?contentItemDescr[^>]*>([^<]+)<.*?"
    r"(?:contentItemType|contentItemGroup)[^>]*>([^<]+)<",
    re.DOTALL | re.IGNORECASE,
)


def _decode_text(value: str) -> str:
    return unquote(value).strip()


def _channel_int(ch_str: str) -> int:
    return int(ch_str, 10)


def _extract_from_onclick(onclick: str) -> tuple[str, int, str] | None:
    dim = _DIM_RE.search(onclick)
    if dim:
        return dim.group(1), _channel_int(dim.group(2)), "dimmer"
    toggle = _TOGGLE_RE.search(onclick)
    if toggle:
        return toggle.group(1), _channel_int(toggle.group(2)), "relay"
    adres = _ADRES_RE.search(onclick)
    if adres:
        return adres.group(1), _channel_int(adres.group(2)), "relay"
    return None


def parse_legacy_central_html(html: str) -> dict[str, Any]:
    """Convert searchItems / showGroupItems HTML to devices.json draft."""
    modules_by_ip: dict[str, dict[str, Any]] = {}

    for match in _ITEM_RE.finditer(html):
        onclick = match.group(1)
        parsed = _extract_from_onclick(onclick)
        if parsed is None:
            continue
        ip, ch, dev_type = parsed
        name = _decode_text(match.group(2)) or f"Ch {ch}"
        room = _decode_text(match.group(3))

        if ip not in modules_by_ip:
            modules_by_ip[ip] = {
                "name": ip,
                "ip": ip,
                "type": "relay",
                "firmware": "",
                "model": "",
                "mac": "",
                "channels": [],
            }
        mod = modules_by_ip[ip]
        if dev_type == "dimmer":
            mod["type"] = "dimmer"

        mod["channels"].append({
            "ch": ch,
            "name": name,
            "room": room or "Unconfigured",
            "semantic_type": "light",
            "active": False,
            "max_watt": 200 if mod["type"] == "dimmer" else 60,
        })

    modules = sorted(modules_by_ip.values(), key=lambda m: m["ip"])
    for mod in modules:
        mod["channels"].sort(key=lambda c: c["ch"])
        if mod["channels"]:
            mod["name"] = mod["channels"][0]["name"]

    return {"modules": modules}
