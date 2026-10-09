"""City names for field-bus dialects.

Ids and display names live on ``Dialect``. Tool text reads them from here,
so a later rename stays in one place. Older gateways still send the previous
ids; ``_LEGACY`` is the only alias and the only place those ids are written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Dialect:
    """One named dialect. ``families`` empty means every ``*.id.*`` form."""

    id: str
    name: str
    summary: str
    families: tuple[str, ...] = ()

    @property
    def message_types(self) -> list[str]:
        if self.families:
            return [f"{family}.{self.id}.*" for family in self.families]
        return [f"*.{self.id}.*"]

    @property
    def description(self) -> str:
        types = " en ".join(self.message_types)
        return (
            f"{self.name}: {self.summary} "
            f"Het id is {self.id}. Berichttypes zijn {types}."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "message_types": list(self.message_types),
            "description": self.description,
        }


KESSEL_LO = Dialect(
    id="kessel-lo",
    name="Kessel-Lo",
    summary="het dialect van de dimmer- en inputmodules uit de eerste testopstelling.",
    families=("dimmer", "input"),
)
TORHOUT = Dialect(
    id="torhout",
    name="Torhout",
    summary="het tweede bevestigde dialect van de modules.",
)

DIALECTS = (KESSEL_LO, TORHOUT)

# Previous ids. Do not copy these strings anywhere else in the toolkit.
_LEGACY = {
    "lab": KESSEL_LO,
    "nolf": TORHOUT,
}


def legacy_segments() -> tuple[str, ...]:
    """Previous id segments. Tests use this so the strings stay in this file."""
    return tuple(_LEGACY)


def full_dialect_id(dialect_id: str) -> str:
    """A message-type id such as ``dimmer.kessel-lo.status_reply``.

    A bare city name has no dots and is not a dialect id for the report.
    """
    shown = present_dialect_id((dialect_id or "").strip())
    if shown.count(".") < 2:
        return ""
    return shown


def present_dialect_id(dialect_id: str) -> str:
    """Map an incoming dialect id onto the current id."""
    parts = dialect_id.split(".")
    changed = False
    for index, part in enumerate(parts):
        dialect = _LEGACY.get(part)
        if dialect is None:
            continue
        if dialect.families:
            family = parts[index - 1] if index else ""
            if family not in dialect.families:
                continue
        parts[index] = dialect.id
        changed = True
    if not changed:
        return dialect_id
    return ".".join(parts)


def find_dialect(dialect_id: str) -> Dialect | None:
    """The dialect whose current id is a segment of ``dialect_id``."""
    shown = present_dialect_id(dialect_id)
    parts = shown.split(".")
    for dialect in DIALECTS:
        if dialect.id in parts:
            return dialect
    return None


def dialect_name(dialect_id: str) -> str:
    found = find_dialect(dialect_id)
    return found.name if found is not None else ""


def dialect_info(dialect_id: str) -> dict[str, Any] | None:
    found = find_dialect(dialect_id)
    if found is None:
        return None
    return found.as_dict()


def present_event(event: dict[str, Any]) -> dict[str, Any]:
    """Copy one event and show its dialect under the current city name."""
    item = dict(event)
    raw = item.get("dialect_id")
    if not isinstance(raw, str) or not raw:
        return item
    shown = present_dialect_id(raw)
    item["dialect_id"] = shown
    name = dialect_name(shown)
    if name:
        item["dialect_name"] = name
    return item


def present_decode(decoded: dict[str, Any]) -> dict[str, Any]:
    """Rewrite dialect ids inside a local decode result."""
    matches: list[dict[str, Any]] = []
    described: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in decoded.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fields = dict(match.get("fields") or {})
        raw = fields.get("dialect_id")
        if isinstance(raw, str) and raw:
            fields["dialect_id"] = present_dialect_id(raw)
            name = dialect_name(fields["dialect_id"])
            if name:
                fields["dialect_name"] = name
            info = dialect_info(fields["dialect_id"])
            if info is not None and info["id"] not in seen:
                seen.add(info["id"])
                described.append(info)
        matches.append({**match, "fields": fields})
    out = dict(decoded)
    out["matches"] = matches
    if described:
        out["dialects"] = described
    return out
