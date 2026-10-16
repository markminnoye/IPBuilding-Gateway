# Changelog

## 0.1.2 — 2026-10-16

- The ticket subject uses the same masks as the report, and the tool shows that subject as plain text.
- Device model codes such as IP0300PoE stay in the report. A room name such as Living becomes Lxxxxx, the same length.
- A command test starts capture while switching, when frame capture is available.
- A core suspicion goes under Bevindingen. A question for the developers goes under Open vragen.
- The tool shows the report as copyable text plus the destination address. A mailto link is only an extra. Before asking for yes, the text says the tester sends the report.
- The report YAML still carries toolkit_version. The switch names and the dimmer DIM 100/0 translation stay.
- The report opens with a fenced yaml block. Linear no longer sees front-matter.
- `connection` is the live event socket. It stays `connecting` until the snapshot, then `connected`, and status and events use that same word.

## 0.1.2-rc.1 — 2026-10-13

- The report YAML keeps `toolkit_version`. The skill tells the assistant to leave that line in place.
- The switch is named **Bediening op afstand (voor debuggen)** and **Remote control (for debugging)** in the skill and in tool text.
- A dimmer command sends DIM 0–100, TOGGLE, DIM_START, or DIM_STOP. ON becomes DIM 100 and OFF becomes DIM 0. PULSE on a dimmer is refused. The type comes from the device list.
- The skill may include an earlier observation when it is relevant and labelled with the date and the build. It asks what the tester sees while switching. It starts a capture before asking for a press, names a cause only with evidence, does not hand changelog or code work to the tester, does not advise a restart without a tool message, shows local time in chat, and offers a report.
- Claude Code can install the plugin from this repository. The plugin files stay in `toolkit/`.

## 0.1.1 — 2026-10-11

- Feedback you give reaches the report.
- You can leave test events out of the report.
- Claude offers to send the report on its own, and understands everyday words such as "bugrapport".
- The text says activiteitenlog.
- The gateway device list is the source for identifying buttons.

## 0.1.1-rc.1 — 2026-10-11

- Feedback about the tool is a parameter and appears under heading 6, with the same redaction. The problem note stays in the summary.
- `include_events` can leave test events out of the report. `send_report` reuses that choice and the last feedback.
- When sending is available, the export offers to send the report to the Sonic Rocket developers.
- Tool descriptions recognize everyday words for a report and for sending it.
- Tester-facing text says activiteitenlog. The skill treats reporting as a main task and the live device list as the only source for button and lamp ids.

## 0.1.0 — 2026-10-09

- Every dialect determination is stored, including `probe_generation` and the local decode in `capture_frames`. A dialect test uses `decode_test`.
- Appendix log lines use the same name mask as the rest of the report. Addresses, IPs, and MAC addresses stay removed.
- Each event is in one section. Bevestigd lists confirming frames only. Routine polls are a count in the appendix.
- The report shows the bundle version.
- YAML `dialects` lists full dialect ids only.
- The export includes only events from this session.

## 0.1.0-rc.12

- A sent `device_command` is stored as `command_result` and shown in the report under Wat getest werd. A command the module confirmed is also under Bevestigd. No module reply is `niet bevestigd`, not an error. A preview is not stored.
- `decode_test` is stored as `decode_result` and shown on the same tested line, with the input hex, dialect id, and a short decode.
- Names in those lines are masked. Addresses are removed. The lines do not push captured frames out of the report.
