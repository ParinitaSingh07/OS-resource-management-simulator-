#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — start the simulator
#
# Usage:
#   ./scripts/run.sh              interactive menu
#   ./scripts/run.sh --report     rebuild report.pdf from real runs
#   ./scripts/run.sh --help       show main.py help
#
# If a .venv exists it is used automatically, so setup.sh --venv followed by
# run.sh works without activating anything by hand.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -x .venv/bin/python ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

if ! command -v "$PYTHON" >/dev/null 2>&1 && [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python not found. Run ./scripts/setup.sh first." >&2
    exit 1
fi

exec "$PYTHON" main.py "$@"
