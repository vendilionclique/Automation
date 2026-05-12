# Project-Level Agent Setup

This repository keeps project-specific agent knowledge and Midscene MCP launch details in the repo, while machine-specific secrets stay local.

## What Is Project-Level

- `.agents/skills/taobao-visual-collection/SKILL.md`: repo-specific workflow skill.
- `.agents/mcp/midscene-computer.json`: portable MCP definition for import-capable agents.
- `.cursor/mcp.json`: Cursor project MCP configuration.
- `scripts/start_midscene_computer_mcp.ps1`: Windows Midscene computer MCP launcher.
- `scripts/sync_agent_project_config.ps1`: one-command Codex sync for a new machine.

## What Remains Machine-Local

- `local/midscene-computer.env`: VLM key and local run directory.
- `config/settings.ini`: local ledger path and service credentials.
- Local Chrome profile and Taobao login state.

## New Machine Bootstrap

```powershell
npm ci
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_agent_project_config.ps1
python harness.py setup
```

For Codex, the sync script writes the `midscene-computer` MCP server into `~/.codex/config.toml` and copies the project skill into `~/.codex/skills/taobao-visual-collection`.

For Cursor, open the repository and use the tracked `.cursor/mcp.json`. If Cursor does not expand `${workspaceFolder}` in MCP args on a specific version, replace that one arg with the absolute path to `scripts\start_midscene_computer_mcp.ps1`.
