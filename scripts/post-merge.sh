#!/usr/bin/env bash
# Post-merge setup: installs/updates dependencies for all project components.
# Runs automatically after each task merge. Safe to run multiple times.
set -euo pipefail

# Agent console dependencies (fast — pure pip, small requirements.txt)
echo "[post-merge] Installing agent-console dependencies…"
pip install -q -r agent-console/requirements.txt

echo "[post-merge] Done."
