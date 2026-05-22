#!/usr/bin/env bash
# Run C: idle UDP/poll window (no relay REST stimulus after inventory). Same BPF as push/pull runbooks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; fi
echo "=== Run C idle (150s post-inventory) ==="
echo "Use same mirror POV as relay captures (en7): default destination 7 <- source 15 (IPBox hub leg); alternate (relay leg only, not hub default) 7 <- source 14. Duration ~160s."
exec "$PY" ipbuilding_capture_run.py \
  --runbook resources_and_docs/workflows/push_pull_run_c_idle_runbook.yaml \
  "$@"
