"""Plain-language errors for a non-technical tester.

The assistant repeats ``message`` to the tester. Keep each string stable:
the Dutch guide and the tests quote them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KIND_UNREACHABLE = "unreachable"
KIND_REMOTE_DEBUGGING_OFF = "remote_debugging_off"
KIND_NOT_AVAILABLE = "not_available"
KIND_OTHER = "other"
KIND_NO_ADDRESS = "no_address"

# Exact phrase the assistant must be able to quote when a feature is absent.
NOT_AVAILABLE_PHRASE = "not available in this gateway version yet"

SWITCH_NAME = "Remote debugging and control"
SWITCH_NAME_NL = "Debuggen en bedienen op afstand"
SWITCH_WHERE = (
    "Instellingen > Add-ons > IPBuilding Gateway > Configuratie"
)

MSG_UNREACHABLE = (
    "De gateway is niet bereikbaar. "
    "Controleer of de add-on IPBuilding Gateway in Home Assistant draait "
    "(Instellingen > Add-ons > IPBuilding Gateway) "
    "en of het gateway-adres in de instellingen van deze bundel klopt "
    "(bijvoorbeeld homeassistant.local, zonder http:// en zonder poort)."
)

MSG_NO_ADDRESS = (
    "Er is geen gateway-adres ingesteld. "
    "Vul het adres in bij de instellingen van deze bundel, "
    "bijvoorbeeld homeassistant.local, zonder http:// en zonder poort."
)

MSG_REMOTE_DEBUGGING_OFF = (
    "De add-on draait, maar 'Remote debugging and control' staat uit. "
    "Zet de schakelaar 'Remote debugging and control' aan in Home Assistant "
    "(Instellingen > Add-ons > IPBuilding Gateway > Configuratie) "
    "zodat de assistent opnieuw kan verbinden. "
    "Bij een Nederlandse Home Assistant heet de schakelaar "
    "'Debuggen en bedienen op afstand' (onder Debug). "
    "De schakelaar zet live logs, veldbusframes en het sturen van testpakketten open, "
    "toont een blijvende melding in Home Assistant, en blijft aan tot je hem zelf uitzet. "
    "Wijzigen herstart de add-on."
)

MSG_SWITCH_UNKNOWN = (
    "De gateway antwoordt, maar deze versie meldt niet of "
    "'Remote debugging and control' aan staat. "
    "Kijk in Home Assistant bij Instellingen > Add-ons > IPBuilding Gateway > Configuratie. "
    "Zet 'Remote debugging and control' aan als je live wilt meekijken "
    "(bij Nederlands: 'Debuggen en bedienen op afstand'). "
    "Een oudere add-on heeft die schakelaar nog niet; dan is eerst een update nodig."
)

MSG_NOT_AVAILABLE = (
    "Deze functie is nog niet beschikbaar in deze gateway-versie "
    "(not available in this gateway version yet)."
)

_CAPABILITY_LABELS = {
    "log_stream": "Live logs meelezen",
    "udp_frame": "Veldbusframes meelezen",
    "raw_send": "Een testpakket sturen",
}

PLANNED_CAPABILITIES = ("log_stream", "udp_frame", "raw_send")

REMOTE_DEBUGGING_DISABLED = "remote_debugging_disabled"


def msg_not_available(capability: str) -> str:
    label = _CAPABILITY_LABELS.get(capability, capability)
    return (
        f"{label} is nog niet beschikbaar in deze gateway-versie "
        f"({NOT_AVAILABLE_PHRASE})."
    )


def msg_other(detail: str) -> str:
    clean = " ".join((detail or "onbekende fout").split())[:180]
    return (
        f"Er ging iets mis bij het praten met de gateway ({clean}). "
        "Controleer of de add-on IPBuilding Gateway nog draait. "
        "Blijft dit zo, bewaar deze melding."
    )


def msg_connected(*, remote_debugging: bool | None, capabilities: list[str]) -> str:
    """Status line for a gateway that answered /api/v1/status."""
    if remote_debugging is False:
        return MSG_REMOTE_DEBUGGING_OFF
    if remote_debugging is None:
        return MSG_SWITCH_UNKNOWN
    missing = [name for name in PLANNED_CAPABILITIES if name not in capabilities]
    if not missing:
        return (
            "De gateway is bereikbaar en 'Remote debugging and control' staat aan. "
            "Live logs, veldbusframes en testpakketten zijn beschikbaar. "
            "Zet de schakelaar na afloop weer uit in Home Assistant "
            "(Instellingen > Add-ons > IPBuilding Gateway > Configuratie). "
            "De melding in Home Assistant verdwijnt nadat de add-on opnieuw is opgestart."
        )
    if len(missing) == len(PLANNED_CAPABILITIES):
        return (
            "De gateway is bereikbaar en 'Remote debugging and control' staat aan. "
            "Live logs, veldbusframes en testpakketten sturen zijn in deze versie "
            f"nog niet beschikbaar ({NOT_AVAILABLE_PHRASE}). "
            "De installatie bekijken kan wel. "
            "Zet de schakelaar weer uit als je hem niet nodig hebt."
        )
    ready = [name for name in PLANNED_CAPABILITIES if name in capabilities]
    return (
        "De gateway is bereikbaar en 'Remote debugging and control' staat aan. "
        f"Beschikbaar: {', '.join(ready)}. "
        f"Nog niet in deze versie ({NOT_AVAILABLE_PHRASE}): {', '.join(missing)}. "
        "Zet de schakelaar na afloop weer uit."
    )


@dataclass(frozen=True)
class ClassifiedError:
    kind: str
    message: str
    detail: str = ""


def _error_codes(body: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(body, dict):
        return found
    for key in ("error", "code"):
        value = body.get(key)
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            for nested in ("error", "code"):
                inner = value.get(nested)
                if isinstance(inner, str):
                    found.add(inner)
    return found


def is_remote_debugging_disabled(body: Any) -> bool:
    return REMOTE_DEBUGGING_DISABLED in _error_codes(body)


def classify_http(status: int, body: Any) -> ClassifiedError:
    """Classify a non-success HTTP response from the gateway."""
    if is_remote_debugging_disabled(body):
        return ClassifiedError(
            KIND_REMOTE_DEBUGGING_OFF,
            MSG_REMOTE_DEBUGGING_OFF,
            REMOTE_DEBUGGING_DISABLED,
        )
    if status in (404, 501):
        return ClassifiedError(KIND_NOT_AVAILABLE, MSG_NOT_AVAILABLE, f"HTTP {status}")
    detail = f"HTTP {status}"
    if isinstance(body, dict):
        raw = body.get("message") or body.get("error")
        if isinstance(raw, str) and raw.strip():
            detail = raw.strip()
    return ClassifiedError(KIND_OTHER, msg_other(detail), detail)


def classify_transport(exc: BaseException) -> ClassifiedError:
    """DNS, timeout, connection refused, and other failures to reach the add-on."""
    return ClassifiedError(KIND_UNREACHABLE, MSG_UNREACHABLE, type(exc).__name__)


def gate_feature(
    status: dict[str, Any] | None,
    capability: str,
    transport_error: ClassifiedError | None = None,
) -> ClassifiedError | None:
    """Decide whether a debug feature may run.

    Unreachable wins. A feature missing from ``/status.capabilities`` is
    reported as not in this version, also when the switch is off: turning
    the switch on does not add a feature this build does not have.
    When the feature is listed and the switch is off, ask to turn it on.
    """
    if transport_error is not None and transport_error.kind in (
        KIND_UNREACHABLE,
        KIND_NO_ADDRESS,
        KIND_REMOTE_DEBUGGING_OFF,
    ):
        return transport_error
    if not isinstance(status, dict):
        if transport_error is not None:
            return transport_error
        return ClassifiedError(KIND_UNREACHABLE, MSG_UNREACHABLE)
    caps = status.get("capabilities")
    if not isinstance(caps, list):
        caps = []
    if capability not in caps:
        return ClassifiedError(KIND_NOT_AVAILABLE, msg_not_available(capability), capability)
    if is_remote_debugging_disabled(status):
        return ClassifiedError(KIND_REMOTE_DEBUGGING_OFF, MSG_REMOTE_DEBUGGING_OFF)
    if status.get("remote_debugging") is False:
        return ClassifiedError(KIND_REMOTE_DEBUGGING_OFF, MSG_REMOTE_DEBUGGING_OFF)
    if "remote_debugging" not in status:
        return ClassifiedError(KIND_REMOTE_DEBUGGING_OFF, MSG_SWITCH_UNKNOWN)
    if transport_error is not None:
        return transport_error
    return None
