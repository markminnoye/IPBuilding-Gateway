# Mac Docker HA Test Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Home Assistant in Docker on macOS with the `ipbuilding-gateway-ha` companion mounted, connected to a simulated IPBuilding Gateway — no field hardware required.

**Architecture:** Two-container `docker compose` stack in `docker/ha-test/`: a `gateway` service (built from `ipbuilding_gateway/Dockerfile`, `GATEWAY_SIMULATED=1`) and a `homeassistant` service (`ghcr.io/home-assistant/home-assistant:stable`) on a shared bridge network. HA reaches the gateway at `http://gateway:8080` (Docker DNS). The companion custom component is bind-mounted from the sibling repo `ipbuilding-gateway-ha`. A shell smoke script verifies REST endpoints before and after HA onboarding.

**Tech Stack:** Docker Desktop (macOS), docker compose v2, Python 3.11 gateway image, Home Assistant stable container, `ipbuilding-gateway-ha` v0.1.1+

**Scope:** MVP test only — no EEPROM, no Supervisor auto-detect (plain Docker HA has no Supervisor), no veldbus VLAN.

---

## File map

| File | Responsibility |
|------|----------------|
| `docker/ha-test/docker-compose.yml` | Defines `gateway` + `homeassistant` services, volumes, network |
| `docker/ha-test/.env.example` | Documented defaults (`COMPOSE_PROJECT_NAME`, paths) |
| `docker/ha-test/config/.gitkeep` | HA config dir (created on first run; gitignored except keep) |
| `docker/ha-test/.gitignore` | Ignore `config/*` except `.gitkeep` |
| `docker/ha-test/scripts/smoke.sh` | Pre-flight: gateway REST + optional HA health |
| `docker/ha-test/README.md` | Operator runbook (start, onboard, add integration, verify entities) |
| `devices.json` (repo root) | Shared install config mounted read-only into gateway |

---

### Task 1: Scaffold `docker/ha-test/` directory

**Files:**
- Create: `docker/ha-test/config/.gitkeep`
- Create: `docker/ha-test/.gitignore`
- Create: `docker/ha-test/.env.example`

- [ ] **Step 1: Create directories**

```bash
mkdir -p "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test/config"
mkdir -p "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test/scripts"
touch "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test/config/.gitkeep"
```

- [ ] **Step 2: Write `.gitignore`**

Create `docker/ha-test/.gitignore`:

```gitignore
config/*
!config/.gitkeep
.env
```

- [ ] **Step 3: Write `.env.example`**

Create `docker/ha-test/.env.example`:

```bash
# Copy to .env and adjust if your paths differ
COMPOSE_PROJECT_NAME=ipbuilding-ha-test

# Absolute path to ipbuilding-gateway-ha repo (sibling checkout)
COMPANION_SRC=/Users/markminnoye/git/ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha

# Gateway devices file (repo root devices.json)
GATEWAY_DEVICES_FILE=/Users/markminnoye/git/IPBuilding Gateway/devices.json
```

- [ ] **Step 4: Commit scaffold**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add docker/ha-test/.gitignore docker/ha-test/.env.example docker/ha-test/config/.gitkeep
git commit -m "chore(docker): scaffold ha-test directory for Mac Docker HA"
```

---

### Task 2: `docker-compose.yml`

**Files:**
- Create: `docker/ha-test/docker-compose.yml`

- [ ] **Step 1: Write compose file**

Create `docker/ha-test/docker-compose.yml`:

```yaml
services:
  gateway:
    build:
      context: ../../ipbuilding_gateway
      dockerfile: Dockerfile
    container_name: ipbuilding-gateway-test
    environment:
      GATEWAY_SIMULATED: "1"
      GATEWAY_PASSIVE_ARP_MONITOR: "0"
      GATEWAY_AUTO_DISCOVER_ON_START: "0"
      GATEWAY_DEVICES_FILE: /data/devices.json
      GATEWAY_API_PORT: "8080"
      GATEWAY_LOG_LEVEL: info
    volumes:
      - ${GATEWAY_DEVICES_FILE}:/data/devices.json:ro
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/devices')"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 15s
    restart: unless-stopped

  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant-test
    depends_on:
      gateway:
        condition: service_healthy
    environment:
      TZ: Europe/Brussels
    volumes:
      - ./config:/config
      - ${COMPANION_SRC}:/config/custom_components/ipbuilding_gateway_ha:ro
    ports:
      - "8123:8123"
    restart: unless-stopped
```

Notes baked into this file:
- `build.context` points at `ipbuilding_gateway/` (same Dockerfile as HA add-on).
- Simulated mode — no `host_network`, no `10.10.1.x` required.
- Companion bind-mount is read-only; edit source in `ipbuilding-gateway-ha` and restart HA to pick up Python changes.

- [ ] **Step 2: Copy env file**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test"
cp .env.example .env
# Edit .env if companion repo path differs
```

- [ ] **Step 3: Validate compose syntax**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test"
docker compose config
```

Expected: prints resolved YAML without errors.

- [ ] **Step 4: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add docker/ha-test/docker-compose.yml
git commit -m "feat(docker): add compose stack for Mac HA + simulated gateway"
```

---

### Task 3: Smoke test script

**Files:**
- Create: `docker/ha-test/scripts/smoke.sh`

- [ ] **Step 1: Write smoke script**

