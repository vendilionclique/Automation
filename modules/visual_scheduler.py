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
from modules.session_capsule import RUNNABLE_STATUSES, build_session_capsule, session_dir_for
from modules.task_state import TaskRecord
from modules.utils import ConfigManager, ensure_dir, get_project_root
from modules.visual_control import (
    DEFAULT_CAPTURE_WORKER_STALE_AFTER_MINUTES,
    capture_worker_liveness,
    control_blocks_dispatch,
    load_control_state,
    session_runtime_summary,
    write_worker_runtime,
)


@dataclass
class SchedulerConfig:
    daily_keyword_budget: int = 120
    daily_session_count: int = 4
    capture_freshness_days: int = 30
    session_due_times: str = ""
    session_due_interval_minutes: int = 0
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
        session_due_times=config.get("SCHEDULER", "session_due_times", fallback="").strip(),
        session_due_interval_minutes=max(
            0,
            config.getint("SCHEDULER", "session_due_interval_minutes", fallback=0),
        ),
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
    sessions = _assign_sessions(selected, scheduler.daily_session_count, today, scheduler)

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
        "created_at": today.isoformat(timespec="seconds"),
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


def heartbeat_daily_collection(
    raw_input_file: Optional[str] = None,
    config_file: str = "config/settings.ini",
    plan_id: Optional[str] = None,
    session_index: Optional[int] = None,
    limit: Optional[int] = None,
    random_sample: Optional[int] = None,
    random_seed: Optional[int] = None,
    session_count: Optional[int] = None,
    mode: str = "all",
    manual_state: Optional[str] = None,
    force_lease: bool = False,
) -> Dict[str, Any]:
    """
    Short-lived scheduler heartbeat for daily visual collection.

    The heartbeat owns only control-plane decisions. It may sync existing worker
    output and prepare Midscene contracts, but it never opens Chrome, touches
    Taobao, or starts a background capture process.
    """
    mode = str(mode or "all").strip().lower()
    if mode not in {"sync", "prepare", "dispatch", "all"}:
        raise ValueError(f"不支持 heartbeat mode: {mode}")

    plan_id = plan_id or _today_plan_id()
    control = load_control_state(plan_id)
    result: Dict[str, Any] = {
        "ok": True,
        "action": "noop",
        "mode": mode,
        "plan_id": plan_id,
        "session_index": session_index,
        "control": control,
        "sync": [],
        "prepare": None,
        "dispatch": None,
        "status": _status_if_plan_exists(plan_id),
    }

    if mode in {"sync", "all"}:
        result["sync"] = _sync_existing_worker_results(plan_id, session_index)
        if result["sync"]:
            result["action"] = "synced"
        stale = _mark_stale_capture_workers_for_heartbeat(plan_id, session_index, config_file)
        if stale:
            result["stale_workers"] = stale
            if result["action"] == "noop":
                result["action"] = "stale_recovered"
            result["reason"] = stale[0].get("reason", "capture_worker_stale")

    plan_block = control_blocks_dispatch(control)
    if plan_block.get("blocked"):
        return _heartbeat_paused(plan_id, session_index, control, plan_block, result)

    if mode in {"prepare", "all"}:
        tick = auto_tick_daily_collection(
            raw_input_file=raw_input_file,
            config_file=config_file,
            plan_id=plan_id,
            session_index=session_index,
            limit=limit,
            random_sample=random_sample,
            random_seed=random_seed,
            session_count=session_count,
            prepare_requests=False,
            force_lease=force_lease,
        )
        result["prepare"] = tick
        result["session_index"] = tick.get("session_index") or session_index
        result["status"] = tick.get("status") or _status_if_plan_exists(plan_id)
        if tick.get("action") == "noop":
            result["action"] = result["action"] if result["action"] != "noop" else "noop"
            result["reason"] = tick.get("reason", "")
        else:
            chosen = int(tick.get("session_index") or 0)
            session_block = control_blocks_dispatch(control, chosen)
            if session_block.get("blocked"):
                return _heartbeat_paused(plan_id, chosen, control, session_block)

            from modules.visual_pipeline import run_visual_collection

            request_result = run_visual_collection(
                plan_id,
                config_file=config_file,
                limit=limit,
                manual_state=manual_state,
                session_index=chosen,
                force_lease=force_lease,
            )
            tick["request_result"] = request_result
            tick["action"] = "requests_prepared"
            result["action"] = "prepared"
            result["prepare"] = tick
            result["status"] = scheduler_status(plan_id)
            _write_heartbeat_runtime(plan_id, chosen, "prepared", result)

    if mode in {"dispatch", "all"}:
        dispatch_session = int(result.get("session_index") or session_index or 0)
        if dispatch_session <= 0 and mode == "dispatch":
            dispatch_session = _dispatch_session_from_existing_contracts(plan_id)
            result["session_index"] = dispatch_session or result.get("session_index")
        if dispatch_session > 0:
            session_block = control_blocks_dispatch(control, dispatch_session)
            if session_block.get("blocked"):
                return _heartbeat_paused(plan_id, dispatch_session, control, session_block)
            dispatch = _dispatch_advice(
                plan_id,
                dispatch_session,
                config_file=config_file,
                limit=limit,
                manual_state=manual_state,
                force_lease=force_lease,
            )
            result["dispatch"] = dispatch
            if dispatch.get("contract_exists"):
                result["action"] = "dispatch_advised"
                if dispatch.get("capture_worker_stale"):
                    result["reason"] = dispatch.get("reason", "capture_worker_stale")
                runtime_status = "failed_recoverable" if dispatch.get("capture_worker_stale") else "dispatch_advised"
                _write_heartbeat_runtime(plan_id, dispatch_session, runtime_status, result)
            elif result["action"] == "noop":
                result["reason"] = "no_prepared_contract"

    if result.get("session_index"):
        result["runtime"] = session_runtime_summary(plan_id, int(result["session_index"]))
    result["status"] = _status_if_plan_exists(plan_id)
    return result


