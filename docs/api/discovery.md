# Discovery CLI reference

## `gateway.discover` — open field module discovery

Standalone ARP-first discovery — no IPBox required.

**Entry point:**
```bash
PYTHONPATH=. python3 -m gateway.discover [--options]
# or directly:
PYTHONPATH=. python3 gateway/__main__discover.py [--options]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `devices.discovered.json` | Output path |
| `--subnet` | `10.10.1` | Subnet prefix |
| `--range-start` | `30` | Start of IP range (inclusive) |
| `--range-end` | `59` | End of IP range (inclusive) |
| `--ping-timeout` | `0.5` | ICMP ping timeout in seconds |
| `--http-timeout` | `2.0` | HTTP getSysSet timeout in seconds |
| `--ping-concurrency` | `20` | Max concurrent ping processes |
| `--no-arp` | — | Skip ARP-first; use HTTP-only sweep |
| `--udp-probe` | — | Also send UDP/10001 probe (opt-in) |
| `--udp-duration` | `30` | UDP probe listen duration in seconds |
| `--baseline` | `devices.json` | Existing config for MAC IP-change detection; pass `''` to skip |

**Output:** `devices.discovered.json` — same schema as `devices.json`, without `ipbox_id` (open gateway, no IPBox dependency). Can overwrite `devices.json` after review (scratch test — no merge).

**Flow:**
1. Ping-sweep range → populate kernel ARP cache
2. Read `arp -an` (macOS) / `/proc/net/arp` (Linux)
3. Filter OUI `00:24:77` (field modules); exclude `00:30:18` (IPBox hub)
4. HTTP `GET api.html?method=getSysSet` on each ARP candidate (parallel)
5. Fall back to full HTTP sweep if no ARP candidates found

**Exit codes:** `0` on success, `1` on error (e.g. `--range-end` < `--range-start`).

---

## `scripts/discover_from_ipbox.py` — IPBox migration (requires IPBox)

Full migration including `ipbox_id` per channel for REST shim compatibility.

**Required env vars:**

| Variable | Example | Description |
|----------|---------|-------------|
| `IPBOX_WEB_HOST` | `http://192.168.0.185` | IPBox WebConfig base URL |
| `IPBOX_SESSION_COOKIE` | `ASP.NET_SessionId=abc123` | Browser session cookie |
| `DISCOVERY_OUTPUT` | `devices.discovered.json` | Output path (optional) |

**Usage:**
```bash
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python3 scripts/discover_from_ipbox.py
```

**Auth:** Log in to IPBox WebConfig in a browser → DevTools → Application → Cookies → copy `ASP.NET_SessionId`.

**Flow:**
1. `POST /general/Wizards/Modules/ScanForModules` → list of modules (IP, MAC, Type, Version)
2. For each relay: `POST /general/Hardware/Relais/ImportRelayInfo` → channel list with `id` (ipbox_id)
3. For each dimmer: `POST /general/Hardware/Dim/ImportDimInfo` → channel list with `id` (ipbox_id)
4. Assemble `devices.json` with `ipbox_id` per channel

**Output:** `devices.discovered.json` — full schema with `ipbox_id` for REST shim compatibility. Can overwrite `devices.json` after review.

**Exit code:** `1` if `IPBOX_SESSION_COOKIE` is not set.

---

## `scripts/arp_discover_spike.py` — raw ARP verification (no dependencies)

Manual field verification script — no extra packages.

```bash
python3 scripts/arp_discover_spike.py [--options]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--subnet` | `10.10.1` | Subnet prefix |
| `--range-start` | `30` | Start of IP range |
| `--range-end` | `59` | End of IP range |
| `--ping-timeout` | `0.5` | ICMP ping timeout |
| `--concurrency` | `20` | Concurrent ping tasks |
| `--http-verify` | — | Also curl getSysSet per found IP |
| `--verbose` | — | Show non-field ARP entries |
| `--require-field` | — | Exit 1 if no `00:24:77` entries found |

**Output:** Prints field modules (OUI `00:24:77`), hub (OUI `00:30:18`), and other ARP entries. With `--http-verify`: shows devtype/firm per IP.

---

Both `gateway.discover` and `discover_from_ipbox.py` output a draft JSON file. Prefer applying via the installation API (merge policy A) instead of overwriting `devices.json` by hand:

```bash
# Legacy IP0000 / mobile centrale (10.10.1.1)
python3 scripts/import_from_legacy_central.py \
  --central-host 10.10.1.1 \
  --apply http://127.0.0.1:8080 \
  --mode merge_modules

# IPBox WebConfig export
python3 scripts/discover_from_ipbox.py --apply http://127.0.0.1:8080

# Any JSON draft
python3 scripts/apply_installation.py \
  --gateway http://127.0.0.1:8080 \
  --mode merge_modules \
  --file devices.import.json
```

`POST /api/v1/discover` (runtime module HTTP discovery) uses the same apply path internally (`merge_modules`). Unidentified modules (`type: unknown`) are never persisted.

## Choosing a discovery method

| Scenario | Use |
|----------|-----|
| Fresh install, no IPBox | `gateway.discover` (ARP-first) + `apply_installation.py` |
| Migrating from IPBox, want `ipbox_id` | `discover_from_ipbox.py --apply` |
| Legacy centrale (IP0000 mobile UI) | `import_from_legacy_central.py --apply` |
| Verify ARP cache state manually | `arp_discover_spike.py` |
| HA add-on runtime discovery | `POST /api/v1/discover` (REST or WebSocket) -- see `rest.md` and `websocket.md` |

Draft JSON can be reviewed locally, then applied with merge policy A via `POST /api/v1/installation/apply` (see `rest.md` § Installation API).

---

## `scripts/validate_devices_json.py` — config validator

Validates `devices.json` against scratch-test success criteria.

```bash
PYTHONPATH=. python scripts/validate_devices_json.py devices.json [--expect-channels N]
```

**Checks:**
- Every module has a non-empty `mac` field
- No duplicate MACs across modules
- Active channel count matches `--expect-channels` if provided

**Exit codes:** `0` = pass, `1` = errors (per-error line on stderr)

---

## Discovery scratch test workflow

**Purpose:** Prove gateway + companion work from pure discovery-generated `devices.json` without IPBox dependency.

**Runbook:** [`resources_and_docs/workflows/2026-06-03_discovery_scratch_test_runbook.md`](resources_and_docs/workflows/2026-06-03_discovery_scratch_test_runbook.md)

**Summary:**
1. `cp devices.json devices.json.pre-scratch`
2. `PYTHONPATH=. python -m gateway.discover --baseline devices.json --output devices.discovered.json`
3. Review `devices.discovered.json` — fix `semantic_type: fan` for ventilatie channels, encoding issues, etc.
4. `PYTHONPATH=. python scripts/validate_devices_json.py devices.discovered.json --expect-channels 28`
5. `cp devices.discovered.json devices.json`
6. Gateway smoke: `curl localhost:8080/api/v1/devices | jq '.devices | length'` → 28
7. WebSocket: connect to `ws://localhost:8080/ws` — first message must be `type: snapshot`
8. HA companion: reload, verify entity count + names from discovery