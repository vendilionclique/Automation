#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="${ROOT_DIR}/local/chrome-taobao-visual-profile"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
WINDOW_X="${WINDOW_X:-0}"
WINDOW_Y="${WINDOW_Y:-0}"
WINDOW_WIDTH="${WINDOW_WIDTH:-1600}"
WINDOW_HEIGHT="${WINDOW_HEIGHT:-1000}"
START_URL="${START_URL:-https://www.taobao.com/}"

mkdir -p "${PROFILE_DIR}"

if pgrep -f -- "--user-data-dir=${PROFILE_DIR}" >/dev/null; then
  echo "Taobao visual Chrome is already running with profile:"
  echo "  ${PROFILE_DIR}"
  echo "Not opening another tab. Bring the existing Chrome window to front and continue."
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

exec "${CHROME_BIN}" "${args[@]}"