Create `docker/ha-test/scripts/smoke.sh`:

```bash
#!/usr/bin/env bash
# smoke.sh — verify gateway (and optionally HA) before manual onboarding
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"
HA_URL="${HA_URL:-http://127.0.0.1:8123}"

echo "=== Gateway REST ==="
DEVICES_JSON=$(curl -sf "${GATEWAY_URL}/api/v1/devices")
DEVICE_COUNT=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('devices',[])))" <<< "$DEVICES_JSON")
echo "devices: ${DEVICE_COUNT}"
if [ "${DEVICE_COUNT}" -lt 1 ]; then
  echo "FAIL: expected at least 1 device from devices.json" >&2
  exit 1
fi

SAMPLE_ID=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d['devices'][0]['id'])" <<< "$DEVICES_JSON")
echo "sample entity id: ${SAMPLE_ID}"

echo "=== Gateway command (simulated ON) ==="
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${GATEWAY_URL}/api/v1/devices/${SAMPLE_ID}/action" \
  -H 'Content-Type: application/json' \
  -d '{"action":"ON"}')
echo "POST action HTTP ${HTTP_CODE}"
if [ "${HTTP_CODE}" != "200" ]; then
  echo "FAIL: expected HTTP 200 from action endpoint" >&2
  exit 1
fi

if curl -sf "${HA_URL}/" >/dev/null 2>&1; then
  echo "=== Home Assistant UI reachable at ${HA_URL} ==="
else
  echo "=== Home Assistant not up yet (skip) ==="
fi

echo "PASS"
```

- [ ] **Step 2: Make executable and run against running gateway**

```bash
chmod +x "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test/scripts/smoke.sh"
cd "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test"
docker compose up -d gateway
docker compose ps
./scripts/smoke.sh
```

Expected output includes `devices: 28` (or your `devices.json` count) and `PASS`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add docker/ha-test/scripts/smoke.sh
git commit -m "test(docker): add smoke script for ha-test gateway stack"
```

---

### Task 4: Operator README

**Files:**
- Create: `docker/ha-test/README.md`

- [ ] **Step 1: Write README**

Create `docker/ha-test/README.md` with these sections:

1. **Prerequisites** — Docker Desktop running; sibling clone of `ipbuilding-gateway-ha` at path in `.env`.
2. **Start stack**

```bash
cd docker/ha-test
cp .env.example .env   # once
docker compose up -d
./scripts/smoke.sh
```

3. **First HA onboarding** — open `http://localhost:8123`, create account, finish wizard.
4. **Add companion integration**
   - Settings → Devices & services → Add integration → "IPBuilding Gateway HA"
   - Host: `gateway` (Docker service name, **not** `127.0.0.1`)
   - Port: `8080`
   - Supervisor auto-detect will **not** work in plain Docker — manual host is required.
5. **Verify entities** — Developer tools → States; filter `light.`, `switch.`, `sensor.`.
6. **Toggle a light** — UI or service call; gateway logs should show `STATE` lines.
7. **Stop / reset**

```bash
docker compose down          # keep config
docker compose down -v       # only if you mounted named volumes (not default)
rm -rf config/.storage config/home-assistant_v2.db  # full HA reset
```

8. **Companion code changes** — edit files in `ipbuilding-gateway-ha`, then `docker compose restart homeassistant`.

- [ ] **Step 2: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add docker/ha-test/README.md
git commit -m "docs(docker): add Mac HA test environment runbook"
```

---

### Task 5: End-to-end verification checklist

**Files:**
- Modify: none (manual verification)

- [ ] **Step 1: Start full stack**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway/docker/ha-test"
docker compose up -d
docker compose logs -f gateway
# wait for: IPBuilding Gateway started ... api=0.0.0.0:8080
```

- [ ] **Step 2: Run smoke script**

```bash
./scripts/smoke.sh
```

Expected: `PASS`

- [ ] **Step 3: Onboard HA and add integration**

Manual steps per README Task 4. Confirm integration shows ~28 devices (depends on `devices.json`).

- [ ] **Step 4: Toggle entity from HA UI**

Pick any `light.*` entity → turn on. In gateway logs:

```bash
docker compose logs gateway | tail -20
```

Expected: `STATE` or command log line for the entity id (format `10.10.1.30-0`).

- [ ] **Step 5: Document result**

Add a one-line note to `docker/ha-test/README.md` under **Verified** with date and HA version if all steps pass. Commit:

```bash
git add docker/ha-test/README.md
git commit -m "docs(docker): record ha-test e2e verification on macOS"
```

---

## Self-review

| Requirement | Task |
|-------------|------|
| Docker HA on Mac | Task 2, 4, 5 |
| Simulated gateway (no hardware) | Task 2 (`GATEWAY_SIMULATED=1`) |
| Companion mounted | Task 2 volume + `.env` |
| Manual config flow host (`gateway:8080`) | Task 4 README |
| Smoke / automated pre-check | Task 3 |
| Reproducible docs | Task 4 |
| EEPROM / veldbus | Out of scope (MVP) |

No placeholders remain — all file contents and commands are specified.

---

## Out of scope (post-MVP)

- QNAP / host-network veldbus testing (separate runbook; needs `10.10.1.x` source IP)
- HA add-on inside this compose stack (Supervisor not available in plain container)
- Companion dynamic `device_added` handling (companion v2 workstream)
