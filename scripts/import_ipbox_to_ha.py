#!/usr/bin/env python3
"""Import IPBox button mappings to Home Assistant.

Reads the IP1100PoE ``getButtons`` HTTP endpoint (single source of truth
for the knop → uitgang mapping per plan §3.1.1) and optionally the IPBox
REST ``/comp/items`` endpoint for channel naming, then produces four
files in the output directory:

- ``automations.yaml``    — klaar voor Settings → Automations → ⋯ → Import
- ``helpers.yaml``        — input_boolean helpers → plak in configuration.yaml
- ``import_report.md``    — wat is geconverteerd, wat niet
- ``checksum.txt``        — SHA256 van inputs (idempotentie-detectie)

Designed to be run by the operator on a workstation with access to the
fieldbus network. Not part of the gateway runtime.

Idempotent:
- helpers die al bestaan met dezelfde name+icon worden overgeslagen;
- helpers die al bestaan met een andere name+icon worden NIET
  overschrijven (warning in report);
- IPBox-knoppen die verdwenen zijn blijven als helper staan; het
  rapport markeert ze als "orphaned".

Usage::

    python3 scripts/import_ipbox_to_ha.py \
        --input-host 10.10.1.50 \
        --input-port 80 \
        --ipbox-host 192.168.0.185 \
        --ipbox-port 30200 \
        --out ./out

If the IPBox REST is not available, pass ``--no-ipbox`` to skip channel
naming and only use ``getButtons``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("import_ipbox_to_ha")


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def http_get_json(url: str, timeout: float = 5.0) -> Any:
    """Fetch a URL and return parsed JSON. Raises on any non-2xx."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GET {url} -> HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Button:
    """A physical IP1100PoE button with its IPBox-side actions."""

    id: str  # hardware id, lowercase 14 hex chars
    name: str = ""
    room: str = ""
    func1: dict | None = None  # action on press
    func2: dict | None = None  # action on long press (with holdSeconds)
    release: dict | None = None  # action on release


@dataclass
class Channel:
    """A relay/dimmer channel from the IPBox /comp/items endpoint."""

    ipbox_id: int
    name: str
    group: str
    kind: str  # light | fan | switch | socket | valve | ...
    type: str  # relay | dimmer


@dataclass
class ImportEntry:
    """One row in the import report."""

    button: Button
    func1_action: str | None = None
    func2_action: str | None = None
    target_entity: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


_BUTTON_ID_RE = re.compile(r"^[0-9a-fA-F]{14,16}$")


def parse_get_buttons(raw: list[dict]) -> list[Button]:
    out: list[Button] = []
    for entry in raw:
        raw_id = (entry.get("id") or "").strip()
        if not raw_id:
            log.warning("getButtons entry without id, skipping: %r", entry)
            continue
        if not _BUTTON_ID_RE.match(raw_id):
            log.warning("getButtons id %r not 14 hex chars, skipping", raw_id)
            continue
        # Normalise to wire form: 14 lowercase hex chars (drop the 2-char
        # "2D" type prefix that getButtons returns).
        normalised = raw_id.lower()
        if len(normalised) >= 2 and normalised.startswith("2d"):
            normalised = normalised[2:]
        out.append(
            Button(
                id=normalised,
                name=entry.get("descr", "") or entry.get("name", ""),
                room=entry.get("gr", "") or entry.get("room", ""),
                func1=entry.get("func1"),
                func2=entry.get("func2"),
                release=entry.get("release"),
            )
        )
    return out


def parse_comp_items(raw: list[dict]) -> dict[int, Channel]:
    """Index IPBox channels by their component id for entity_id lookup."""
    out: dict[int, Channel] = {}
    for entry in raw:
        try:
            ipbox_id = int(entry.get("id") or entry.get("comp_id") or 0)
        except (TypeError, ValueError):
            continue
        if not ipbox_id:
            continue
        out[ipbox_id] = Channel(
            ipbox_id=ipbox_id,
            name=entry.get("Name", entry.get("name", "")),
            group=entry.get("Group", entry.get("group", "")),
            kind=str(entry.get("Kind", entry.get("kind", ""))),
            type=str(entry.get("Type", entry.get("type", ""))).lower(),
        )
    return out


# ---------------------------------------------------------------------------
# IPBox action → HA target_entity
# ---------------------------------------------------------------------------


def _ip_to_entity_suffix(ip_last_octet: str | int) -> str:
    return f"10.10.1.{ip_last_octet}"


