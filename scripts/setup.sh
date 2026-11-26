#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup.sh — check the environment and prepare the project folders
#
# Usage:
#   ./scripts/setup.sh            use the system python3 (default)
#   ./scripts/setup.sh --venv     create .venv and install requirements.txt
#
# Works on Linux, macOS and Windows Git Bash. Run from anywhere; the script
# changes to the project root itself.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
USE_VENV=0
if [[ "${1:-}" == "--venv" ]]; then
    USE_VENV=1
elif [[ $# -gt 0 ]]; then
    echo "usage: $0 [--venv]" >&2
    exit 2
fi

echo "== OS Resource Management Simulator — setup =="

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: '$PYTHON' not found. Install Python 3.9+ or set PYTHON=/path/to/python3." >&2
    exit 1
fi
echo "Python      : $("$PYTHON" --version 2>&1)  ($(command -v "$PYTHON"))"

"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 9):
    sys.exit(f"ERROR: Python 3.9+ required, found {sys.version.split()[0]}")
print("Version     : OK (>= 3.9)")
PY

if [[ "$USE_VENV" -eq 1 ]]; then
    if [[ ! -d .venv ]]; then
        echo "Creating    : .venv"
        "$PYTHON" -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    PYTHON="python3"
    echo "Installing  : requirements.txt into .venv"
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet -r requirements.txt
fi

if "$PYTHON" -c "import matplotlib" >/dev/null 2>&1; then
    echo "matplotlib  : $("$PYTHON" -c 'import matplotlib; print(matplotlib.__version__)')"
else
    echo "matplotlib  : NOT installed — text output works, charts and report.pdf will be skipped."
    echo "              Install it with: $PYTHON -m pip install -r requirements.txt"
fi

echo "Folders     : creating data/, outputs/{logs,charts,reports}/, screenshots/"
mkdir -p data outputs/logs outputs/charts outputs/reports screenshots

echo "Byte-compile: main.py modules/ utils/ tests/"
"$PYTHON" -m compileall -q main.py modules utils tests

chmod +x scripts/*.sh 2>/dev/null || true

echo
echo "Setup complete. Next:"
echo "  ./scripts/run.sh          launch the menu"
echo "  ./scripts/test.sh         run the unit tests"
echo "  ./scripts/clean.sh        remove generated files"
