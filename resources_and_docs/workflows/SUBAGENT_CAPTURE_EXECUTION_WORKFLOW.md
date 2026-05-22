# Subagent Capture Execution Workflow

This document operationalizes the plan in `/Users/markminnoye/.cursor/plans/subagent_execution_capture_plan_3d4fb4e6.plan.md` without editing that plan file.

## Runtime Parameters

Use these environment variables so the workflow is portable:

- `CAP_IFACE` (default `en7`)
- `IPBOX_HOST` (default `192.168.0.185` — archief; thuis-LAN is **`192.168.1.0/24`**: zet env naar je actuele IPBox-host)
- `IPBOX_PORT` (default `30200`)
- `CTRL_IP_SET` (default `10.10.1.30,10.10.1.40,10.10.1.50`)

## Execution Matrix

| Phase | Owner | Prerequisites | Success criteria | Retry policy | Stop/escalate |
|---|---|---|---|---|---|
| Preflight | Implementer subagent (network focus) | `CAP_IFACE` exists, `python3`/`tcpdump`/`tshark` available, REST reachable at `IPBOX_HOST:IPBOX_PORT`, non-interactive sudo check passes | All checks pass, or fallback mode activated | 2 retries (15s, 30s) | Stop if still failing |
| Run0 Gate | Implementer | Preflight passed | At least 5 `udp/1001` frames over >=10s with endpoint match against `CTRL_IP_SET` | 3 attempts total | Stop trigger series if gate fails |
| Trigger src 12 | Implementer | Run0 passed | Correlated payload delta, or explicit inconclusive with evidence | 2 retries on execution errors | Escalate if repeated failures |
| Trigger src 13 | Implementer | src 12 complete and reviewed | Same as src 12 | 2 retries on execution errors | Escalate if repeated failures |
| Trigger src 14 | Implementer | src 13 complete and reviewed | Same as src 12 | 2 retries on execution errors | Escalate if repeated failures |
| Reporting | Implementer | All source blocks done | Best source chosen with confidence and evidence map | 2 review-fix loops | Stop if reviews still fail |

## Strict Dispatch Order

For each phase:
1. Implementer subagent executes phase.
2. Spec reviewer validates phase against handoff scope.
3. If spec fails, implementer fixes, then spec review repeats.
4. Code quality reviewer validates reproducibility and safety.
5. If quality fails, implementer fixes, then spec review, then quality review repeats.
6. Move to next phase only if phase gate passes and both reviews pass.

Implementation blocks are sequential only: Preflight -> Run0 -> src12 -> src13 -> src14 -> Reporting.

## Evidence Checklist

### Preflight evidence
- `python3 --version` output captured.
- `which tcpdump` and `which tshark` captured.
- `ifconfig $CAP_IFACE` success captured.
- `curl` probe to `http://$IPBOX_HOST:$IPBOX_PORT/api/v1/comp/items` captured.
- `sudo -n true` success captured before starting capture commands.
- MCP capabilities captured, or fallback declaration captured.

### Run0 gate evidence
- Capture filter recorded as `udp port 1001`.
- Pcap exists and is non-zero.
- Parsed frame list contains `ip.src`, `ip.dst`, `udp.srcport`, `udp.dstport`.
- Gate decision includes endpoint matches from `CTRL_IP_SET`.
- Gate decision logs minimum frame-count and duration checks (>=5 frames and >=10s).

### Per source (12/13/14) evidence
- Capture start/stop UTC timestamps recorded.
- REST trigger timestamps recorded.
- Packet CSV with payload hex present.
- Correlation result marked `CORRELATED`, `INCONCLUSIVE`, or `FAILED_EXECUTION`.
- Test sequence finishes with explicit safe state restore action.

### Reporting evidence
- Per-source comparison summary exists.
- Best source and confidence are explicit.
- Every conclusion maps to artifact file paths.

## Artifact Naming Contract (UTC)

Run directory:
`captures/<RUN_TS>__capture-tests/`

Timestamp format:
`YYYYMMDDTHHMMSSZ`

Filename format:
`<RUN_TS>__<phase>__src-<port-or-na>__scenario-<id>__try-<nn>__<kind>.<ext>`

Examples:
- `20260503T160201Z__run0__src-na__scenario-smoke__try-01__gate.pcapng`
- `20260503T160201Z__trigger__src-12__scenario-onoff__try-01__packets.csv`
- `20260503T160201Z__reporting__src-na__scenario-final__try-01__final_report.md`

## Non-MCP Fallback Procedure

