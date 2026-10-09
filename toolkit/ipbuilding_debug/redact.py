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
    "instance_id",
    "ip",
    "mac",
    "module_id",
    "module_ip",
    "module_name",
    "name",
    "room",
    "service_name",
    "src",
    "target",
    "uuid",
}

_PLACEHOLDER = {
    "address": "[adres]",
    "descr": "[naam]",
    "device_id": "[id]",
    "dst": "[adres]",
    "gr": "[naam]",
    "host": "[adres]",
    "id": "[id]",
    "instance_id": "[id]",
    "ip": "[adres]",
    "mac": "[mac]",
    "module_id": "[id]",
    "module_ip": "[adres]",
    "module_name": "[naam]",
    "name": "[naam]",
    "room": "[naam]",
    "service_name": "[id]",
    "src": "[adres]",
    "target": "[id]",
    "uuid": "[id]",
}

# Keyed values in log lines. A bare UUID stays, so the random installation id
# in the frontmatter is left alone. The lookbehind keeps ``installatie_id`` intact.
_IDENTITY_KV = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(instance_id|uuid|service_name)(?![A-Za-z0-9_])"
    r"(\s*[:=]\s*)"
    r'(?:"[^"]*"|\'[^\']*\'|\S+)'
)

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


def mask_stem(name: str) -> str:
    """Keep the first character and replace every following one with ``x``."""
    if not name:
        return ""
    return name[0] + ("x" * (len(name) - 1))


def collect_display_names(value: Any, hosts: set[str] | None = None) -> list[str]:
    """Inventory names, in walk order. One entry per name, first spelling wins."""
    found: list[str] = []
    seen: set[str] = set()
    known = {host.lower() for host in hosts or () if host}

    def add(item: Any) -> None:
        if not isinstance(item, str):
            return
        token = item.strip()
        folded = token.casefold()
        if (
            not token
            or folded in seen
            or token.lower() in _SKIP_TOKENS
            or _fully_removed(token, known) is not None
        ):
            return
        seen.add(folded)
        found.append(token)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in _NAME_KEYS:
                    add(item)
                else:
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return found


def name_masks(names: list[str], appearance: str) -> dict[str, str]:
    """One mask per name. A shared stem gets ``-1``, ``-2`` in appearance order.

    The first name keeps the bare stem when nothing else shares it. Names
    that never occur as a whole word fall back to ``names`` order.
    """
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        folded = name.casefold()
        if not name or folded in seen:
            continue
        seen.add(folded)
        unique.append(name)
    position = {name: index for index, name in enumerate(unique)}

    def first_at(name: str) -> int:
        match = re.search(
            rf"(?i)(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])",
            appearance,
        )
        if match is not None:
            return match.start()
        return len(appearance) + 1 + position[name]

    groups: dict[str, list[str]] = {}
    for name in unique:
        groups.setdefault(mask_stem(name), []).append(name)
    masks: dict[str, str] = {}
    for stem, group in groups.items():
        if len(group) == 1:
            masks[group[0]] = stem
            continue
        ranked = sorted(group, key=lambda item: (first_at(item), position[item]))
        for number, item in enumerate(ranked, start=1):
            masks[item] = f"{stem}-{number}"
    return masks


