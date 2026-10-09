## Installeren

Dubbelklik op `ipbuilding-gateway-tools.mcpb`. Claude Desktop vraagt of je IPBuilding Gateway Tools wil installeren. Kies **Install**. Staat de plug-in er al, dan staat er **Update**.

`homeassistant.local` volstaat meestal. Druk dan op **Save**.

Zegt de assistent dat de gateway niet bereikbaar is, controleer dan of de add-on draait en of de schakelaar aan staat. Vul bij **Configure** het adres in dat je ook in je browser gebruikt om Home Assistant te openen, zonder `http://` en zonder poort.

Je hebt de gateway nodig van develop `1.8.0-dev.5` of nieuwer.

## IPBuilding Gateway Tools

Met deze plug-in krijgt Claude toegang tot je IPBuilding Gateway om je installatie te testen en te debuggen. Claude kan commando's uitvoeren en de resultaten ervan terugkrijgen als feedback.

**Meekijken aanzetten**

Claude kan pas meekijken als een schakelaar aan staat.

1. Ga in Home Assistant naar Instellingen → Add-ons → IPBuilding Gateway → Configuratie.
2. Zet onder Debug de schakelaar **Bediening op afstand (voor debuggen)** aan (Engels: *Remote control (for debugging)*).
3. De add-on start even opnieuw. Dat hoort zo.

Let op: zolang de schakelaar aan staat, kan iedereen op je thuisnetwerk meelezen met je modules en testpakketjes sturen. De schakelaar gaat niet vanzelf uit.

**Voorbeelden van vragen**

Je mag gewoon in je eigen woorden vragen. Claude vraagt altijd eerst bevestiging voordat er iets geschakeld of verstuurd wordt.

*Je installatie in kaart brengen*
- "Met welke gateway ben je verbonden, en wat kun je allemaal?"
- "Welke modules heb ik, en welke lampen, dimmers en knoppen hangen eraan?"
- "Zoek opnieuw naar modules en vertel me wat er veranderd is."
- "Antwoorden al mijn modules? Is er een die traag of niet reageert?"
- "Welke taal (dialect) spreken mijn modules?"

*Testen en meekijken*
- "Ik druk zo op een knop. Vertel me wat de gateway ziet, met module en kanaal."
- "Zet de lamp in de keuken aan en controleer of de module dat bevestigt."
- "Dim de lamp boven de tafel naar 30% en daarna weer uit."
- "Toon de logs van de laatste minuut. Zie je fouten of waarschuwingen?"

*Een probleem uitzoeken*
- "Het licht in de living gaat soms niet uit. Help me uitzoeken waarom."
- "Een knop in de gang reageert niet altijd. Wat zie je gebeuren als ik druk?"
- "Een dimmer doet raar. Kijk mee terwijl ik hem bedien."

*Feedback geven*
- "Maak een rapport van deze sessie, zonder adressen of namen erin."
- "Wat werkte vandaag niet, en wat zou de gateway beter moeten doen?"

**Klaar?**

Zet de schakelaar weer uit. De add-on start opnieuw en de melding in Home Assistant verdwijnt. Stuur het rapport naar ons, zodat we de software kunnen verbeteren.

## Layout

| Path | Role |
| --- | --- |
| `ipbuilding_debug/` | MCP server |
| `skills/ipbuilding-gateway-tools/SKILL.md` | Session guidance, also sent as the server instructions |
| `HANDLEIDING.md` | Plain-language install guide |
| `.claude-plugin/`, `.mcp.json` | Claude Code plugin |
| `scripts/build.py` | One build used locally and in CI |
| `VERSION` | Version. A release tag `gateway-tools-vX.Y.Z` must match this file |

The gateway address is a user setting (`gateway_address` in the bundle, the same key in the Claude Code plugin). It is optional. The manifest default is `homeassistant.local`, and that host usually suffices. The server skips a loopback address from mDNS, then tries the mDNS hostname, then the configured address. From the newer develop add-on the gateway announces its LAN address. If `connection_status` says the gateway is unreachable, the tester checks that the add-on is running and the switch is on, and fills Configure with the address used in the browser to open Home Assistant. It is passed as `IPBUILDING_GATEWAY_ADDRESS`.

## Tools

