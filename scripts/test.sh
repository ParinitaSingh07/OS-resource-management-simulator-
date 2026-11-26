#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# test.sh — run the full unittest suite
#
# Usage:
#   ./scripts/test.sh                 verbose, all tests
#   ./scripts/test.sh test_disk       only tests/test_disk.py
#   ./scripts/test.sh -q              quiet summary
#
# The exit status of the test run is preserved, so CI (or you) can tell
# success from failure. The last lines are saved to outputs/logs/.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -x .venv/bin/python ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

mkdir -p outputs/logs

TARGET="${1:-}"
if [[ -n "$TARGET" && "$TARGET" != -* ]]; then
    if [[ -f "tests/test_${TARGET}.py" ]]; then
        MODULE="tests.test_${TARGET}"
    elif [[ -f "tests/${TARGET}.py" ]]; then
        MODULE="tests.${TARGET%.py}"
    else
        echo "ERROR: no such test module: $TARGET" >&2
        exit 2
    fi
    shift
    set +e
    "$PYTHON" -m unittest "$MODULE" -v "$@" 2>&1 | tee -a outputs/logs/tests.log
    STATUS=${PIPESTATUS[0]}
    set -e
else
    set +e
    "$PYTHON" -m unittest discover -s tests -v "$@" 2>&1 | tee -a outputs/logs/tests.log
    STATUS=${PIPESTATUS[0]}
    set -e
fi

echo
if [[ "$STATUS" -eq 0 ]]; then
    echo "ALL TESTS PASSED"
else
    echo "TESTS FAILED (exit status $STATUS)" >&2
fi
exit "$STATUS"
