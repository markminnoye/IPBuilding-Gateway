# Acceptance test — HA discovery flow

Validates the Music-Assistant-style dual discovery (Supervisor add-on +
Zeroconf) for the IPBuilding Gateway add-on and companion.

**Target HA build:** 2026.3+ (companion requires `EventEntity`).
**Required versions:** gateway add-on v0.3.0 + companion v0.3.0.
Versions are kept in lockstep so a release is always add-on + companion
together; the `0.3.0` number is the same for both.

This is a manual checklist — the integration code is covered by
`tests/test_ha_discovery.py` (gateway, 18 tests) and
`tests/test_config_flow_parsing.py` (companion, 8 tests). What cannot be
unit-tested is the end-to-end behaviour against a real Home Assistant
Core, which is what this document covers.

---

## Pre-flight

- [ ] Companion v0.3.0 installed via HACS (or copied into
  `config/custom_components/ha_ipbuilding_gateway/`).
- [ ] Home Assistant restarted after installing the companion.
- [ ] Gateway add-on v0.1.4 installed from your add-on repository.
- [ ] `ipbuilding_gateway/CHANGELOG.md` and
  `ha-ipbuilding-gateway/CHANGELOG.md` mention the discovery change.

---

## Scenario 1 — Add-on deployment (HA OS / Supervised)

1. Stop the gateway add-on if it's currently running.
2. Start the gateway add-on. Tail the add-on log and confirm:
  - `[run.sh] GATEWAY_*` lines are present (env-vars translated).
  - `Starting HA discovery  instance_id=…  base_url=http://127.0.0.1:8080  addon=true` appears.
  - `HassIO discovery announced: uuid=…` appears.
3. Open **Developer Tools → Services → `hassio.addon_info`** and call it
  with `{"addon": "ipbuilding_gateway"}` to confirm Supervisor sees
   the add-on.
4. Open **Instellingen → Apparaten & Diensten → Ontdekt**.
5. **Expected:** a card titled **IPBuilding Gateway HA** appears in the
  Discovered list.
6. Click **Toevoegen** (Add). A confirmation step shows the add-on
  name; submit.
7. **Expected:** the integration entry is created; entities for the
  three field modules start populating.
8. Reload the gateway add-on. Reopen the **Ontdekt** list.
9. **Expected:** no duplicate entry (the `unique_id` is the Supervisor
  discovery UUID, so HA reuses the existing config entry).
10. Stop the gateway add-on. After 30–60 s, the integration status
  changes to **unavailable** (entities go `unavailable`).
11. Restart the gateway add-on. The integration recovers automatically.

### Negative — add-on not running

- [ ] Stop the add-on and remove the integration.
- [ ] Wait 5 minutes (Supervisor clears stale discovery entries).
- [ ] Reopen **Ontdekt**: the entry should be gone.

### Negative — companion not installed

- [ ] Temporarily move `config/custom_components/ha_ipbuilding_gateway/`
  out of the way and restart HA.
- [ ] **Expected:** no entry in **Ontdekt**, even though the add-on
  is announcing itself. (No companion = no handler = nothing to
  discover.)
- [ ] Restore the companion and restart HA; **Ontdekt** repopulates
  on the next Supervisor re-announce (≤ 5 min).

---

## Scenario 2 — Standalone Docker / Pi on the LAN

1. On a host with **host networking** (required for mDNS), run:
  ```bash
   docker run --network=host -v /data/ipbuilding:/data \
     ghcr.io/markminnoye/ipbuilding-gateway:0.1.4
  ```
   Confirm the log shows:
   `Zeroconf registered: <id>._ipbuilding-gateway._tcp.local. on port 8080`
2. From the HA host, sanity-check the broadcast:
  ```bash
   avahi-browse -art | grep ipbuilding
  ```
   (or `dns-sd -B _ipbuilding-gateway._tcp.local.` on macOS).
   The service should appear with the gateway's LAN IP and port 8080.
3. Open **Instellingen → Apparaten & Diensten → Ontdekt** in HA.
4. **Expected:** a card titled **IPBuilding Gateway HA** (no add-on
  suffix) appears. The description shows the advertised `base_url`.
5. Click **Toevoegen**, confirm, submit. The integration entry is
  created; entities populate.
6. **Expected:** the integration uses the LAN IP from the TXT record,
  not `127.0.0.1`.
7. Restart the gateway. After ~30 s, the companion reconnects to
  the same `base_url` (or to the new IP if it changed).

### Negative — mDNS not reaching HA

- [ ] Disable multicast on the gateway host, or move HA to a separate
  VLAN without an mDNS reflector.
- [ ] **Expected:** no entry in **Ontdekt** via Zeroconf. The
  Supervisor discovery path is also unavailable (no add-on context).
- [ ] As a fallback, use **Integratie toevoegen → IPBuilding Gateway HA**
  and enter host + port manually. The integration should still
  configure correctly.

---

## Scenario 3 — Deduplication (add-on broadcasting both channels)

1. With the add-on running and the integration already configured
  (Scenario 1, step 7), observe **Instellingen → Apparaten & Diensten**.
2. Confirm the add-on is broadcasting **both** channels — log lines
  `HassIO discovery announced` and `Zeroconf registered` are both
   present.
3. **Expected:** exactly **one** config entry. The companion's
  `async_step_zeroconf` aborts with `already_discovered_addon` when
   it sees `homeassistant_addon=true` in the TXT record, so the
   Supervisor flow stays the only path.
4. The **Ontdekt** list shows nothing for this gateway while the
  entry is already configured.

---

## Verification commands (developer reference)


| Goal                                               | Command                                                                                                                           |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Confirm the gateway advertises on mDNS             | `avahi-browse -art | grep ipbuilding` (Linux) / `dns-sd -B _ipbuilding-gateway._tcp.local.` (macOS)                               |
| Confirm the gateway announces to Supervisor        | `curl -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/discovery` — should list the `ha_ipbuilding_gateway` service |
| Confirm the companion's config flow parses the TXT | `PYTHONPATH=. pytest tests/test_config_flow_parsing.py`                                                                           |
| Confirm the gateway's discovery advertiser         | `PYTHONPATH=. pytest tests/test_ha_discovery.py`                                                                                  |
| Confirm no regression in the broader gateway       | `PYTHONPATH=. pytest tests/ --ignore=tests/test_discover_from_ipbox.py`                                                           |


---

## Rollback plan

If the discovery flow misbehaves on a real install:

1. **Companion**: revert to v0.2.2 (pre-`zeroconf:` entry in
  `manifest.json`). The `async_step_user` manual flow keeps working.
2. **Add-on**: revert to v0.1.3 (pre-`discovery:` entry in
  `config.yaml`). Disable the HaDiscoveryAdvertiser by setting
   `GATEWAY_HA_DISCOVERY_ENABLED=0` in the add-on options.
3. Clear the add-on's Supervisor discovery entry:
  `curl -H "Authorization: Bearer $SUPERVISOR_TOKEN" -X DELETE http://supervisor/discovery/{uuid}`.

---

## Sign-off

- [ ] Scenario 1 (add-on) passes
- [ ] Scenario 2 (standalone) passes
- [ ] Scenario 3 (dedup) passes
- [ ] Negative cases pass
- [ ] Rollback plan tested in dev environment

Date: ____________

Reviewer: ____________