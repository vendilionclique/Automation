"""
Midscene computer request artifacts for pure-vision desktop collection.

This module does not control the browser directly. It prepares bounded,
auditable instructions for Codex App to execute through a midscene-computer MCP
server: system screenshot in, coordinate mouse/keyboard/scroll out.
"""
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.page_sampling import PageSamplingConfig, estimate_tile_scroll_distance
from modules.utils import ensure_dir
from modules.visual_capture import screenshot_path_for


TAOBAO_HOME = "https://www.taobao.com/"

OPERATIONAL_STATES = [
    "visible_results",
    "popup_closeable",
    "empty_result",
    "login_required",
    "captcha_or_risk",
    "white_skeleton",
    "page_not_loaded",
    "unknown",
]

HARD_STOP_STATES = [
    "login_required",
    "captcha_or_risk",
    "white_skeleton",
    "page_not_loaded",
    "unknown",
]


@dataclass
class MidsceneComputerConfig:
    window_width: int = 1600
    window_height: int = 1000
    max_scrolls_per_keyword: int = 2
    page_load_wait: float = 8.0
    session_keyword_limit: int = 3
    keyword_timeout_seconds: int = 180
    mcp_request_timeout_seconds: int = 240
    consecutive_abnormal_stop: int = 2
    min_rows_per_keyword: int = 5
    confidence_threshold: float = 0.80
    screenshot_retention: bool = True
    screenshot_prefixes: List[str] = field(default_factory=lambda: ["initial", "results", "scroll_1"])
    model_enabled: bool = False
    model_name: str = ""
    model_family: str = ""
    model_base_url: str = ""
    model_api_key_env: str = "MIDSCENE_MODEL_API_KEY"
    reasoning_enabled: bool = False
    temperature: float = 0.6
    allow_midscene_act: bool = True
    allow_midscene_query: bool = False
    final_extraction_owner: str = "codex"
    micro_pause_short: str = "0.2,0.8,0.90"
    micro_pause_medium: str = "0.8,1.5,0.08"
    micro_pause_long: str = "1.5,2.5,0.02"
    inter_keyword_pause_min: float = 180.0
    inter_keyword_pause_max: float = 420.0
    detail_page_peek_probability: float = 0.08
    cart_or_favorites_peek_probability: float = 0.03
    allow_cart_or_favorites_peek: bool = True
    allow_claim_rewards: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def midscene_computer_config_from_settings(config) -> MidsceneComputerConfig:
    visual_section = "VISUAL_CAPTURE"
    section = "MIDSCENE_COMPUTER"
    model_section = "MIDSCENE_MODEL"
    behavior_section = "VISUAL_BEHAVIOR"
    return MidsceneComputerConfig(
        window_width=config.getint(section, "window_width", fallback=1600),
        window_height=config.getint(section, "window_height", fallback=1000),
        max_scrolls_per_keyword=config.getint(section, "max_scrolls_per_keyword", fallback=2),
        page_load_wait=config.getfloat(section, "page_load_wait", fallback=8.0),
        session_keyword_limit=max(1, config.getint(section, "session_keyword_limit", fallback=3)),
        keyword_timeout_seconds=max(30, config.getint(section, "keyword_timeout_seconds", fallback=180)),
        mcp_request_timeout_seconds=max(
            30,
            config.getint(section, "mcp_request_timeout_seconds", fallback=240),
        ),
        consecutive_abnormal_stop=max(
            1, config.getint(section, "consecutive_abnormal_stop", fallback=2)
        ),
        min_rows_per_keyword=config.getint(section, "min_rows_per_keyword", fallback=5),
        confidence_threshold=config.getfloat(visual_section, "confidence_threshold", fallback=0.80),
        screenshot_retention=config.getboolean(visual_section, "screenshot_retention", fallback=True),
        screenshot_prefixes=_split_csv(
            config.get(section, "screenshot_prefixes", fallback="initial,results,scroll_1")
        ),
        model_enabled=config.getboolean(model_section, "enabled", fallback=False),
        model_name=config.get(model_section, "model_name", fallback=""),
        model_family=config.get(model_section, "model_family", fallback=""),
        model_base_url=config.get(model_section, "base_url", fallback=""),
        model_api_key_env=config.get(model_section, "api_key_env", fallback="MIDSCENE_MODEL_API_KEY"),
        reasoning_enabled=config.getboolean(
            model_section, "reasoning_enabled", fallback=False
        ),
        temperature=config.getfloat(model_section, "temperature", fallback=0.6),
        allow_midscene_act=config.getboolean(model_section, "allow_midscene_act", fallback=True),
        allow_midscene_query=config.getboolean(model_section, "allow_midscene_query", fallback=False),
        final_extraction_owner=config.get(model_section, "final_extraction_owner", fallback="codex"),
        micro_pause_short=config.get(behavior_section, "micro_pause_short", fallback="0.2,0.8,0.90"),
        micro_pause_medium=config.get(behavior_section, "micro_pause_medium", fallback="0.8,1.5,0.08"),
        micro_pause_long=config.get(behavior_section, "micro_pause_long", fallback="1.5,2.5,0.02"),
        inter_keyword_pause_min=config.getfloat(
            behavior_section, "inter_keyword_pause_min", fallback=180.0
        ),
        inter_keyword_pause_max=config.getfloat(
            behavior_section, "inter_keyword_pause_max", fallback=420.0
        ),
        detail_page_peek_probability=config.getfloat(
            behavior_section, "detail_page_peek_probability", fallback=0.08
        ),
        cart_or_favorites_peek_probability=config.getfloat(
            behavior_section, "cart_or_favorites_peek_probability", fallback=0.03
        ),
        allow_cart_or_favorites_peek=config.getboolean(
            behavior_section, "allow_cart_or_favorites_peek", fallback=True
        ),
        allow_claim_rewards=config.getboolean(
            behavior_section, "allow_claim_rewards", fallback=False
        ),
    )


