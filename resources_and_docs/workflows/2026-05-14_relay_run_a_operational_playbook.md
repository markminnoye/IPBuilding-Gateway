# Relay Run A — operational playbook (2026-05-14)

Companion to the RE plan: controlled relay capture with mirror validation, Run A stimulus, and automated direction verdict.

**Bidirectionele UDP:** objectieve uitleg + `tshark`-check: [2026-05-15_capture_bidirectional_explainer.md](../evidence/2026-05-15_capture_bidirectional_explainer.md). **Aanbevolen standaard:** **bron 15 → bestemming 7** (**`7←15`**, IPBox-been / hub-zicht). **`7←14`** is een **expliciet alternatief** alleen wanneer je de relay-switchpoort (`10.10.1.30`) als POV wilt; leg altijd manifest + notitie gelijk aan de UniFi-config van die run.

## Mirror and safety

- **Default / recommended (Run A, quiet evening, idle, orchestrator workflow):** UniFi destination port **7** (Mac capture NIC, typically `en7`) **←** source **15** (IPBox field VLAN leg, hub `10.10.1.1`). Confirm in UniFi before capture; use preview → apply.
- **Alternate (relay switch port only):** destination **7** **←** source **14** (`10.10.1.30`). Use when the goal is relay-leg / port-specific capture; expect possible asymmetry vs hub POV (see bidirectional explainer).
- **Rollback:** After the session, restore mirror to your normal profile (typically **`7←15`** for the standard hub view, or **`7←14`** only if that relay-leg profile is your deliberate baseline; otherwise disable mirror overrides). Never leave experimental mirror on **IPBox access port 8** if the IPBox must remain reachable (see `resources_and_docs/archive/NEXT_AGENT_STATUS_QUO_2026-05-03.md`).

## Tooling (lokaal IPBox-thuisadres)

Het canonieke runbook gebruikt archief-IP `192.168.0.185`. Op `192.168.1.x` (of ander thuis-IP) moeten **REST-URL**, **BPF** en **`correlate --rest-ip`** gelijk lopen.

- Preflight (mirror + tshark-hints): [`scripts/relay_run_a_mirror_preflight.sh`](../scripts/relay_run_a_mirror_preflight.sh)
- Genereer `captures/_local_push_pull_run_a.yaml`: [`scripts/prepare_local_push_pull_run_a_runbook.py`](../scripts/prepare_local_push_pull_run_a_runbook.py) (`IPBUILDING_IPBOX_REST_HOST` of `--host`; optioneel `--verdict-pair`)
- Gate-regel in export: [`scripts/verify_capture_session_gate.sh`](../scripts/verify_capture_session_gate.sh) `captures/<SESSION>/`

## Run capture

**Python:** op macOS met PEP 668 kan `pip install` falen; gebruik een venv in de repo-root:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-capture.txt
.venv/bin/python ipbuilding_capture_run.py --runbook … --interface en7
```

From repo root:

```bash
./scripts/relay_run_a_mirror_preflight.sh
IPBUILDING_IPBOX_REST_HOST=<jouw-ipbox> python3 scripts/prepare_local_push_pull_run_a_runbook.py
./scripts/relay_run_a_capture.sh --interface en7 --runbook captures/_local_push_pull_run_a.yaml
# or archive IP unchanged:
./scripts/relay_run_a_capture.sh
# or with overrides:
python3 ipbuilding_capture_run.py --runbook resources_and_docs/workflows/push_pull_run_a_runbook.yaml --interface en7
```

Runbook: [push_pull_run_a_runbook.yaml](push_pull_run_a_runbook.yaml) (relay IDs `547/557/563/570`, OFF→ON→OFF cadence).

### Quiet evening (no kitchen fan 570)

Same mirror and BPF as Run A, but only gelijkvloers relays **547, 557, 563** (see [device-inventory-local-ipbox.md](../reference/device-inventory-local-ipbox.md)). Om **570** (Keuken ventilatie) te vermijden — nuttig als kinderen slapen of ventilator hinderlijk is.

```bash
./scripts/relay_run_a_quiet_capture.sh
# or:
python3 ipbuilding_capture_run.py --runbook resources_and_docs/workflows/push_pull_run_a_quiet_evening.yaml --interface en7
```

Runbook: [push_pull_run_a_quiet_evening.yaml](push_pull_run_a_quiet_evening.yaml).

Optional idle cadence window (Run C): same mirror, then:

```bash
./scripts/relay_run_c_idle_capture.sh --interface en7 --non-interactive
# or:
python3 ipbuilding_capture_run.py --runbook resources_and_docs/workflows/push_pull_run_c_idle_runbook.yaml --interface en7
```

Sessievoorbeeld + interpretatie: [2026-05-15_push_pull_run_c_idle_session_notes.md](../evidence/2026-05-15_push_pull_run_c_idle_session_notes.md).

## Post-session analysis

The orchestrator appends `settings.correlate_extra_args` from the runbook and runs [scripts/correlate_capture_session.py](scripts/correlate_capture_session.py) automatically unless `--no-correlate` is set.

```bash
./scripts/verify_capture_session_gate.sh captures/<SESSION>
```

Manual re-run on a session folder:

```bash
python3 scripts/correlate_capture_session.py captures/<SESSION> --verdict-profile relay --rest-ip 192.168.0.185
```

Use your real IPBox REST host for `--rest-ip` if it is not `192.168.0.185`.

Interpret **STATUS_VERDICT_GATE** in `udp_ipbox_export.txt` (and stdout): **WARN** means do not claim wire-absence of status replies; **PASS** means bidirectional UDP was seen between `10.10.1.30` and `10.10.1.1` or the configured REST IP in the filtered export.

## Evidence

Record session path, mirror snapshot reference (UniFi MCP export if used), and gate outcome in a dated note under `resources_and_docs/` or append to existing relay correlation evidence.

## Optional: dimmer capture (stap 4)

Alleen wanneer geluid/licht acceptabel is. **Niet** hetzelfde als relay-runbook: hier geen volledige orchestrator-pcap tenzij je `dumpcap` zelf start.

1. UniFi mirror **7←12** (dimmer `10.10.1.40` op poort **12**, niet 11). Preview → apply.
2. Start handmatig `dumpcap` op `en7` met bijv. BPF `host 10.10.1.40 and udp port 1001` (of breder volgens [CAPTURE_LIVE_STATUS.md](CAPTURE_LIVE_STATUS.md)).
3. `./scripts/dimmer_only_re_stimulus.sh` (optioneel `MANIFEST_PATH` naar je logpad).
4. Stop `dumpcap`; correlatie: `python3 scripts/correlate_capture_session.py <sessie_map> --verdict-profile dimmer --rest-ip 192.168.0.185` (sessiemap moet `capture.pcapng` + `manifest.jsonl` bevatten als je alles in één map wilt — anders handmatige tijd-correlatie met `dimmer_re_manifest.log`).
5. Mirror terug naar **`7←15`** (standaard hub) of **`7←14`** (relay-poort-POV) of je normale profiel.

Snelle preflight-herinnering:

```bash
./scripts/dimmer_mirror12_preflight.sh
```