def _heartbeat_paused(
    plan_id: str,
    session_index: Optional[int],
    control: Dict[str, Any],
    block: Dict[str, Any],
    partial_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if session_index is not None:
        _write_heartbeat_runtime(
            plan_id,
            int(session_index),
            "paused",
            {"block": block, "control": control},
        )
    result = {
        "ok": True,
        "action": "paused",
        "plan_id": plan_id,
        "session_index": session_index,
        "reason": block.get("reason", "control_blocked"),
        "control": control,
        "block": block,
        "status": _status_if_plan_exists(plan_id),
    }
    if partial_result:
        for key in ("mode", "sync", "prepare", "dispatch", "stale_workers", "runtime"):
            if key in partial_result:
                result[key] = partial_result[key]
    return result


def _sync_existing_worker_results(
    plan_id: str,
    session_index: Optional[int],
) -> List[Dict[str, Any]]:
    from modules.visual_pipeline import sync_midscene_worker_results

    synced = []
    for idx in _sync_candidate_sessions(plan_id, session_index):
        worker_result = _session_worker_result_path(plan_id, idx)
        if not os.path.exists(worker_result) and not _session_has_keyword_results(plan_id, idx):
            continue
        sync_result = sync_midscene_worker_results(plan_id, idx)
        sync_result["worker_result"] = worker_result
        synced.append(sync_result)
        _write_heartbeat_runtime(
            plan_id,
            idx,
            "synced",
            {"sync_result": sync_result},
        )
    return synced


def _session_has_keyword_results(plan_id: str, session_index: int) -> bool:
    """Allow heartbeat sync to consume per-keyword capture output mid-session."""
    try:
        from modules.visual_capture import keyword_evidence_dir
        from modules.visual_pipeline import load_visual_manifest, task_dir_for_run

        task_dir = task_dir_for_run(plan_id)
        manifest = load_visual_manifest(plan_id)
    except Exception:
        return False

    for record in manifest.get("records", []):
        record_session = record.get("extra", {}).get("daily_session_index")
        if int(record_session or 0) != int(session_index):
            continue
        keyword = record.get("keyword", "")
        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        if os.path.exists(os.path.join(evidence_dir, "keyword_result.json")):
            return True
    return False


def _sync_candidate_sessions(plan_id: str, session_index: Optional[int]) -> List[int]:
    if session_index is not None:
        return [int(session_index)]
    status = _status_if_plan_exists(plan_id)
    session_keys = status.get("by_session", {}).keys()
    indices = []
    for key in session_keys:
        try:
            indices.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(set(indices))


def _dispatch_session_from_existing_contracts(plan_id: str) -> int:
    for idx in _sync_candidate_sessions(plan_id, None):
        if os.path.exists(_session_contract_path(plan_id, idx)):
            return idx
    return 0


def _dispatch_advice(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    limit: Optional[int] = None,
    manual_state: Optional[str] = None,
    force_lease: bool = False,
) -> Dict[str, Any]:
    contract = _session_contract_path(plan_id, session_index)
    instructions = os.path.join(
        session_dir_for(plan_id, session_index),
        "midscene_session_worker_instructions.md",
    )
    result_path = _session_worker_result_path(plan_id, session_index)
    liveness = capture_worker_liveness(
        plan_id,
        session_index,
        stale_after_seconds=_capture_worker_stale_after_seconds(config_file),
    )
    manifest_state = _session_manifest_recovery_state(plan_id, session_index)
    recovery_prepare_result = None
    recovery_reason = ""
    stale_manifest_update = None
    if liveness.get("stale"):
        recovery_reason = liveness.get("reason", "capture_worker_stale")
        stale_manifest_update = _mark_session_records_recoverable_stale(
            plan_id,
            session_index,
            liveness,
        )
        manifest_state["stale_manifest_update"] = stale_manifest_update
        manifest_state = _session_manifest_recovery_state(plan_id, session_index)
        manifest_state["stale_manifest_update"] = stale_manifest_update
    elif liveness.get("session_result_exists") and not liveness.get("session_result_success"):
        recovery_reason = (
            f"session_result:{liveness.get('session_result_status') or 'unknown'}"
        )

    should_prepare_recovery_contract = (
        not bool(liveness.get("active"))
        and not bool(liveness.get("session_result_success"))
        and bool(recovery_reason)
        and int(manifest_state.get("runnable_count", 0)) > 0
    )
    if should_prepare_recovery_contract:
        from modules.visual_pipeline import run_visual_collection

        recovery_prepare_result = run_visual_collection(
            plan_id,
            config_file=config_file,
            limit=limit,
            manual_state=manual_state,
            session_index=session_index,
            force_lease=True if (liveness.get("stale") or liveness.get("session_result_exists")) else force_lease,
        )
        manifest_state = _session_manifest_recovery_state(plan_id, session_index)
        if stale_manifest_update is not None:
            manifest_state["stale_manifest_update"] = stale_manifest_update

    capture_command = (
        f"python3 harness.py visual-capture-worker --contract {json.dumps(contract, ensure_ascii=False)}"
    )
    has_runnable_manifest_records = int(manifest_state.get("runnable_count", 0)) > 0
    capture_start_allowed = (
        os.path.exists(contract)
        and has_runnable_manifest_records
        and not bool(liveness.get("active"))
        and not bool(liveness.get("session_result_success"))
        and (
            (
                not recovery_reason
                and not bool(liveness.get("session_result_exists"))
            )
            or (
                bool(recovery_reason)
                and (
                    int(manifest_state.get("runnable_count", 0)) > 0
                    or bool(recovery_prepare_result)
                )
            )
        )
    )
    worker_commands = {
        "codex_extract_prepare": (
            f"python3 harness.py visual-codex-extract-prepare "
            f"--plan-id {json.dumps(plan_id, ensure_ascii=False)} --session {int(session_index)}"
        ),
        "codex_extract_dispatch_advice": (
            f"python3 harness.py visual-codex-extract-dispatch "
            f"--plan-id {json.dumps(plan_id, ensure_ascii=False)} --session {int(session_index)}"
        ),
        "codex_extract_dispatch_start": (
            f"python3 harness.py visual-codex-extract-dispatch "
            f"--plan-id {json.dumps(plan_id, ensure_ascii=False)} --session {int(session_index)} --start"
        ),
    }
    reason = recovery_reason or liveness.get("reason", "")
    if liveness.get("stale") and capture_start_allowed:
        worker_commands["capture"] = capture_command
        worker_commands["capture_recoverable_restart"] = capture_command
    elif capture_start_allowed:
        worker_commands["capture"] = capture_command
    return {
        "ok": True,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "contract": contract,
        "contract_exists": os.path.exists(contract),
        "instructions": instructions,
        "instructions_exists": os.path.exists(instructions),
        "expected_result": result_path,
        "capture_worker_liveness": liveness,
        "capture_worker_stale": bool(liveness.get("stale")),
        "capture_start_allowed": capture_start_allowed,
        "manifest_recovery_state": manifest_state,
        "recovery_prepare_result": recovery_prepare_result,
        "reason": reason,
        "worker_commands": worker_commands,
        "suggested_command": (
            f"python3 harness.py visual-sync-worker {plan_id} --session {int(session_index)}"
        ),
        "notes": (
            "v1 heartbeat does not start a background worker. Hand the contract "
            "to the bounded Midscene computer worker only when "
            "capture_start_allowed is true, then run the suggested sync command "
            "after session_worker_result.json exists."
        ),
    }


def _mark_stale_capture_workers_for_heartbeat(
    plan_id: str,
    session_index: Optional[int],
    config_file: str,
) -> List[Dict[str, Any]]:
    stale = []
    stale_after_seconds = _capture_worker_stale_after_seconds(config_file)
    for idx in _sync_candidate_sessions(plan_id, session_index):
        liveness = capture_worker_liveness(plan_id, idx, stale_after_seconds=stale_after_seconds)
        if not liveness.get("stale"):
            continue
        manifest_update = _mark_session_records_recoverable_stale(plan_id, idx, liveness)
        item = {
            "plan_id": plan_id,
            "session_index": idx,
            "reason": liveness.get("reason", "capture_worker_stale"),
            "stale_reason": liveness.get("stale_reason", ""),
            "runtime": liveness.get("runtime", {}),
            "manifest_update": manifest_update,
        }
        stale.append(item)
        _write_heartbeat_runtime(
            plan_id,
            idx,
            "failed_recoverable",
            {
                "action": "stale_recovered",
                "reason": item["reason"],
                "plan_id": plan_id,
                "session_index": idx,
            },
        )
    return stale


def _session_manifest_recovery_state(plan_id: str, session_index: int) -> Dict[str, Any]:
    try:
        from modules.visual_pipeline import load_visual_manifest

        manifest = load_visual_manifest(plan_id)
    except Exception as exc:
        return {"runnable_count": 0, "failed_recoverable_count": 0, "error": str(exc)}
    runnable_count = 0
    failed_recoverable_count = 0
    by_status: Dict[str, int] = {}
    for record in manifest.get("records", []):
        record_session = record.get("extra", {}).get("daily_session_index")
        if int(record_session or 0) != int(session_index):
            continue
        status = str(record.get("status") or "")
        by_status[status] = by_status.get(status, 0) + 1
        if status in RUNNABLE_STATUSES:
            runnable_count += 1
        if status == "failed_recoverable":
            failed_recoverable_count += 1
    return {
        "runnable_count": runnable_count,
        "failed_recoverable_count": failed_recoverable_count,
        "by_status": by_status,
    }


def _mark_session_records_recoverable_stale(
    plan_id: str,
    session_index: int,
    liveness: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        from modules.visual_pipeline import load_visual_manifest, save_visual_manifest
        from modules.visual_capture import keyword_evidence_dir
        from modules.visual_pipeline import task_dir_for_run

        manifest = load_visual_manifest(plan_id)
        task_dir = task_dir_for_run(plan_id)
    except Exception as exc:
        return {"updated": 0, "error": str(exc)}
    now = datetime.now().isoformat(timespec="seconds")
    updated = 0
    skipped_keyword_results = 0
    for record in manifest.get("records", []):
        record_session = record.get("extra", {}).get("daily_session_index")
        if int(record_session or 0) != int(session_index):
            continue
        if str(record.get("status") or "") in {"captured", "extracted", "success", "skipped", "failed_hard"}:
            continue
        keyword = record.get("keyword", "")
        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        if os.path.exists(os.path.join(evidence_dir, "keyword_result.json")):
            skipped_keyword_results += 1
            continue
        record["status"] = "failed_recoverable"
        record["failure_reason"] = "capture_worker_stale"
        record["last_action"] = "capture_worker_stale_recovered"
        record["updated_at"] = now
        record.setdefault("extra", {})
        record["extra"]["capture_worker_stale_reason"] = liveness.get("stale_reason", "")
        record["extra"]["capture_worker_runtime"] = liveness.get("runtime", {})
        updated += 1
    if updated > 0:
        session = manifest.setdefault("session", {})
        session["status"] = "failed_recoverable"
        session["worker_status"] = "failed_recoverable"
        session["failure_reason"] = "capture_worker_stale"
        session["stale_reason"] = liveness.get("stale_reason", "")
        session["updated_at"] = now
    save_visual_manifest(plan_id, manifest)
    return {"updated": updated, "skipped_keyword_results": skipped_keyword_results}


def _capture_worker_stale_after_seconds(config_file: str = "config/settings.ini") -> float:
    config = ConfigManager(config_file)
    minutes = config.getint(
        "SCHEDULER",
        "capture_worker_stale_after_minutes",
        fallback=DEFAULT_CAPTURE_WORKER_STALE_AFTER_MINUTES,
    )
    return float(max(1, int(minutes)) * 60)


def _session_contract_path(plan_id: str, session_index: int) -> str:
    return os.path.join(
        session_dir_for(plan_id, session_index),
        "midscene_session_worker_request.json",
    )


def _session_worker_result_path(plan_id: str, session_index: int) -> str:
    return os.path.join(session_dir_for(plan_id, session_index), "session_worker_result.json")


def _write_heartbeat_runtime(
    plan_id: str,
    session_index: int,
    status: str,
    payload: Dict[str, Any],
) -> None:
    compact_payload = {
        "action": payload.get("action", status),
        "mode": payload.get("mode", ""),
        "reason": payload.get("reason", ""),
        "plan_id": payload.get("plan_id", plan_id),
        "session_index": payload.get("session_index", session_index),
    }
    if payload.get("sync_result") is not None:
        compact_payload["sync_result"] = payload.get("sync_result")
    if payload.get("sync") is not None:
        compact_payload["sync_count"] = len(payload.get("sync") or [])
    if payload.get("dispatch") is not None:
        dispatch = payload.get("dispatch") or {}
        compact_payload["dispatch"] = {
            "contract": dispatch.get("contract", ""),
            "contract_exists": dispatch.get("contract_exists", False),
            "expected_result": dispatch.get("expected_result", ""),
        }
    write_worker_runtime(
        plan_id,
        session_index,
        "heartbeat",
        status,
        heartbeat=True,
        heartbeat_action=compact_payload["action"],
        heartbeat_payload=compact_payload,
    )


def _status_if_plan_exists(plan_id: str) -> Dict[str, Any]:
    try:
        return scheduler_status(plan_id)
    except FileNotFoundError:
        return {
            "plan_id": plan_id,
            "selected_count": 0,
            "daily_keyword_budget": 0,
            "daily_session_count": 0,
            "by_status": {},
            "by_session": {},
            "task_dir": os.path.join(get_project_root(), "data", "tasks", plan_id),
            "exists": False,
        }


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


def _assign_sessions(
    selected: List[Dict[str, Any]],
    session_count: int,
    base_time: Optional[datetime] = None,
    scheduler: Optional[SchedulerConfig] = None,
) -> List[Dict[str, Any]]:
    total = len(selected)
    if total == 0:
        return []
    base_time = base_time or datetime.now()
    schedule = _build_session_schedule(base_time, session_count, scheduler)
    per_session = int(math.ceil(total / max(1, session_count)))
    sessions = []
    for idx, item in enumerate(selected):
        session_index = min(session_count, idx // per_session + 1)
        item["session_index"] = session_index
    for session_index in range(1, session_count + 1):
        count = sum(1 for item in selected if item["session_index"] == session_index)
        due = schedule[session_index - 1]
        sessions.append(
            {
                "session_index": session_index,
                "keyword_count": count,
                "status": "pending",
                "due_at": due["due_at"],
                "due_time": due["due_time"],
                "schedule_mode": due["schedule_mode"],
            }
        )
    return sessions


def _build_session_schedule(
    base_time: datetime,
    session_count: int,
    scheduler: Optional[SchedulerConfig],
) -> List[Dict[str, str]]:
    session_count = max(1, int(session_count))
    interval_minutes = int(getattr(scheduler, "session_due_interval_minutes", 0) or 0)
    fixed_times = str(getattr(scheduler, "session_due_times", "") or "").strip()
    if interval_minutes > 0:
        return [
            _schedule_item(
                base_time + timedelta(minutes=interval_minutes * idx),
                "interval_from_plan_start",
            )
            for idx in range(session_count)
        ]
    if fixed_times:
        parsed = _parse_session_due_times(fixed_times)
        if len(parsed) != session_count:
            raise ValueError(
                "SCHEDULER.session_due_times 的数量必须等于 daily_session_count；"
                f"当前 {len(parsed)} 个时间 / {session_count} 个 session。"
            )
        return [_schedule_item(base_time.replace(hour=hour, minute=minute, second=0, microsecond=0), "fixed_time") for hour, minute in parsed]
    minutes_per_session = 1440 / session_count
    day_start = base_time.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        _schedule_item(day_start + timedelta(minutes=minutes_per_session * idx), "even_day_split")
        for idx in range(session_count)
    ]


def _parse_session_due_times(value: str) -> List[tuple]:
    result = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            hour_text, minute_text = item.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError as exc:
            raise ValueError(f"无效 session_due_times 时间: {item}") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError(f"无效 session_due_times 时间: {item}")
        result.append((hour, minute))
    for previous, current in zip(result, result[1:]):
        if current <= previous:
            raise ValueError("SCHEDULER.session_due_times 必须按时间严格递增，且不能重复")
    return result


def _schedule_item(due_at: datetime, mode: str) -> Dict[str, str]:
    return {
        "due_at": due_at.isoformat(timespec="seconds"),
        "due_time": due_at.strftime("%H:%M"),
        "schedule_mode": mode,
    }


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


def _choose_due_session(
    plan: Dict[str, Any],
    manifest: Dict[str, Any],
    now: Optional[datetime] = None,
) -> int:
    sessions = plan.get("sessions", [])
    if not sessions:
        return 0
    session_count = max(1, int(plan.get("daily_session_count") or len(sessions) or 1))
    runnable_by_session = _runnable_counts_by_session(manifest)
    due_indices = _due_session_indices(sessions, session_count, now or datetime.now())
    for idx in due_indices:
        if runnable_by_session.get(idx, 0) > 0:
            return idx
    return 0


def _due_session_indices(
    sessions: List[Dict[str, Any]],
    session_count: int,
    now: datetime,
) -> List[int]:
    due = []
    explicit_due_count = sum(1 for session in sessions if str(session.get("due_at") or "").strip())
    if explicit_due_count and explicit_due_count != len(sessions):
        raise ValueError("daily_plan sessions 的 due_at 不完整；请重新生成 plan 或补齐 session due-time")
    for session in sessions:
        idx = int(session.get("session_index") or 0)
        if idx <= 0:
            continue
        due_at = str(session.get("due_at") or "").strip()
        if not due_at:
            continue
        try:
            parsed = datetime.fromisoformat(due_at)
        except ValueError as exc:
            raise ValueError(f"daily_plan session {idx} 的 due_at 无效: {due_at}") from exc
        if parsed <= now:
            due.append(idx)
    if explicit_due_count:
        return sorted(set(due))
    minute_of_day = now.hour * 60 + now.minute
    minutes_per_session = 1440 / max(1, session_count)
    due_session = min(session_count, max(1, int(minute_of_day // minutes_per_session) + 1))
    return list(range(1, due_session + 1))


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