def write_midscene_session_worker_contract(
    run_id: str,
    session_index: int,
    task_dir: str,
    session_dir: str,
    records: List[Dict[str, Any]],
    config: MidsceneComputerConfig,
    sampling_config: Optional[PageSamplingConfig] = None,
    manual_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Write the bounded small-session capture-worker contract."""
    ensure_dir(session_dir)
    sampling_config = sampling_config or PageSamplingConfig()
    calibration = estimate_tile_scroll_distance(
        screen_height=config.window_height,
        config=sampling_config,
    )
    contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
    instructions_path = os.path.join(session_dir, "midscene_session_worker_instructions.md")
    result_path = os.path.join(session_dir, "session_worker_result.json")
    keyword_tasks = []
    for index, record in enumerate(records, start=1):
        keyword = record.get("keyword", "")
        evidence_dir = record.get("evidence_dir") or os.path.join(
            task_dir, "evidence", _safe_keyword_dir(keyword)
        )
        ensure_dir(evidence_dir)
        task_id = (
            record.get("task_id")
            or record.get("extra", {}).get("task_id")
            or f"{run_id}-s{int(session_index):02d}-k{index:03d}"
        )
        keyword_result_path = os.path.join(evidence_dir, "keyword_result.json")
        primary_screenshot_path = screenshot_path_for(evidence_dir, keyword)
        abnormal_screenshot_path = os.path.join(evidence_dir, "abnormal_state.png")
        capture_plan = {
            "start_url": TAOBAO_HOME,
            "entry_mode": "taobao_home_visible_search_box",
            "max_tiles_per_keyword": sampling_config.max_tiles_per_keyword,
            "target_listings_per_keyword": sampling_config.target_listings_per_keyword,
            "tile_scroll_distance_px": calibration["tile_scroll_distance_px"],
            "tile_id_pattern": "tile_00, tile_01, ...",
            "tile_path_pattern": os.path.join(evidence_dir, "tile_<NN>.png"),
            "primary_screenshot_path": primary_screenshot_path,
            "abnormal_screenshot_path": abnormal_screenshot_path,
            "timeout_seconds": config.keyword_timeout_seconds,
        }
        keyword_tasks.append(
            {
                "task_id": task_id,
                "keyword_index": index,
                "capture_plan": capture_plan,
                "result_path": keyword_result_path,
                "abnormal_screenshot_path": abnormal_screenshot_path,
                # Compatibility fields consumed by existing sync/review code.
                "index": index,
                "keyword": keyword,
                "status": record.get("status", ""),
                "evidence_dir": evidence_dir,
                "keyword_result_path": keyword_result_path,
                "primary_screenshot_path": primary_screenshot_path,
                "tile_path_pattern": os.path.join(evidence_dir, "tile_<NN>.png"),
            }
        )

    payload = {
        "schema": "taobao_visual_capture_worker_v1",
        "compatible_with": ["taobao_midscene_session_worker_v1"],
        "run_id": run_id,
        "session_index": int(session_index),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task_dir": task_dir,
        "session_dir": session_dir,
        "manual_state": manual_state or "",
        "start_url": TAOBAO_HOME,
        "worker_role": "visual_capture_worker",
        "session_result_path": result_path,
        "instructions_path": instructions_path,
        "keyword_count": len(keyword_tasks),
        "keyword_limit": len(keyword_tasks),
        "configured_keyword_limit": config.session_keyword_limit,
        "keyword_tasks": keyword_tasks,
        "config": config.to_dict(),
        "visual_behavior": {
            "micro_pause_distribution": {
                "short": config.micro_pause_short,
                "medium": config.micro_pause_medium,
                "long": config.micro_pause_long,
            },
            "inter_keyword_pause_seconds": [
                config.inter_keyword_pause_min,
                config.inter_keyword_pause_max,
            ],
            "detail_page_peek_probability": config.detail_page_peek_probability,
            "cart_or_favorites_peek_probability": config.cart_or_favorites_peek_probability,
            "allow_cart_or_favorites_peek": config.allow_cart_or_favorites_peek,
            "allow_claim_rewards": config.allow_claim_rewards,
        },
        "operational_states": OPERATIONAL_STATES,
        "hard_stop_states": HARD_STOP_STATES,
        "hard_stop_policy": {
            "stop_immediately_on": [
                "login_required",
                "captcha_or_risk",
                "account_state_changed_or_unusual",
            ],
            "stop_after_consecutive_abnormal": config.consecutive_abnormal_stop,
            "timeout_per_keyword_seconds": config.keyword_timeout_seconds,
            "mcp_request_timeout_seconds": config.mcp_request_timeout_seconds,
            "retain_abnormal_screenshots": True,
        },
        "action_boundary": {
            "autonomy": "small_session_only",
            "input": "system screenshots only",
            "actions": ["coordinate click", "keyboard input", "keyboard shortcut", "page-level scroll"],
            "allowed_act_scope": "complete bounded keyword capture tasks in this session only",
            "forbidden_strategy_scope": "no daily planning, no cross-session routing, no final exception strategy",
            "product_rows_source": "Codex-reviewed visible screenshots only",
        },
        "model_boundary": {
            "midscene_vlm_enabled": config.model_enabled,
            "midscene_vlm_role": "visual grounding and coarse operational state only",
            "midscene_model_name": config.model_name,
            "midscene_model_family": config.model_family,
            "midscene_model_base_url": config.model_base_url,
            "midscene_api_key_env": config.model_api_key_env,
            "midscene_model_reasoning_enabled": config.reasoning_enabled,
            "midscene_model_temperature": config.temperature,
            "allow_midscene_act": config.allow_midscene_act,
            "allow_midscene_query": config.allow_midscene_query,
            "final_extraction_owner": config.final_extraction_owner,
            "forbidden_outputs": [
                "final product rows",
                "price trust decisions",
                "business filtering",
                "statistical assignment",
                "cross-session recovery strategy",
            ],
        },
        "page_sampling": {
            **sampling_config.to_dict(),
            "calibration": calibration,
            "tile_id_pattern": "tile_00, tile_01, ...",
            "screenshot_capture_command": "/usr/sbin/screencapture -x -D 1 <path>",
            "tile_summary_command": (
                "python harness.py visual-log-tile {run_id} --keyword <keyword> "
                "--tile-id <tile_id> --scroll-distance-px <px> "
                "--rough-state <state> --image <path>"
            ),
        },
        "expected_outputs": {
            "session_worker_result": result_path,
            "keyword_result": {
                "path": "<evidence_dir>/keyword_result.json",
                "schema": {
                    "keyword": "",
                    "status": "",
                    "rough_state": "",
                    "screenshots": [],
                    "abnormal_screenshot": "",
                    "elapsed_seconds": 0,
                    "stop_reason": "",
                    "notes": "",
                },
            },
            "event_logs": [
                os.path.join(task_dir, "task_events.jsonl"),
                os.path.join(task_dir, "tile_summary.jsonl"),
            ],
        },
    }
    _write_json(contract_path, payload)
    _write_text(instructions_path, build_midscene_session_worker_instructions(payload))
    return {
        "ok": True,
        "contract": contract_path,
        "instructions": instructions_path,
        "result": result_path,
        "keyword_count": len(keyword_tasks),
    }


def build_midscene_session_worker_instructions(payload: Dict[str, Any]) -> str:
    states = ", ".join(payload["operational_states"])
    hard_stops = ", ".join(payload["hard_stop_states"])
    keywords = "\n".join(
        f"- {item['index']}. {item['keyword']} -> {item['evidence_dir']}"
        for item in payload["keyword_tasks"]
    )
    return f"""# Midscene Small Session Worker

Run ID: {payload["run_id"]}
Session: {payload["session_index"]}
Task dir: {payload["task_dir"]}
Worker result: {payload["session_result_path"]}

You are the bounded Midscene computer worker for this small session. Complete
only the keyword capture tasks listed below, then stop. Do not create new daily
plans, choose new keywords, retry future sessions, or decide final exception
strategy.

Communication rule:
- Communicate progress, blockers, final summaries, and inbox item copy to the
  user in Chinese by default. Keep machine-readable JSON keys and status values
  exactly as specified below.

Chrome foreground rule:
- If the current screenshot shows Codex, Cursor, Terminal, or another app, do
  not classify that as Taobao/Chrome failure. It usually only means Chrome is
  not foreground.
- First try to bring Chrome forward visually: taskbar/Dock click, Alt-Tab on
  Windows, or Cmd-Tab on macOS. A human clicking Codex to check progress is not
  Chrome instability.
- If Chrome is not visible after visual switching, run the platform launcher
  from the repository root. It reuses any already running logged-in Chrome
  window and must not start a duplicate collection window/profile merely
  because Codex was foreground:
  - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\start_taobao_visual_chrome.ps1`
  - macOS: `bash scripts/start_taobao_visual_chrome.sh`
- After the launcher, take a fresh system screenshot and continue from the
  visible Chrome page. Only stop with `chrome_start_failed` if Chrome still
  cannot be foregrounded.

Keywords:
{keywords or "- none"}

Allowed autonomy:
- You may use bounded `act` or equivalent continuous visual actions to complete
  this small session.
- For each keyword, search Taobao through the visible foreground Chrome window,
  wait for visible content to settle, classify only the coarse operational state,
  save viewport tile screenshots, and write keyword_result.json.
- Continue to the next keyword only after the previous keyword result and tile
  summaries are written.

State boundary:
- Allowed operational states: {states}.
- Hard stop states: {hard_stops}.
- Stop immediately on login, captcha, security/risk verification, or unusual
  account state. Stop after {payload["hard_stop_policy"]["stop_after_consecutive_abnormal"]}
  consecutive abnormal keyword states. Per-keyword timeout is
  {payload["hard_stop_policy"]["timeout_per_keyword_seconds"]} seconds.
- If a hard stop occurs, retain the abnormal screenshot, write
  session_worker_result.json with status `needs_review`, and stop the session.
  Do not use `unknown` merely because Codex was foreground before switching to
  Chrome.

Data boundary:
- Use system screenshots only. Do not read DOM, HTML, AX tree, selector maps,
  cookies, storage, network payloads, page source, or JavaScript-evaluated data.
- Do not fall back to separate Computer Use tools/plugins for Taobao collection.
  If macOS opens Accessibility/System Settings or an automation permission
  panel, stop as setup drift instead of clicking through it.
- Do not output final product rows, price trust decisions, business filtering,
  statistical assignment, or recovery strategy. Codex extract workers will
  review screenshots later, then `visual-apply-extracted-rows` will persist rows.
- Do not add to cart, favorite/unfavorite, claim rewards, checkout, pay, or
  otherwise change account state.

Tile capture:
- Max tiles per keyword: {payload["page_sampling"]["max_tiles_per_keyword"]}.
- Estimated scroll distance per tile:
  {payload["page_sampling"]["calibration"]["tile_scroll_distance_px"]} px.
- After each tile, append the tile summary using:
  `{payload["page_sampling"]["tile_summary_command"]}`.

Expected keyword_result.json shape:
```json
{{
  "keyword": "",
  "status": "captured | needs_review | failed | skipped | real_not_available",
  "rough_state": "",
  "screenshots": [],
  "abnormal_screenshot": "",
  "elapsed_seconds": 0,
  "stop_reason": "",
  "notes": ""
}}
```

Expected session_worker_result.json shape:
```json
{{
  "run_id": "{payload["run_id"]}",
  "session_index": {payload["session_index"]},
  "status": "captured | needs_review | failed | real_not_available",
  "processed_keywords": 0,
  "stop_reason": "",
  "keyword_results": [],
  "notes": ""
}}
```
"""


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _safe_keyword_dir(value: str) -> str:
    keep = []
    for ch in str(value):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    return ("".join(keep).strip("_") or "keyword")[:80]


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _write_text(path: str, text: str) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
