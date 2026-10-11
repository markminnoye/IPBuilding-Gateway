# Changelog

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
