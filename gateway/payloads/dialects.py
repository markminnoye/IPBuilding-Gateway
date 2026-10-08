"""Canonical field-bus dialect ids and display names.

A later city rename changes only the ``Dialect`` entries below. Message
types are ``{module}.{id}.{kind}`` via :meth:`Dialect.message_type`.
The dialect registry quotes the same id and display name; a test keeps
them in step. The gateway does not alias a retired id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dialect:
    """One wire dialect: stable id plus the city name used in docs."""

    id: str
    display_name: str

    def message_type(self, module: str, kind: str) -> str:
        if "." in module or "." in kind or not module or not kind:
            raise ValueError("module and kind are single path segments")
        return f"{module}.{self.id}.{kind}"


KESSEL_LO = Dialect("kessel-lo", "Kessel-Lo")
TORHOUT = Dialect("torhout", "Torhout")

DIALECTS = (KESSEL_LO, TORHOUT)
