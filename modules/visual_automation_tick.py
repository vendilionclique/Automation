"""
Thin Codex App Automation tick for visual collection.

This module intentionally stays deterministic and short-lived: it asks the
scheduler heartbeat for dispatch advice, and optionally hands a due session to
the session-bounded capture watchdog.
"""
from typing import Any, Dict, Optional

from modules import visual_scheduler
from modules.visual_capture_watchdog import run_capture_watchdog


def run_visual_automation_tick(
    raw_input_file: Optional[str] = None,
    config_file: str = "config/settings.ini",
    plan_id: Optional[str] = None,
    session_index: Optional[int] = None,
    limit: Optional[int] = None,
    random_sample: Optional[int] = None,
    random_seed: Optional[int] = None,
    session_count: Optional[int] = None,
    force_lease: bool = False,
    start_capture: bool = False,
) -> Dict[str, Any]:
    """
    Run one automation tick.

    The tick starts capture only when heartbeat dispatch explicitly allows it
    and provides a capture command. It does not daemonize, use nohup, or bypass
    supervisor/scheduler control.
    """
    heartbeat = visual_scheduler.heartbeat_daily_collection(
        raw_input_file=raw_input_file,
        config_file=config_file,
        plan_id=plan_id,
        session_index=session_index,
        limit=limit,
        random_sample=random_sample,
        random_seed=random_seed,
        session_count=session_count,
        mode="all",
        force_lease=force_lease,
    )
    dispatch = heartbeat.get("dispatch") or {}
    commands = dispatch.get("worker_commands") or {}
    capture_command = commands.get("capture")
    capture_start_allowed = bool(dispatch.get("capture_start_allowed"))
    resolved_plan_id = heartbeat.get("plan_id") or dispatch.get("plan_id") or plan_id
    resolved_session_index = heartbeat.get("session_index") or dispatch.get("session_index") or session_index

    capture_started = False
    capture_returncode = None
    capture_error = None
    watchdog_result = None
    sync_result = None
    sync_reason = "not_started"

    if not start_capture:
        sync_reason = "dry_run"
    elif not capture_start_allowed:
        sync_reason = dispatch.get("reason") or "capture_start_not_allowed"
    elif not capture_command:
        sync_reason = "capture_command_missing"
    else:
        if not resolved_plan_id or not resolved_session_index:
            capture_error = "resolved_plan_or_session_missing"
            sync_reason = capture_error
        else:
            watchdog_result = run_capture_watchdog(
                plan_id=str(resolved_plan_id),
                session_index=int(resolved_session_index),
                raw_input_file=raw_input_file,
                start=True,
                config_file=config_file,
            )
            capture_started = watchdog_result.get("status") != "skipped"
            capture_returncode = watchdog_result.get("last_capture_returncode")
            sync_result = watchdog_result.get("last_heartbeat")
            sync_reason = (
                watchdog_result.get("reason")
                or (sync_result or {}).get("reason")
                or (sync_result or {}).get("action")
                or "watchdog_finished"
            )

    return {
        "ok": True,
        "action": "automation_tick",
        "heartbeat_action": heartbeat.get("action"),
        "plan_id": resolved_plan_id,
        "session_index": resolved_session_index,
        "capture_start_allowed": capture_start_allowed,
        "capture_command_exists": bool(capture_command),
        "capture_started": capture_started,
        "capture_returncode": capture_returncode,
        "capture_error": capture_error,
        "watchdog_result": watchdog_result,
        "sync_result": sync_result,
        "sync_reason": sync_reason,
        "heartbeat": heartbeat,
    }
