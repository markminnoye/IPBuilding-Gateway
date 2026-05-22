#!/usr/bin/env bash
# Sprint 5 — physical input capture (mirror 7←15 on UniFi before running)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"
RUNBOOK="${REPO_ROOT}/resources_and_docs/workflows/sprint5_input_physical_runbook.yaml"
INTERFACE="${INTERFACE:-en7}"
NONINTERACTIVE="${NONINTERACTIVE:-0}"

echo "=== Sprint 5 — IP1100 physical input capture ==="
echo "Mirror: UniFi 7←15 (source 15 → dest 7) on Unify Switch 16"
echo "Interface: ${INTERFACE}"
echo ""
if [[ "${NONINTERACTIVE}" != "1" ]]; then
  echo "Druk ENTER om te starten; druk fysieke knoppen wanneer het script daarom vraagt."
  read -r
fi

if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -q -r "${REPO_ROOT}/requirements-capture.txt"
fi

ARGS=(
  "${VENV}/bin/python" "${REPO_ROOT}/ipbuilding_capture_run.py"
  --runbook "${RUNBOOK}"
  --interface "${INTERFACE}"
  --output-dir "${REPO_ROOT}/captures"
)
if [[ "${NONINTERACTIVE}" == "1" ]]; then
  ARGS+=(--non-interactive)
fi

sudo -E "${ARGS[@]}" 2>&1 | tee "${REPO_ROOT}/captures/_sprint5_last_run.log"
echo ""
echo "Zoek sessiemap: ls -td ${REPO_ROOT}/captures/*_sprint5-input-physical"
