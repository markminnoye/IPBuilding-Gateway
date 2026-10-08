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
KIND_LOG_LEVEL_RATE_LIMITED = "log_level_rate_limited"
KIND_OTHER = "other"
KIND_NO_ADDRESS = "no_address"

# Exact phrase the assistant must be able to quote when a feature is absent.
NOT_AVAILABLE_PHRASE = "not available in this gateway version yet"

# Older gateways omit command confirmation and per-module reachability.
# Support is the presence of those fields, not a capability name.
MSG_NOT_IN_THIS_GATEWAY_VERSION = "niet beschikbaar in deze gatewayversie"

SWITCH_NAME = "Remote control (for debugging)"
SWITCH_NAME_NL = "Bediening op afstand (voor debuggen)"
SWITCH_WHERE = (
    "Instellingen > Add-ons > IPBuilding Gateway > Configuratie"
)

MSG_UNREACHABLE = (
    "De gateway is niet bereikbaar. "
    "Controleer of de add-on IPBuilding Gateway in Home Assistant draait "
    "(Instellingen > Add-ons > IPBuilding Gateway) "
    f"en of de schakelaar '{SWITCH_NAME}' aan staat "
    f"(bij Nederlands: '{SWITCH_NAME_NL}'). "
    "homeassistant.local volstaat meestal. "
    "Lukt dat niet, vul dan in Configure het adres in dat je ook in je browser "
    "gebruikt om Home Assistant te openen, zonder http:// en zonder poort."
)

MSG_NO_ADDRESS = (
    "Er is geen gateway-adres ingesteld. "
    "Vul het adres in bij de instellingen van deze bundel, "
    "bijvoorbeeld homeassistant.local, zonder http:// en zonder poort."
)

MSG_REMOTE_DEBUGGING_OFF = (
    f"De add-on draait, maar '{SWITCH_NAME}' staat uit. "
    f"Zet de schakelaar '{SWITCH_NAME}' aan in Home Assistant "
    f"({SWITCH_WHERE}) "
    "zodat de assistent opnieuw kan verbinden. "
    "Bij een Nederlandse Home Assistant heet de schakelaar "
    f"'{SWITCH_NAME_NL}' (onder Debug). "
    "De schakelaar zet live logs, veldbusframes en het sturen van testpakketten open, "
    "toont een blijvende melding in Home Assistant, en blijft aan tot je hem zelf uitzet. "
    "Wijzigen herstart de add-on."
)

MSG_SWITCH_UNKNOWN = (
    "De gateway antwoordt, maar deze versie meldt niet of "
    f"'{SWITCH_NAME}' aan staat. "
    "Kijk in Home Assistant bij Instellingen > Add-ons > IPBuilding Gateway > Configuratie. "
    f"Zet '{SWITCH_NAME}' aan als je live wilt meekijken "
    f"(bij Nederlands: '{SWITCH_NAME_NL}'). "
    "Een oudere add-on heeft die schakelaar nog niet; dan is eerst een update nodig."
)

MSG_NOT_AVAILABLE = (
    "Deze functie is nog niet beschikbaar in deze gateway-versie "
    "(not available in this gateway version yet)."
)

MSG_LOG_LEVEL_RATE_LIMITED = (
    "Het logniveau is te vaak gewijzigd. "
    "De gateway laat hoogstens 10 wijzigingen per minuut toe. "
    "Wacht even en probeer het opnieuw."
)

# Quoted by the assistant when /status has none of the live-debug capabilities.
# Wording follows docs/develop-addon.md (Add-on store, Repositories, -dev. version).
MSG_LOGS_USE_ADDON_TAB = (
    "Open in Home Assistant het tabblad Log van de add-on IPBuilding Gateway "
    "en plak de relevante regels hier."
)

MSG_GATEWAY_TOO_OLD = (
    "De gateway is bereikbaar, maar deze gateway is te oud voor live debugging; "
    "installeer de testversie via het develop-kanaal. "
    "In Home Assistant: Instellingen, Add-ons, Add-onwinkel, "
    "rechtsboven de drie puntjes, Repositories, en plak "
    "https://github.com/markminnoye/IPBuilding-Gateway#develop. "
    "Ververs de winkel. De ontwikkelversie heeft -dev. in het versienummer. "
    "De gewone release is een gewoon nummer zonder -dev. "
    "Draai niet twee gateways tegelijk."
)