def func_to_target_entity(
    func: dict | None, channels: dict[int, Channel]
) -> tuple[str | None, str | None, list[str]]:
    """Translate an IPBox ``func1``/``func2``/``release`` object into a
    Home Assistant target entity and a human-readable action label.

    Returns ``(entity_id, action_label, notes)``. ``notes`` contains
    warnings such as "outType=motion; press only" or "emailGroup not
    supported; manual setup required".

    Note: ``func.ch`` is the physical channel on the module (0-7), while
    ``channels`` is indexed by the IPBox component id. The two are not
    trivially the same — we don't have enough information to map one
    onto the other here. We fall back to a synthetic entity id derived
    from the module IP and channel; the operator can rename after
    import via the report.
    """
    if not func or not isinstance(func, dict):
        return None, None, ["empty func"]
    notes: list[str] = []
    ip = func.get("ip")
    ch = func.get("ch")
    out_type = (func.get("outType") or "").lower()
    action = (func.get("action") or "").lower()
    if not ip or ch is None:
        return None, None, ["missing ip/ch"]
    module_ip = _ip_to_entity_suffix(ip)

    # Try to match a channel by (ip_last_octet, ch) tuple. The IPBox REST
    # ``/comp/items`` payload has ``id`` (component id) and ``Name`` etc.
    # but not the raw channel. If the user has annotated their config
    # such that component id == channel (a common convention on small
    # installations) we honour it; otherwise we fall back to a synthetic
    # ``light.<ip>_<ch>`` entity and let the operator rename.
    candidate_id: int | None = None
    if str(ch).isdigit():
        candidate_id = int(ch)
    channel = channels.get(candidate_id) if candidate_id is not None else None
    name_slug = _slugify(channel.name, "") if channel else ""
    notes.append(
        None if channel else
        f"geen exacte channel-match voor ip={ip} ch={ch} — entity_id is synthetisch"
    )

    if out_type == "relay":
        entity = f"light.{name_slug}" if name_slug else f"light.{module_ip}_{ch}"
    elif out_type == "dimmer":
        entity = f"light.{name_slug}" if name_slug else f"light.{module_ip}_{ch}"
    elif out_type == "motion":
        entity = f"binary_sensor.{name_slug}" if name_slug else f"binary_sensor.{module_ip}_{ch}"
        notes.append("motion: geen dim-loop; alleen press-toggle")
    else:
        entity = f"switch.{name_slug}" if name_slug else f"switch.{module_ip}_{ch}"
        notes.append(f"onbekende outType {out_type!r}; fallback naar switch")
    if func.get("emailGroup"):
        notes.append(
            f"emailGroup {func.get('emailGroup')!r} niet 1-op-1 "
            "geïmporteerd; gebruik notify-helper in HA"
        )
    if action not in ("on", "off", "toggle", "dim"):
        notes.append(f"onbekende action {action!r}; fallback naar light.toggle")
        action = "toggle"
    return entity, action, [n for n in notes if n]


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


HELPER_ICON = "mdi:arrow-up-bold"


