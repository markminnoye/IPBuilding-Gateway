"""Strip addresses, hardware ids, and installation names from a session export.

Redaction is on by default. A local raw view is an explicit opt-out.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Hex and colons, plus an embedded IPv4 tail. Validated as IPv6 so a
# colon-MAC or a clock time is left alone.
_IPV6_RUN = re.compile(
    r"(?<![0-9A-Fa-f:])[0-9A-Fa-f:]{2,}(?:(?:\.\d{1,3}){3})?(?![0-9A-Fa-f:])"
)
_MAC_COLON = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
_MAC_DASH = re.compile(r"\b(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b")
_MAC_DOT = re.compile(r"\b(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}\b")
# A hyphen on either side keeps the last group of a UUID intact.
_MAC_BARE = re.compile(r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])")
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
# Hostname in free text. Boundaries keep dotted ids such as
# input.kessel-lo.button_event intact. Two labels only when the last
# one is not a file type.
_HOST_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9.-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:local|[a-z]{2,63})"
    r"(?![A-Za-z0-9_-])(?!\.[A-Za-z0-9])",
    re.IGNORECASE,
)
_FILE_TLDS = frozenset(
    {
        "bin",
        "css",
        "csv",
        "doc",
        "gz",
        "html",
        "ico",
        "js",
        "json",
        "log",
        "md",
        "pdf",
        "png",
        "py",
        "svg",
        "txt",
        "xml",
        "yaml",
        "yml",
        "zip",
    }
)

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

# Short names and rooms are redacted only from these fields, as whole words.
_NAME_KEYS = {"descr", "gr", "module_name", "name", "room"}

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
                    if token and token.lower() not in _SKIP_TOKENS:
                        if len(token) >= 3 or key in _NAME_KEYS:
                            found.add(token)
                else:
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return found


def redact_text(
    text: str,
    tokens: set[str] | None = None,
    hosts: set[str] | None = None,
) -> str:
    """Replace addresses, MAC addresses, emails, hostnames, and known names."""
    cleaned = _IPV6_RUN.sub(_ipv6_or_keep, text)
    cleaned = _IPV4.sub("[adres]", cleaned)
    cleaned = _MAC_COLON.sub("[mac]", cleaned)
    cleaned = _MAC_DASH.sub("[mac]", cleaned)
    cleaned = _MAC_DOT.sub("[mac]", cleaned)
    cleaned = _MAC_BARE.sub("[mac]", cleaned)
    cleaned = _EMAIL.sub("[e-mail]", cleaned)
    cleaned = _HOST_IN_TEXT.sub(_host_or_keep, cleaned)
    known_hosts = {host.lower() for host in hosts or () if host}
    for host in sorted(known_hosts, key=len, reverse=True):
        if _is_ip(host):
            continue
        cleaned = re.sub(
            rf"(?i)(?<![A-Za-z0-9.-]){re.escape(host)}(?![A-Za-z0-9.-])",
            "[adres]",
            cleaned,
        )
    for token in sorted(tokens or (), key=len, reverse=True):
        if token.lower() in known_hosts:
            continue
        if len(token) >= 3:
            cleaned = re.sub(re.escape(token), "[naam]", cleaned, flags=re.IGNORECASE)
        elif token:
            cleaned = re.sub(
                rf"(?i)(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])",
                "[naam]",
                cleaned,
            )
    return cleaned


def redact_payload(
    value: Any,
    tokens: set[str] | None = None,
    hosts: set[str] | None = None,
) -> Any:
    """Copy ``value`` with sensitive fields and free-text leaks removed."""
    known = collect_tokens(value) if tokens is None else set(tokens)
    return _redact(value, known, set(hosts or ()))


def session_hosts(session: Any) -> set[str]:
    """Gateway hostname, mDNS name, and other hosts this session already saw."""
    found: set[str] = set()
    raws: list[Any] = [
        getattr(session, "host", ""),
        getattr(session, "address", ""),
    ]
    for item in getattr(session, "tried", []) or []:
        if isinstance(item, dict):
            raws.append(item.get("host"))
    for raw in raws:
        host = _plain_host(raw)
        if host and not _is_ip(host):
            found.add(host)
    return found


def _redact(value: Any, tokens: set[str], hosts: set[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _SENSITIVE_KEYS:
                out[key] = _PLACEHOLDER[key]
            else:
                out[key] = _redact(item, tokens, hosts)
        return out
    if isinstance(value, list):
        return [_redact(item, tokens, hosts) for item in value]
    if isinstance(value, str):
        return redact_text(value, tokens, hosts)
    return value


def _ipv6_or_keep(match: re.Match[str]) -> str:
    raw = match.group(0)
    if raw.count(":") < 2:
        return raw
    try:
        ipaddress.IPv6Address(raw)
    except ValueError:
        return raw
    return "[adres]"


def _host_or_keep(match: re.Match[str]) -> str:
    host = match.group(0)
    labels = host.split(".")
    tld = labels[-1].lower()
    if tld == "local" or len(labels) >= 3:
        return "[adres]"
    if len(labels) == 2 and tld not in _FILE_TLDS:
        return "[adres]"
    return host


def _plain_host(raw: Any) -> str:
    text = str(raw or "").strip().strip("[]").rstrip(".")
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    if text.count(":") == 1 and text.rsplit(":", 1)[-1].isdigit():
        text = text.rsplit(":", 1)[0]
    return text.lower()


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        return False
    return True
