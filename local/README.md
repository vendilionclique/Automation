# Local Runtime Data

This directory is for machine-local runtime data that must not be committed.

Recommended Chrome visual collection profile:

```text
local/chrome-taobao-visual-profile
```

Start it with:

```bash
local/start_taobao_visual_chrome.sh
```

Midscene computer MCP is launched through:

```bash
local/start_midscene_computer_mcp.sh
```

For external VLM grounding, copy:

```bash
cp local/midscene-computer.env.example local/midscene-computer.env
```

Then fill `local/midscene-computer.env` with `MIDSCENE_MODEL_*` values. The
real env file is local-only and ignored by git.

Only this README and `.gitkeep` are tracked. Recreate directory contents on each
machine after cloning, then log in to Taobao manually in that Chrome profile.
