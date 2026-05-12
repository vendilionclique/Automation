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

from modules.utils import ensure_dir
from modules.visual_capture import screenshot_path_for


TAOBAO_HOME = "https://www.taobao.com/"


@dataclass
class MidsceneComputerConfig:
    window_width: int = 1600
    window_height: int = 1000
    max_scrolls_per_keyword: int = 2
    page_load_wait: float = 8.0
    min_rows_per_keyword: int = 5
    confidence_threshold: float = 0.80
    screenshot_retention: bool = True
    screenshot_prefixes: List[str] = field(default_factory=lambda: ["initial", "results", "scroll_1"])
    model_enabled: bool = False
    model_name: str = ""
    model_family: str = ""
    model_base_url: str = ""
    model_api_key_env: str = "MIDSCENE_MODEL_API_KEY"
    allow_midscene_act: bool = False
    allow_midscene_query: bool = False
    final_extraction_owner: str = "codex"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MidsceneComputerRequest:
    run_id: str
    keyword: str
    start_url: str
    evidence_dir: str
    screenshot_path: str
    request_path: str
    instruction_path: str
    status: str = "needs_midscene_computer"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def midscene_computer_config_from_settings(config) -> MidsceneComputerConfig:
    visual_section = "VISUAL_CAPTURE"
    section = "MIDSCENE_COMPUTER"
    model_section = "MIDSCENE_MODEL"
    return MidsceneComputerConfig(
        window_width=config.getint(section, "window_width", fallback=1600),
        window_height=config.getint(section, "window_height", fallback=1000),
        max_scrolls_per_keyword=config.getint(section, "max_scrolls_per_keyword", fallback=2),
        page_load_wait=config.getfloat(section, "page_load_wait", fallback=8.0),
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
        allow_midscene_act=config.getboolean(model_section, "allow_midscene_act", fallback=False),
        allow_midscene_query=config.getboolean(model_section, "allow_midscene_query", fallback=False),
        final_extraction_owner=config.get(model_section, "final_extraction_owner", fallback="codex"),
    )


