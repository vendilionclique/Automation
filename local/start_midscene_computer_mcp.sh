#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${MIDSCENE_ENV_FILE:-${ROOT_DIR}/local/midscene-computer.env}"
LOCAL_NODE_BIN="${ROOT_DIR}/local/node-runtime/node-v24.14.0-darwin-arm64/bin/node"
NODE_BIN="${NODE_BIN:-}"
if [[ -z "${NODE_BIN}" && -x "${LOCAL_NODE_BIN}" ]]; then
  NODE_BIN="${LOCAL_NODE_BIN}"
fi
if [[ -z "${NODE_BIN}" ]] && command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
fi
MIDSCENE_MCP_LAUNCHER="${ROOT_DIR}/scripts/midscene_computer_mcp_launcher.cjs"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export MIDSCENE_RUN_DIR="${MIDSCENE_RUN_DIR:-${ROOT_DIR}/local/midscene-run}"
export MIDSCENE_REPORT_QUIET="${MIDSCENE_REPORT_QUIET:-true}"

if [[ -z "${NODE_BIN}" || ! -x "${NODE_BIN}" ]]; then
  echo "Node.js not found. Install dependencies with npm ci, or set NODE_BIN to a local node executable." >&2
  exit 127
fi

exec "${NODE_BIN}" "${MIDSCENE_MCP_LAUNCHER}" "$@"
