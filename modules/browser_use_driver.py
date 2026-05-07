"""
Codex Browser Use MCP handoff helpers.

The Browser Use capability lives in the Codex app, not inside this Python
process. This module therefore does not import the Python ``browser-use``
package, instantiate an LLM client, or require an API key. It only writes a
bounded request artifact that Codex can execute with the configured Browser Use
MCP, then feed back through ``harness.py visual-ingest``.
"""
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from modules.utils import ensure_dir
from modules.visual_capture import screenshot_path_for


TAOBAO_SEARCH = "https://s.taobao.com/search?q={keyword}"


@dataclass
class BrowserUseConfig:
    allowed_domains: List[str] = field(
        default_factory=lambda: ["https://www.taobao.com", "https://s.taobao.com", "*.taobao.com"]
    )
    window_width: int = 1600
    window_height: int = 1000
    max_scrolls_per_keyword: int = 2
    page_load_wait: float = 8.0
    min_rows_per_keyword: int = 5
    confidence_threshold: float = 0.80
    screenshot_retention: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrowserUseRequest:
    run_id: str
    keyword: str
    url: str
    evidence_dir: str
    screenshot_path: str
    request_path: str
    instruction_path: str
    status: str = "needs_codex_browser_use"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def browser_use_config_from_settings(config) -> BrowserUseConfig:
    section = "BROWSER_USE_CAPTURE"
    visual = "VISUAL_CAPTURE"
    return BrowserUseConfig(
        allowed_domains=_split_csv(
            config.get(
                section,
                "allowed_domains",
                fallback="https://www.taobao.com,https://s.taobao.com,*.taobao.com",
            )
        ),
        window_width=config.getint(section, "window_width", fallback=config.getint(visual, "window_width", fallback=1600)),
        window_height=config.getint(section, "window_height", fallback=config.getint(visual, "window_height", fallback=1000)),
        max_scrolls_per_keyword=config.getint(section, "max_scrolls_per_keyword", fallback=2),
        page_load_wait=config.getfloat(section, "page_load_wait", fallback=8.0),
        min_rows_per_keyword=config.getint(section, "min_rows_per_keyword", fallback=5),
        confidence_threshold=config.getfloat(section, "confidence_threshold", fallback=0.80),
        screenshot_retention=config.getboolean(section, "screenshot_retention", fallback=True),
    )


def write_browser_use_request(
    run_id: str,
    keyword: str,
    evidence_dir: str,
    config: BrowserUseConfig,
    manual_state: Optional[str] = None,
) -> BrowserUseRequest:
    ensure_dir(evidence_dir)
    url = TAOBAO_SEARCH.format(keyword=quote(keyword))
    screenshot_path = screenshot_path_for(evidence_dir, keyword)
    request_path = os.path.join(evidence_dir, "browser_use_request.json")
    instruction_path = os.path.join(evidence_dir, "codex_browser_use_instructions.md")
    task_dir = os.path.dirname(os.path.dirname(evidence_dir))
    request = BrowserUseRequest(
        run_id=run_id,
        keyword=keyword,
        url=url,
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
        "for_executor": "Codex app Browser Use MCP",
        "forbidden": [
            "OpenAI API or third-party LLM API calls from project code",
            "Browser Use Cloud",
            "proxy rotation or stealth profile creation",
            "cookies/storage/network/source extraction",
            "automatic login, captcha, SMS, or risk-check handling",
        ],
        "expected_ingest": {
            "command": (
                f"python harness.py visual-ingest {json.dumps(task_dir, ensure_ascii=False)} "
                f"--keyword {json.dumps(keyword, ensure_ascii=False)} "
                "--rows-file <rows.json> "
                f"--screenshot {json.dumps(screenshot_path, ensure_ascii=False)} "
                "--retain-screenshot"
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
    _write_text(instruction_path, build_browser_use_instructions(payload))
    return request


def build_browser_use_instructions(payload: Dict[str, Any]) -> str:
    cfg = payload["config"]
    return f"""# Codex Browser Use MCP Capture

Keyword: {payload["keyword"]}
URL: {payload["url"]}
Screenshot target: {payload["screenshot_path"]}

Use the Browser Use MCP configured in Codex App. Project Python must not call
OpenAI, Zhipu, Browser Use Cloud, cookies, storage, network, DOM source, or
JavaScript extraction.

Steps:
1. Open the target URL in the logged-in local browser context.
2. Wait about {cfg["page_load_wait"]} seconds for visible content to settle.
3. Decide page state: visible_ready, login_required, captcha_required,
   white_skeleton, empty_result, or unknown.
4. If visible_ready, capture the visible screenshot and extract at least
   {cfg["min_rows_per_keyword"]} visible product rows when possible.
5. Scroll at most {cfg["max_scrolls_per_keyword"]} times, then stop.
6. Write a rows JSON file and ingest it with harness.py visual-ingest.

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
