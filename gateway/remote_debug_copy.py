"""User-facing copy for the remote-control add-on option.

The tool name is one constant per language. Sentences below insert that
name. ``ipbuilding_gateway/translations`` must match; a test checks it.
"""

from __future__ import annotations

TOOL_NAME = {
    "en": "IPBuilding Gateway Tools",
    "nl": "IPBuilding Gateway Tools",
}

OPTION_NAME = {
    "en": "Remote control (for debugging)",
    "nl": "Bediening op afstand (voor debuggen)",
}

_OPTION_DESCRIPTION = {
    "en": (
        "Allows the {tool_name} to read live logs and field-bus traffic and "
        "to send commands to your modules remotely, so problems can be "
        "diagnosed. Only turn this on during a debug session. It stays on "
        "until you turn it off."
    ),
    "nl": (
        "Laat de {tool_name} live logs en veldbusverkeer lezen en op afstand "
        "commando's naar je modules sturen, zodat problemen opgespoord kunnen "
        "worden. Zet dit alleen aan tijdens een debugsessie. Het blijft aan "
        "tot je het zelf uitzet."
    ),
}

_NOTIFICATION_MESSAGE = {
    "en": (
        "Remote control is on. The {tool_name} can read live traffic and "
        "send commands to your modules. Turn it off in the add-on settings "
        "when debugging is finished."
    ),
    "nl": (
        "Bediening op afstand staat aan. De {tool_name} kan live verkeer "
        "lezen en commando's naar je modules sturen. Zet het uit in de "
        "instellingen van de add-on als het debuggen klaar is."
    ),
}


def language_code(language: str | None) -> str:
    """Home Assistant language. Dutch for ``nl``, English otherwise."""
    if isinstance(language, str) and language.lower().startswith("nl"):
        return "nl"
    return "en"


def option_description(language: str) -> str:
    code = language_code(language)
    return _OPTION_DESCRIPTION[code].format(tool_name=TOOL_NAME[code])


def notification_message(language: str) -> str:
    code = language_code(language)
    return _NOTIFICATION_MESSAGE[code].format(tool_name=TOOL_NAME[code])


def notification_title(language: str) -> str:
    return OPTION_NAME[language_code(language)]
