"""
Daily scheduling helpers for full-ledger visual collection.

The scheduler reads the business ledger, selects statistical-mode cards whose
Taobao capture time is missing or stale, and writes a session plan that the
existing visual pipeline can advance with Midscene computer requests.
"""
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.input_reader import build_search_keywords
from modules.session_capsule import RUNNABLE_STATUSES, build_session_capsule
from modules.task_state import TaskRecord
from modules.utils import ConfigManager, ensure_dir, get_project_root


@dataclass
class SchedulerConfig:
    daily_keyword_budget: int = 120
    daily_session_count: int = 4
    capture_freshness_days: int = 30
    capture_time_output_column: str = "淘宝采集时间"
    preferred_mode_column: str = "preferred_mode"
    pricing_mode_column: str = "pricing_mode"
    card_name_column: str = "中文卡牌名"
    keyword_prefix: str = "万智牌"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def scheduler_config_from_settings(config: ConfigManager) -> SchedulerConfig:
    return SchedulerConfig(
        daily_keyword_budget=config.getint("SCHEDULER", "daily_keyword_budget", fallback=120),
        daily_session_count=max(1, config.getint("SCHEDULER", "daily_session_count", fallback=4)),
        capture_freshness_days=max(0, config.getint("SCHEDULER", "capture_freshness_days", fallback=30)),
        capture_time_output_column=config.get(
            "PRODUCT_ROUTING", "capture_time_output_column", fallback="淘宝采集时间"
        ).strip() or "淘宝采集时间",
        preferred_mode_column=config.get(
            "PRODUCT_ROUTING", "preferred_mode_column", fallback="preferred_mode"
        ).strip() or "preferred_mode",
        pricing_mode_column=config.get(
            "PRODUCT_ROUTING", "pricing_mode_column", fallback="pricing_mode"
        ).strip() or "pricing_mode",
        card_name_column=config.get("INPUT", "card_name_column", fallback="中文卡牌名").strip()
        or "中文卡牌名",
        keyword_prefix=config.get("INPUT", "keyword_prefix", fallback="万智牌").strip()
        or "万智牌",
    )


def plan_daily_collection(
    raw_input_file: str,
    config_file: str = "config/settings.ini",
    plan_id: Optional[str] = None,
    random_sample: Optional[int] = None,
    random_seed: Optional[int] = None,
    session_count: Optional[int] = None,
) -> Dict[str, Any]:
    config = ConfigManager(config_file)
    scheduler = scheduler_config_from_settings(config)
    if session_count is not None:
        scheduler.daily_session_count = max(1, int(session_count))
    raw_input_file = os.path.abspath(raw_input_file)
    if not os.path.exists(raw_input_file):
        raise FileNotFoundError(f"原始输入表不存在: {raw_input_file}")

    raw_df = pd.read_excel(raw_input_file, engine="openpyxl", dtype=str)
    mode_col = _find_existing_col(
        raw_df, [scheduler.preferred_mode_column, scheduler.pricing_mode_column]
    )
    card_col = _find_existing_col(raw_df, [scheduler.card_name_column, "中文卡牌名", "card_name", "目标牌名"])
    if mode_col is None:
        raise ValueError("原始输入表缺少 preferred_mode/pricing_mode 列")
    if card_col is None:
        raise ValueError("原始输入表缺少牌名列")

    capture_col = scheduler.capture_time_output_column
    today = datetime.now()
    stale_before = today - timedelta(days=scheduler.capture_freshness_days)
    candidates = _select_candidates(
        raw_df=raw_df,
        mode_col=mode_col,
        card_col=card_col,
        capture_col=capture_col,
        stale_before=stale_before,
        keyword_prefix=scheduler.keyword_prefix,
    )
    candidates = _sample_candidates(candidates, random_sample, random_seed)
    selected = candidates[: max(0, scheduler.daily_keyword_budget)]
    sessions = _assign_sessions(selected, scheduler.daily_session_count)

    plan_id = plan_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = os.path.join(get_project_root(), "data", "tasks", plan_id)
    evidence_root = os.path.join(task_dir, "evidence")
    ensure_dir(evidence_root)

    keywords = [item["keyword"] for item in selected]
    records = []
    for item in selected:
        evidence_dir = os.path.join(evidence_root, _safe_name(item["keyword"]))
        ensure_dir(evidence_dir)
        record = TaskRecord(
            keyword=item["keyword"],
            status="pending",
            evidence_dir=evidence_dir,
            last_action="daily_plan_prepared",
            agent_notes="Selected from full ledger for scheduled Midscene computer collection.",
            extra={
                "card_name": item["card_name"],
                "daily_session_index": item["session_index"],
                "ledger_row_indices": item["row_indices"],
                "previous_capture_time": item["previous_capture_time"],
                "selection_reason": item["selection_reason"],
            },
        )
        records.append(record.to_dict())

    manifest = {
        "run_id": plan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "raw_input_file": raw_input_file,
            "config": os.path.abspath(config_file),
            "selection": "preferred_mode=statistical and capture time missing or stale; with_keywords is a future pending route",
        },
        "workflow": "scheduled_midscene_computer_visual_capture",
        "keywords": keywords,
        "records": records,
        "scheduler": scheduler.to_dict(),
        "sessions": sessions,
    }
    plan = {
        "plan_id": plan_id,
        "created_at": manifest["created_at"],
        "raw_input_file": raw_input_file,
        "task_dir": task_dir,
        "daily_keyword_budget": scheduler.daily_keyword_budget,
        "daily_session_count": scheduler.daily_session_count,
        "capture_freshness_days": scheduler.capture_freshness_days,
        "stale_before": stale_before.strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "random_sample": random_sample,
        "random_seed": random_seed,
        "sessions": sessions,
        "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
    }

    ensure_dir(task_dir)
    _write_json(plan["manifest_path"], manifest)
    _write_json(os.path.join(task_dir, "daily_plan.json"), plan)
    _write_text(os.path.join(task_dir, "keywords.txt"), "\n".join(keywords) + ("\n" if keywords else ""))
    return plan


