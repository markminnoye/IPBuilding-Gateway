# Changelog

## 0.1.0-rc.12

- A sent `device_command` is stored as `command_result` and shown in the report under Wat getest werd. A command the module confirmed is also under Bevestigd. No module reply is `niet bevestigd`, not an error. A preview is not stored.
- `decode_test` is stored as `decode_result` and shown on the same tested line, with the input hex, dialect id, and a short decode.
- Names in those lines are masked. Addresses are removed. The lines do not push captured frames out of the report.
