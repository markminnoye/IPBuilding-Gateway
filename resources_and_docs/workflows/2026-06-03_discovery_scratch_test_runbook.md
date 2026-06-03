# Discovery Scratch Test Runbook

**Purpose:** Prove the gateway and companion work from pure discovery-generated `devices.json` — no IPBox, no manual config. This is a full end-to-end validation of the discovery pipeline.

**When to run:** After any change to `devices.json` schema, discovery output, or InstallationConfig parsing; or when modules have been physically reconfigured.

---

## Prerequisites

- [ ] Test host has `10.10.1.1` on the IPBuilding VLAN interface
- [ ] IPBox hub is **off** or its second NIC is not active as `10.10.1.1` (no conflict)
- [ ] Modules reachable: `10.10.1.30` (relay), `10.10.1.40` (dimmer), `10.10.1.50` (input)
- [ ] UniFi mirror **7←15** active for pcap debug (optional but recommended)
- [ ] Mirror **off** for pure hub validation
- [ ] No `GATEWAY_SIMULATED=1` — real UDP
- [ ] `PYTHONPATH=.` available in shell

---

## Step 1 — Backup current config

```bash
cp devices.json devices.json.pre-scratch
```

If `devices.json` is already a draft from a previous run, keep a backup:

```bash
cp devices.json devices.json.pre-scratch-$(date +%Y%m%d)
```

---

## Step 2 — Run discovery

```bash
PYTHONPATH=. python -m gateway.discover \
  --baseline devices.json \
  --output devices.discovered.json \
  --range-start 30 \
  --range-end 59
```

**Expected output (example):**

```
ARP-first 10.10.1.30 – 10.10.1.59 (ping 0.5s, concurrency 20)...
  Found 3 module(s)
UDP/10001 probe (duration 30s)...

Total: 3 module(s) discovered:
  10.10.1.30  model=IP0200PoE  type=relay  fw=5.1  mac=00:24:77:52:ac:be  channels=24
  10.10.1.40  model=IP0300PoE  type=dimmer  fw=5.4  mac=00:24:77:52:9e:a8  channels=4
  10.10.1.50  model=IP1100PoE  type=input   fw=5.2.4  mac=00:24:77:52:ad:aa  channels=0

Draft written to: devices.discovered.json
NOTE: no ipbox_id in output — correct for the open gateway.
```

If any module's IP has changed from the baseline, you will also see:

```
WARNING: Module 00:24:77:52:ac:be IP changed 10.10.1.30 → 10.10.1.35; device ids may need review
```

---

## Step 3 — Manual review checklist

Open `devices.discovered.json` and check every channel. Known items from the spec:

| Module | Channel | Issue | Action |
|--------|---------|-------|--------|
| relay | ch 9 | Ventilatie kanaal | Set `"semantic_type": "fan"` |
| relay | ch 15 | Encoding `¿` in name | Fix to correct character |
| relay | ch 23 | Keuken Ventilatie | Set `"semantic_type": "fan"` |
| dimmer | ch 2 | Check name (`Keuken main`) | Verify is correct |
| dimmer | ch 3 | Label `40.1.4` / room `Vrij` | Confirm if placeholder or intentional |

**Per-channel review criteria:**

```
name         — from backupConfig; encoding fixed
room         — from backupConfig
semantic_type — light (default); fan for ventilatie kanalen
active       — true (all discovered channels)
max_watt     — ~200 for dimmer, ~60 for relay/fan
```

**Not required (out of scope):**
- `ipbox_id` — not needed for open gateway
- `description` / `group` — legacy fields, not in new schema
- Custom `id` — falls back to `{ip}-{channel}` automatically

Edit `devices.discovered.json` in place for any corrections, then proceed.

---

## Step 4 — Overwrite and validate

```bash
# Confirm active channel count: relay 24 + dimmer 4 = 28
PYTHONPATH=. python scripts/validate_devices_json.py \
  devices.discovered.json \
  --expect-channels 28
```

Expected: `OK: devices.discovered.json`

If errors, fix `devices.discovered.json` and re-validate.

**Then overwrite:**

```bash
cp devices.discovered.json devices.json
```

---

## Step 5 — Gateway smoke test

```bash
PYTHONPATH=. python -m gateway
```

In another terminal:

```bash
# Check device count
curl -s http://localhost:8080/api/v1/devices | python -c "
import sys, json
d = json.load(sys.stdin)
print(f'Devices: {len(d[\"devices\"])}')
"

# Check modules endpoint
curl -s http://localhost:8080/api/v1/modules | python -c "
import sys, json
d = json.load(sys.stdin)
for m in d['modules']:
    print(f'  {m[\"ip\"]}  {m[\"type\"]}  fw={m.get(\"firmware\",\"\")}  mac={m[\"mac\"]}')
"
```

**Expected:**
- Devices: 28 (or number in your config)
- Modules: 3 with correct MACs, firmware from `getSysSet`

---

## Step 6 — WebSocket snapshot

```bash
# Connect to WS, expect first message type=snapshot
curl -s --include \
  --no-buffer \
  --max-time 5 \
  http://localhost:8080/ws
```

Or use [websocat](https://github.com/websocat/websocat):

```bash
websocat ws://localhost:8080/ws | python -c "
import sys, json
line = sys.stdin.readline()
msg = json.loads(line)
print(f'WS type: {msg.get(\"type\")}')
print(f'Modules: {len(msg.get(\"modules\", []))}')
print(f'Devices: {len(msg.get(\"devices\", []))}')
"
```

**Expected first WS message:** `{"type": "snapshot", "modules": [...], "devices": [...]}`

- `modules` array: 3 entries with MAC, network config
- `devices` array: 28 entries with `module_id` (MAC), `module_ip`, `channel`

---

## Step 7 — HA companion reload

1. Reload the `ipbuilding_gateway_ha` integration in Home Assistant
2. Confirm entity count matches device count
3. Verify entity names match discovery names (e.g. `10.10.1.30-9` becomes `Badkamer ventilatie` with `fan` semantic type)
4. Test one relay ON/OFF and one dimmer brightness command from HA

---

## Step 8 — Save evidence

```bash
DATE=$(date +%Y-%m-%d)
mkdir -p resources_and_docs/evidence/
cp devices.discovered.json resources_and_docs/evidence/${DATE}_discovery_scratch.json
cp devices.json resources_and_docs/evidence/${DATE}_devices_after_scratch.json
```

Create `resources_and_docs/evidence/${DATE}_discovery_scratch.md`:

```markdown
# Discovery Scratch Test — YYYY-MM-DD

## Result
- PASS / PARTIAL / FAIL

## Modules discovered
| IP | Type | MAC | Firmware | Channels |
|----|------|-----|----------|----------|
| 10.10.1.30 | relay | ... | 5.1 | 24 |
| ... | ... | ... | ... | ... |

## IP-change warnings
(list any WARNING lines from discovery output)

## Review edits made
(list any changes to devices.discovered.json after review)

## Validation
```bash
PYTHONPATH=. python scripts/validate_devices_json.py devices.discovered.json --expect-channels 28
# output: OK / ERROR: ...
```

## Gateway smoke
- Devices via REST: N
- Modules via REST: N
- WS first message type: snapshot / device_list

## HA companion
- Entities loaded: N
- Notable issues: ...

## Notes
(Free-text observations)
```

Commit evidence only on request.

---

## Rollback

If anything fails and you need to restore:

```bash
cp devices.json.pre-scratch devices.json
# Restart gateway to reload config
```
