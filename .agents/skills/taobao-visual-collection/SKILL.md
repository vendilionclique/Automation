---
name: taobao-visual-collection
description: "Use for this repository's Taobao MTG visual price collection workflow: daily/session planning, Midscene computer pure-vision execution, Codex extract workers, deterministic rows apply/export, abnormal-state handling, and preserving the no-DOM/no-network/no-storage boundary."
---

# Taobao Visual Collection

Use this skill for project-specific Taobao collection work in this repository. It is not a general spreadsheet or browser skill.

## Boundaries

- Mainline collection is local Chrome with real login state, human-in-the-loop for login/captcha/risk states, and Midscene computer pure-vision actions.
- Allowed inputs/actions: system screenshots, visible-page reasoning, coordinate click, keyboard input, keyboard shortcut, page-level scroll.
- Forbidden for Taobao collection: DOM/HTML extraction, network/interface extraction, cookies/storage reads, JS eval, DOMSnapshot/AX tree, selector maps, hidden fields, CDP/full-page screenshot as the mainline.
- Product fields must come from retained visible screenshots, not page structure.
- Do not automate login, captcha, security verification, cart/favorite mutation, checkout, reward claiming, or any account-state-changing action.
- For Taobao visual cron, do not fall back to the separate Computer Use plugin/tools. Use only Midscene computer MCP/system screenshot tools for foregrounding and page actions. If macOS opens Accessibility/System Settings or permission panels, stop and report setup drift instead of clicking through them.

## Core Workflow

1. Read `AGENTS.md` for current project policy and status.
2. Run `python harness.py setup` when environment readiness is unclear.
3. Use `python harness.py visual-plan-day` for ledger-driven planning; `visual-auto-tick` is retained as a compatibility helper, not the current documented mainline.
4. Prefer `python harness.py visual-heartbeat --mode prepare|dispatch|sync|all` for the local short-lived scheduler heartbeat. It may prepare contracts and return worker commands, but it must not open Chrome or touch Taobao.
5. Use `python harness.py visual-control status|pause|resume|stop|cooldown|lock|unlock --plan-id ...` as the Codex/human supervisor control plane. Codex should not be the long-running heartbeat.
6. Use `python harness.py visual-session-run <plan_id> --session <N>` when a bounded session contract must be prepared directly.
7. The capture worker owns session-level screenshot capture. `python harness.py visual-capture-worker --contract <...>` must use Midscene computer MCP for real bounded capture; if Midscene is unavailable, it writes `real_not_available` instead of simulating success.
8. Codex extract worker owns screenshot-to-rows recognition in the current mainline. Use `python harness.py visual-codex-extract-prepare --plan-id <plan_id> --session <N>` to create keyword-level extract contracts, then `python harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session <N>` to return launch advice or add `--start` to run short-lived non-interactive `codex exec` workers. Each worker writes `rows_result.json`; deterministic persistence is `python harness.py visual-apply-extracted-rows --request <extract_request.json>`. Do not call this deterministic apply step a second extract worker.
9. Before declaring Chrome unavailable, bring the dedicated Chrome profile to the foreground with normal visual/system switching. Use the launcher only after visual switching fails.
10. Execute generated session worker requests with Midscene computer MCP only if the MCP tools are callable in the current agent app. Cron automation must use the latest available GPT-5.5 model and the `taobao_visual_cron` Codex profile, or equivalent non-sandboxed/screen-recording permissions, unless a human explicitly says otherwise.
11. Stop safely on login/captcha/security/risk/white-skeleton/continuous abnormal states; record session and keyword results instead of retrying aggressively.
12. Keep DB/LLM/statistical/final assignment decoupled from the capture worker, Codex extract worker, and deterministic rows apply step.

## Double Worker Memory

