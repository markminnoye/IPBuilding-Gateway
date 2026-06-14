# Deployment hardware evaluation

**Date:** 2026-06-14  
**Status:** Decision record (not an implementation spec)  
**Related:** [ARCHITECTURE.md](../../ARCHITECTURE.md) §3, roadmap Fase 12 (ESP32 POC)

Evaluatie van hardware-opties om de IPBuilding gateway (veldbus-hub + northbound WS/REST) buiten de HA add-on te draaien. Brainstorm uit agent-sessie 2026-06-14.

---

## Summary

| Platform | Deployment | Code path | Effort (Minimal POC) | Recommendation |
|----------|------------|-----------|-------------------|----------------|
| **HA add-on / HA Green** | A | Python (shipping) | **0** — done | Primary target |
| **Raspberry Pi 3B** | B | Python (same repo) | **0.5–2 days** | **Best near-term alternative** |
| **Raspberry Pi 4 / Zero 2 W / Linux** | B | Python | **0.5–2 days** | Same as Pi 3B |
| **ESP32-S3 + Ethernet** | C | C++ ESP-IDF (new) | **3–5 weeks FT** | Fase 12 — later |
| **Raspberry Pi Pico W** | C-like | C++ Pico SDK (new) | **4–6 weeks FT** | Defer unless W5500 HAT available |
| **Pico W WiFi-only** | — | — | N/A | Not viable for isolated IPBuilding VLAN |

**Decision:**

- **Near-term:** use **Raspberry Pi 3B** with native Python (`python -m gateway`) — Deployment B.
- **Later:** ESP32 POC (Fase 12) — full C++ rewrite, same northbound protocol.
- **Not now:** Pico W unless a **W5500 Ethernet HAT** is added; WiFi-only does not replace the IPBox field-bus NIC.

---

## Network topology (all standalone hubs)

The IPBox is **dual-homed**: REST on home LAN, field bus on **`10.10.1.0/24`** (UDP/1001, hub **`10.10.1.1`**). Any replacement must reach modules on the field VLAN and expose northbound API to Home Assistant.

### Raspberry Pi 3B (recommended pattern)

Pi 3B has **built-in WiFi + one Ethernet port** — no extra hardware for dual-homed:

```
Pi 3B
├── eth0 (cable)  → IPBuilding VLAN  10.10.1.1   (UDP/1001 field bus)
└── wlan0 (WiFi)  → home LAN         192.168.1.x  (REST/WS :8080 for HA)
```

- Companion on HA Green points to **Pi WiFi IP** `:8080`, not necessarily `10.10.1.1`.
- Turn **IPBox off** (or use mirror capture) when binding `10.10.1.1` on the Pi.
- UniFi: allow routing/firewall from HA subnet → Pi WiFi IP port **8080**.

### ESP32 / Pico W

- **Ethernet required** for field bus (W5500 SPI or LAN8720 RMII).
- **WiFi** (or second interface) for northbound to HA.
- **ESP32-S3 + PSRAM** preferred over classic ESP32 for WebSocket JSON snapshots.
- **Pico W:** only **264 KB RAM** — compact WS snapshots, single client; **+20–40% effort** vs ESP32-S3.

---

## Platform details

### Deployment A — HA add-on (primary)

- Same Python code in Docker on HA Green (`aarch64` / `amd64` images on ghcr.io).
- Companion auto-discovery via Supervisor.
- No extra hardware when HA already runs the add-on.

### Deployment B — Linux standalone (Pi 3B, Pi 4, NAS, VPS)

Uses **existing** `gateway/` Python package — no port.

**Run options on Pi 3B:**

| Option | Notes |
|--------|--------|
| **Native Python (recommended)** | `python3 -m venv`, `pip install -r requirements-gateway.txt`, `PYTHONPATH=. python -m gateway`. Works on **32-bit** Raspberry Pi OS (armv7). |
| **Docker** | Published ghcr image is **aarch64 + amd64 only** — on 32-bit Pi OS, build locally from `ipbuilding_gateway/Dockerfile` (slow on Pi 3B). |
| **HA add-on on Pi 3B** | Only if HA runs on the same Pi — **not recommended** (Pi 3B underpowered for modern HA OS). |

