"""
Conservative page-state detection for the visual collection MVP.

Product data extraction remains screenshot/vision based.  CDP/browser-use MCP
state is used only for safe page-state hints: URL/title/tab metadata,
interactive element visible text, viewport, and scroll position.  Do not use
HTML, JavaScript eval, cookies/storage, network payloads, or hidden DOM data as
collection input.
"""
from dataclasses import asdict, dataclass
import json
from typing import Any, Dict, Iterable, List, Optional


VISIBLE_READY = "visible_ready"
WHITE_SKELETON = "white_skeleton"
LOGIN_REQUIRED = "login_required"
CAPTCHA_REQUIRED = "captcha_required"
POPUP_BLOCKED = "popup_blocked"
EMPTY_RESULT = "empty_result"
UNKNOWN = "unknown"


LOGIN_TEXT_MARKERS = (
    "登录",
    "扫码",
    "密码登录",
    "免费注册",
    "手机扫码",
    "安全登录",
    "亲，请登录",
)
CAPTCHA_TEXT_MARKERS = (
    "验证码",
    "安全验证",
    "滑块",
    "拖动",
    "验证一下",
    "风险",
    "异常",
)
EMPTY_TEXT_MARKERS = (
    "没有找到",
    "暂无相关",
    "无相关商品",
    "抱歉，没有找到",
)
VISIBLE_READY_TEXT_MARKERS = (
    "付款",
    "人付款",
    "已售",
    "包邮",
    "店",
    "发货地",
    "¥",
    "￥",
)


@dataclass
class PageState:
    status: str
    confidence: float
    reason: str
    metrics: Dict[str, float]

    def to_dict(self):
        return asdict(self)


def detect_page_state(image_path: str, manual_state: Optional[str] = None) -> PageState:
    if manual_state:
        return PageState(
            status=manual_state,
            confidence=1.0,
            reason="manual_override",
            metrics={},
        )

    try:
        from PIL import Image, ImageStat
    except ImportError as e:
        raise RuntimeError("Pillow 未安装，请运行 pip install -r requirements.txt") from e

    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    crop_top = int(height * 0.28)
    content = img.crop((0, crop_top, width, height))
    pixels = list(content.getdata())
    total = max(1, len(pixels))

    orange_red = 0
    dark = 0
    light = 0
    grayish = 0
    for r, g, b in pixels:
        if r > 190 and 45 <= g <= 150 and b < 90:
            orange_red += 1
        if r < 90 and g < 90 and b < 90:
            dark += 1
        if r > 225 and g > 225 and b > 225:
            light += 1
        if abs(r - g) < 12 and abs(g - b) < 12 and 185 <= r <= 245:
            grayish += 1

    stat = ImageStat.Stat(content)
    variance = sum(stat.var) / 3.0
    metrics = {
        "orange_red_ratio": orange_red / total,
        "dark_ratio": dark / total,
        "light_ratio": light / total,
        "grayish_ratio": grayish / total,
        "variance": variance,
        "width": float(width),
        "height": float(height),
    }

    # Taobao product cards usually include orange price text and dark title text.
    if metrics["orange_red_ratio"] > 0.006 and metrics["dark_ratio"] > 0.035:
        return PageState(
            status=VISIBLE_READY,
            confidence=0.72,
            reason="detected_price_colored_text_and_product_text_regions",
            metrics=metrics,
        )

    # Skeleton pages trend very light/gray with low orange price signal.
    if metrics["light_ratio"] > 0.62 and metrics["grayish_ratio"] > 0.05 and metrics["orange_red_ratio"] < 0.003:
        return PageState(
            status=WHITE_SKELETON,
            confidence=0.64,
            reason="mostly_light_gray_content_with_no_price_signal",
            metrics=metrics,
        )

    return PageState(
        status=UNKNOWN,
        confidence=0.35,
        reason="heuristics_inconclusive",
        metrics=metrics,
    )


def detect_page_state_from_browser_state(
    browser_state: Any,
    manual_state: Optional[str] = None,
) -> PageState:
    """Classify page state from safe browser-use MCP state summaries.

    Accepted input is the value returned by ``browser_get_state`` or its text
    payload.  The classifier intentionally consumes only metadata and visible
    interactive text.  It does not require or inspect HTML, network responses,
    cookies/storage, or arbitrary JavaScript results.
    """
    if manual_state:
        return PageState(
            status=manual_state,
            confidence=1.0,
            reason="manual_override",
            metrics={},
        )

    normalized = _normalize_browser_state(browser_state)
    url = str(normalized.get("url") or "")
    title = str(normalized.get("title") or "")
    texts = _collect_visible_texts(normalized)
    joined = " ".join([title, *texts])
    metrics = {
        "visible_text_count": float(len(texts)),
        "login_marker_count": float(_count_markers(joined, LOGIN_TEXT_MARKERS)),
        "captcha_marker_count": float(_count_markers(joined, CAPTCHA_TEXT_MARKERS)),
        "empty_marker_count": float(_count_markers(joined, EMPTY_TEXT_MARKERS)),
        "ready_marker_count": float(_count_markers(joined, VISIBLE_READY_TEXT_MARKERS)),
        "has_search_url": 1.0 if "s.taobao.com/search" in url else 0.0,
    }

    if metrics["captcha_marker_count"] > 0:
        return PageState(
            status=CAPTCHA_REQUIRED,
            confidence=0.86,
            reason="safe_state_contains_captcha_or_risk_text",
            metrics=metrics,
        )

    if metrics["login_marker_count"] >= 2 or (
        metrics["login_marker_count"] >= 1 and metrics["ready_marker_count"] == 0
    ):
        return PageState(
            status=LOGIN_REQUIRED,
            confidence=0.84,
            reason="safe_state_contains_login_text_without_product_markers",
            metrics=metrics,
        )

    if metrics["empty_marker_count"] > 0:
        return PageState(
            status=EMPTY_RESULT,
            confidence=0.78,
            reason="safe_state_contains_empty_result_text",
            metrics=metrics,
        )

    if metrics["ready_marker_count"] >= 2:
        return PageState(
            status=VISIBLE_READY,
            confidence=0.68,
            reason="safe_state_contains_visible_listing_markers",
            metrics=metrics,
        )

    if "s.taobao.com/search" in url and len(texts) <= 2:
        return PageState(
            status=WHITE_SKELETON,
            confidence=0.55,
            reason="search_url_with_too_few_visible_interactive_texts",
            metrics=metrics,
        )

    return PageState(
        status=UNKNOWN,
        confidence=0.35,
        reason="safe_state_heuristics_inconclusive",
        metrics=metrics,
    )


def _normalize_browser_state(browser_state: Any) -> Dict[str, Any]:
    if isinstance(browser_state, dict):
        if "content" in browser_state:
            for item in browser_state.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    parsed = _loads_json_object(item.get("text", ""))
                    if parsed is not None:
                        return parsed
        return browser_state

    if isinstance(browser_state, str):
        parsed = _loads_json_object(browser_state)
        if parsed is not None:
            return parsed

    # pydantic MCP result objects expose model_dump; keep this generic so tests
    # can pass plain dicts.
    if hasattr(browser_state, "model_dump"):
        return _normalize_browser_state(browser_state.model_dump(mode="json"))

    return {}


def _loads_json_object(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _collect_visible_texts(state: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for element in _iter_elements(state.get("interactive_elements")):
        text = str(element.get("text") or "").strip()
        if text:
            values.append(text)
    return values


def _iter_elements(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _count_markers(text: str, markers: Iterable[str]) -> int:
    return sum(1 for marker in markers if marker and marker in text)
