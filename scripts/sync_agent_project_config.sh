#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
CODEX_CONFIG="${CODEX_HOME}/config.toml"
MCP_LAUNCHER="${ROOT_DIR}/local/start_midscene_computer_mcp.sh"
LOCAL_ENV="${ROOT_DIR}/local/midscene-computer.env"

mkdir -p "${CODEX_HOME}"
touch "${CODEX_CONFIG}"

python3 - "$CODEX_CONFIG" "$MCP_LAUNCHER" "$ROOT_DIR" <<'PY'
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
launcher = sys.argv[2]
root_dir = sys.argv[3]
text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
tools = [
    "ListDisplays",
    "computer_connect",
    "computer_disconnect",
    "computer_list_displays",
    "take_screenshot",
    "Tap",
    "DoubleClick",
    "RightClick",
    "MouseMove",
    "Input",
    "Scroll",
    "KeyboardPress",
    "DragAndDrop",
    "ClearInput",
    "act",
    "assert",
]
tool_blocks = "".join(
    f"[mcp_servers.midscene-computer.tools.{tool}]\n"
    'approval_mode = "approve"\n\n'
    for tool in tools
)
server_block = (
    "[mcp_servers.midscene-computer]\n"
    f'command = "{launcher}"\n'
    "args = []\n"
    "env = {}\n"
    "startup_timeout_sec = 30\n"
    "tool_timeout_sec = 180\n"
    "enabled = true\n\n"
    'default_tools_approval_mode = "approve"\n\n'
    f"{tool_blocks}"
)

profile_block = (
    "[profiles.taobao_visual_cron]\n"
    'model = "gpt-5.5"\n'
    'sandbox_mode = "danger-full-access"\n'
    'approval_policy = "never"\n'
    f'cwd = "{root_dir}"\n\n'
)

extract_profile_block = (
    "[profiles.taobao_visual_extract]\n"
    'model = "gpt-5.5"\n'
    'sandbox_mode = "danger-full-access"\n'
    'approval_policy = "never"\n'
    f'cwd = "{root_dir}"\n\n'
)

def upsert_block(src: str, pattern: re.Pattern[str], block: str) -> str:
    if pattern.search(src):
        return pattern.sub(block, src)
    if src and not src.endswith("\n"):
        src += "\n"
    return src + "\n" + block

server_pattern = re.compile(
    r"(?ms)^\[mcp_servers\.midscene-computer\]\r?\n.*?"
    r"(?=^\[(?!mcp_servers\.midscene-computer(?:\.tools\.)?)|\Z)"
)
profile_pattern = re.compile(
    r"(?ms)^\[profiles\.taobao_visual_cron\]\r?\n.*?(?=^\[|\Z)"
)
extract_profile_pattern = re.compile(
    r"(?ms)^\[profiles\.taobao_visual_extract\]\r?\n.*?(?=^\[|\Z)"
)
text = upsert_block(text, server_pattern, server_block)
text = upsert_block(text, profile_pattern, profile_block)
text = upsert_block(text, extract_profile_pattern, extract_profile_block)
config_path.write_text(text, encoding="utf-8")
PY

if [[ -n "${CODEX_SET_DEFAULT_TAOBAO_VISUAL_CRON:-}" ]]; then
python3 - "$CODEX_CONFIG" <<'PY'
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
defaults = {
    "model": '"gpt-5.5"',
    "sandbox_mode": '"danger-full-access"',
    "approval_policy": '"never"',
}
for key, value in defaults.items():
    line = f"{key} = {value}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text = line + "\n" + text
config_path.write_text(text, encoding="utf-8")
PY
fi

if [[ ! -f "${LOCAL_ENV}" ]]; then
  mkdir -p "$(dirname "${LOCAL_ENV}")"
  cat > "${LOCAL_ENV}" <<EOF
# Local Midscene computer VLM config. Gitignored; do not commit.
export MIDSCENE_MODEL_NAME="glm-4.6v-flash"
export MIDSCENE_MODEL_API_KEY=""
export MIDSCENE_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export MIDSCENE_MODEL_FAMILY="glm-v"
export MIDSCENE_MODEL_REASONING_ENABLED="false"
export MIDSCENE_RUN_DIR="${ROOT_DIR}/local/midscene-run"
export MIDSCENE_REPORT_QUIET="true"
EOF
fi

echo "Codex MCP configured: ${CODEX_CONFIG}"
echo "Codex cron profile configured: taobao_visual_cron"
echo "Codex extract profile configured: taobao_visual_extract"
echo "Project skill remains repo-local: ${ROOT_DIR}/.agents/skills/taobao-visual-collection"
echo "Midscene env file: ${LOCAL_ENV}"