If Wireshark/UniFi MCP is unavailable, run command-line capture and analysis:

```bash
CAP_IFACE="${CAP_IFACE:-en7}"
IPBOX_HOST="${IPBOX_HOST:-192.168.0.185}"
IPBOX_PORT="${IPBOX_PORT:-30200}"
CTRL_IP_SET="${CTRL_IP_SET:-10.10.1.30,10.10.1.40,10.10.1.50}"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="captures/${RUN_TS}__capture-tests"
mkdir -p "$RUN_DIR"
```

Preflight fallback:

```bash
python3 --version
which tcpdump
which tshark
ifconfig "$CAP_IFACE"
sudo -n true
curl -sS -m 3 "http://${IPBOX_HOST}:${IPBOX_PORT}/api/v1/comp/items"
```

Run0 fallback:

```bash
PCAP="$RUN_DIR/${RUN_TS}__run0__src-na__scenario-smoke__try-01__gate.pcapng"
CSV="$RUN_DIR/${RUN_TS}__run0__src-na__scenario-smoke__try-01__frames.csv"

cleanup() { [ -n "${TCPDUMP_PID:-}" ] && sudo kill -INT "$TCPDUMP_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

sudo tcpdump -i "$CAP_IFACE" -n -s0 -U -w "$PCAP" 'udp port 1001' &
TCPDUMP_PID=$!
sleep 25
sudo kill -INT "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true

tshark -r "$PCAP" \
  -Y 'udp.port==1001' \
  -T fields -e frame.time_epoch -e ip.src -e udp.srcport -e ip.dst -e udp.dstport -e data \
  > "$CSV"
```

Acceptance:
- pcap exists and has non-zero size;
- CSV has endpoint matches against `CTRL_IP_SET`;
- CSV shows at least 5 frames across >=10 seconds for gate pass;
- otherwise revalidate mirror/source mapping and retry within policy.

## Per-source Trigger Recipe

Safety constraints (mandatory):

- Allowed action types: `ON`, `OFF`, `DIM`, `SCENE`.
- Allowed IDs: only IDs listed in `resources_and_docs/reference/IPBOX_REST_API_TEST_CALLS.md`.
- Max trigger count per source block: 2 actions.
- Abort immediately if any unexpected component changes outside target IDs.
- Mandatory rollback: end each block with device in known safe state (OFF or DIM 0).

Example source block execution (`src-12`; repeat for `src-13`, `src-14`):

```bash
SRC=12
TRY=01
PCAP="$RUN_DIR/${RUN_TS}__trigger__src-${SRC}__scenario-onoff__try-${TRY}__capture.pcapng"
PKTCSV="$RUN_DIR/${RUN_TS}__trigger__src-${SRC}__scenario-onoff__try-${TRY}__packets.csv"
MANIFEST="$RUN_DIR/${RUN_TS}__trigger__src-${SRC}__scenario-onoff__try-${TRY}__manifest.jsonl"

cleanup() { [ -n "${TCPDUMP_PID:-}" ] && sudo kill -INT "$TCPDUMP_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

sudo tcpdump -i "$CAP_IFACE" -n -s0 -U -w "$PCAP" 'udp port 1001' &
TCPDUMP_PID=$!

TS1="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "{\"ts\":\"$TS1\",\"src\":$SRC,\"action\":\"ON\",\"id\":5}" >> "$MANIFEST"
curl -sS -m 5 "http://${IPBOX_HOST}:${IPBOX_PORT}/api/v1/action/action?id=5&actionType=ON&value=1" >/dev/null

sleep 2

TS2="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "{\"ts\":\"$TS2\",\"src\":$SRC,\"action\":\"OFF\",\"id\":5}" >> "$MANIFEST"
curl -sS -m 5 "http://${IPBOX_HOST}:${IPBOX_PORT}/api/v1/action/action?id=5&actionType=OFF&value=0" >/dev/null

sleep 3
sudo kill -INT "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true

tshark -r "$PCAP" -Y 'udp.port==1001' \
  -T fields -e frame.number -e frame.time_epoch -e ip.src -e udp.srcport -e ip.dst -e udp.dstport -e data \
  > "$PKTCSV"
```

Correlation rubric:

- `CORRELATED`: at least one payload delta occurs within +/-2s of trigger timestamp and endpoint belongs to `CTRL_IP_SET`.
- `INCONCLUSIVE`: valid capture exists but no qualifying delta within window.
- `FAILED_EXECUTION`: capture failed, REST failed, or evidence files missing.
