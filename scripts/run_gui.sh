#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Start the web GUI.  Extra arguments are passed through to server.py, e.g.
#   ./scripts/run_gui.sh --port 9000
# Stop the server with Ctrl+C.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python3 -c "import sys; sys.exit(0)" 2>/dev/null; then
  echo "python3 was not found on PATH." >&2
  exit 1
fi

echo "Starting the OS Resource Management Simulator web GUI..."
exec python3 webapp/server.py "$@"
