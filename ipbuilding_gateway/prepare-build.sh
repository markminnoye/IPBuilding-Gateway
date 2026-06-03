#!/usr/bin/env bash
# prepare-build.sh — stage gateway/ into add-on context for Docker build
#
# In the monorepo the canonical gateway/ lives at repo-root.
# The HA builder uses ipbuilding_gateway/ as the Docker build context,
# so we copy gateway/ into the add-on folder before docker build.
#
# Usage:
#   ./prepare-build.sh           # local dev
#   (called automatically by .github/workflows/builder.yaml in CI)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[prepare-build] Removing old staging copy..."
rm -rf "$REPO_ROOT/ipbuilding_gateway/gateway" || true

echo "[prepare-build] Copying gateway/ from repo-root to add-on folder..."
cp -r --no-preserve=mode,ownership "$REPO_ROOT/gateway" "$REPO_ROOT/ipbuilding_gateway/gateway"

echo "[prepare-build] Done — $(find "$REPO_ROOT/ipbuilding_gateway/gateway" -type f | wc -l) files staged"