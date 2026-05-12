"""
Task state and evidence helpers for long-running collection jobs.

This module is intentionally small and independent from browser automation.
It gives both scripts and agents a stable place to write task status,
failure reasons, and diagnostic evidence.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYABLE = "retryable"
    NEEDS_HUMAN = "needs_human"
    SKIPPED = "skipped"


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
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str = field(default_factory=now_iso)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
