# IPBuilding debug toolkit

Local helper for a tester who runs the IPBuilding Gateway add-on at home. It is a stdio MCP server, a Claude Desktop bundle (`.mcpb`), and a Claude Code plugin. Testers install the bundle and follow [HANDLEIDING.md](HANDLEIDING.md). They do not need Git or a terminal.

The toolkit only talks to the gateway REST and WebSocket API on port 8080. It never opens its own field-bus socket.

## Layout

| Path | Role |
| --- | --- |
| `ipbuilding_debug/` | MCP server |
| `skills/ipbuilding-debug/SKILL.md` | Session guidance, also sent as the server instructions |
| `HANDLEIDING.md` | Plain-language install guide |
| `.claude-plugin/`, `.mcp.json` | Claude Code plugin |
| `scripts/build.py` | One build used locally and in CI |
| `VERSION` | Version. A release tag `toolkit-vX.Y.Z` must match this file |

The gateway address is a user setting (`gateway_address` in the bundle, the same key in the Claude Code plugin). It is passed as `IPBUILDING_GATEWAY_ADDRESS`. Nothing in this folder hardcodes an address.

## Tools

| Tool | This version | Waits on |
| --- | --- | --- |
| `connection_status` | Works against `/api/v1/status` and the local buffer | — |
| `probe_generation` | Works against `/status`, `/modules`, `/devices` | — |
| `decode_test` | Local, uses `gateway/payloads` | — |
| `export_session` | Local notes, gap markers, buffered events | Live logs appear in the export once `log_stream` exists |
| `capture_frames` | Subscribes when `udp_frame` is advertised | Gateway `udp_frame` |
| `send_raw` | Posts when `raw_send` is advertised, and only after `confirmed=true` | Gateway raw send |

If a name is missing from `/status.capabilities`, the tool returns a not-available message instead of failing. Planned names: `log_stream`, `udp_frame`, `raw_send`.

`connection_status` also tells the tester when **Remote debugging and control** is off (`remote_debugging: false`, or error code `remote_debugging_disabled`).

## Contract the later gateway changes should meet

The client already speaks this. Adjust the client in the same change if the gateway picks different names.

- WebSocket client → gateway, only when `log_stream` is listed: `{"type":"subscribe_logs","min_level":"INFO"}` and `{"type":"set_log_level","level":"DEBUG","ttl":900}`. More than 10 level changes in 60 seconds come back as `{"type":"error","error":"log_level_rate_limited"}`. The tool then tells the tester to wait a minute.
- WebSocket client → gateway, only when `udp_frame` is listed and a capture is running: `{"type":"subscribe_udp_frames"}`.
- Gateway → client frames: `{"type":"udp_frame","direction":"tx","hex":"...","src":"...","dst":"...","port":1001}`.
- Raw send: `POST /api/v1/debug/raw-send` with `target`, `port`, `payload_hex`, `window_ms`. Refusal body: `{"error":"remote_debugging_disabled"}`.

The WebSocket stays up for the life of the MCP process, reconnects with backoff from 1 s to 30 s, resubscribes, replaces local state from the snapshot, and inserts a gap marker. `wait_for_state` never waits longer than 30 s. Logging goes to stderr.

## Build and release

```bash
python3 toolkit/scripts/build.py
```

The script stages a bundle, copies the decoders it needs, and runs `mcpb validate` and `mcpb pack`. CI does the same on every pull request. A tag `toolkit-vX.Y.Z` whose number matches `VERSION` attaches the `.mcpb` to a GitHub release.

Do not use a `vX.Y.Z` tag for this package. That tag builds the Home Assistant add-on.

## Tests

```bash
PYTHONPATH=toolkit:. python3 -m pytest toolkit/tests -q
```

Tests use a fake gateway on localhost. They do not touch a real installation.
