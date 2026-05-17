#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "Checking tracked files for machine-local absolute paths..."
if git grep -n -E '/Users/[^/"[:space:]]+' -- ':!scripts/check_portable_config.sh' ':!tests/test_midscene_config.py'; then
  echo "Found user-specific absolute paths in tracked files." >&2
  exit 1
fi
if git grep -n -E '[A-Za-z]:\\Users\\[^\\[:space:]]+' -- ':!scripts/check_portable_config.sh' ':!tests/test_midscene_config.py'; then
  echo "Found Windows user-specific absolute paths in tracked files." >&2
  exit 1
fi

echo "Checking Midscene GLM-5V-Turbo env example..."
grep -q 'MIDSCENE_MODEL_NAME="glm-5v-turbo"' local/midscene-computer.env.example
grep -q 'MIDSCENE_MODEL_API_KEY=""' local/midscene-computer.env.example
grep -q 'MIDSCENE_MODEL_BASE_URL="https://api.z.ai/api/paas/v4"' local/midscene-computer.env.example
grep -q 'MIDSCENE_MODEL_FAMILY="glm-v"' local/midscene-computer.env.example
grep -q 'MIDSCENE_MODEL_REASONING_ENABLED="false"' local/midscene-computer.env.example
grep -q 'MIDSCENE_MODEL_TEMPERATURE="0"' local/midscene-computer.env.example
grep -q '^mcp_request_timeout_seconds = 180$' config/settings.example.ini

echo "Checking shell script syntax..."
while IFS= read -r script; do
  bash -n "${script}"
done < <(git ls-files '*.sh')

echo "Checking Python syntax..."
python3 -m py_compile harness.py modules/*.py

echo "Portable config checks passed."
