#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_SCREENSHOT="${TMPDIR:-/tmp}/taobao_visual_cron_preflight.png"

echo "Taobao visual cron permission preflight"
echo "Workspace: ${ROOT_DIR}"

if ! command -v pgrep >/dev/null 2>&1; then
  echo "[FAIL] pgrep is unavailable; Chrome reuse checks cannot run." >&2
  exit 1
fi

if ! pgrep -x "Google Chrome" >/dev/null 2>&1; then
  echo "[WARN] Google Chrome is not currently running, or this execution context cannot see it."
else
  echo "[OK] Can enumerate Google Chrome with pgrep."
fi

if ! /usr/sbin/screencapture -x -D 1 "${TMP_SCREENSHOT}" >/dev/null 2>&1; then
  echo "[FAIL] Cannot persist a system screenshot with screencapture." >&2
  echo "       Run this cron with Codex profile taobao_visual_cron or equivalent" >&2
  echo "       danger-full-access/screen-recording permissions before collection." >&2
  exit 1
fi

if [[ ! -s "${TMP_SCREENSHOT}" ]]; then
  echo "[FAIL] screencapture returned success but produced no image bytes." >&2
  exit 1
fi

rm -f "${TMP_SCREENSHOT}"
echo "[OK] Can persist system screenshots."
echo "[OK] Preflight passed."