def write_midscene_computer_request(
    run_id: str,
    keyword: str,
    evidence_dir: str,
    config: MidsceneComputerConfig,
    manual_state: Optional[str] = None,
) -> MidsceneComputerRequest:
    ensure_dir(evidence_dir)
    screenshot_path = screenshot_path_for(evidence_dir, keyword)
    request_path = os.path.join(evidence_dir, "midscene_computer_request.json")
    instruction_path = os.path.join(evidence_dir, "codex_midscene_computer_instructions.md")
    task_dir = os.path.dirname(os.path.dirname(evidence_dir))
    request = MidsceneComputerRequest(
        run_id=run_id,
        keyword=keyword,
        start_url=TAOBAO_HOME,
        evidence_dir=evidence_dir,
        screenshot_path=screenshot_path,
        request_path=request_path,
        instruction_path=instruction_path,
    )
    payload = {
        **request.to_dict(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "manual_state": manual_state,
        "config": config.to_dict(),
        "for_executor": "Codex App using midscene-computer MCP",
        "action_boundary": {
            "input": "system screenshots only",
            "actions": ["coordinate click", "keyboard input", "keyboard shortcut", "page-level scroll"],
            "product_rows_source": "retained visible screenshots only",
        },
        "model_boundary": {
            "midscene_vlm_enabled": config.model_enabled,
            "midscene_vlm_role": "visual grounding for local UI operations only",
            "midscene_model_name": config.model_name,
            "midscene_model_family": config.model_family,
            "midscene_model_base_url": config.model_base_url,
            "midscene_api_key_env": config.model_api_key_env,
            "allow_midscene_act": config.allow_midscene_act,
            "allow_midscene_query": config.allow_midscene_query,
            "final_extraction_owner": config.final_extraction_owner,
        },
        "forbidden": [
            "browser CDP connection for Taobao mainline collection",
            "DOM/HTML/AX tree/selector map extraction",
            "network/API payload extraction",
            "cookies/storage/localStorage/sessionStorage reads",
            "arbitrary JavaScript eval in the page",
            "automatic login, captcha, SMS, or risk-check handling",
            "Midscene Web bridge or Chrome extension bridge for Taobao mainline collection",
            "Midscene product extraction as the final source of truth",
        ],
        "expected_ingest": {
            "command": (
                f"python harness.py visual-ingest {json.dumps(task_dir, ensure_ascii=False)} "
                f"--keyword {json.dumps(keyword, ensure_ascii=False)} "
                "--rows-file <rows.json> "
                f"--screenshot {json.dumps(screenshot_path, ensure_ascii=False)}"
            ),
            "rows_schema": [
                "商品名称",
                "现价",
                "店铺名称",
                "付款人数",
                "地区",
                "截图坐标",
                "识别置信度",
                "识别备注",
            ],
        },
    }
    _write_json(request_path, payload)
    _write_text(instruction_path, build_midscene_computer_instructions(payload))
    return request


def build_midscene_computer_instructions(payload: Dict[str, Any]) -> str:
    cfg = payload["config"]
    model = payload["model_boundary"]
    prefixes = ", ".join(cfg["screenshot_prefixes"])
    manual = f"\nManual page state hint: {payload['manual_state']}" if payload.get("manual_state") else ""
    return f"""# Midscene Computer Pure-Vision Capture

Keyword: {payload["keyword"]}
Start URL: {payload["start_url"]}
Evidence directory: {payload["evidence_dir"]}
Primary screenshot target: {payload["screenshot_path"]}
Suggested screenshot prefixes: {prefixes}{manual}

Use the midscene-computer MCP server from Codex App. The browser must already be
the visible, foreground Chrome window using the dedicated Taobao collection
profile. Midscene computer should only use system screenshots for observation
and system mouse, keyboard, and scroll events for action.

Architecture:
- Codex is the long-running task agent: scheduling, checkpointing, abnormal
  state handling, evidence retention, row extraction/review, ingest, export,
  filtering, DB/LLM/statistical assignment.
- Midscene may use its configured external VLM only for bounded visual
  grounding of UI operations, such as finding the visible Taobao search box or
  search button.
- Final product rows must be based on visible screenshots and reviewed by
  Codex before visual-ingest. Midscene VLM output is an operation aid, not the
  final evidence source.

Midscene model boundary:
- VLM enabled in project config: {model["midscene_vlm_enabled"]}
- Model name: {model["midscene_model_name"] or "<local env>"}
- Model family: {model["midscene_model_family"] or "<local env>"}
- API key env: {model["midscene_api_key_env"]}
- allow_midscene_act: {model["allow_midscene_act"]}
- allow_midscene_query: {model["allow_midscene_query"]}

Safety boundary:
- Do not connect to browser CDP for this Taobao mainline flow.
- Do not read DOM, HTML, AX tree, selector maps, cookies, storage, network
  payloads, or page source.
- Do not use JavaScript eval in the page.
- Do not use Midscene Web bridge, Chrome extension bridge, or structural
  aiQuery extraction as the final product data source.
- Prefer single-step Midscene tools (`take_screenshot`, `tap`, `input`,
  `keyboardpress`, `scroll`, `assert`) over long autonomous `act` chains.
- If login, captcha, SMS, risk verification, pop-up blocking, white skeleton,
  or an unusual account state appears, stop and retain a screenshot.

Steps:
1. Confirm Chrome is foreground and on the dedicated profile. If needed, ask a
   human to start local/start_taobao_visual_chrome.sh and log in manually.
   The startup script should be run once per session; if Chrome is already
   running with the dedicated profile, reuse that window instead of opening a
   new tab.
2. Use system screenshot observation to verify initialization before any
   keyword work:
   - Chrome is the visible foreground app.
   - The page is in the dedicated Taobao collection profile.
   - The window is large enough for dense listing capture, usually about
     {cfg["window_width"]}x{cfg["window_height"]}.
   - The visible page zoom/layout shows multiple product cards per row. If the
     page is too zoomed in, ask a human to adjust browser zoom before continuing.
3. Navigate to Taobao home only through normal visible browser controls when
   needed, then focus the visible Taobao search input.
4. Type the keyword exactly as:
   {payload["keyword"]}
   Then trigger the visible search action.
5. Wait about {cfg["page_load_wait"]} seconds for visible content to settle.
6. Save the visible results screenshot to the primary screenshot target above.
7. If visible listings are present, scroll at most {cfg["max_scrolls_per_keyword"]}
   times with page-level scroll input and save additional screenshots in the
   same evidence directory.
8. Codex should identify at least {cfg["min_rows_per_keyword"]} visible product
   rows when possible from visible screenshots, then write rows JSON and
   ingest with harness.py visual-ingest.
   Do not pass `--retain-screenshot` for normal successful extraction; the
   ingest step keeps screenshots only when extraction needs review. Retain
   abnormal-state screenshots such as login, captcha, risk, or white skeleton.

Rows JSON shape:
```json
{{
  "rows": [
    {{
      "商品名称": "",
      "现价": "",
      "店铺名称": "",
      "付款人数": "",
      "地区": "",
      "截图坐标": "",
      "识别置信度": 0.0,
      "识别备注": ""
    }}
  ]
}}
```
"""


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


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
