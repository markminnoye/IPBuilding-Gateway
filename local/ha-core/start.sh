#!/usr/bin/env bash
# Run Home Assistant in the venv. Foreground; Ctrl+C to stop.
# Re-uses the venv created by setup.sh.
#
#   ./local/ha-core/start.sh           # default
#   ./local/ha-core/start.sh --debug   # hass --debug -v (core debug + verbose logs)
#   ./local/ha-core/start.sh --help
set -euo pipefail

usage() {
  cat <<EOF
Usage: ./local/ha-core/start.sh [--debug] [-h|--help]

Starts Home Assistant Core in the foreground (Ctrl+C to stop) on
http://127.0.0.1:8123. Companion is the symlink from setup.sh.

  (default)   hass
  --debug     hass --debug -v — HA debug mode plus verbose logging to
              ~/.homeassistant/home-assistant.log (and the terminal).
              Companion command lines (TOGGLE vs DIM) stay at DEBUG in
              the integration logger; use gateway --debug for TX frames.

See local/README.md for the two-terminal workflow.
EOF
}

debug=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --debug)
      debug=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "error: unknown option '$1'" >&2
      usage >&2
      exit 1
      ;;
    *)
      echo "error: unexpected argument '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

VENV_DIR="${HA_CORE_VENV:-$HOME/.ha-core-venv}"

if [ ! -d "${VENV_DIR}" ]; then
  echo "Venv not found at ${VENV_DIR}. Run ./local/ha-core/setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

hass_args=()
if [ "${debug}" -eq 1 ]; then
  hass_args+=(--debug -v)
fi

echo "[start.sh] debug=${debug}"

exec hass "${hass_args[@]}"