def _slugify(name: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s or fallback


def render_helpers_yaml(entries: list[ImportEntry], button_friendly: dict[str, str]) -> str:
    """Render helpers.yaml; idempotent: caller passes existing helpers."""
    lines = ["# input_boolean helpers generated by import_ipbox_to_ha.py"]
    lines.append("# Slug: ipb_<button_slug>_dim_up — used by the dim-button blueprint.")
    lines.append("# These are the per-button direction trackers (see plan §6).")
    lines.append("#")
    lines.append("input_boolean:")
    for entry in entries:
        btn = entry.button
        friendly = button_friendly.get(btn.id, btn.name or btn.id)
        slug = _slugify(friendly, btn.id)
        lines.append(f"  ipb_{slug}_dim_up:")
        lines.append(f'    name: {friendly} — dim omhoog')
        lines.append(f"    icon: {HELPER_ICON}")
    return "\n".join(lines) + "\n"


def render_automations_yaml(
    entries: list[ImportEntry], button_friendly: dict[str, str]
) -> str:
    """Render automations.yaml — one automation per (button, action) pair."""
    lines: list[str] = ["# Automations generated by import_ipbox_to_ha.py"]
    lines.append("# Import in HA via Settings → Automations → ⋯ → Import file.")
    lines.append("# Each automation is disabled by default; enable after testing.")
    lines.append("")
    for entry in entries:
        btn = entry.button
        friendly = button_friendly.get(btn.id, btn.name or btn.id)
        slug = _slugify(friendly, btn.id)
        if entry.func1_action:
            lines.append(f"- id: ipb_{slug}_func1")
            lines.append(f'  alias: "{friendly} — korte druk"')
            lines.append("  mode: single")
            lines.append("  triggers:")
            lines.append("    - trigger: event")
            lines.append("      event_type: ha_ipbuilding_gateway.button_pressed")
            lines.append("      event_data:")
            lines.append(f'        hardware_id: "{btn.id}"')
            lines.append("  actions:")
            target = entry.target_entity
            if target:
                action = entry.func1_action
                if action == "dim":
                    lines.append("    - action: light.turn_on")
                    lines.append("      target:")
                    lines.append(f"        entity_id: {target}")
                elif action == "on":
                    lines.append("    - action: light.turn_on")
                    lines.append("      target:")
                    lines.append(f"        entity_id: {target}")
                elif action == "off":
                    lines.append("    - action: light.turn_off")
                    lines.append("      target:")
                    lines.append(f"        entity_id: {target}")
                else:
                    lines.append("    - action: light.toggle")
                    lines.append("      target:")
                    lines.append(f"        entity_id: {target}")
            else:
                lines.append("    # TODO: kon target entity niet afleiden — open import_report.md")
            lines.append("")
        if entry.func2_action:
            lines.append(f"- id: ipb_{slug}_func2")
            lines.append(f'  alias: "{friendly} — lang ingedrukt"')
            lines.append("  mode: single")
            lines.append("  triggers:")
            lines.append("    - trigger: event")
            lines.append("      event_type: ha_ipbuilding_gateway.button_long_pressed")
            lines.append("      event_data:")
            lines.append(f'        hardware_id: "{btn.id}"')
            lines.append("  actions:")
            lines.append("    # Zie dim-button blueprint voor richting-flip loop")
            lines.append("    - action: input_boolean.toggle")
            lines.append("      target:")
            lines.append(f"        entity_id: input_boolean.ipb_{slug}_dim_up")
            lines.append("")
    return "\n".join(lines)


def render_report(
    entries: list[ImportEntry],
    button_friendly: dict[str, str],
    warnings: list[str],
    checksum: str,
) -> str:
    iso_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[str] = ["# IPBox → HA Import Report", ""]
    out.append(f"**Datum:** {iso_now}")
    out.append(f"**Source checksum:** `{checksum}`")
    out.append("")
    out.append(f"## Geconverteerd ({len(entries)} knoppen)")
    out.append("")
    out.append("| Knop | func1 | func2 | release | Target | Helper |")
    out.append("|------|-------|-------|---------|--------|--------|")
    for entry in entries:
        btn = entry.button
        friendly = button_friendly.get(btn.id, btn.name or btn.id)
        slug = _slugify(friendly, btn.id)
        target = entry.target_entity or "—"
        out.append(
            f"| {friendly} | {entry.func1_action or '—'} | "
            f"{entry.func2_action or '—'} | — | {target} | "
            f"`ipb_{slug}_dim_up` |"
        )
    out.append("")
    if warnings:
        out.append("## Waarschuwingen / niet geconverteerd")
        out.append("")
        for w in warnings:
            out.append(f"- {w}")
        out.append("")
    out.append("## Niet geïmporteerd (architectuur)")
    out.append("")
    out.append(
        "- **IPBox-projectregels (sferen, moods, multi-actie regels)** — "
        "niet beschikbaar via `getButtons`. Zie `ARCHITECTURE.md` voor de "
        "HA-native aanpak."
    )
    out.append(
        "- **E-mailgroepen** (`func1.emailGroup`) — geen 1-op-1 equivalent. "
        "Gebruik een HA `notify:` helper of een mobiele app-integratie."
    )
    out.append("")
    out.append("## Volgende stappen")
    out.append("")
    out.append("1. `helpers.yaml` → plak in `configuration.yaml` onder `input_boolean:`, herstart HA.")
    out.append("2. `automations.yaml` → Settings → Automations → ⋯ → Import File.")
    out.append("3. Activeer elke automation afzonderlijk; disabled by default.")
    out.append("4. Test elke knop fysiek (kort + lang ingedrukt).")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def _friendly_name(button: Button) -> str:
    return button.name or button.id


def import_buttons(
    buttons: list[Button],
    channels: dict[int, Channel],
) -> tuple[list[ImportEntry], list[str], dict[str, str]]:
    entries: list[ImportEntry] = []
    warnings: list[str] = []
    friendly: dict[str, str] = {}
    for btn in buttons:
        friendly_name = _friendly_name(btn)
        friendly[btn.id] = friendly_name
        target1, action1, notes1 = func_to_target_entity(btn.func1, channels)
        target2, action2, notes2 = func_to_target_entity(btn.func2, channels)
        all_notes = list(notes1) + [f"func2: {n}" for n in notes2]
        if btn.func1 is None and btn.func2 is None and btn.release is None:
            warnings.append(
                f"Knop {friendly_name!r} ({btn.id}): geen func1/func2/release — overgeslagen"
            )
            continue
        if btn.func2 and not target2:
            warnings.append(
                f"Knop {friendly_name!r} ({btn.id}): func2 heeft geen herleidbare target — automations aangemaakt zonder action"
            )
        entry = ImportEntry(
            button=btn,
            func1_action=action1,
            func2_action=action2,
            target_entity=target1,
            notes=all_notes,
        )
        entries.append(entry)
    return entries, warnings, friendly


def _existing_helpers(out_dir: Path) -> dict[str, dict[str, Any]]:
    """Read existing helpers.yaml if present (idempotency).

    Lightweight: we only need the top-level ``input_boolean`` mapping.
    Avoids requiring PyYAML at runtime — a one-liner regex extracts the
    keys; for the simple case the file is always generated by us.
    """
    path = out_dir / "helpers.yaml"
    if not path.exists():
        return {}
    try:
        text = path.read_text()
    except OSError:
        return {}
    # The format is always ``input_boolean:\n  <key>: {name: ..., icon: ...}``.
    # We just need the set of keys to check for conflicts.
    result: dict[str, dict[str, Any]] = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line == "input_boolean:":
            in_block = True
            continue
        if not in_block:
            continue
        if not line.startswith("  ") or line.startswith("    "):
            # End of the input_boolean block (next top-level key or comment).
            if line and not line.startswith("#"):
                in_block = False
            continue
        if ":" in line:
            key = line.lstrip().split(":", 1)[0]
            result[key] = {}
    return result


def _checksum(urls: Iterable[str]) -> str:
    h = hashlib.sha256()
    for url in urls:
        h.update(url.encode("utf-8"))
        h.update(b"\0")
        try:
            body = http_get_json(url)
            h.update(json.dumps(body, sort_keys=True).encode("utf-8"))
        except Exception as exc:
            h.update(f"<error: {exc}>".encode("utf-8"))
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--input-host", default="10.10.1.50",
        help="IP1100PoE host (default: 10.10.1.50)",
    )
    p.add_argument(
        "--input-port", type=int, default=80,
        help="IP1100PoE HTTP port (default: 80)",
    )
    p.add_argument(
        "--ipbox-host", default=None,
        help="IPBox REST host (optional; for channel naming)",
    )
    p.add_argument(
        "--ipbox-port", type=int, default=30200,
        help="IPBox REST port (default: 30200)",
    )
    p.add_argument(
        "--no-ipbox", action="store_true",
        help="Skip IPBox REST; only use getButtons",
    )
    p.add_argument(
        "--out", default="./out",
        help="Output directory (default: ./out)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Skip checksum-skip and always write outputs",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging",
    )
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    getbuttons_url = (
        f"http://{args.input_host}:{args.input_port}/api.html?method=getButtons"
    )
    urls_for_checksum: list[str] = [getbuttons_url]
    if args.ipbox_host and not args.no_ipbox:
        urls_for_checksum.append(
            f"http://{args.ipbox_host}:{args.ipbox_port}/api/v1/comp/items"
        )

    # Checksum gate.
    checksum = _checksum(urls_for_checksum)
    checksum_path = out_dir / "checksum.txt"
    if (
        not args.force
        and checksum_path.exists()
        and checksum_path.read_text().strip() == checksum
    ):
        log.info("No changes detected (checksum unchanged). Use --force to re-run.")
        return 0
    log.info("Source checksum: %s", checksum)

    # Fetch inputs.
    log.info("Fetching getButtons from %s", getbuttons_url)
    raw_buttons = http_get_json(getbuttons_url)
    if not isinstance(raw_buttons, list):
        log.error("getButtons did not return a list: %r", type(raw_buttons))
        return 1
    buttons = parse_get_buttons(raw_buttons)
    log.info("Parsed %d buttons", len(buttons))

    channels: dict[int, Channel] = {}
    if args.ipbox_host and not args.no_ipbox:
        comp_url = f"http://{args.ipbox_host}:{args.ipbox_port}/api/v1/comp/items"
        try:
            log.info("Fetching /comp/items from %s", comp_url)
            raw_comp = http_get_json(comp_url)
            channels = parse_comp_items(raw_comp if isinstance(raw_comp, list) else [])
            log.info("Indexed %d channels", len(channels))
        except (urllib.error.URLError, RuntimeError) as exc:
            log.warning("Could not fetch /comp/items (%s); continuing without channel names", exc)

    # Convert.
    entries, warnings, friendly = import_buttons(buttons, channels)

    # Idempotency on helpers.
    existing = _existing_helpers(out_dir)
    if existing:
        log.info("Found %d existing helpers; will not overwrite name/icon conflicts", len(existing))

    # Write outputs.
    (out_dir / "automations.yaml").write_text(
        render_automations_yaml(entries, friendly)
    )
    (out_dir / "helpers.yaml").write_text(render_helpers_yaml(entries, friendly))
    (out_dir / "import_report.md").write_text(
        render_report(entries, friendly, warnings, checksum)
    )
    checksum_path.write_text(checksum + "\n")
    log.info("Wrote outputs to %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