def redact_text(
    text: str,
    tokens: set[str] | None = None,
    hosts: set[str] | None = None,
    masks: dict[str, str] | None = None,
) -> str:
    """Replace addresses, MAC addresses, emails, hostnames, and known names.

    With ``masks``, inventory names become that mask. Matching is
    case-insensitive and whole-word; the mask text comes from the inventory
    spelling. Without masks, those names become ``[naam]``.
    """
    cleaned = _IDENTITY_KV.sub(r"\1\2[id]", text)
    cleaned = _IPV6_RUN.sub(_ipv6_or_keep, cleaned)
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
    spans: list[tuple[int, int, str, int]] = []
    masked = masks or {}
    masked_folded = {name.casefold() for name in masked}
    for name in sorted(masked, key=len, reverse=True):
        if not name:
            continue
        pattern = re.compile(
            rf"(?i)(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
        )
        for match in pattern.finditer(cleaned):
            spans.append((match.start(), match.end(), masked[name], 0))
    for token in sorted(tokens or (), key=len, reverse=True):
        if not token or token.casefold() in masked_folded or token.lower() in known_hosts:
            continue
        if len(token) >= 3:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
        else:
            pattern = re.compile(
                rf"(?i)(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])"
            )
        # A report passes masks. Leftover tokens are ids, not lamp names,
        # so they use the same ``[id]`` marker as id fields. ``read_logs``
        # passes no masks and still says ``[naam]``.
        token_mark = "[id]" if masks is not None else "[naam]"
        for match in pattern.finditer(cleaned):
            spans.append((match.start(), match.end(), token_mark, 1))
    return _apply_spans(cleaned, spans)


def redact_payload(
    value: Any,
    tokens: set[str] | None = None,
    hosts: set[str] | None = None,
    masks: dict[str, str] | None = None,
) -> Any:
    """Copy ``value`` with sensitive fields and free-text leaks removed."""
    known = collect_tokens(value) if tokens is None else set(tokens)
    return _redact(value, known, set(hosts or ()), masks)


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


def _redact(
    value: Any,
    tokens: set[str],
    hosts: set[str],
    masks: dict[str, str] | None = None,
) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _NAME_KEYS and masks is not None and isinstance(item, str):
                out[key] = _mask_name_field(item, masks, hosts)
            elif key in _SENSITIVE_KEYS:
                out[key] = _PLACEHOLDER[key]
            else:
                out[key] = _redact(item, tokens, hosts, masks)
        return out
    if isinstance(value, list):
        return [_redact(item, tokens, hosts, masks) for item in value]
    if isinstance(value, str):
        return redact_text(value, tokens, hosts, masks)
    return value


def _mask_name_field(value: str, masks: dict[str, str], hosts: set[str]) -> str:
    token = value.strip()
    removed = _fully_removed(token, {host.lower() for host in hosts if host})
    if removed is not None:
        return removed
    if not token or token.lower() in _SKIP_TOKENS:
        return _PLACEHOLDER["name"]
    found = _lookup_mask(token, masks)
    if found is not None:
        return found
    return mask_stem(token)


def _lookup_mask(token: str, masks: dict[str, str]) -> str | None:
    if token in masks:
        return masks[token]
    folded = token.casefold()
    for name, mask in masks.items():
        if name.casefold() == folded:
            return mask
    return None


def _fully_removed(token: str, hosts: set[str]) -> str | None:
    """IP, MAC, hostname, and email stay fully removed, never masked."""
    if not token:
        return None
    if _is_ip(token) or token.lower() in hosts:
        return "[adres]"
    host_match = _HOST_IN_TEXT.fullmatch(token)
    if host_match is not None and _host_or_keep(host_match) == "[adres]":
        return "[adres]"
    if _EMAIL.fullmatch(token):
        return "[e-mail]"
    if any(
        pattern.fullmatch(token)
        for pattern in (_MAC_COLON, _MAC_DASH, _MAC_DOT, _MAC_BARE)
    ):
        return "[mac]"
    return None


def _apply_spans(text: str, spans: list[tuple[int, int, str, int]]) -> str:
    """Apply non-overlapping spans.

    A name mask always wins over ``[naam]``, even when the ``[naam]`` token is
    longer and would otherwise swallow the name. Within one kind, the longer
    match wins.
    """
    chosen: list[tuple[int, int, str]] = []
    ordered = sorted(spans, key=lambda item: (item[3], -(item[1] - item[0]), item[0]))
    for start, end, replacement, _rank in ordered:
        if any(not (end <= have or start >= stop) for have, stop, _ in chosen):
            continue
        chosen.append((start, end, replacement))
    if not chosen:
        return text
    chosen.sort()
    parts: list[str] = []
    cursor = 0
    for start, end, replacement in chosen:
        parts.append(text[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


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
