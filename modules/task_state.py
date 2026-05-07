"""
Task state and evidence helpers for long-running collection jobs.

This module is intentionally small and independent from browser automation.
It gives both scripts and agents a stable place to write task status,
failure reasons, and diagnostic evidence.
"""
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from modules.utils import ensure_dir, get_project_root, sanitize_filename


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYABLE = "retryable"
    NEEDS_HUMAN = "needs_human"
    SKIPPED = "skipped"


class FailureReason(str, Enum):
    PROXY_ERROR = "proxy_error"
    ADSPOWER_ERROR = "adspower_error"
    PLUGIN_ERROR = "plugin_error"
    CAPTCHA_OR_RISK = "captcha_or_risk"
    NO_RESULTS = "no_results"
    DOM_CHANGED = "dom_changed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class TaskRecord:
    keyword: str
    status: str = TaskStatus.PENDING.value
    failure_reason: Optional[str] = None
    error: Optional[str] = None
    evidence_dir: Optional[str] = None
    retry_count: int = 0
    last_action: Optional[str] = None
    agent_notes: str = ""
    profile_id: Optional[str] = None
    proxy: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str = field(default_factory=now_iso)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceRecorder:
    """Writes structured evidence files under data/tasks/<run>/evidence."""

    def __init__(self, base_dir: str = "data/tasks"):
        root = get_project_root()
        self.base_dir = base_dir if os.path.isabs(base_dir) else os.path.join(root, base_dir)

    def create_dir(self, label: str, run_id: Optional[str] = None) -> str:
        run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = sanitize_filename(label)[:80]
        base = os.path.join(self.base_dir, run_id, "evidence")
        evidence_dir = os.path.join(base, safe_label)
        suffix = 2
        while os.path.exists(evidence_dir):
            evidence_dir = os.path.join(base, f"{safe_label}_{suffix}")
            suffix += 1
        ensure_dir(evidence_dir)
        return evidence_dir

    def write_json(self, evidence_dir: str, name: str, data: Dict[str, Any]) -> str:
        path = os.path.join(evidence_dir, sanitize_filename(name))
        if not path.endswith(".json"):
            path += ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def write_text(self, evidence_dir: str, name: str, text: str) -> str:
        path = os.path.join(evidence_dir, sanitize_filename(name))
        if not path.endswith(".txt"):
            path += ".txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