_CAPABILITY_LABELS = {
    "log_stream": "Live logs meelezen",
    "udp_frame": "Veldbusframes meelezen",
    "raw_send": "Een testpakket sturen",
}

PLANNED_CAPABILITIES = ("log_stream", "udp_frame", "raw_send")

REMOTE_DEBUGGING_DISABLED = "remote_debugging_disabled"
LOG_LEVEL_RATE_LIMITED = "log_level_rate_limited"


def msg_mdns_loopback(*, loopback: list[str], tried: list[dict[str, Any]]) -> str:
    """Failure text after mDNS announced only a loopback address."""
    skipped = ", ".join(loopback) or "een loopback-adres"
    attempted = [
        str(item.get("host"))
        for item in tried
        if item.get("result") != "skipped_loopback" and item.get("host")
    ]
    attempted_text = ", ".join(attempted) or "geen ander adres"
    return (
        "mDNS vond de gateway, maar het aangekondigde adres is een loopback-adres "
        f"({skipped}). Dat adres hoort bij deze computer en is overgeslagen. "
        f"Daarna geprobeerd: {attempted_text}. "
        "Geen van die adressen antwoordde. "
        "Vul in Configure het adres in dat je ook in je browser gebruikt "
        "om Home Assistant te openen "
        "(vaak homeassistant.local, zonder http:// en zonder poort)."
    )


def msg_log_level_applied(info: dict[str, Any]) -> str:
    """Dutch sentence from a gateway ``log_level`` reply (``ttl`` is seconds)."""
    level = info.get("effective_level") or info.get("level") or "onbekend"
    ttl = info.get("ttl")
    until = info.get("reverts_at")
    if not isinstance(ttl, int):
        return f"Logniveau is nu {level}. De gateway meldde geen geldigheidsduur."
    if ttl >= 60 and ttl % 60 == 0:
        span = f"{ttl // 60} minuten ({ttl} seconden)"
    else:
        span = f"{ttl} seconden"
    when = f" tot {until}" if isinstance(until, str) and until else ""
    return (
        f"Logniveau is nu {level}. "
        f"De gateway laat dit {span} gelden{when} en valt daarna terug."
    )


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
            f"De gateway is bereikbaar en '{SWITCH_NAME}' staat aan. "
            "Live logs, veldbusframes en testpakketten zijn beschikbaar. "
            "Zet de schakelaar na afloop weer uit in Home Assistant "
            "(Instellingen > Add-ons > IPBuilding Gateway > Configuratie). "
            "De melding in Home Assistant verdwijnt nadat de add-on opnieuw is opgestart."
        )
    if len(missing) == len(PLANNED_CAPABILITIES):
        return (
            f"De gateway is bereikbaar en '{SWITCH_NAME}' staat aan. "
            "Live logs, veldbusframes en testpakketten sturen zijn in deze versie "
            f"nog niet beschikbaar ({NOT_AVAILABLE_PHRASE}). "
            "De installatie bekijken kan wel. "
            "Zet de schakelaar weer uit als je hem niet nodig hebt."
        )
    ready = [name for name in PLANNED_CAPABILITIES if name in capabilities]
    return (
        f"De gateway is bereikbaar en '{SWITCH_NAME}' staat aan. "
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


def is_log_level_rate_limited(body: Any) -> bool:
    return LOG_LEVEL_RATE_LIMITED in _error_codes(body)


def classify_http(status: int, body: Any) -> ClassifiedError:
    """Classify a non-success HTTP response from the gateway."""
    if is_log_level_rate_limited(body):
        return ClassifiedError(
            KIND_LOG_LEVEL_RATE_LIMITED,
            MSG_LOG_LEVEL_RATE_LIMITED,
            LOG_LEVEL_RATE_LIMITED,
        )
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
