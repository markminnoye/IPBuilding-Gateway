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
| `--output` | `devices.json.discovered` | Output path |
| `--subnet` | `10.10.1` | Subnet prefix |
| `--range-start` | `30` | Start of IP range (inclusive) |
| `--range-end` | `59` | End of IP range (inclusive) |
| `--ping-timeout` | `0.5` | ICMP ping timeout in seconds |
| `--http-timeout` | `2.0` | HTTP getSysSet timeout in seconds |
| `--ping-concurrency` | `20` | Max concurrent ping processes |
| `--no-arp` | — | Skip ARP-first; use HTTP-only sweep |
| `--udp-probe` | — | Also send UDP/10001 probe (opt-in) |
| `--udp-duration` | `30` | UDP probe listen duration in seconds |

**Output:** `devices.json.discovered` — same schema as `devices.json`, without `ipbox_id` (open gateway, no IPBox dependency).

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
| `DISCOVERY_OUTPUT` | `devices.json.discovered` | Output path (optional) |

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

**Output:** `devices.json.discovered` — full schema with `ipbox_id` for REST shim compatibility.

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

## Choosing a discovery method

| Scenario | Use |
|----------|-----|
| Fresh install, no IPBox | `gateway.discover` (ARP-first) |
| Migrating from IPBox, want `ipbox_id` | `discover_from_ipbox.py` |
| Verify ARP cache state manually | `arp_discover_spike.py` |
| HA add-on runtime discovery | `gateway.discover` via config flow (future) |

Both `gateway.discover` and `discover_from_ipbox.py` output `devices.json.discovered` — diff, review, rename to `devices.json`.