"""
Real browser-use integration for local Chrome collection.

The primary workflow is Codex App -> browser-use MCP server -> local Chrome.
This file writes bounded request artifacts for that MCP workflow. It also keeps
an optional standalone browser-use Agent fallback for environments that provide
their own LLM API key.
"""
import asyncio
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
    chrome_executable_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = ""
    headless: bool = False
    keep_alive: bool = False
    enable_default_extensions: bool = False
    max_steps: int = 20
    agent_llm_provider: str = "zhipu"
    agent_llm_model: str = "glm-4.7-flashx"
    agent_llm_api_key: str = ""
    agent_llm_api_key_env: str = "ZHIPU_API_KEY"
    agent_llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    use_vision: bool = True
    save_history: bool = True

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
    status: str = "needs_browser_use_agent"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrowserUseRunResult:
    ok: bool
    status: str
    rows: List[Dict[str, Any]]
    page_state: str
    screenshot_path: str
    history_path: str
    final_result: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def browser_use_config_from_settings(config) -> BrowserUseConfig:
    section = "BROWSER_USE"
    old_section = "BROWSER_USE_CAPTURE"
    visual = "VISUAL_CAPTURE"
    agent_section = "BROWSER_USE_AGENT"
    llm_section = "LLM"
    return BrowserUseConfig(
        allowed_domains=_split_csv(
            config.get(
                section,
                "allowed_domains",
                fallback=config.get(
                    old_section,
                    "allowed_domains",
                    fallback="https://www.taobao.com,https://s.taobao.com,*.taobao.com",
                ),
            )
        ),
        window_width=config.getint(section, "window_width", fallback=config.getint(visual, "window_width", fallback=1600)),
        window_height=config.getint(section, "window_height", fallback=config.getint(visual, "window_height", fallback=1000)),
        max_scrolls_per_keyword=config.getint(section, "max_scrolls_per_keyword", fallback=2),
        page_load_wait=config.getfloat(section, "page_load_wait", fallback=8.0),
        min_rows_per_keyword=config.getint(section, "min_rows_per_keyword", fallback=5),
        confidence_threshold=config.getfloat(section, "confidence_threshold", fallback=0.80),
        screenshot_retention=config.getboolean(section, "screenshot_retention", fallback=True),
        chrome_executable_path=config.get(
            section,
            "chrome_executable_path",
            fallback=config.get(visual, "chrome_path", fallback="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ),
        chrome_user_data_dir=config.get(
            section,
            "chrome_user_data_dir",
            fallback=config.get(visual, "chrome_user_data_dir", fallback=""),
        ),
        chrome_profile_directory=config.get(
            section,
            "chrome_profile_directory",
            fallback=config.get(visual, "chrome_profile_directory", fallback=""),
        ),
        headless=config.getboolean(section, "headless", fallback=False),
        keep_alive=config.getboolean(section, "keep_alive", fallback=False),
        enable_default_extensions=config.getboolean(section, "enable_default_extensions", fallback=False),
        max_steps=config.getint(section, "max_steps", fallback=20),
        agent_llm_provider=config.get(
            agent_section,
            "llm_provider",
            fallback=config.get(llm_section, "provider", fallback="zhipu"),
        ),
        agent_llm_model=config.get(
            agent_section,
            "llm_model",
            fallback=config.get(llm_section, "zhipu_model", fallback="glm-4.7-flashx"),
        ),
        agent_llm_api_key=config.get(
            agent_section,
            "llm_api_key",
            fallback=config.get(llm_section, "zhipu_api_key", fallback=""),
        ),
        agent_llm_api_key_env=config.get(agent_section, "llm_api_key_env", fallback="ZHIPU_API_KEY"),
        agent_llm_base_url=config.get(
            agent_section,
            "llm_base_url",
            fallback=config.get(llm_section, "zhipu_api_base", fallback="https://open.bigmodel.cn/api/paas/v4"),
        ),
        use_vision=config.getboolean(section, "use_vision", fallback=True),
        save_history=config.getboolean(section, "save_history", fallback=True),
    )


def run_browser_use_capture(
    run_id: str,
    keyword: str,
    evidence_dir: str,
    config: BrowserUseConfig,
    manual_state: Optional[str] = None,
) -> BrowserUseRunResult:
    return asyncio.run(_run_browser_use_capture(run_id, keyword, evidence_dir, config, manual_state))


async def _run_browser_use_capture(
    run_id: str,
    keyword: str,
    evidence_dir: str,
    config: BrowserUseConfig,
    manual_state: Optional[str] = None,
) -> BrowserUseRunResult:
    ensure_dir(evidence_dir)
    screenshot_path = screenshot_path_for(evidence_dir, keyword)
    history_path = os.path.join(evidence_dir, "browser_use_history.json")
    url = TAOBAO_SEARCH.format(keyword=quote(keyword))

    try:
        from browser_use import Agent, BrowserSession
        from pydantic import BaseModel, Field
    except ImportError as e:
        return BrowserUseRunResult(
            ok=False,
            status="failed",
            rows=[],
            page_state="browser_use_missing",
            screenshot_path=screenshot_path,
            history_path=history_path,
            error=f"browser-use 未安装: {e}",
        )

    class ProductRow(BaseModel):
        title: str = Field("", description="商品名称")
        price: str = Field("", description="现价")
        shop: str = Field("", description="店铺名称")
        pay_count: str = Field("", description="付款人数")
        location: str = Field("", description="地区")
        bbox: str = Field("", description="截图坐标")
        confidence: float = Field(0.0, description="识别置信度，0 到 1")
        notes: str = Field("", description="识别备注")

    class CaptureOutput(BaseModel):
        page_state: str = Field(
            "unknown",
            description="visible_ready, login_required, captcha_required, white_skeleton, empty_result, unknown",
        )
        notes: str = ""
        rows: List[ProductRow] = Field(default_factory=list)

    browser = BrowserSession(
        executable_path=_expand(config.chrome_executable_path) or None,
        user_data_dir=_expand(config.chrome_user_data_dir) or None,
        profile_directory=config.chrome_profile_directory or None,
        headless=config.headless,
        allowed_domains=config.allowed_domains,
        window_size={"width": config.window_width, "height": config.window_height},
        keep_alive=config.keep_alive,
        use_cloud=False,
        captcha_solver=False,
        enable_default_extensions=config.enable_default_extensions,
    )

    task = _build_agent_task(url=url, keyword=keyword, config=config, manual_state=manual_state)
    try:
        llm = _create_llm(config)
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser,
            output_model_schema=CaptureOutput,
            use_vision=config.use_vision,
            save_conversation_path=os.path.join(evidence_dir, "browser_use_conversation.json")
            if config.save_history
            else None,
            max_actions_per_step=3,
            use_judge=False,
            max_failures=3,
            step_timeout=180,
        )
        history = await agent.run(max_steps=config.max_steps)
        if config.save_history:
            history.save_to_file(history_path)
        try:
            await browser.take_screenshot(path=screenshot_path, full_page=False)
        except Exception:
            pass

        output = history.get_structured_output(CaptureOutput)
        final_result = history.final_result() or ""
        if output is None:
            return BrowserUseRunResult(
                ok=False,
                status="needs_review",
                rows=[],
                page_state="unknown",
                screenshot_path=screenshot_path,
                history_path=history_path,
                final_result=final_result,
                error="browser-use 没有返回结构化结果",
            )

        rows = [_row_to_ingest_dict(row) for row in output.rows]
        ok = output.page_state == "visible_ready" and bool(rows)
        return BrowserUseRunResult(
            ok=ok,
            status="captured" if ok else "needs_review",
            rows=rows,
            page_state=output.page_state,
            screenshot_path=screenshot_path,
            history_path=history_path,
            final_result=final_result,
            error=None if ok else (output.notes or "browser_use_returned_no_visible_rows"),
        )
    except Exception as e:
        return BrowserUseRunResult(
            ok=False,
            status="failed",
            rows=[],
            page_state="error",
            screenshot_path=screenshot_path,
            history_path=history_path,
            error=str(e),
        )
    finally:
        if not config.keep_alive:
            try:
                await browser.kill()
            except Exception:
                pass


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
        "for_executor": "Codex App using the open-source browser-use MCP server",
        "forbidden": [
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
    return f"""# browser-use MCP Local Chrome Capture

Keyword: {payload["keyword"]}
URL: {payload["url"]}
Screenshot target: {payload["screenshot_path"]}

Use the open-source browser-use MCP server configured in Codex App. Codex is the
agent; browser-use MCP only provides local Chrome tools. Do not use Browser Use
Cloud, proxy rotation, stealth profiles, cookies/storage/network extraction, or
automatic login/captcha handling.

Steps:
1. Use browser-use MCP to open the target URL in the logged-in local Chrome profile.
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


def _build_agent_task(url: str, keyword: str, config: BrowserUseConfig, manual_state: Optional[str]) -> str:
    manual = f"\nManual page state hint: {manual_state}" if manual_state else ""
    return f"""
Open this Taobao search page in the local Chrome browser: {url}

Goal: collect visible product listing information for keyword "{keyword}".
Only use normal browser-use browser actions and visible page content. Do not
solve captcha, do not automate login, do not use proxies, and do not switch to
network/API/cookie/storage extraction.

Wait about {config.page_load_wait} seconds after navigation. Determine page_state
as one of: visible_ready, login_required, captcha_required, white_skeleton,
empty_result, unknown.{manual}

If page_state is visible_ready, extract up to {config.min_rows_per_keyword} to
{max(config.min_rows_per_keyword, 12)} visible product rows. Scroll at most
{config.max_scrolls_per_keyword} times if needed. For each row capture title,
price, shop, pay_count, location, approximate visible bounding box, confidence,
and notes. If login/captcha/risk page appears, stop and return no rows.

Return only the requested structured output.
""".strip()


def _create_llm(config: BrowserUseConfig):
    provider = (config.agent_llm_provider or "").strip().lower()
    api_key = config.agent_llm_api_key or os.environ.get(config.agent_llm_api_key_env or "") or ""

    if provider in ("browser-use", "browser_use", "bu"):
        from browser_use import ChatBrowserUse

        return ChatBrowserUse(model=config.agent_llm_model or "bu-latest", api_key=api_key or None)

    if provider in ("openai", "openai-compatible", "openai_compatible", "zhipu", "bigmodel"):
        from browser_use import ChatOpenAI

        return ChatOpenAI(
            model=config.agent_llm_model,
            api_key=api_key or None,
            base_url=config.agent_llm_base_url or None,
            max_completion_tokens=4096,
        )

    raise ValueError(f"不支持的 browser-use Agent LLM provider: {config.agent_llm_provider}")


def _row_to_ingest_dict(row) -> Dict[str, Any]:
    return {
        "商品名称": row.title,
        "现价": row.price,
        "店铺名称": row.shop,
        "付款人数": row.pay_count,
        "地区": row.location,
        "截图坐标": row.bbox,
        "识别置信度": row.confidence,
        "识别备注": row.notes,
    }


def _expand(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(str(value or "").strip()))


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
