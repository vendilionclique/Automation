"""
Durable control and worker-runtime state for visual collection.

This module intentionally keeps the control plane boring: small JSON files,
short-lived updates, and no model/browser access. Codex or future chat bridges
can call the harness control commands, while the local heartbeat owns the clock.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from modules.page_sampling import write_task_event
from modules.session_capsule import session_dir_for
from modules.utils import ensure_dir, get_project_root


CONTROL_ACTIONS = {"status", "pause", "resume", "stop", "cooldown", "lock", "unlock"}
WORKER_KINDS = {"capture", "codex_extract", "heartbeat"}
DEFAULT_CAPTURE_WORKER_STALE_AFTER_MINUTES = 240
CAPTURE_SESSION_SUCCESS_STATUSES = {"captured", "completed", "success", "succeeded"}


def control_path_for(plan_id: str) -> str:
    return os.path.join(get_project_root(), "data", "tasks", plan_id, "control.json")


def worker_runtime_path(plan_id: str, session_index: int, worker_kind: str) -> str:
    if worker_kind not in WORKER_KINDS:
        raise ValueError(f"未知 worker 类型: {worker_kind}")
    return os.path.join(
        session_dir_for(plan_id, session_index),
        f"{worker_kind}_worker_runtime.json",
    )


def load_control_state(plan_id: str) -> Dict[str, Any]:
    path = control_path_for(plan_id)
    if not os.path.exists(path):
        return _default_control_state(plan_id)
    with open(path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return {**_default_control_state(plan_id), **state}


def write_control_state(plan_id: str, state: Dict[str, Any]) -> str:
    state["plan_id"] = plan_id
    state["updated_at"] = _now()
    return _write_json(control_path_for(plan_id), state)


def apply_control_action(
    plan_id: str,
    action: str,
    session_index: Optional[int] = None,
    reason: str = "",
    cooldown_minutes: int = 60,
) -> Dict[str, Any]:
    if action not in CONTROL_ACTIONS:
        raise ValueError(f"不支持的 control action: {action}")
    state = load_control_state(plan_id)
    now = _now()
    reason = reason or action
    session_key = str(session_index) if session_index is not None else ""

    if action == "pause":
        state["status"] = "paused"
        state["reason"] = reason
        if session_key:
            _session_control(state, session_key).update({"status": "paused", "reason": reason})
    elif action == "resume":
        state["status"] = "running"
        state["reason"] = reason
        state["stop_requested"] = False
        state["locked"] = False
        state["cooldown_until"] = ""
        if session_key:
            _session_control(state, session_key).update(
                {"status": "running", "reason": reason, "cooldown_until": ""}
            )
    elif action == "stop":
        state["status"] = "stopped"
        state["reason"] = reason
        state["stop_requested"] = True
        if session_key:
            _session_control(state, session_key).update({"status": "stopped", "reason": reason})
    elif action == "cooldown":
        until = (datetime.now() + timedelta(minutes=max(1, int(cooldown_minutes)))).isoformat(
            timespec="seconds"
        )
        state["status"] = "cooling_down"
        state["reason"] = reason
        state["cooldown_until"] = until
        if session_key:
            _session_control(state, session_key).update(
                {"status": "cooling_down", "reason": reason, "cooldown_until": until}
            )
    elif action == "lock":
        state["status"] = "locked"
        state["locked"] = True
        state["reason"] = reason
        if session_key:
            _session_control(state, session_key).update({"status": "locked", "reason": reason})
    elif action == "unlock":
        state["status"] = "running"
        state["locked"] = False
        state["reason"] = reason
        if session_key:
            _session_control(state, session_key).update({"status": "running", "reason": reason})

    if action != "status":
        state["last_action"] = action
        state["last_action_at"] = now
        write_control_state(plan_id, state)
        _write_control_event(plan_id, action, session_index=session_index, reason=reason)
    return {
        "ok": True,
        "plan_id": plan_id,
        "action": action,
        "control": state,
        "control_path": control_path_for(plan_id),
    }


def control_blocks_dispatch(state: Dict[str, Any], session_index: Optional[int] = None) -> Dict[str, Any]:
    session = {}
    if session_index is not None:
        session = state.get("sessions", {}).get(str(session_index), {})
    for source in (session, state):
        status = str(source.get("status") or "").strip()
        if status in {"paused", "stopped", "locked"}:
            return {"blocked": True, "reason": status, "source": source}
        if status == "cooling_down":
            until = str(source.get("cooldown_until") or "")
            if not until or _parse_time(until) > datetime.now():
                return {"blocked": True, "reason": "cooling_down", "source": source}
    if bool(state.get("stop_requested")) or bool(state.get("locked")):
        return {"blocked": True, "reason": "stop_or_locked", "source": state}
    return {"blocked": False, "reason": "", "source": {}}


def control_interrupt_for_worker(plan_id: str, session_index: Optional[int] = None) -> Dict[str, Any]:
    """Return the current pause/stop/cooldown block for a running worker."""
    state = load_control_state(plan_id)
    block = control_blocks_dispatch(state, session_index)
    if not block.get("blocked"):
        return {"interrupted": False, "reason": "", "control": state, "block": block}
    return {
        "interrupted": True,
        "reason": block.get("reason") or "control_blocked",
        "control": state,
        "block": block,
    }


def write_worker_runtime(
    plan_id: str,
    session_index: int,
    worker_kind: str,
    status: str,
    **extra: Any,
) -> Dict[str, Any]:
    path = worker_runtime_path(plan_id, session_index, worker_kind)
    existing = load_worker_runtime(plan_id, session_index, worker_kind)
    now = _now()
    payload = {
        **existing,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "worker_kind": worker_kind,
        "status": status,
        "pid": os.getpid(),
        "updated_at": now,
        **extra,
    }
    payload.setdefault("created_at", now)
    _write_json(path, payload)
    return {"ok": True, "runtime": path, "state": payload}


def load_worker_runtime(plan_id: str, session_index: int, worker_kind: str) -> Dict[str, Any]:
    path = worker_runtime_path(plan_id, session_index, worker_kind)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def session_runtime_summary(plan_id: str, session_index: int) -> Dict[str, Any]:
    return {
        "capture_worker": load_worker_runtime(plan_id, session_index, "capture"),
        "codex_extract_worker": load_worker_runtime(plan_id, session_index, "codex_extract"),
        "heartbeat_worker": load_worker_runtime(plan_id, session_index, "heartbeat"),
    }


def capture_worker_liveness(
    plan_id: str,
    session_index: int,
    stale_after_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Inspect capture worker runtime without starting or touching browser state."""
    runtime = load_worker_runtime(plan_id, session_index, "capture")
    session_result = os.path.join(session_dir_for(plan_id, session_index), "session_worker_result.json")
    result_exists = os.path.exists(session_result)
    status = str(runtime.get("status") or "").strip()
    if result_exists:
        session_result_payload = _read_json_safely(session_result)
        session_status = str(session_result_payload.get("status") or "").strip().lower()
        session_success = session_status in CAPTURE_SESSION_SUCCESS_STATUSES
        reason = "session_result_success" if session_success else "session_result_non_success"
        return {
            "active": False,
            "stale": False,
            "reason": reason,
            "status": status,
            "runtime": runtime,
            "session_result": session_result,
            "session_result_exists": True,
            "session_result_status": session_status,
            "session_result_success": session_success,
            "session_result_terminal_success": session_success,
            "session_result_payload": session_result_payload,
        }
    if not runtime:
        return {
            "active": False,
            "stale": False,
            "reason": "runtime_missing",
            "status": "",
            "runtime": {},
            "session_result": session_result,
            "session_result_exists": False,
        }
    if status != "running":
        return {
            "active": False,
            "stale": False,
            "reason": f"runtime_status:{status or 'unknown'}",
            "status": status,
            "runtime": runtime,
            "session_result": session_result,
            "session_result_exists": False,
        }

    stale_reason = _capture_runtime_stale_reason(runtime, stale_after_seconds)
    if stale_reason:
        marked = mark_capture_worker_stale(plan_id, session_index, runtime, stale_reason)
        return {
            "active": False,
            "stale": True,
            "reason": f"capture_worker_stale:{stale_reason}",
            "stale_reason": stale_reason,
            "status": marked.get("status", "failed_recoverable"),
            "runtime": marked,
            "session_result": session_result,
            "session_result_exists": False,
        }
    return {
        "active": True,
        "stale": False,
        "reason": "capture_worker_running",
        "status": status,
        "runtime": runtime,
        "session_result": session_result,
        "session_result_exists": False,
    }


