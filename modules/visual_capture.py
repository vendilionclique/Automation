"""
Visual capture records and filesystem helpers.
"""
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from modules.utils import ensure_dir, sanitize_filename


@dataclass
class CaptureRecord:
    run_id: str
    keyword: str
    evidence_dir: str
    screenshot_path: str
    status: str
    page_state: Dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    retained: bool = True
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def keyword_evidence_dir(task_dir: str, keyword: str) -> str:
    path = os.path.join(task_dir, "evidence", sanitize_filename(keyword)[:80] or "keyword")
    ensure_dir(path)
    return path


def screenshot_path_for(evidence_dir: str, keyword: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(evidence_dir, f"{stamp}_{sanitize_filename(keyword)[:40] or 'keyword'}.png")


def write_capture_manifest(record: CaptureRecord) -> str:
    path = os.path.join(record.evidence_dir, "capture_manifest.json")
    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = data.get("captures", []) if isinstance(data, dict) else []
        except Exception:
            existing = []
    existing.append(record.to_dict())
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"captures": existing}, f, ensure_ascii=False, indent=2)
    return path


def write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def maybe_delete_screenshot(path: Optional[str]) -> bool:
    if not path or not os.path.exists(path):
        return False
    os.remove(path)
    return True
