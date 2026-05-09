#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${MIDSCENE_ENV_FILE:-${ROOT_DIR}/local/midscene-computer.env}"
NODE_BIN="${NODE_BIN:-/Users/zhunshi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
MIDSCENE_BIN="${ROOT_DIR}/node_modules/@midscene/computer/bin/midscene-computer"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export MIDSCENE_RUN_DIR="${MIDSCENE_RUN_DIR:-${ROOT_DIR}/local/midscene-run}"
export MIDSCENE_REPORT_QUIET="${MIDSCENE_REPORT_QUIET:-true}"

exec "${NODE_BIN}" "${MIDSCENE_BIN}" "$@"
