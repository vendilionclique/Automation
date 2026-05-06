"""
Screenshot-based page-state detection for the visual collection MVP.

The heuristics here are intentionally conservative. They do not read DOM or
network state; when uncertain they return "unknown" so the scheduler can pause
or ask for human/Codex review.
"""
from dataclasses import asdict, dataclass
from typing import Dict, Optional


VISIBLE_READY = "visible_ready"
WHITE_SKELETON = "white_skeleton"
LOGIN_REQUIRED = "login_required"
CAPTCHA_REQUIRED = "captcha_required"
POPUP_BLOCKED = "popup_blocked"
UNKNOWN = "unknown"


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
