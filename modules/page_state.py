"""
Conservative page-state detection for the visual collection MVP.

Product data extraction remains screenshot/vision based. This module only
classifies coarse operational states from visible screenshot pixels.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


VISIBLE_READY = "visible_ready"
WHITE_SKELETON = "white_skeleton"
LOGIN_REQUIRED = "login_required"
CAPTCHA_REQUIRED = "captcha_required"
POPUP_BLOCKED = "popup_blocked"
EMPTY_RESULT = "empty_result"
UNKNOWN = "unknown"


@dataclass
class PageState:
    status: str
    confidence: float
    reason: str
    metrics: Dict[str, float]

    def to_dict(self):
        return asdict(self)


@dataclass
class VisibleKeywordVerification:
    status: str
    expected_keyword: str
    observed_keyword: str
    confidence: float
    reason: str
    source: str

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
    pixels = _image_pixels(content)
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

    # A full-page screenshot can include a large white footer, which dilutes the
    # price-color ratio even when the visible listing grid is healthy. Re-check
    # the likely results band and require price-like color to be spread across
    # several columns so a single login/captcha/security button is not enough.
    listing_metrics = _listing_band_metrics(img)
    metrics.update(listing_metrics)
    if (
        metrics["listing_orange_red_ratio"] > 0.006
        and metrics["listing_dark_ratio"] > 0.055
        and metrics["listing_variance"] > 1200
        and metrics["listing_orange_bucket_count"] >= 4
        and metrics["listing_dark_bucket_count"] >= 4
    ):
        return PageState(
            status=VISIBLE_READY,
            confidence=0.70,
            reason="detected_distributed_price_text_in_listing_region",
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


def _listing_band_metrics(img) -> Dict[str, float]:
    width, height = img.size
    left = int(width * 0.04)
    top = int(height * 0.23)
    right = int(width * 0.96)
    bottom = int(height * 0.58)
    crop = img.crop((left, top, right, bottom))
    crop_width, crop_height = crop.size
    pixels = _image_pixels(crop)
    total = max(1, len(pixels))

    orange_red = 0
    dark = 0
    bucket_count = 12
    orange_buckets = [0] * bucket_count
    dark_buckets = [0] * bucket_count
    for index, (r, g, b) in enumerate(pixels):
        x = index % crop_width if crop_width else 0
        bucket = min(bucket_count - 1, x * bucket_count // max(1, crop_width))
        if r > 190 and 45 <= g <= 150 and b < 90:
            orange_red += 1
            orange_buckets[bucket] += 1
        if r < 90 and g < 90 and b < 90:
            dark += 1
            dark_buckets[bucket] += 1

    try:
        from PIL import ImageStat

        variance = sum(ImageStat.Stat(crop).var) / 3.0
    except Exception:
        variance = 0.0

    orange_bucket_threshold = total * 0.00015
    dark_bucket_threshold = total * 0.001
    return {
        "listing_orange_red_ratio": orange_red / total,
        "listing_dark_ratio": dark / total,
        "listing_variance": float(variance),
        "listing_orange_bucket_count": float(
            sum(1 for value in orange_buckets if value > orange_bucket_threshold)
        ),
        "listing_dark_bucket_count": float(
            sum(1 for value in dark_buckets if value > dark_bucket_threshold)
        ),
    }


def _image_pixels(img):
    getter = getattr(img, "get_flattened_data", None)
    if getter:
        return list(getter())
    return list(img.getdata())


def verify_visible_keyword(
    image_path: str,
    expected_keyword: str,
    page_state: Optional[Dict[str, Any]] = None,
) -> VisibleKeywordVerification:
    """Conservatively verify the visible search keyword from screenshot evidence.

    This function never reads page structure. It first honors structured
    screenshot-derived hints supplied by tests or future OCR/classifier code, then
    tries optional local OCR when available. Unknown is preferred over guessing.
    """
    expected = _normalize_keyword(expected_keyword)
    state = page_state or {}
    hinted = _hinted_visible_keyword(state)
    if hinted:
        observed = _normalize_keyword(hinted)
        if observed == expected:
            return VisibleKeywordVerification(
                status="matched",
                expected_keyword=expected_keyword,
                observed_keyword=hinted,
                confidence=0.95,
                reason="visible_search_keyword_hint_matched",
                source="page_state_hint",
            )
        return VisibleKeywordVerification(
            status="mismatch",
            expected_keyword=expected_keyword,
            observed_keyword=hinted,
            confidence=0.95,
            reason="visible_search_keyword_hint_mismatched",
            source="page_state_hint",
        )

    ocr_text = _ocr_top_region_text(image_path)
    if not ocr_text:
        return VisibleKeywordVerification(
            status="unknown",
            expected_keyword=expected_keyword,
            observed_keyword="",
            confidence=0.0,
            reason="visible_keyword_ocr_unavailable_or_empty",
            source="ocr",
        )
    if expected and expected in _normalize_keyword(ocr_text):
        return VisibleKeywordVerification(
            status="matched",
            expected_keyword=expected_keyword,
            observed_keyword=ocr_text[:120],
            confidence=0.70,
            reason="visible_keyword_ocr_contains_expected_keyword",
            source="ocr",
        )
    return VisibleKeywordVerification(
        status="unknown",
        expected_keyword=expected_keyword,
        observed_keyword=ocr_text[:120],
        confidence=0.25,
        reason="visible_keyword_ocr_inconclusive",
        source="ocr",
    )


def _hinted_visible_keyword(page_state: Dict[str, Any]) -> str:
    for key in ("visible_search_keyword", "observed_keyword", "search_keyword"):
        value = str(page_state.get(key) or "").strip()
        if value:
            return value
    verification = page_state.get("keyword_verification")
    if isinstance(verification, dict):
        return str(verification.get("observed_keyword") or "").strip()
    return ""


def _ocr_top_region_text(image_path: str) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image
    except Exception:
        return ""
    try:
        img = Image.open(image_path).convert("RGB")
        width, height = img.size
        top = img.crop((0, 0, width, max(1, int(height * 0.24))))
        return " ".join(str(pytesseract.image_to_string(top, lang="chi_sim+eng") or "").split())
    except Exception:
        return ""


def _normalize_keyword(value: str) -> str:
    return "".join(str(value or "").lower().split())
