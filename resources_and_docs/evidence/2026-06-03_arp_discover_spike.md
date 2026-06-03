# ARP discovery spike — 2026-06-03

**Script:** `scripts/arp_discover_spike.py` (ping sweep + `arp -an`, OUI `00:24:77`, optional HTTP)

## Verdict

| Test | Result |
|------|--------|
| Range `10.10.1.30–59` | **PASS** — 3 field modules via ARP |
| Range `10.10.1.1–254` | **PASS** — same 3 modules (geen extra `00:24:77` op /24) |
| HTTP `getSysSet` op gevonden IPs | **PASS** — JSON antwoord; geen `devtype`/`firm` in payload (zie onder) |
| `gateway/__main__discover.py` `.30–59` | **PASS** — 3 modules; `model`/`type` via `backupConfig` `device.refNr` (live `getSysSet` lacks `name`); channel labels from `channels[]`; MAC via ARP |

## Gevonden veldmodules (ARP + HTTP)

| IP | MAC | Model | Type |
|----|-----|-------|------|
| `10.10.1.30` | `00:24:77:52:ac:be` | IP200PoE | relay |
| `10.10.1.40` | `00:24:77:52:9e:a8` | IP0300PoE | dimmer |
| `10.10.1.50` | `00:24:77:52:ad:aa` | IP1100PoE | input |

Ping: 3/30 replied in `.30–59`; 5/254 in volledige sweep. ARP vult ook bij niet-pingende hosts zolang L2 antwoordt (`.40` zichtbaar in ARP).

## Implementatienota

- macOS `arp -an` gebruikt MAC-notatie `0:24:77:…` → normaliseren naar `00:24:77:…` voor OUI-filter.
- ARP-first + JSON `getSysSet` parsing + `model`/`type` via `_MODEL_TO_TYPE` geïmplementeerd in `gateway/discovery.py` (2026-06-03).
- Live `getSysSet` (2026-06-03) heeft geen `name`/`devtype`; discovery gebruikt **`backupConfig` `device.refNr`** voor `model` + `type`, en `channels[]` voor kanaallabels (relay/dimmer).
- Optioneel vervolg: `getButtons` / `pushbuttons[]` voor input-module (niet in `devices.json` — automatisering in HA).

## Open

- `type=unknown` als `name` niet in `_MODEL_TO_TYPE` staat — modules met onbekende firmware string worden nog niet getypt; `model` blijft beschikbaar voor identificatie.
- `firmware`-veld in live JSON nog niet bevestigd — zie `_DEVTYPE_MAP` opmerking in `discovery.py`.