- Current architecture is four-layer: local deterministic heartbeat, session-level capture worker, asynchronous Codex extract worker, and non-resident Codex supervisor.
- Heartbeat is short-lived and recoverable from files. Do not rely on a Codex/chat session as the daily scheduler.
- Capture worker writes screenshots, `keyword_result.json`, `session_worker_result.json`, capture events, and tile summaries. It must not output final product rows.
- Capture worker must not have a simulated success route. A run without callable Midscene computer MCP is `real_not_available` / setup drift, not `captured`.
- Codex extract worker reads captured screenshots and writes `rows_result.json` from visible pixels only. `visual-apply-extracted-rows` then writes `rows_pending.json`, raw rows, Excel, manifest updates, and keyword-level screenshot cleanup. Neither step may operate the browser.
- Row dedupe belongs to deterministic apply/storage code, not to the visual extract worker's judgment and not to later DB/LLM filtering. Hard dedupe skips exact duplicate `搜索关键词` + `商品名称` + `现价` + `店铺名称`. Fuzzy dedupe runs only after same keyword and same normalized price, then requires store-name similarity >= 0.70 and title similarity >= 0.95 by script-side normalized Levenshtein similarity. If title similarity is below threshold, keep the row as another same-store same-price listing. Do not add MTG token special cases here; judge from the whole normalized strings and keep examples in apply/ingest results.
- Codex supervisor intervenes through `visual-control` only: status review, pause/resume/stop/cooldown/lock/unlock, exception judgment, and human communication.
- Screenshot deletion is keyword-granular: delete only after keyword ingest succeeds and quality is acceptable; retain screenshots for low confidence, abnormal states, or human/supervisor review.

## VLM Supply Memory

- The current limiting factor for pure-vision capture is stable real-time VLM
  grounding, not browser control. Midscene computer provides system screenshot,
  coordinate click, keyboard input, and scroll actions; locating the Taobao
  search box, confirming result pages, recognizing abnormal states, and deciding
  visible-screen progress all require a reliable VLM.
- `glm-4.6v-flash` is the tracked free/default development fallback after
  `glm-4.6v-flashx` quota was exhausted. It can be useful for local testing, but
  observed free-tier `429` traffic pressure means it must not be treated as the
  unattended production SLA. If it fails, stop as `needs_review`/`cooldown` and
  retain evidence instead of pretending capture succeeded.
- Do not make a long-lived Codex chat session the real-time visual controller.
  Codex remains the supervisor/control-plane and the short-lived screenshot
  extract worker. It may judge low-frequency abnormal states, but it should not
  participate in every ordinary click/scroll decision.
- Avoid the dual-brain loop where Midscene has a VLM but Codex makes each live
  click decision; it adds latency, synchronization cost, and failure surface.
- DeepSeek local VLMs are not the preferred GUI grounding route. DeepSeek-VL2
  tiny may be a research backup, but it needs custom serving, coordinate parsing,
  prompts, and regression tests. Janus-Pro is not recommended for dense Taobao
  UI coordinate grounding. If testing local VLM on the M4/16GB Mac, prefer small
  Qwen2.5-VL/Qwen3-VL or UI-TARS-style candidates first; for production, prefer
  a stable paid cloud VLM key connected to Midscene.

## Cron Communication

- Taobao visual cron runs must communicate with the user in Chinese by default: progress updates, blockers, final summaries, and inbox item copy should all be Chinese.
- Keep machine-readable artifacts and schema keys unchanged when the project expects English identifiers, such as `status`, `rough_state`, `stop_reason`, JSON field names, CLI flags, and file paths.
- If a human explicitly asks for another language in a specific thread, follow that request for that thread only.
- Taobao visual cron must be created through the Codex App Automations feature so it appears in the app automation list and has a dedicated trackable conversation. Do not simulate app automations with `launchd`, `nohup`, background shell jobs, or ad hoc `codex exec` unless a human explicitly asks for a system-level test process.
- If the Codex App automation creation/update tool is not available in the current session, stop and report that limitation instead of starting an invisible system cron.

## Chrome Foreground Rule

- Seeing Codex, Cursor, Terminal, or another app in the current screenshot is not a blocker. It usually only means Chrome is not foreground.
- First try normal visual/system switching: taskbar/Dock click, Alt-Tab on Windows, or Cmd-Tab on macOS. A user clicking Codex to check progress is not Chrome instability.
- If Chrome is still not visible after visual switching, run the platform launcher. The launcher must reuse an existing logged-in Chrome window when any Chrome is already running; it must not open duplicate collection windows or restart a new profile just because Codex was foreground.