**Feature parity with add-on:** full UDP poll, WS `/ws`, REST `/api/v1/`, runtime auto-discovery (Linux `arp`), optional REST shim `:30200`. EEPROM-sync (Fase 8) still open everywhere.

**Pi 3B caveats:** SD wear (use quality card or USB boot); gateway is lightweight enough for 2 s poll + aiohttp; discovery spec already uses 15 s AtomicWriter lock for SD robustness.

**Effort breakdown (Pi 3B):**

| Task | Time |
|------|------|
| Pi OS + dual network (eth0 + wlan0, static IPs) | 2–6 h |
| Repo + venv + `devices.json` | 1–2 h |
| Field test (relay / dimmer / input) | 2–4 h |
| systemd + companion on HA Green | 1–3 h |
| **Total** | **~0.5–2 working days** |

### Deployment C — ESP32 POC (Fase 12)

- **Not** a Python port — **C++ ESP-IDF** firmware per [ARCHITECTURE.md](../../ARCHITECTURE.md).
- Same northbound protocol so `ipbuilding-gateway-ha` works transparently.
- **Minimal POC scope:** UDP/1001 + device registry + WS `/ws` + static `devices.json` on flash; **no** discovery, MQTT, Matter, REST shim, EEPROM-sync in first cut.

**Effort (ESP32-S3 + Ethernet, full-time experienced dev):**

| Scope | Full-time | Part-time (~50%) |
|-------|-----------|------------------|
| Minimal POC | 3–5 weeks | 6–10 weeks |
| Near-parity (discovery, metadata, full REST) | 8–12 weeks | 4–6 months |

### Raspberry Pi Pico W

- **Microcontroller (RP2040)** — cannot run Python gateway or Docker.
- Same embedded path as ESP32; needs **W5500** for field bus.
- MicroPython **not** suitable for production WS + companion integration on 264 KB RAM.
- Only consider if Pico W + W5500 is already on hand; otherwise prefer Pi 3B or ESP32-S3.

---

## What not to do

| Anti-pattern | Why |
|--------------|-----|
| Python on ESP32/Pico | Architecture specifies C++ for Deployment C |
| Pico W WiFi-only as hub | IPBuilding VLAN is isolated; modules need L2/L3 on `10.10.1.x` |
| ESP32 as UDP-only bridge with northbound elsewhere | Breaks Deployment C; companion expects one gateway API |
| Rely on GitHub Issues alone for this matrix | Use this file as canonical reference in git |

---

## Quick start — Pi 3B native (Deployment B)

```bash
git clone https://github.com/markminnoye/IPBuilding-Gateway.git
cd IPBuilding-Gateway
python3 -m venv .venv
.venv/bin/pip install -r requirements-gateway.txt
# Place or generate devices.json (see README_gateway.md)
GATEWAY_DEVICES_FILE=./devices.json \
GATEWAY_HUB_IP=10.10.1.1 \
GATEWAY_API_PORT=8080 \
PYTHONPATH=. .venv/bin/python -m gateway
```

Configure companion on HA Green: gateway host = **Pi WiFi IP**, port **8080**.

---

## GitHub tracking

| Item | Issue |
|------|-------|
| Epic: Pi 3B standalone hub (Deployment B) | [#11](https://github.com/markminnoye/IPBuilding-Gateway/issues/11) |
| Backlog: ESP32 POC Fase 12 (Deployment C) | [#12](https://github.com/markminnoye/IPBuilding-Gateway/issues/12) |
| Backlog: Pico W (deferred) | [#13](https://github.com/markminnoye/IPBuilding-Gateway/issues/13) |

Project board: **IPBuilding Gateway** (GitHub Projects).

---

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Deployments A / B / C
- [README_gateway.md](../../README_gateway.md) — env vars, local run
- [ipbuilding_gateway/DOCS.md](../../ipbuilding_gateway/DOCS.md) — add-on install (Deployment A)
- [docs/api/websocket.md](../../docs/api/websocket.md) — northbound contract
- [IPBUILDING_KNOWLEDGE.md](../IPBUILDING_KNOWLEDGE.md) §3 — dual-homed IPBox topology
