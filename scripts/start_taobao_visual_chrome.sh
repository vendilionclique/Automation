#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="${TAOBAO_CHROME_PROFILE_DIR:-${ROOT_DIR}/local/chrome-taobao-visual-profile}"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
WINDOW_X="${TAOBAO_WINDOW_X:-0}"
WINDOW_Y="${TAOBAO_WINDOW_Y:-0}"
WINDOW_WIDTH="${TAOBAO_WINDOW_WIDTH:-1600}"
WINDOW_HEIGHT="${TAOBAO_WINDOW_HEIGHT:-1000}"
START_URL="${TAOBAO_START_URL:-https://www.taobao.com/}"

mkdir -p "${PROFILE_DIR}"

if pgrep -f -- "--user-data-dir=${PROFILE_DIR}" >/dev/null; then
  echo "Taobao visual Chrome is already running with profile:"
  echo "  ${PROFILE_DIR}"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true
  fi
  echo "Foreground focus attempted. Reuse the existing Chrome window."
  exit 0
fi

args=(
  --user-data-dir="${PROFILE_DIR}"
  --profile-directory=Default
  --no-first-run
  --no-default-browser-check
  --disable-features=Translate
  --new-window
  --window-position="${WINDOW_X},${WINDOW_Y}"
  --window-size="${WINDOW_WIDTH},${WINDOW_HEIGHT}"
  "${START_URL}"
)

"${CHROME_BIN}" "${args[@]}" &
sleep 2
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true
fi
echo "Started Taobao visual Chrome with profile:"
echo "  ${PROFILE_DIR}"
