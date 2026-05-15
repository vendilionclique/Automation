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
WORKER_KINDS = {"capture", "codex_extract"}


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
    }


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


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