def mark_capture_worker_stale(
    plan_id: str,
    session_index: int,
    runtime: Optional[Dict[str, Any]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    state = dict(runtime or load_worker_runtime(plan_id, session_index, "capture"))
    now = _now()
    original_runtime = dict(state)
    state.update(
        {
            "plan_id": plan_id,
            "session_index": int(session_index),
            "worker_kind": "capture",
            "status": "failed_recoverable",
            "failure_reason": "capture_worker_stale",
            "stale": True,
            "stale_reason": reason or "unknown",
            "stale_detected_at": now,
            "stale_original_pid": original_runtime.get("pid"),
            "stale_original_updated_at": original_runtime.get("updated_at"),
            "stale_original_runtime": original_runtime,
            "updated_at": now,
        }
    )
    _write_json(worker_runtime_path(plan_id, session_index, "capture"), state)
    return state


def _read_json_safely(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {"status": "", "payload": payload}
    except Exception as exc:
        return {"status": "", "read_error": str(exc)}


def _default_control_state(plan_id: str) -> Dict[str, Any]:
    now = _now()
    return {
        "schema": "taobao_visual_control_v1",
        "plan_id": plan_id,
        "status": "running",
        "reason": "",
        "stop_requested": False,
        "locked": False,
        "cooldown_until": "",
        "sessions": {},
        "created_at": now,
        "updated_at": now,
        "last_action": "",
        "last_action_at": "",
    }


def _session_control(state: Dict[str, Any], session_key: str) -> Dict[str, Any]:
    sessions = state.setdefault("sessions", {})
    return sessions.setdefault(session_key, {"status": "running", "reason": "", "cooldown_until": ""})


def _write_control_event(
    plan_id: str,
    action: str,
    session_index: Optional[int] = None,
    reason: str = "",
) -> None:
    task_dir = os.path.join(get_project_root(), "data", "tasks", plan_id)
    write_task_event(
        task_dir,
        event=f"visual_control_{action}",
        run_id=plan_id,
        session_index=session_index,
        reason=reason,
    )


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.max


def _capture_runtime_stale_reason(
    runtime: Dict[str, Any],
    stale_after_seconds: Optional[float],
) -> str:
    pid = runtime.get("pid")
    if not pid:
        return "missing_pid"
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        pass
    except (OSError, ValueError, TypeError):
        return "pid_not_active"
    if not stale_after_seconds or stale_after_seconds <= 0:
        return ""
    updated_at = str(runtime.get("updated_at") or runtime.get("started_at") or "").strip()
    if not updated_at:
        return "missing_updated_at"
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return "invalid_updated_at"
    if datetime.now() - updated > timedelta(seconds=float(stale_after_seconds)):
        return "ttl_exceeded"
    return ""


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
