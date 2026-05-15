# Local Runtime Data

This directory is for machine-local runtime data that must not be committed.

Recommended Chrome visual collection profile:

```text
local/chrome-taobao-visual-profile
```

Start it with:

```bash
bash scripts/start_taobao_visual_chrome.sh
```

On Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_taobao_visual_chrome.ps1
```

Midscene computer MCP is launched through:

```bash
local/start_midscene_computer_mcp.sh
```

On Windows, use the tracked project launcher instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_midscene_computer_mcp.ps1
```

To sync the project MCP and project skill into Codex on a new machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_agent_project_config.ps1
```

The sync script also pre-approves the Midscene computer tools needed by the
Taobao visual workflow in `~/.codex/config.toml` with
`approval_mode = "never"`. This keeps cron-launched sessions from pausing on
every `Tap`, `Input`, `Scroll`, or screenshot action. The approval is scoped to
the Midscene computer MCP action surface; it does not add DOM, HTML, network,
cookie, storage, or CDP extraction tools.

For external VLM grounding, copy:

```bash
cp local/midscene-computer.env.example local/midscene-computer.env
```

Then fill `local/midscene-computer.env` with `MIDSCENE_MODEL_*` values. The
tracked example defaults to `MIDSCENE_MODEL_NAME=glm-4.6v`,
`MIDSCENE_MODEL_FAMILY=glm-v`, and the Zhipu OpenAI-compatible base URL; adjust
the model id locally if the Zhipu console uses a different exact 4.6v vision
identifier.

Taobao capture intentionally has no model fallback. A 429 containing
`余额不足或无可用资源包`, `无可用资源包`, `code: 1113`, or `code 1113` means the
configured Zhipu resource package is unavailable, not ordinary QPS throttling.
The capture worker stops the current session as `vlm_resource_unavailable` so a
human/supervisor can pause, cool down, or update billing/resources. Viewport
tile movement uses fixed-distance Midscene MCP `Scroll` first to reduce VLM
calls; search may still use `act` for visible search-box grounding.

The real env file is local-only and ignored by git.

Only this README and `.gitkeep` are tracked. Recreate directory contents on each
machine after cloning, then log in to Taobao manually in that Chrome profile.
