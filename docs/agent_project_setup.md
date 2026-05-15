# Project-Level Agent Setup

This repository keeps project-specific agent knowledge and Midscene MCP launch details in the repo, while machine-specific secrets stay local.

## What Is Project-Level

- `.agents/skills/taobao-visual-collection/SKILL.md`: repo-specific workflow skill.
- `.agents/mcp/midscene-computer.json`: macOS MCP definition for import-capable agents.
- `.cursor/mcp.json`: macOS Cursor project MCP configuration.
- `local/start_midscene_computer_mcp.sh`: macOS Midscene computer MCP launcher.
- `scripts/sync_agent_project_config.sh`: macOS Codex sync for MCP and tool approvals.
- `scripts/check_taobao_visual_cron_permissions.sh`: macOS cron preflight for process enumeration and screenshot persistence.
- `scripts/*.ps1`: Windows helpers retained for future/experimental work; Windows is not part of the current Taobao collection mainline.

## What Remains Machine-Local

- `local/midscene-computer.env`: VLM key and local run directory.
- `config/settings.ini`: local ledger path and service credentials.
- Local Chrome profile and Taobao login state.

`local/midscene-computer.env.example` and the sync scripts default the Midscene
computer external VLM to Zhipu `glm-4.6v-flashx` with
`MIDSCENE_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4` and
`MIDSCENE_MODEL_FAMILY=glm-v`. Keep the API key machine-local in
`local/midscene-computer.env`.

## New Machine Bootstrap

macOS:

```bash
npm ci
bash scripts/sync_agent_project_config.sh
bash scripts/check_taobao_visual_cron_permissions.sh
python harness.py setup
```

Windows is future/experimental for this workflow and is not part of the current business mainline:

```powershell
npm ci
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_agent_project_config.ps1
python harness.py setup
```

For Codex, the sync scripts write the `midscene-computer` MCP server into
`~/.codex/config.toml`, mark the Taobao visual workflow's Midscene computer
tools as `approval_mode = "approve"` for unattended cron/session runs, and
leave the workflow skill repo-local at
`.agents/skills/taobao-visual-collection/SKILL.md`.

Do not duplicate this Taobao workflow skill into `~/.codex/skills`. The project
skill is the source of truth; a global copy can drift and cause future sessions
to follow stale capture-worker rules.

The sync scripts also create a Codex profile named `taobao_visual_cron`:

```toml
[profiles.taobao_visual_cron]
model = "gpt-5.5"
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

They also create a non-interactive profile named `taobao_visual_extract` for
short-lived Codex extract workers:

```toml
[profiles.taobao_visual_extract]
model = "gpt-5.5"
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

Both Taobao profiles are configured this way so unattended collection and
extract workers do not pause on shell, MCP, or related tool approval prompts.

Run unattended Taobao visual collection supervisor/cron sessions with
`taobao_visual_cron`, or with an equivalent app-level setting. Ordinary
sandboxed execution is not sufficient for that workflow on macOS because it can
block `pgrep`/`ps` process enumeration and `screencapture` evidence persistence.
Those failures can make the Chrome launcher misread an already-running browser
as missing, then attempt to start a duplicate profile and surface misleading
Chrome crash reports.

The pre-approved Midscene tool set is limited to the visual workflow surface:
display listing/connection, system screenshots, coordinate mouse actions,
keyboard input, scroll, assertion, and disconnect. It does not grant DOM, HTML,
network, cookie, storage, or CDP extraction capabilities.

Cron automations for this workflow should request the latest GPT-5.5 model by
default. Codex extract dispatch may use `codex exec -p taobao_visual_extract`
to start a bounded worker that reads one keyword-level screenshot contract,
writes `rows_result.json`, runs `visual-apply-extracted-rows`, and exits. This
is not a Codex App UI chat session and it will not appear as a visible
conversation in the app. Python scheduler/launcher code may start that
short-lived non-interactive worker, but it cannot create Codex App UI-visible
chat sessions; visible supervisor conversations should be started by the app,
human operator, or a future CC-connect/Feishu entrypoint.

If a run asks for Midscene MCP tool approval one-by-one, or if shell
process/screenshot checks fail under ordinary sandboxing, rerun the sync script,
use the `taobao_visual_cron` profile, and restart Codex if needed before relying
on unattended collection.

Taobao visual cron runs should also speak Chinese to the user by default:
progress updates, blockers, final summaries, and inbox item copy should be
Chinese. Keep machine-readable JSON schema keys, CLI flags, file paths, and
status identifiers unchanged when the project expects English identifiers.

Create Taobao visual cron jobs through the Codex App Automations feature, not
through system-level substitutes such as `launchd`, `nohup`, background shell
jobs, or ad hoc `codex exec`. The app automation path gives the user a visible
automation entry, a dedicated conversation, and status tracking. If the Codex
automation creation/update tool is unavailable in the current session, report
that limitation rather than starting an invisible system cron.

That cron rule is about the daily/supervisor entrypoint. It does not forbid the
local extract dispatcher from using `codex exec` as a leaf worker after capture
screenshots already exist.

Do not use the separate Computer Use plugin as a fallback inside Taobao visual
cron. The intended control layer is Midscene computer MCP only. If macOS opens
Accessibility/System Settings or any GUI automation permission panel, stop the
session and report setup drift instead of clicking through permission screens.

`approval_mode` is a Codex MCP client setting, not a Midscene server setting.
Codex accepts `auto`, `prompt`, and `approve`; use `approve` for trusted local
Midscene computer tools in unattended collection.

For Cursor on macOS, open the repository and use the tracked `.cursor/mcp.json`. If Cursor does not expand `${workspaceFolder}` in MCP args on a specific version, replace that one arg with the absolute path to `local/start_midscene_computer_mcp.sh`.

For lightweight local checks before committing config/script changes:

```bash
scripts/check_portable_config.sh
```
