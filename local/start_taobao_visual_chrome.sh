#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="${ROOT_DIR}/local/chrome-taobao-visual-profile"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
REMOTE_DEBUGGING_PORT="${REMOTE_DEBUGGING_PORT:-9222}"
ENABLE_REMOTE_DEBUGGING="${ENABLE_REMOTE_DEBUGGING:-false}"

mkdir -p "${PROFILE_DIR}"

args=(
  --user-data-dir="${PROFILE_DIR}"
  --profile-directory=Default
  --no-first-run
  --no-default-browser-check
  --disable-features=Translate
  "https://www.taobao.com/"
)

if [[ "${ENABLE_REMOTE_DEBUGGING}" == "true" ]]; then
  args=(--remote-debugging-port="${REMOTE_DEBUGGING_PORT}" "${args[@]}")
fi

exec "${CHROME_BIN}" "${args[@]}"
