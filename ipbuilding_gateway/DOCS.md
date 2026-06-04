# IPBuilding Gateway — Home Assistant Add-on

Open veldbus-hub voor IPBuilding relais, dimmers en drukknoppen via **UDP/1001**. Vervangt de propriëtaire IPBox en stelt het `ipbuilding-gateway-ha` Home Assistant component bloot via WebSocket (`8080`) en optioneel REST (`30200`).

## Features

- **UDP/1001 veldbus** — praat rechtstreeks met IP0200PoE, IP0300PoE en IP1100PoE
- **WebSocket + REST northbound API** — productie-protocol op `8080`
- **Auto-discovery** — ARP-first module detectie
- **IPBox migratie-shim** — REST compatibiliteit op `30200` (opt-in)
- **Supervisor integratie** — add-on beheer, auto-update, logs

---

## Installation

### 1. Add repository

[![Add Repository](./assets/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway)

Of handmatig: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
```
https://github.com/markminnoye/IPBuilding-Gateway
```

### 2. Install add-on

**Add-on Store** → zoek **"IPBuilding Gateway"** → **Install**

### 3. Configure

Kopieer `devices.json` naar de add-on data folder via **Samba** of **SSH**:

```
/addon_configs/<repo-hash>_ipbuilding_gateway/data/devices.json
```

Het `<repo-hash>` is zichtbaar in de add-on info panel.

#### Generate devices.json (fresh install)

```bash
cd /path/to/IPBuilding-Gateway
PYTHONPATH=. python -m gateway.discover --range-start 30 --range-end 59
cp devices.discovered.json devices.json
```

#### Generate devices.json (migrating from IPBox)

```bash
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python scripts/discover_from_ipbox.py
```

### 4. Start

**Settings → Add-ons → IPBuilding Gateway → Start**

Bekijk logs voor de opstartstatus:
```
[run.sh] GATEWAY_HUB_IP=10.10.1.1
[run.sh] GATEWAY_API_PORT=8080
[run.sh] GATEWAY_DEVICES_FILE=/data/devices.json
```

---

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `hub_ip` | `10.10.1.1` | Hub/adres waar modules op reageren |
| `poll_interval` | `2.0` | Polling interval in seconden |
| `api_port` | `8080` | WebSocket + REST northbound API poort |
| `rest_shim_enabled` | `false` | IPBox REST shim op poort `30200` (enkel migratie) |
| `log_level` | `info` | Log niveau: `debug`, `info`, `warning`, `error` |
| `devices_file` | `/data/devices.json` | Pad naar installatie configuratie |

---

## Network

** Vereiste:** HA moet de veldbus-modules (`10.10.1.30/40/50`) kunnen bereiken met een **source IP in `10.10.1.x`**.

| Methode | Wanneer |
|--------|---------|
| **VLAN trunk op één NIC** (aanbevolen HA Green) | Native = thuisnetwerk, getagd = IPBuilding VLAN |
| **Extra NIC** op veldbus-segment | vast `10.10.1.x` adres |

Check of VLAN correct is:

```bash
ip addr show eth0.2
ping -c1 10.10.1.30
ping -c1 10.10.1.40
ping -c1 10.10.1.50
```

---

## Ports

| Poort | Protocol | Gebruik |
|-------|----------|---------|
| `8080` | HTTP + WebSocket | Northbound API — companion, apps, Node-RED |
| `30200` | HTTP REST | IPBox compatibiliteits Shim — **uitgeschakeld tenzij `rest_shim_enabled: true`** |

---

## Troubleshooting

### Add-on start niet

```
Settings → Add-ons → IPBuilding Gateway → Logs
```

Zoek naar `[run.sh]` — als die ontbreekt is `devices.json` niet geladen.

### Companion vindt de add-on niet

- Add-on moet ** draaien** (niet enkel geïnstalleerd)
- Check `api_port` is `8080`
- De companion detecteert de add-on automatisch via Supervisor — geen handmatige host/poort nodig

### Geen entities met namen — "10.10.1.30:0"

`devices.json` ontbreekt of is incompleet. Genereer opnieuw met de discovery CLI.

### UDP polling werkt niet

- `host_network: true` is vereist — check `config.yaml`
- HA heeft een **IP adres op `10.10.1.x`** nodig
- Inter-VLAN routing vanuit thuisnetwerk (zonder eigen `10.10.1.x` op HA) is **niet voldoende** voor UDP replies

---

## Architectuur

```
IPBuilding veldbus (UDP/1001 · 10.10.1.x)
  ├── IP0200PoE relay   → 10.10.1.30
  ├── IP0300PoE dimmer  → 10.10.1.40
  └── IP1100PoE input   → 10.10.1.50

              ↓ UDP/1001 (host_network: true)

         ipbuilding_gateway (HA Add-on)
         ├── REST :30200   (shim, opt-in)
         └── REST :8080 + WebSocket /ws  ←── ipbuilding-gateway-ha
```

---

Companion installatie: [`ipbuilding-gateway-ha/README.md`](ipbuilding-gateway-ha/README.md)
