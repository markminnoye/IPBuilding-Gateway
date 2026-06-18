#!/usr/bin/env bash
# One-time setup: create venv, install Home Assistant, symlink the
# companion custom_component from the sibling ha-ipbuilding-gateway repo.
set -euo pipefail

VENV_DIR="${HA_CORE_VENV:-$HOME/.ha-core-venv}"
HA_CONFIG_DIR="$HOME/.homeassistant"
COMPANION_SRC="/Users/markminnoye/git/ha-ipbuilding-gateway/custom_components/ha_ipbuilding_gateway"
COMPANION_DOMAIN="ha_ipbuilding_gateway"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HA_PACKAGE="${HA_PACKAGE:-homeassistant}"

echo ">>> Using venv: ${VENV_DIR}"
echo ">>> HA config:  ${HA_CONFIG_DIR}"
echo ">>> Companion:  ${COMPANION_SRC}"

if [ ! -d "${COMPANION_SRC}" ]; then
  echo "Companion source not found at ${COMPANION_SRC}" >&2
  echo "Adjust COMPANION_SRC in this script or clone the repo first." >&2
  exit 1
fi

# 1. venv
if [ ! -d "${VENV_DIR}" ]; then
  echo ">>> Creating venv"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# 2. install HA
echo ">>> Installing ${HA_PACKAGE} (this can take a few minutes)"
pip install --upgrade pip wheel setuptools
pip install "${HA_PACKAGE}"

# 2a. HA Core 2026.x pulls in `serialx` for the new usb/bluetooth stack,
# which requires `aioesphomeapi` at runtime. Install it explicitly so the
# usb → bluetooth → default_config dependency chain doesn't fail at startup.
# Re-run safe: pip install is idempotent.
echo ">>> Installing aioesphomeapi (required by HA 2026.x usb/bluetooth stack)"
pip install aioesphomeapi
# Also pin bleak — a few HA integrations (shelly, esphome) use it via the
# bluetooth stack. Keeps startup warnings to a minimum.
pip install bleak

# 3. symlink companion custom_component
mkdir -p "${HA_CONFIG_DIR}/custom_components"
ln -sfn "${COMPANION_SRC}" "${HA_CONFIG_DIR}/custom_components/${COMPANION_DOMAIN}"

echo
echo "Done. Start HA with:  ./local/ha-core/start.sh"
echo "Then open:           http://localhost:8123"
