"""Privacy notice shown before a tester confirms a debug report.

There is no privacy-statement link for this project.
"""

from __future__ import annotations

# Shown above every report. Exact warning from the privacy review.
FEEDBACK_WARNING = "Zet geen namen, adressen, wachtwoorden of codes in je feedback."

# Confirmed by Mark. The whole ticket is deleted, not only the email address.
RETENTION = (
    "12 maanden na het afsluiten van het ticket, daarna wordt het volledige ticket verwijderd"
)

# Public contact for questions or deletion. Not the Linear intake address.
CONTACT_ADDRESS = "mark@sonicrocket.be"


def privacy_notice() -> str:
    """Three sentences, shown before the tester confirms sending."""
    return (
        "Je verstuurt dit gefilterde rapport, inclusief je e-mailadres, "
        "naar Sonic Rocket, dat het ticket bewaart in Linear, "
        "om je probleem te onderzoeken en de toolkit te verbeteren. "
        f"Bewaartermijn: {RETENTION}. "
        f"Vragen of verwijdering: {CONTACT_ADDRESS}."
    )