Windows is future/experimental for this workflow; the current Taobao collection mainline is macOS.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_taobao_visual_chrome.ps1
```

macOS:

```bash
bash scripts/start_taobao_visual_chrome.sh
```

- Only stop for `chrome_start_failed` after the launcher fails or Chrome still cannot be foregrounded.
- Once Chrome is foreground, continue from the visible page. Do not treat the previous Codex foreground screenshot as page state.

## Codex/Midscene Permission Setup

- Unattended cron/session runs must pre-approve the Midscene computer MCP server and its bounded visual tools. On macOS, run `bash scripts/sync_agent_project_config.sh`. Windows PowerShell helpers are retained for future/experimental work and are not part of the current business mainline.
- The same sync scripts create Codex profiles named `taobao_visual_cron` and `taobao_visual_extract` with `model = "gpt-5.5"`, `sandbox_mode = "danger-full-access"`, and `approval_policy = "never"`. Run Taobao visual cron jobs with `taobao_visual_cron`; run short-lived Codex extract workers with `taobao_visual_extract`. Both profiles are intended to avoid unattended automation pausing for tool approvals.
- Codex extract dispatch must use CLI options supported by the bundled Codex CLI: use `-c sandbox_mode=...` and `-c approval_policy=...`, add `--ignore-rules` by default, attach screenshots with `-i`, and pass the worker prompt through stdin instead of as the final CLI argument so image varargs do not consume the prompt.
- On macOS, run `bash scripts/check_taobao_visual_cron_permissions.sh` from the repository root before relying on an unattended cron. It must be able to see Chrome with `pgrep` when Chrome is running and save a system screenshot with `screencapture`.
- The sync scripts write Codex-side `default_tools_approval_mode = "approve"` and per-tool `approval_mode = "approve"` for the actual Midscene tool names: `computer_connect`, `computer_disconnect`, `computer_list_displays`, `ListDisplays`, `take_screenshot`, `Tap`, `DoubleClick`, `RightClick`, `MouseMove`, `Input`, `Scroll`, `KeyboardPress`, `DragAndDrop`, `ClearInput`, `act`, and `assert`.
- If a cron worker still asks for these approvals, or if shell `pgrep`/`screencapture` fails under ordinary sandboxing, treat it as project setup drift: rerun the sync script, use the `taobao_visual_cron` profile or equivalent app setting, and restart Codex if the app cached MCP settings. Do not proceed by manually approving one tool at a time for unattended collection.
- If the run reaches macOS Accessibility/System Settings, or any prompt asking for GUI automation/screen recording permission, stop the session as `needs_review`/`setup_drift`. Do not keep switching windows or use Computer Use as a workaround.

## Project Files To Check

- `config/settings.ini`: machine-local secrets and ledger path; ignored by git.
- `local/midscene-computer.env`: machine-local Midscene VLM key; ignored by git.
- `scripts/start_taobao_visual_chrome.ps1`: future/experimental Windows launcher/focus helper for the dedicated Taobao Chrome profile.
- `scripts/start_taobao_visual_chrome.sh`: macOS launcher/focus helper for the dedicated Taobao Chrome profile.
- `scripts/start_midscene_computer_mcp.ps1`: future/experimental Windows stdio launcher for Midscene MCP.
- `scripts/check_taobao_visual_cron_permissions.sh`: macOS preflight for process enumeration and screenshot persistence in the cron execution context.
- `scripts/sync_agent_project_config.sh`: macOS Codex MCP/skill sync with Midscene tool pre-approval.
- `scripts/sync_agent_project_config.ps1`: future/experimental Windows Codex sync helper.
- `.cursor/mcp.json`: project-level Cursor MCP declaration.
- `.agents/mcp/midscene-computer.json`: portable MCP declaration for agent apps/import scripts.
- `data/tasks/<plan_id>/`: durable plan/session/evidence state; ignored by git.

## New Machine Setup

Windows is future/experimental for this workflow. From the repository root on macOS:

```bash
npm ci
bash scripts/sync_agent_project_config.sh
bash scripts/check_taobao_visual_cron_permissions.sh
python harness.py setup
```

Then fill `local/midscene-computer.env` with the local VLM key if it was newly created, start/login the dedicated Taobao Chrome profile manually, and restart the agent app if it caches MCP server lists.
