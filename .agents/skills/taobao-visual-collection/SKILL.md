---
name: taobao-visual-collection
description: Use for this repository's Taobao MTG visual price collection workflow: daily/session planning, Midscene computer pure-vision execution, screenshot evidence review, visual-ingest/export, abnormal-state handling, and preserving the no-DOM/no-network/no-storage boundary.
---

# Taobao Visual Collection

Use this skill for project-specific Taobao collection work in this repository. It is not a general spreadsheet or browser skill.

## Boundaries

- Mainline collection is local Chrome with real login state, human-in-the-loop for login/captcha/risk states, and Midscene computer pure-vision actions.
- Allowed inputs/actions: system screenshots, visible-page reasoning, coordinate click, keyboard input, keyboard shortcut, page-level scroll.
- Forbidden for Taobao collection: DOM/HTML extraction, network/interface extraction, cookies/storage reads, JS eval, DOMSnapshot/AX tree, selector maps, hidden fields, CDP/full-page screenshot as the mainline.
- Product fields must come from retained visible screenshots, not page structure.
- Do not automate login, captcha, security verification, cart/favorite mutation, checkout, reward claiming, or any account-state-changing action.

## Core Workflow

1. Read `AGENTS.md` for current project policy and status.
2. Run `python harness.py setup` when environment readiness is unclear.
3. Use `python harness.py visual-plan-day` or `visual-auto-tick` for ledger-driven planning.
4. Use `python harness.py visual-session-run <plan_id> --session <N>` to prepare bounded Midscene worker contracts.
5. Execute the generated session worker request with Midscene computer MCP only if the MCP tools are callable in the current agent app.
6. Stop safely on login/captcha/security/risk/white-skeleton/continuous abnormal states; record session and keyword results instead of retrying aggressively.
7. After screenshots exist, extract rows visually, then run `visual-ingest` and `visual-export`.
8. Keep DB/LLM/statistical/final assignment decoupled from the capture layer.

## Project Files To Check

- `config/settings.ini`: machine-local secrets and ledger path; ignored by git.
- `local/midscene-computer.env`: machine-local Midscene VLM key; ignored by git.
- `scripts/start_midscene_computer_mcp.ps1`: Windows stdio launcher for Midscene MCP.
- `scripts/sync_agent_project_config.ps1`: syncs project MCP/skill into Codex on a new machine.
- `.cursor/mcp.json`: project-level Cursor MCP declaration.
- `.agents/mcp/midscene-computer.json`: portable MCP declaration for agent apps/import scripts.
- `data/tasks/<plan_id>/`: durable plan/session/evidence state; ignored by git.

## New Machine Setup

From the repository root on Windows:

```powershell
npm ci
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_agent_project_config.ps1
python harness.py setup
```

Then fill `local/midscene-computer.env` with the local VLM key if it was newly created, start/login the dedicated Taobao Chrome profile manually, and restart the agent app if it caches MCP server lists.
