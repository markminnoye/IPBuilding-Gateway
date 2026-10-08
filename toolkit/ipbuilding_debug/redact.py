"""Strip addresses, hardware ids, and installation names from a session export.

Redaction is on by default. A local raw view is an explicit opt-out.
"""

from __future__ import annotations

import re
from typing import Any

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")

# Values under these keys are installation-specific. States, types, and
# versions are not in this set.
_SENSITIVE_KEYS = {
    "address",
    "descr",
    "device_id",
    "dst",
    "gr",
    "host",
    "id",
    "ip",
    "mac",
    "module_id",
    "module_ip",
    "module_name",
    "name",
    "room",
    "src",
    "target",
}

_PLACEHOLDER = {
    "address": "[adres]",
    "descr": "[naam]",
    "device_id": "[id]",
    "dst": "[adres]",
    "gr": "[naam]",
    "host": "[adres]",
    "id": "[id]",
    "ip": "[adres]",
    "mac": "[mac]",
    "module_id": "[id]",
    "module_ip": "[adres]",
    "module_name": "[naam]",
    "name": "[naam]",
    "room": "[naam]",
    "src": "[adres]",
    "target": "[id]",
}

_SKIP_TOKENS = {
    "on",
    "off",
    "ok",
    "true",
    "false",
    "null",
    "none",
    "relay",
    "dimmer",
    "input",
    "button",
    "light",
    "unknown",
    "inactive",
}


def collect_tokens(value: Any) -> set[str]:
    """Names and ids that must also disappear from free text."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in _SENSITIVE_KEYS and isinstance(item, str):
                    token = item.strip()
                    if len(token) >= 3 and token.lower() not in _SKIP_TOKENS:
                        found.add(token)
                else:
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return found


def redact_text(text: str, tokens: set[str] | None = None) -> str:
    """Replace addresses, MAC addresses, and known names inside one string."""
    cleaned = _IPV4.sub("[adres]", text)
    cleaned = _MAC.sub("[mac]", cleaned)
    for token in sorted(tokens or (), key=len, reverse=True):
        if len(token) < 3:
            continue
        cleaned = re.sub(re.escape(token), "[naam]", cleaned, flags=re.IGNORECASE)
    return cleaned


def redact_payload(value: Any, tokens: set[str] | None = None) -> Any:
    """Copy ``value`` with sensitive fields and free-text leaks removed."""
    known = collect_tokens(value) if tokens is None else set(tokens)
    return _redact(value, known)


def _redact(value: Any, tokens: set[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _SENSITIVE_KEYS:
                out[key] = _PLACEHOLDER[key]
            else:
                out[key] = _redact(item, tokens)
        return out
    if isinstance(value, list):
        return [_redact(item, tokens) for item in value]
    if isinstance(value, str):
        return redact_text(value, tokens)
    return value
