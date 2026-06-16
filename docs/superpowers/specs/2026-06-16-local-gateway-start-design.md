# Local gateway start.sh — sim, init, help

**Datum:** 2026-06-16
**Type:** Design spec (dev tooling, gateway-side)
**Status:** Approved (2026-06-16)
**Scope:** `local/gateway/start.sh` (dev-only launcher) + kleine uitbreiding in `gateway/config.py` en `gateway/auto_discovery.py`.

---

## 1. Doel

De huidige [`local/gateway/start.sh`](local/gateway/start.sh) is simulated-only en hardcodet pad + env-vars. Voor dagelijkse dev-loop op de Mac zijn drie workflows nodig:

| Workflow | Trigger | Wanneer |
|----------|---------|---------|
| Real gateway, bestaande `devices.json` | `(geen)` | Default dagelijks werk |
| Simulated gateway (geen hardware) | `--sim` | Companion/HA testen zonder veldbus |
| Install/refresh vanaf veldbus | `--init` + shell-prompt | Eerste keer of na wijziging |

Daarnaast `--help` zodat de launcher zichzelf documenteert.

`local/` is **geen** productcode — niet verpakt in de add-on, niet verscheept. Wijzigingen raken alleen dev-workflow.

---

## 2. Twee discovery-paden, één flag

De gateway heeft al **twee** discovery-mechanismen in [`gateway/auto_discovery.py`](gateway/auto_discovery.py):

| Pad | Overschrijft `devices.json`? | Trigger vandaag |
|-----|------------------------------|-----------------|
| Init-sweep | Ja (volledige vervanging) | Lege file + `GATEWAY_AUTO_DISCOVER_ON_START=1` bij opstart |
| Forced discovery (merge) | Nee — behoudt namen/kamers/`active` | Alleen `run_forced_discovery()` vanuit `POST /api/v1/discover` of `WS {type:"discover"}` |

Beide paden bestonden al; we voegen alleen een **opstart-trigger** voor de merge toe, zodat het script de gateway niet via een HTTP round-trip hoeft aan te sturen. Eén env-var in Python, één regel in de orchestrator.

### Waarom geen POST als trigger?

Een POST-aanroep vanuit het script zou de gateway op de achtergrond starten, wachten tot de API klaar is, en dan één request doen. Problemen:

- Twee processen (background + foreground) — lastig op Raspberry Pi W
- `wait_for_api` retry-loop in shell — extra foutpad
- `curl` is een extra single-point-of-failure naast de bestaande merge-logica

Eén in-process aanroep via env-var is eenvoudiger, sneller, en deelt de bestaande merge-code met `POST /api/v1/discover`. Het endpoint blijft bestaan voor HA/operator-acties; het script gebruikt het niet.

---

## 3. Design

### Flags

| Flag | Functie |
|------|---------|
| `(geen)` | Real veldbus, passive ARP, bestaande `devices.json` |
| `--sim` | `GATEWAY_SIMULATED=1`, alle discovery uit |
| `--init` | Shell-prompt → keuze → één foreground start |
| `-h` / `--help` | Usage, exit 0 |

Conflicten: `--sim --init` → exit 1 met duidelijke melding (init vereist echte veldbus). Onbekende flags → usage + exit 1.

### Env-var matrix

| Variabele | Default | `--sim` | `--init` + y | `--init` + N |
|-----------|---------|---------|--------------|--------------|
| `GATEWAY_SIMULATED` | `0` | `1` | `0` | `0` |
| `GATEWAY_PASSIVE_ARP_MONITOR` | `1` | `0` | `1` | `1` |
| `GATEWAY_AUTO_DISCOVER_ON_START` | `0` | `0` | `1` | `0` |
| `GATEWAY_FORCE_DISCOVER_ON_START` | `0` | `0` | `0` | `1` |
| `GATEWAY_DEVICES_FILE` | `./devices.json` | idem | idem | idem |

**`AUTO_DISCOVER` en `FORCE_DISCOVER` sluiten elkaar uit** — het script zet nooit beide tegelijk.

### `--init` prompt (vóór `python -m gateway`)

```
Overwrite devices.json? Names, rooms, and active flags will be lost
(backup -> devices.json.bak).
  [y] Yes - reset and init-sweep from field bus
  [N] No  - merge discovery (keep existing config)
```

| Keuze | Vóór start | Env bij start |
|-------|------------|---------------|
| **y** | `cp devices.json devices.json.bak` (indien aanwezig), wipe naar `{"modules":[]}` | `GATEWAY_AUTO_DISCOVER_ON_START=1` |
| **N** (default) | geen file-wijziging | `GATEWAY_FORCE_DISCOVER_ON_START=1` |

