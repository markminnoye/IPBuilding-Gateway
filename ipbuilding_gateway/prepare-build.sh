#!/usr/bin/env bash
# prepare-build.sh — stage gateway/ and shared root-level files into
# the add-on context for the Docker build.
#
# In the monorepo the canonical gateway/ lives at repo-root.
# The HA builder uses ipbuilding_gateway/ as the Docker build context,
# so we copy gateway/ (and any other root-level files the Dockerfile
# needs) into the add-on folder before docker build.
#
# Usage:
#   ./prepare-build.sh           # local dev
#   (called automatically by .github/workflows/builder.yaml in CI)
#
# The Dockerfile is intentionally context-agnostic: it expects a
# requirements file at the build context root. We keep one source of
# truth at the repo root and copy it into the add-on folder here so
# the Dockerfile can stay self-contained.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[prepare-build] Removing old staging copies..."
rm -rf "$REPO_ROOT/ipbuilding_gateway/gateway" || true
rm -f "$REPO_ROOT/ipbuilding_gateway/requirements-gateway.txt" || true
# The version is no longer stamped into a generated file. config.yaml is
# the single source of truth: gateway/version.py reads it directly at
# runtime, both in local dev and inside the Docker image. No _version.py
# is created or removed here on purpose — if one ever appears, that's a
# regression and the .cursor/hooks/check-release-sync.sh hook (or a
# human reviewer) should flag it.
rm -f "$REPO_ROOT/ipbuilding_gateway/gateway/_version.py" || true

echo "[prepare-build] Copying gateway/ from repo-root to add-on folder..."
cp -r "$REPO_ROOT/gateway" "$REPO_ROOT/ipbuilding_gateway/gateway"

echo "[prepare-build] Copying requirements-gateway.txt from repo-root to add-on folder..."
cp "$REPO_ROOT/requirements-gateway.txt" "$REPO_ROOT/ipbuilding_gateway/requirements-gateway.txt"

# config.yaml stays where it is: the add-on context already includes
# ipbuilding_gateway/ (the Dockerfile's build context is this whole
# folder), and gateway/version.py resolves it via _repo_root() relative
# to the installed gateway/ package. No copy needed.

echo "[prepare-build] Done — $(find "$REPO_ROOT/ipbuilding_gateway/gateway" -type f | wc -l) gateway files staged"