| Tool | This version | Waits on |
| --- | --- | --- |
| `connection_status` | Works against `/api/v1/status` and the local buffer. Reports `connected`, `capability_status` (`supported` for the gateway version, `active` for working now, with a plain-language `reason` when `active` is false), `missing_capabilities`, `unavailable_tools`, the host, and how it was found (`mdns`, `mdns_hostname`, `config_default`, or `manual`). A loopback address from mDNS is skipped; the mDNS hostname is tried next, then the bundle address. Shows the current log level and when it falls back, once the gateway has reported a `ttl`. If the status omits the switch, one log subscription is used as a probe | — |
| `gateway_health` | Status, subsystems, issues, uptime, buffer from `/api/v1/status` | — |
| `list_devices` | Module, channel, type, name, state from `/modules` and `/devices`. Relay and dimmer channels count from 0. Shows `last_seen` when the gateway sends it. Shows per-module `reachability` (`last_reply_at`, `last_reply_ms`, `avg_reply_ms`, `missed_replies`) when that object is present. An older gateway without the object is told the timing is not in this version. No capability and no probe | — |
| `recent_events` | Buffered `state_changed` and `button_event` (press, single_press, release). No `udp_frame` required | — |
| `read_logs` | Subscribes to the live log stream. Filters on `since` or the last `seconds`, minimum level, and `limit`. Redacts addresses and names unless `redact=false`. Without `log_stream`, points at the add-on Log tab | Gateway `log_stream` |
| `discover` | `POST /api/v1/discover` only after `confirmed=true`, then the inventory diff | — |
| `device_command` | `POST /api/v1/devices/{id}/command` only after `confirmed=true`. Reports `module_confirmed`, `confirm_ms`, and `reported` when the gateway sends them. Without those fields, says this version cannot confirm the module. A confirmed send is stored as `command_result` for the report. A preview is not | — |
| `probe_generation` | Works against `/status`, `/modules`, `/devices` | — |
| `decode_test` | Local, uses `gateway/payloads`, then shows the current dialect city name. Kessel-Lo (`kessel-lo`) and Torhout (`torhout`) are defined in `ipbuilding_debug/dialect.py`. The result is stored as `decode_result` for the report | — |
| `export_session` | Local notes and buffered events. Each event gets `local_time` (ISO 8601 with offset) and `time_source` (`gateway` or `received`). Redacts addresses, MAC addresses, email addresses, and names unless `redact=false`. Adds a fixed plain-text report and YAML frontmatter. `command_result` and `decode_result` appear under Wat getest werd. A command the module confirmed is also under Bevestigd. No module reply is `niet bevestigd` | Live logs appear in the export once `log_stream` is active |
| `send_report` | On by default. Shows the privacy notice and the filtered report, then a `mailto:` link after `confirmed=true`. The process does not send mail. Without `IPBUILDING_REPORT_INTAKE` the option is unavailable. The Linear template files the ticket in the backlog with the label Agent | — |
| `capture_frames` | Subscribes when `udp_frame` is advertised | Gateway `udp_frame` |
| `send_raw` | `POST /api/v1/debug/raw-send` when `raw_send` is advertised, and only after `confirmed=true`. Body is `module_ip`, optional port 1001, `payload_hex` (1–64 bytes), `window_ms` (1–3000, default 2000). Empty `replies` is success | Gateway raw send |

If a name is missing from `/status.capabilities`, the tool returns a not-available message instead of failing. Planned names: `log_stream`, `udp_frame`, `raw_send`. A listed name with the switch off is `supported` and not `active`. Button and state events still arrive while the switch is off; log lines do not.

Dialect ids and display names are `Dialect` values in `ipbuilding_debug/dialect.py`. An older gateway id is rewritten there and is not repeated in docs or tool output. A new dialect from another tester gets a random city, never a home town and never a personal name.

`connection_status` also tells the tester when **Remote control (for debugging)** is off (`remote_debugging: false`, or error code `remote_debugging_disabled`). In Dutch the switch is **Bediening op afstand (voor debuggen)**.

## Contract the later gateway changes should meet

The client already speaks this. Adjust the client in the same change if the gateway picks different names.

- WebSocket client → gateway, only when `log_stream` is listed: `{"type":"subscribe_logs","min_level":"info"}` and `{"type":"set_log_level","level":"DEBUG","ttl":900}`. The gateway accepts `debug`, `info`, `warning`, or `error`. A successful reply is `{"type":"log_level","ok":true,"level":"debug","ttl":900,"effective_level":"debug"}`. It has no absolute expiry; the toolkit computes `reverts_at` from `ttl` and says when the level falls back. Live lines are `{"type":"log","ts":"...","level":"info","logger":"...","message":"..."}`. More than 10 level changes in 60 seconds come back as `{"type":"error","error":"log_level_rate_limited"}`. The tool then tells the tester to wait a minute.
- WebSocket client → gateway, only when `udp_frame` is listed and a capture is running: `{"type":"subscribe_udp_frames"}`.
- Gateway → client frames: `{"type":"udp_frame","direction":"tx","hex":"...","src":"...","dst":"...","port":1001}`.
- Raw send: `POST /api/v1/debug/raw-send` with `target`, `port`, `payload_hex`, `window_ms`. Refusal body: `{"error":"remote_debugging_disabled"}`.

The WebSocket stays up for the life of the MCP process, reconnects with backoff from 1 s to 30 s, resubscribes, replaces local state from the snapshot, and inserts a gap marker. `wait_for_state` never waits longer than 30 s. Logging goes to stderr.

## Build and release

```bash
python3 toolkit/scripts/build.py
```

The script stages a bundle, copies the decoders it needs, and runs `mcpb validate` and `mcpb pack`. CI does the same on every pull request. A tag `gateway-tools-vX.Y.Z` whose number matches `VERSION` attaches the `.mcpb` to a GitHub release. The release text is `HANDLEIDING.md`. The workflow artifact is `ipbuilding-gateway-tools`. The packed file is `ipbuilding-gateway-tools-<version>.mcpb`.

Sending a report is on unless `IPBUILDING_REPORT_SEND` is `0`, `false`, `no`, or `off`. The intake address is not in the repository. CI passes the Actions secret `IPBUILDING_REPORT_INTAKE` into the bundle environment of the same name, and only when that value is non-empty. Without it, `send_report` stays unavailable. A confirmed call returns a `mailto:` link; the toolkit does not send the mail. The Linear template puts the ticket in the backlog with the label Agent.

Each test bundle uses the next `0.1.0-rc.N` (`rc.1`, `rc.2`, …) in `toolkit/VERSION`. The same string goes in `.claude-plugin/plugin.json`, `pyproject.toml`, and the `.mcpb` manifest. Raise N by one for every new test build so Claude Desktop offers Update instead of Install, and so the builds stay distinct. Do not reuse a number.

Do not use a `vX.Y.Z` tag for this package. That tag builds the Home Assistant add-on.

## Tests

```bash
PYTHONPATH=toolkit:. python3 -m pytest toolkit/tests -q
```

Tests use a fake gateway on localhost. They do not touch a real installation.