De prompt vraagt **vóór** `python -m gateway` — niet tijdens runtime. Dat is gewoon bash `read` op `/dev/tty`. De gateway heeft bij start alle info om direct de juiste discovery-sweep te draaien.

Daarna: één `python -m gateway` foreground. Geen achtergrond, geen curl, geen wacht-loop.

### Python-uitbreiding

[`gateway/config.py`](gateway/config.py):

```python
force_discover_on_start: bool = False
# from_env: GATEWAY_FORCE_DISCOVER_ON_START in (1, true, yes)
```

[`gateway/auto_discovery.py`](gateway/auto_discovery.py) — in `DiscoveryOrchestrator.start()`, na init-sweep en vóór ARP-monitor:

```python
if self._config.force_discover_on_start:
    try:
        result = await self.run_forced_discovery()
        log.info("DiscoveryOrchestrator: force-discover on start: %s", result)
    except Exception:
        log.exception("DiscoveryOrchestrator: force-discover on start failed")
```

`run_forced_discovery()` is **dezelfde code** als `POST /api/v1/discover`. Geen nieuwe merge-implementatie.

`force_discover_on_start` wordt op **beide** `DiscoveryConfig` klassen gezet (in `config.py` en `auto_discovery.py`) — ze bestaan historisch dubbel, en `main.py` geeft die van `config.py` door aan de orchestrator.

### Test

[`tests/test_auto_discovery.py`](tests/test_auto_discovery.py):

- `test_discovery_config_from_env` — `GATEWAY_FORCE_DISCOVER_ON_START=1` → `force_discover_on_start is True`
- `test_start_runs_forced_discovery_when_force_flag_set` — `run_forced_discovery` wordt aangeroepen bij `start()`
- `test_start_does_not_run_forced_discovery_by_default` — flag uit = geen aanroep

---

## 4. Wat `--init` NIET doet

- Geen interactieve runtime-prompt (alleen vóór start)
- Geen tweede gateway-proces op de achtergrond
- Geen HTTP-call naar een eigen endpoint
- Geen `--init merge|reset` argumenten (niet scripteerbaar zonder stdin — bewuste keuze voor dev-launcher)
- Geen wijziging aan `~/.homeassistant`, companion entities, of module-EEPROM

---

## 5. Add-on parity (optioneel, buiten scope)

[`ipbuilding_gateway/run.sh`](ipbuilding_gateway/run.sh) en [`ipbuilding_gateway/config.yaml`](ipbuilding_gateway/config.yaml) tonen `GATEWAY_AUTO_DISCOVER_ON_START` al als add-on option. `GATEWAY_FORCE_DISCOVER_ON_START` werkt via `config.py.from_env()` zonder extra wijziging; toevoegen aan de add-on UI is een aparte workstream (niet in deze PR nodig voor lokaal dev).

---

## 6. Verificatie

| Test | Verwacht |
|------|----------|
| `./local/gateway/start.sh --help` | Usage, exit 0 |
| `./local/gateway/start.sh --sim --init` | Error, exit 1 |
| `./local/gateway/start.sh --unknown` | Error + usage, exit 1 |
| `./local/gateway/start.sh --init` → `y` (TTY) | `.bak` aanwezig, lege `devices.json`, init-sweep log |
| `./local/gateway/start.sh --init` → `N` (TTY) | `devices.json` ongewijzigd, merge-sweep log |
| `./local/gateway/start.sh` (default) | Real veldbus, geen prompt |
| `./local/gateway/start.sh --sim` | Sim, geen UDP, geen prompt |
| `pytest tests/test_auto_discovery.py` | PASS |

---

## 7. Bestanden

| Actie | Bestand |
|-------|---------|
| Herschrijven | [`local/gateway/start.sh`](local/gateway/start.sh) |
| Bijwerken | [`local/README.md`](local/README.md) |
| Wijzigen | [`gateway/config.py`](gateway/config.py) |
| Wijzigen | [`gateway/auto_discovery.py`](gateway/auto_discovery.py) |
| Wijzigen | [`tests/test_auto_discovery.py`](tests/test_auto_discovery.py) |
| Nieuw | [`docs/superpowers/specs/2026-06-16-local-gateway-start-design.md`](docs/superpowers/specs/2026-06-16-local-gateway-start-design.md) |
| Aanvulling | [`README_gateway.md`](README_gateway.md) |
