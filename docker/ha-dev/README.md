# IPBuilding — Mac HA dev stack

Lokale testomgeving voor de **companion** (`ipbuilding-gateway-ha`) tegen een **simulated gateway**. De gateway draait als Python-proces op je Mac; Home Assistant draait in een container (OrbStack). Geen veldbus, geen EEPROM, geen IPBox nodig.

## Architectuur

```
[Browser] ──> http://localhost:8123 ──> [HA container in OrbStack]
                                          │ http://host.docker.internal:8080
                                          ▼
                                       [gateway: python -m gateway op Mac :8080]
```

De companion bind-mount komt uit `../ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha` (sibling repo).

## Vereisten

- macOS 13+ (Apple Silicon aanbevolen)
- **OrbStack** (aanbevolen) of Docker Desktop — geïnstalleerd en **running**
  - Start OrbStack vanuit `/Applications/OrbStack.app` en wacht tot de menubalk "running" toont
  - Verifieer: `docker ps` werkt zonder error
- Sibling clone van [`ipbuilding-gateway-ha`](https://github.com/markminnoye/ipbuilding-gateway-ha) (commit v0.1.1+)
- Poorten 8080 en 8123 vrij op de host
- Python venv: `cd "/Users/markminnoye/git/IPBuilding Gateway" && source .venv/bin/activate`

## Eerste keer

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-dev"
cp .env.example .env
# Pas .env aan als je companion-pad afwijkt
```

## Starten

```bash
./scripts/up.sh
```

Dit script:
1. Start de simulated gateway op de achtergrond
2. Wacht tot `http://127.0.0.1:8080/health` antwoord geeft
3. Start de Home Assistant container
4. Print URLs en wacht tot je `Ctrl+C` drukt

Handmatig equivalent (als je processen liever gescheiden houdt):

```bash
# Terminal 1 — gateway
./scripts/start-gateway.sh

# Terminal 2 — HA
docker compose up -d
```

## Verifiëren vóór HA-onboarding

```bash
./scripts/smoke.sh
```

Verwacht: `PASS`, ~28 devices uit je `devices.json`.

## Home Assistant onboarden

1. Open `http://localhost:8123`
2. Maak een account aan, finish de onboarding wizard
3. Wacht tot HA klaar is (kan 1–2 min duren bij eerste start)

## Companion integratie toevoegen

> **Let op:** plain Docker HA heeft **geen Supervisor**, dus de auto-detect werkt niet. Je moet handmatig host/poort opgeven.

1. **Settings → Devices & services → Add integration**
2. Zoek **IPBuilding Gateway HA**
3. Kies **"manual entry"** (geen add-on-detect)
4. Host: `host.docker.internal` — **niet** `127.0.0.1` (dat is HA zelf)
5. Port: `8080`
6. Verifieer: HA toont ~28 entities (afhankelijk van je `devices.json`)

## Testen

**Entities bekijken:** Developer Tools → States → filter `light.`, `switch.`, `sensor.`

**Light togglen:** klik op een entity in Developer Tools → **"ON"** of **"OFF"**

**Gateway logs:** in de terminal waar `up.sh` draait, zie je `STATE 10.10.1.30-0: ...` regels.

**Vanuit de HA-container naar de gateway:**

```bash
docker exec homeassistant-dev curl -s http://host.docker.internal:8080/api/v1/devices | head
```

## Companion herladen (na broncode-wijziging)

```bash
docker compose restart homeassistant
```

HA herlaadt `custom_components/`. Wijzigingen in `coordinator.py`, `light.py`, etc. worden meteen opnieuw ingeladen. Entities worden opnieuw aangemaakt als hun ID is veranderd.

## Stoppen

- `Ctrl+C` in de `up.sh`-terminal stopt gateway + HA-container
- Of: `docker compose down` (HA uit, gateway laten draaien)
- Of: `kill %1` (alleen gateway, in tweede terminal)

## Volledig resetten

```bash
docker compose down
rm -rf config/*
docker compose up -d
```

Dit wist HA's `.storage/`, de auth-database, en de device registry. Je moet opnieuw onboarden.

## Troubleshooting

**`docker: command not found`**
OrbStack (of Docker Desktop) draait niet. Open de app, wacht tot de VM running is, probeer opnieuw.

**`host.docker.internal` werkt niet vanuit HA**

```bash
docker exec homeassistant-dev cat /etc/hosts | grep host.docker.internal
```

Verwacht: een regel die `host.docker.internal` resolvet naar een IP. Zo niet: OrbStack oudere versie — werk bij of gebruik `host.orb.internal` (OrbStack-specifiek).

**`./scripts/up.sh` zegt "Gateway did not become ready in 30s"**

Check of poort 8080 al in gebruik is:

```bash
lsof -i :8080
```

Vermoedelijke oorzaak: een tweede gateway-proces, of een ander project gebruikt dezelfde poort.

**HA start, geen entities**

- Integratie toevoegen gelukt? Check Settings → Devices & services.
- `host.docker.internal:8080` bereikbaar vanuit de container? Zie check hierboven.
- Gateway heeft devices? `curl -s http://127.0.0.1:8080/api/v1/devices | python3 -m json.tool | head`

**`active: false` modules verschijnen als entities**

De companion houdt daar (nog) geen rekening mee. Workaround: zet `active: true` in `devices.json` voor de modules die je wilt zien, of wacht op companion v2.

## Buiten scope

- Veldbus (vereist `10.10.1.x` source IP — niet op een Mac)
- EEPROM / `saveAutonomy`
- HA add-on in deze stack (Supervisor ontbreekt in plain Docker)

## Verified

_(nog te vullen na eerste E2E)_
