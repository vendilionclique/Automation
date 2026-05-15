#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "Checking tracked files for machine-local absolute paths..."
if git grep -n -E '/Users/[^/"[:space:]]+'; then
  echo "Found user-specific absolute paths in tracked files." >&2
  exit 1
fi

echo "Checking shell script syntax..."
while IFS= read -r script; do
  bash -n "${script}"
done < <(git ls-files '*.sh')

echo "Checking Python syntax..."
python3 -m py_compile harness.py modules/*.py

echo "Portable config checks passed."
