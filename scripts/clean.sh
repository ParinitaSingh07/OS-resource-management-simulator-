#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# clean.sh — remove generated files, keeping the project and datasets
#
# Usage:
#   ./scripts/clean.sh          caches + charts + logs + texts, keeps report.pdf
#   ./scripts/clean.sh --all    also deletes report.pdf and .venv
#
# Deletes only inside this project. `.gitkeep` files and every source file,
# dataset and document are preserved.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

REMOVE_PDF=0
if [[ "${1:-}" == "--all" ]]; then
    REMOVE_PDF=1
elif [[ $# -gt 0 ]]; then
    echo "usage: $0 [--all]" >&2
    exit 2
fi

echo "== cleaning generated files =="

find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true

for dir in outputs/charts outputs/logs outputs/reports; do
    if [[ -d "$dir" ]]; then
        find "$dir" -type f ! -name ".gitkeep" -delete
        echo "  cleared $dir/"
    fi
done

find . -maxdepth 1 -type f -name ".coverage" -delete 2>/dev/null || true

if [[ "$REMOVE_PDF" -eq 1 ]]; then
    rm -f report.pdf
    rm -rf .venv
    echo "  removed report.pdf and .venv"
fi

echo "Done. Source files, datasets, docs and screenshots were not touched."
