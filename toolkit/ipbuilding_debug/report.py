"""Fixed debug report and the mailto draft.

Sending is on unless ``IPBUILDING_REPORT_SEND`` is ``0``, ``false``, ``no``,
or ``off``. The intake address is read from ``IPBUILDING_REPORT_INTAKE`` and
is never stored in this file. Without that address the option stays unavailable.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

from ipbuilding_debug.privacy import FEEDBACK_WARNING, privacy_notice
from ipbuilding_debug.redact import redact_text
from ipbuilding_debug.version import __version__

_BODY_LIMIT = 250_000
_CONFIRMED_TYPES = {"udp_frame"}
_SUSPECTED_TYPES = {
    "log",
    "log_dropped",
    "state_changed",
    "button_event",
    "device_added",
    "device_removed",
    "device_ip_changed",
    "device_firmware_changed",
}


_SEND_OFF = {"0", "false", "no", "off"}


def report_send_enabled() -> bool:
    """Feature flag. On unless the environment explicitly turns it off."""
    raw = os.environ.get("IPBUILDING_REPORT_SEND")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _SEND_OFF


def intake_address() -> str:
    """Linear intake address injected at build time, or empty."""
    return os.environ.get("IPBUILDING_REPORT_INTAKE", "").strip()


def render_report(body: dict[str, Any]) -> tuple[str, str]:
    """Plain-text report and its YAML frontmatter.

    ``body`` is the export payload. Pass the redacted copy when redaction is on.
    """
    sections = _sections(body)
    frontmatter = _frontmatter(body, sections["dialects"])
    report = "\n".join(
        [
            FEEDBACK_WARNING,
            "",
            frontmatter,
            "",
            "1. Samenvatting",
            sections["samenvatting"],
            "",
            "2. Omgeving",
            sections["omgeving"],
            "",
            "3. Wat getest werd",
            sections["getest"],
            "",
            "4. Bevindingen",
            "Bevestigd",
            sections["bevestigd"],
            "Vermoeden",
            sections["vermoeden"],
            "",
            "5. Open vragen",
            sections["open"],
            "",
            "6. Feedback over de tool",
            sections["feedback"],
            "",
            "7. Bijlage",
            sections["bijlage"],
            "",
        ]
    )
    return report, frontmatter


def email_body(report_sections: dict[str, str], frontmatter: str) -> str:
    """One ``Sleutel: waarde`` line per section, then the machine-readable block."""
    lines = [FEEDBACK_WARNING, ""]
    for key in (
        "Samenvatting",
        "Omgeving",
        "Wat getest werd",
        "Bevestigd",
        "Vermoeden",
        "Open vragen",
        "Feedback over de tool",
        "Bijlage",
    ):
        value = " ".join(report_sections[key].split())
        lines.append(f"{key}: {value}")
    lines.extend(["", frontmatter, ""])
    text = "\n".join(lines)
    if len(text) <= _BODY_LIMIT:
        return text
    marker = "\nIngekort: de body mag hoogstens 250000 tekens zijn.\n"
    return text[: _BODY_LIMIT - len(marker)] + marker


def section_map(body: dict[str, Any]) -> dict[str, str]:
    sections = _sections(body)
    return {
        "Samenvatting": sections["samenvatting"],
        "Omgeving": sections["omgeving"],
        "Wat getest werd": sections["getest"],
        "Bevestigd": sections["bevestigd"],
        "Vermoeden": sections["vermoeden"],
        "Open vragen": sections["open"],
        "Feedback over de tool": sections["feedback"],
        "Bijlage": sections["bijlage"],
    }


def subject_line(
    installatie_id: str,
    korte_fout: str,
    moment: datetime | None = None,
    masks: dict[str, str] | None = None,
) -> str:
    when = (moment or datetime.now().astimezone()).isoformat(timespec="seconds")
    short = _short_fault(korte_fout, masks)
    return f"[DEBUG] {installatie_id} | {short} | {when}"


def mailto_link(address: str, subject: str, body: str) -> str:
    return f"mailto:{quote(address)}?subject={quote(subject)}&body={quote(body)}"


def preview_message(report: str) -> str:
    return (
        f"{privacy_notice()}\n\n{report}\n"
        "Bevestig om een mailto-link te maken. De toolkit verstuurt niets."
    )


def sent_message(link: str) -> str:
    return (
        f"{link}\n\n"
        "De mail is niet verstuurd. Open de link, kies in je mailprogramma "
        "het afzenderadres en verstuur zelf. Je krijgt geen bevestiging."
    )


def unavailable_message() -> str:
    return (
        "Doorsturen is niet beschikbaar. "
        "Er is geen intake-adres ingesteld. Het rapport blijft lokaal."
    )


def disabled_message() -> str:
    return (
        "Doorsturen staat uit. "
        "Gebruik het rapport uit export_session. De toolkit verstuurt niets."
    )


def parse_mailto(link: str) -> dict[str, str]:
    """Split a mailto link. Tests use this; it does not send anything."""
    if not link.startswith("mailto:"):
        return {}
    rest = link.removeprefix("mailto:")
    address, _, query = rest.partition("?")
    fields = {"address": unquote(address)}
    for part in query.split("&"):
        key, _, value = part.partition("=")
        fields[key] = unquote(value)
    return fields


def _sections(body: dict[str, Any]) -> dict[str, Any]:
    notes = [item for item in body.get("notes") or [] if isinstance(item, dict)]
    events = [item for item in body.get("events") or [] if isinstance(item, dict)]
    confirmed = [_event_line(item) for item in events if item.get("type") in _CONFIRMED_TYPES]
    suspected = [_event_line(item) for item in events if item.get("type") in _SUSPECTED_TYPES]
    gaps = [item for item in events if item.get("type") == "gap"]
    note_lines = [_note_line(item) for item in notes]
    words = " ".join(str(item.get("text") or "").strip() for item in notes).strip()
    if words:
        summary = (
            f"In de woorden van de tester: {words} "
            "Wat gevonden werd staat onder Bevindingen. "
            "Een oorzaak staat daar alleen als een frame die bevestigt."
        )
    else:
        summary = (
            "De tester heeft nog geen probleem in een notitie gezet. "
            "Een oorzaak staat onder Bevindingen alleen als een frame die bevestigt."
        )
    return {
        "samenvatting": summary,
        "omgeving": _environment(body),
        "getest": "\n".join(note_lines + [_event_line(item) for item in events]) or "Geen stappen genoteerd.",
        "bevestigd": "\n".join(confirmed) or "Geen frame dat dit bevestigt.",
        "vermoeden": "\n".join(suspected) or "Geen vermoeden uit de buffer.",
        "open": _open_questions(gaps),
        "feedback": "—",
        "bijlage": "\n".join(_event_line(item) for item in events) or "Geen gebeurtenissen.",
        "dialects": _dialects(events),
    }


def _environment(body: dict[str, Any]) -> str:
    gateway = body.get("gateway") if isinstance(body.get("gateway"), dict) else {}
    modules = [item for item in body.get("modules") or [] if isinstance(item, dict)]
    caps = gateway.get("capabilities") if isinstance(gateway.get("capabilities"), list) else []
    lines = [
        f"Toolkitversie: {__version__}",
        f"Gatewayversie: {gateway.get('version') or 'onbekend'}",
        f"Rol: {gateway.get('hub_role') or 'onbekend'}",
        f"Schakelaar remote_debugging: {gateway.get('remote_debugging')}",
        "Functies: " + (", ".join(str(item) for item in caps) or "geen"),
        f"Installatie-id: {body.get('installatie_id') or 'onbekend'}",
    ]
    if modules:
        for module in modules:
            kind = module.get("type") or "onbekend"
            model = module.get("model") or ""
            lines.append(f"Module: {kind} {model}".strip())
    else:
        lines.append("Modules: niet geladen in deze sessie.")
    dialects = _dialects(body.get("events") or [])
    lines.append("Dialecten: " + (", ".join(dialects) or "geen bevestigd in de frames"))
    return "\n".join(lines)


def _frontmatter(body: dict[str, Any], dialects: list[str]) -> str:
    gateway = body.get("gateway") if isinstance(body.get("gateway"), dict) else {}
    modules = [item for item in body.get("modules") or [] if isinstance(item, dict)]
    caps = gateway.get("capabilities") if isinstance(gateway.get("capabilities"), list) else []
    lines = [
        "---",
        f"installatie_id: {_yaml(body.get('installatie_id') or '')}",
        f"toolkit_version: {_yaml(__version__)}",
        f"gateway_version: {_yaml(gateway.get('version'))}",
        f"hub_role: {_yaml(gateway.get('hub_role'))}",
        f"remote_debugging: {_yaml(gateway.get('remote_debugging'))}",
    ]
    if caps:
        lines.append("capabilities:")
        lines.extend(f"  - {_yaml(item)}" for item in caps)
    else:
        lines.append("capabilities: []")
    if modules:
        lines.append("modules:")
        for module in modules:
            lines.append(f"  - type: {_yaml(module.get('type'))}")
            lines.append(f"    model: {_yaml(module.get('model'))}")
    else:
        lines.append("modules: []")
    if dialects:
        lines.append("dialects:")
        lines.extend(f"  - {_yaml(item)}" for item in dialects)
    else:
        lines.append("dialects: []")
    lines.append("---")
    return "\n".join(lines)


def _event_line(event: dict[str, Any]) -> str:
    when = str(event.get("local_time") or "")
    kind = str(event.get("type") or "gebeurtenis")
    detail = event.get("message") or event.get("action") or event.get("state") or event.get("hex") or ""
    return f"{when} {kind} {detail}".strip()


def _note_line(note: dict[str, Any]) -> str:
    when = str(note.get("local_time") or "")
    return f"{when} notitie {note.get('text') or ''}".strip()


def _open_questions(gaps: list[dict[str, Any]]) -> str:
    lines = []
    for gap in gaps:
        when = str(gap.get("local_time") or "")
        text = gap.get("message") or "onderbreking zonder toelichting"
        lines.append(f"{when} {text}".strip())
    if not lines:
        return "Geen open vraag uit de buffer."
    return "\n".join(lines)


def _dialects(events: list[Any]) -> list[str]:
    found: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        raw = event.get("dialect_id")
        if isinstance(raw, str) and raw and raw not in found:
            found.append(raw)
        decode = event.get("local_decode")
        if isinstance(decode, dict):
            for item in decode.get("dialects") or []:
                if isinstance(item, dict) and item.get("id") and item["id"] not in found:
                    found.append(str(item["id"]))
    return found


def _short_fault(korte_fout: str, masks: dict[str, str] | None = None) -> str:
    cleaned = redact_text(korte_fout or "", masks=masks)
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.replace("|", "/")
    if not cleaned:
        return "sessie"
    return cleaned[:80]


def _yaml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if text == "" or any(char in text for char in ":#\n\"'[]{}&*"):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text
