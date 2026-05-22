#!/usr/bin/env bash
# Print STATUS_VERDICT_GATE line(s) from udp_ipbox_export.txt for a capture session folder.
set -euo pipefail
SESSION="${1:?usage: verify_capture_session_gate.sh captures/<SESSION_DIR>}"
EXPORT="${SESSION%/}/udp_ipbox_export.txt"
if [[ ! -f "$EXPORT" ]]; then
  echo "Missing $EXPORT" >&2
  exit 1
fi
python3 - <<'PY' "$EXPORT"
import sys
from pathlib import Path
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8", errors="replace")
for line in text.splitlines():
    if "STATUS_VERDICT_GATE" in line:
        print(line)
PY
