"""
Viewport tile sampling helpers for pure-vision collection.

This module intentionally does not inspect DOM, CDP, page source, storage, or
network data. It only computes conservative sampling metadata and writes small
JSONL task artifacts that can outlive deleted screenshots.
"""
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from modules.utils import ensure_dir


HUMAN_REQUIRED_REASONS = {
    "login_required",
    "captcha_or_risk",
    "captcha_required",
    "risk",
    "risk_suspected",
    "security_required",
    "security_verification",
    "manual_review_needed",
    "consecutive_abnormal",
    "locked",
}


@dataclass
class PageSamplingConfig:
    target_listings_per_keyword: int = 48
    max_tiles_per_keyword: int = 6
    tile_scroll_viewport_ratio: float = 0.80
    tile_overlap_ratio: float = 0.20
    min_new_rows_per_tile: int = 2
    allow_second_page: bool = False
    retain_screenshots: str = "human_required_only"
    allow_page_state_json_classifier: bool = False
    calibration_top_reserved_ratio: float = 0.24
    calibration_bottom_reserved_ratio: float = 0.06

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def page_sampling_config_from_settings(config) -> PageSamplingConfig:
    section = "PAGE_SAMPLING"
    json_classifier_value = config.get(section, "allow_page_state_json_classifier", fallback=None)
    if json_classifier_value is None:
        json_classifier_value = config.get(section, "allow_midscene_page_state_probe", fallback=False)
    return PageSamplingConfig(
        target_listings_per_keyword=config.getint(
            section, "target_listings_per_keyword", fallback=48
        ),
        max_tiles_per_keyword=config.getint(section, "max_tiles_per_keyword", fallback=6),
        tile_scroll_viewport_ratio=config.getfloat(
            section, "tile_scroll_viewport_ratio", fallback=0.80
        ),
        tile_overlap_ratio=config.getfloat(section, "tile_overlap_ratio", fallback=0.20),
        min_new_rows_per_tile=config.getint(section, "min_new_rows_per_tile", fallback=2),
        allow_second_page=config.getboolean(section, "allow_second_page", fallback=False),
        retain_screenshots=config.get(
            section, "retain_screenshots", fallback="human_required_only"
        ).strip()
        or "human_required_only",
        allow_page_state_json_classifier=_bool_value(json_classifier_value),
        calibration_top_reserved_ratio=config.getfloat(
            section, "calibration_top_reserved_ratio", fallback=0.24
        ),
        calibration_bottom_reserved_ratio=config.getfloat(
            section, "calibration_bottom_reserved_ratio", fallback=0.06
        ),
    )


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled", ""}:
        return False
    return False


def estimate_tile_scroll_distance(
    screen_height: int,
    config: PageSamplingConfig,
    content_top_y: Optional[int] = None,
    content_bottom_y: Optional[int] = None,
) -> Dict[str, Any]:
    """Estimate a tile scroll distance from visible-screen geometry only."""
    height = max(1, int(screen_height or 0))
    top_y = (
        int(content_top_y)
        if content_top_y is not None
        else int(height * config.calibration_top_reserved_ratio)
    )
    bottom_y = (
        int(content_bottom_y)
        if content_bottom_y is not None
        else int(height * (1.0 - config.calibration_bottom_reserved_ratio))
    )
    top_y = max(0, min(height - 1, top_y))
    bottom_y = max(top_y + 1, min(height, bottom_y))
    visible_product_height = max(1, bottom_y - top_y)
    scroll_distance = max(1, int(round(visible_product_height * config.tile_scroll_viewport_ratio)))
    overlap = max(0, visible_product_height - scroll_distance)
    return {
        "screen_height": height,
        "content_top_y": top_y,
        "content_bottom_y": bottom_y,
        "visible_product_height": visible_product_height,
        "tile_scroll_distance_px": scroll_distance,
        "tile_overlap_px": overlap,
        "tile_scroll_viewport_ratio": config.tile_scroll_viewport_ratio,
        "tile_overlap_ratio": config.tile_overlap_ratio,
        "calibration_source": "system_screenshot_geometry_estimate",
    }


def should_retain_screenshot(retain_policy: str, status: str = "", failure_reason: str = "") -> bool:
    policy = str(retain_policy or "human_required_only").strip().lower()
    if policy in {"always", "true", "yes"}:
        return True
    if policy in {"never", "false", "no"}:
        return False
    reason = str(failure_reason or status or "").strip().lower()
    return reason in HUMAN_REQUIRED_REASONS


def write_task_event(
    task_dir: str,
    event: str,
    level: str = "info",
    run_id: str = "",
    session_index: Optional[int] = None,
    keyword: str = "",
    **extra: Any,
) -> str:
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "event": event,
        "run_id": run_id,
        "session_index": session_index,
        "keyword": keyword,
        **extra,
    }
    return _append_jsonl(os.path.join(task_dir, "task_events.jsonl"), payload)


def write_tile_summary(
    task_dir: str,
    run_id: str,
    keyword: str,
    tile_id: str,
    scroll_distance_px: int = 0,
    rough_state: str = "",
    image_path: str = "",
    image_retained: bool = False,
    rows_extracted: int = 0,
    new_rows_after_dedupe: int = 0,
    stop_reason: str = "",
    notes: str = "",
) -> str:
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "keyword": keyword,
        "tile_id": tile_id,
        "scroll_distance_px": scroll_distance_px,
        "rough_state": rough_state,
        "image_path": image_path,
        "image_retained": image_retained,
        "rows_extracted": rows_extracted,
        "new_rows_after_dedupe": new_rows_after_dedupe,
        "stop_reason": stop_reason,
        "notes": notes,
    }
    return _append_jsonl(os.path.join(task_dir, "tile_summary.jsonl"), payload)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path