def load_daily_plan(plan_id: str) -> Dict[str, Any]:
    path = os.path.join(get_project_root(), "data", "tasks", plan_id, "daily_plan.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到 daily_plan: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scheduler_status(plan_id: str) -> Dict[str, Any]:
    plan = load_daily_plan(plan_id)
    manifest_path = plan.get("manifest_path") or os.path.join(
        get_project_root(), "data", "tasks", plan_id, "visual_tasks.json"
    )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    records = manifest.get("records", [])
    by_status: Dict[str, int] = {}
    by_session: Dict[str, Dict[str, int]] = {}
    for record in records:
        status = str(record.get("status") or "")
        by_status[status] = by_status.get(status, 0) + 1
        session_index = str(record.get("extra", {}).get("daily_session_index", "unassigned"))
        bucket = by_session.setdefault(session_index, {})
        bucket[status] = bucket.get(status, 0) + 1
    return {
        "plan_id": plan_id,
        "selected_count": plan.get("selected_count", 0),
        "daily_keyword_budget": plan.get("daily_keyword_budget", 0),
        "daily_session_count": plan.get("daily_session_count", 0),
        "by_status": by_status,
        "by_session": by_session,
        "task_dir": plan.get("task_dir", ""),
    }


def auto_tick_daily_collection(
    raw_input_file: Optional[str] = None,
    config_file: str = "config/settings.ini",
    plan_id: Optional[str] = None,
    session_index: Optional[int] = None,
    limit: Optional[int] = None,
    random_sample: Optional[int] = None,
    random_seed: Optional[int] = None,
    session_count: Optional[int] = None,
    prepare_requests: bool = False,
    force_lease: bool = False,
) -> Dict[str, Any]:
    """
    Resolve today's plan/session from the full ledger and prepare the next unit.

    This is the automation-friendly entry point: callers do not need to know a
    plan_id or slice the ledger. The durable plan id defaults to one per day.
    """
    config = ConfigManager(config_file)
    raw_input_file = _resolve_raw_input_file(config, raw_input_file)
    plan_id = plan_id or _today_plan_id()
    task_dir = os.path.join(get_project_root(), "data", "tasks", plan_id)
    plan_path = os.path.join(task_dir, "daily_plan.json")

    if os.path.exists(plan_path):
        plan = load_daily_plan(plan_id)
        plan_created = False
    else:
        plan = plan_daily_collection(
            raw_input_file=raw_input_file,
            config_file=config_file,
            plan_id=plan_id,
            random_sample=random_sample,
            random_seed=random_seed,
            session_count=session_count,
        )
        plan_created = True

    manifest_path = plan.get("manifest_path") or os.path.join(task_dir, "visual_tasks.json")
    manifest = _load_json(manifest_path)
    chosen = int(session_index) if session_index is not None else _choose_due_session(plan, manifest)
    if chosen <= 0:
        return {
            "ok": True,
            "action": "noop",
            "reason": "no_due_runnable_session",
            "plan_created": plan_created,
            "plan_id": plan_id,
            "task_dir": task_dir,
            "status": scheduler_status(plan_id),
        }

    capsule = build_session_capsule(
        plan_id,
        chosen,
        config_file=config_file,
        limit=limit,
    )
    result = {
        "ok": True,
        "action": "capsule_prepared",
        "plan_created": plan_created,
        "plan_id": plan_id,
        "session_index": chosen,
        "task_dir": task_dir,
        "capsule": capsule,
        "status": scheduler_status(plan_id),
    }
    if prepare_requests:
        from modules.visual_pipeline import run_visual_collection

        request_result = run_visual_collection(
            plan_id,
            config_file=config_file,
            limit=limit,
            session_index=chosen,
            force_lease=force_lease,
        )
        result["action"] = "requests_prepared"
        result["request_result"] = request_result
        result["status"] = scheduler_status(plan_id)
    return result


def _select_candidates(
    raw_df,
    mode_col: str,
    card_col: str,
    capture_col: str,
    stale_before: datetime,
    keyword_prefix: str,
):
    rows = []
    for idx, row in raw_df.iterrows():
        mode = str(row.get(mode_col, "") or "").strip().lower()
        card_name = str(row.get(card_col, "") or "").strip()
        if mode != "statistical" or not card_name:
            continue
        capture_time = str(row.get(capture_col, "") or "").strip() if capture_col in raw_df.columns else ""
        parsed = pd.to_datetime(capture_time, errors="coerce") if capture_time else pd.NaT
        missing = not capture_time or pd.isna(parsed)
        stale = (not pd.isna(parsed)) and parsed.to_pydatetime() < stale_before
        if missing or stale:
            rows.append(
                {
                    "row_index": int(idx),
                    "card_name": card_name,
                    "capture_time": capture_time,
                    "parsed_capture_time": parsed,
                    "selection_reason": "capture_time_missing" if missing else "capture_time_stale",
                }
            )

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        bucket = grouped.setdefault(
            item["card_name"],
            {
                "card_name": item["card_name"],
                "row_indices": [],
                "previous_capture_time": "",
                "parsed_capture_time": pd.NaT,
                "selection_reason": item["selection_reason"],
            },
        )
        bucket["row_indices"].append(item["row_index"])
        current = item["parsed_capture_time"]
        existing = bucket["parsed_capture_time"]
        if pd.isna(existing) or (not pd.isna(current) and current < existing):
            bucket["parsed_capture_time"] = current
            bucket["previous_capture_time"] = item["capture_time"]
        if item["selection_reason"] == "capture_time_missing":
            bucket["selection_reason"] = "capture_time_missing"

    cards = list(grouped.values())
    keywords = build_search_keywords([item["card_name"] for item in cards], prefix=keyword_prefix)
    for item, keyword in zip(cards, keywords):
        item["keyword"] = keyword

    def sort_key(item):
        parsed = item.get("parsed_capture_time")
        missing_rank = 0 if pd.isna(parsed) else 1
        timestamp = datetime.min if pd.isna(parsed) else parsed.to_pydatetime()
        return (missing_rank, timestamp, item["card_name"])

    return sorted(cards, key=sort_key)


def _sample_candidates(
    candidates: List[Dict[str, Any]],
    random_sample: Optional[int],
    random_seed: Optional[int],
) -> List[Dict[str, Any]]:
    if random_sample is None:
        return candidates
    sample_size = max(0, int(random_sample))
    if sample_size <= 0 or sample_size >= len(candidates):
        return candidates
    rng = random.Random(random_seed)
    sampled = rng.sample(candidates, sample_size)
    sampled_names = {item["card_name"] for item in sampled}
    return [item for item in candidates if item["card_name"] in sampled_names]


def _assign_sessions(selected: List[Dict[str, Any]], session_count: int) -> List[Dict[str, Any]]:
    total = len(selected)
    if total == 0:
        return []
    per_session = int(math.ceil(total / max(1, session_count)))
    sessions = []
    for idx, item in enumerate(selected):
        session_index = min(session_count, idx // per_session + 1)
        item["session_index"] = session_index
    for session_index in range(1, session_count + 1):
        count = sum(1 for item in selected if item["session_index"] == session_index)
        sessions.append({"session_index": session_index, "keyword_count": count, "status": "pending"})
    return sessions


def _resolve_raw_input_file(config: ConfigManager, raw_input_file: Optional[str]) -> str:
    value = (raw_input_file or "").strip()
    if not value:
        value = config.get("PRODUCT_ROUTING", "raw_input_file", fallback="").strip()
    if not value:
        value = config.get("INPUT", "excel_file", fallback="").strip()
    if not value:
        raise ValueError(
            "缺少原始输入台账路径：传 --raw-input，或在 config/settings.ini 的 "
            "[PRODUCT_ROUTING] raw_input_file 中配置。"
        )
    return os.path.abspath(os.path.expanduser(os.path.expandvars(value)))


def _today_plan_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return f"daily_{now.strftime('%Y%m%d')}"


def _choose_due_session(plan: Dict[str, Any], manifest: Dict[str, Any]) -> int:
    sessions = plan.get("sessions", [])
    if not sessions:
        return 0
    session_count = max(1, int(plan.get("daily_session_count") or len(sessions) or 1))
    now = datetime.now()
    minute_of_day = now.hour * 60 + now.minute
    minutes_per_session = 1440 / session_count
    due_session = min(session_count, max(1, int(minute_of_day // minutes_per_session) + 1))
    runnable_by_session = _runnable_counts_by_session(manifest)
    for idx in range(1, due_session + 1):
        if runnable_by_session.get(idx, 0) > 0:
            return idx
    return 0


def _runnable_counts_by_session(manifest: Dict[str, Any]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for record in manifest.get("records", []):
        status = str(record.get("status") or "")
        if status not in RUNNABLE_STATUSES:
            continue
        idx = int(record.get("extra", {}).get("daily_session_index") or 0)
        if idx > 0:
            counts[idx] = counts.get(idx, 0) + 1
    return counts


def _find_existing_col(df, candidates):
    for col in candidates:
        if col and col in df.columns:
            return col
    return None


def _safe_name(value):
    keep = []
    for ch in str(value):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    return ("".join(keep).strip("_") or "keyword")[:80]


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_text(path: str, text: str) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
