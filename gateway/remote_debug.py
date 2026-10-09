"""Refusal shared by every remote-debugging feature.

Log subscription and field-bus frame subscription use this. Raw send
must use the same code and message, on REST and on WebSocket, whenever
``remote_debugging`` is off.
"""

from __future__ import annotations

from typing import Any

from gateway.remote_debug_copy import OPTION_NAME

# Stable machine-readable code. Clients switch on this, not on the sentence.
REMOTE_DEBUGGING_DISABLED = "remote_debugging_disabled"

# Labels as shown in the Home Assistant add-on configuration UI.
OPTION_LABEL_EN = OPTION_NAME["en"]
OPTION_LABEL_NL = OPTION_NAME["nl"]
SETTINGS_PATH = "Settings > Add-ons > IPBuilding Gateway > Configuration"

REMOTE_DEBUGGING_DISABLED_MESSAGE = (
    "Remote debugging is off. Turn on "
    f'"{OPTION_LABEL_EN}" (Nederlands: "{OPTION_LABEL_NL}") '
    f"under {SETTINGS_PATH}."
)

# HTTP status for the REST form of this refusal.
REMOTE_DEBUGGING_DISABLED_STATUS = 403


def ws_remote_debugging_disabled() -> dict[str, Any]:
    """WebSocket error frame. Same code and sentence as the REST body."""
    return {
        "type": "error",
        "error": REMOTE_DEBUGGING_DISABLED,
        "message": REMOTE_DEBUGGING_DISABLED_MESSAGE,
    }
