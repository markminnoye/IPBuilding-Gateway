#!/usr/bin/env bash
# Run Home Assistant in the venv. Foreground; Ctrl+C to stop.
# Re-uses the venv created by setup.sh.
set -euo pipefail

VENV_DIR="${HA_CORE_VENV:-$HOME/.ha-core-venv}"

if [ ! -d "${VENV_DIR}" ]; then
  echo "Venv not found at ${VENV_DIR}. Run ./local/ha-core/setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

exec hass
