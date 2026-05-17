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

Windows 暂不纳入当前业务主线；PowerShell 脚本仅作为远期/实验辅助保留：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_taobao_visual_chrome.ps1
```

Midscene computer MCP is launched through:

```bash
local/start_midscene_computer_mcp.sh
```

Windows MCP launcher is future/experimental only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_midscene_computer_mcp.ps1
```

To sync the project MCP and project skill into Codex on a macOS machine:

```bash
bash scripts/sync_agent_project_config.sh
```

The sync script also pre-approves the Midscene computer tools needed by the
Taobao visual workflow in `~/.codex/config.toml` with
`approval_mode = "approve"`. The generated `taobao_visual_cron` and
`taobao_visual_extract` profiles use `approval_policy = "never"`. This keeps
cron-launched sessions from pausing on the bounded act mainline: connect/list
display, system screenshot, `act`, and coarse `assert`. Short action tools such
as `Tap`, `Input`, `KeyboardPress`, `Scroll`, and `ClearInput` are not part of
the unattended capture approval surface. The approval is scoped to the Midscene
computer MCP action surface; it does not add DOM, HTML, network, cookie,
storage, clipboard, or CDP extraction tools.

For screenshot state checks, the capture mainline treats each retained screenshot
as a single VLM/page-state decision point. One coarse state probe must provide
the fields needed for both verification and state advancement, such as state,
visible search keyword, keyword match, confidence, and reason. Do not add a
second yes/no visual assertion over the same screenshot to decide how to advance
the worker.

For external VLM grounding, copy:

```bash
cp local/midscene-computer.env.example local/midscene-computer.env
```

Then fill `local/midscene-computer.env` with `MIDSCENE_MODEL_*` values. The
real env file is local-only and ignored by git. Leave `MIDSCENE_RUN_DIR` empty
unless this machine needs a custom run directory; the launcher defaults it to
`local/midscene-run` under the repository root.

Only this README and `.gitkeep` are tracked. Recreate directory contents on each
machine after cloning, then log in to Taobao manually in that Chrome profile.
