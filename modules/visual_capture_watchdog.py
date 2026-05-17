"""
Session-bounded capture watchdog for visual collection.

The watchdog is a local deterministic drain around the existing scheduler
heartbeat. It never touches Chrome, Midscene, screenshots, or product rows; it
only starts a capture worker when heartbeat dispatch explicitly says that a
single capture worker may start.
"""
import json
import os
import shlex
import subprocess
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from modules import visual_scheduler
from modules.page_sampling import write_task_event
from modules.utils import ConfigManager, ensure_dir, get_project_root


TERMINAL_SESSION_STATUSES = {
    "captured",
    "completed",
    "success",
    "succeeded",
    "extracted",
    "skipped",
    "failed_hard",
}

HUMAN_OR_CONTROL_REASONS = {
    "paused",
    "stopped",
    "cooling_down",
    "locked",
    "stop_or_locked",
    "control_blocked",
    "paused_needs_human",
    "paused_needs_supervisor",
    "login_required",
    "captcha_required",
    "captcha_or_risk",
    "risk",
    "risk_suspected",
    "security_required",
    "security_verification",
    "real_not_available",
    "automation_permission_blocked",
    "setup_drift",
}


NowFn = Callable[[], datetime]
SleepFn = Callable[[float], None]
PopenFactory = Callable[..., Any]
PidExistsFn = Callable[[int], bool]


def run_capture_watchdog(
    plan_id: str,
    session_index: int,
    raw_input_file: Optional[str] = None,
    start: bool = False,
    poll_seconds: Optional[float] = None,
    idle_timeout_seconds: Optional[float] = None,
    max_restarts: Optional[int] = None,
    config_path: Optional[str] = None,
    config_file: Optional[str] = None,
    project_root: Optional[str] = None,
    now_fn: Optional[NowFn] = None,
    sleep_fn: Optional[SleepFn] = None,
    popen_factory: Optional[PopenFactory] = None,
    pid_exists_fn: Optional[PidExistsFn] = None,
) -> Dict[str, Any]:
    """
    Drain one planned capture session under scheduler/supervisor control.

    Args:
        plan_id: Daily visual plan id.
        session_index: One-based session number inside the plan.
        raw_input_file: Optional ledger path used when heartbeat needs to
            prepare a session contract for an existing plan.
        start: If false, run one heartbeat cycle and exit without starting a worker.
        poll_seconds: Worker polling interval while a child process is alive.
            Defaults to [CAPTURE_WATCHDOG] poll_seconds.
        idle_timeout_seconds: Exit when no progress occurs for this many seconds.
            Defaults to [CAPTURE_WATCHDOG] idle_timeout_seconds.
        max_restarts: Number of recoverable restarts after the first worker start.
            Defaults to [CAPTURE_WATCHDOG] max_restarts.
        config_path/config_file: Scheduler config file path passed through to
            heartbeat. config_file is accepted for harness/CLI consistency.
        project_root: Working directory for capture worker Popen.
        now_fn/sleep_fn/popen_factory: Injection points for tests.
        pid_exists_fn: Injection point for watchdog lock stale-pid tests.
    """
    if not plan_id:
        raise ValueError("plan_id is required")
    session_index = int(session_index)
    config_path = config_path or config_file or "config/settings.ini"
    watchdog_config = _watchdog_config(config_path)
    poll_seconds = float(
        poll_seconds
        if poll_seconds is not None
        else watchdog_config["poll_seconds"]
    )
    idle_timeout_seconds = float(
        idle_timeout_seconds
        if idle_timeout_seconds is not None
        else watchdog_config["idle_timeout_seconds"]
    )
    max_restarts = int(
        max_restarts
        if max_restarts is not None
        else watchdog_config["max_restarts"]
    )
    poll_seconds = max(0.1, poll_seconds)
    idle_timeout_seconds = max(1.0, idle_timeout_seconds)
    max_restarts = max(0, max_restarts)
    project_root = project_root or get_project_root()
    now_fn = now_fn or datetime.now
    sleep_fn = sleep_fn or time.sleep
    popen_factory = popen_factory or subprocess.Popen
    pid_exists_fn = pid_exists_fn or _pid_exists

    paths = _watchdog_paths(project_root, plan_id, session_index)
    ensure_dir(paths["session_dir"])
    lock_acquired, lock_reason = _acquire_watchdog_lock(
        paths["lock_path"],
        plan_id=plan_id,
        session_index=session_index,
        now_fn=now_fn,
        pid_exists_fn=pid_exists_fn,
    )
    if not lock_acquired:
        return {
            "ok": True,
            "action": "capture_watchdog",
            "plan_id": plan_id,
            "session_index": session_index,
            "status": "skipped",
            "reason": lock_reason,
            "cycles": 0,
            "restart_count": 0,
            "runtime_path": paths["runtime_path"],
            "stdout_path": paths["stdout_path"],
            "stderr_path": paths["stderr_path"],
            "lock_path": paths["lock_path"],
            "last_heartbeat": None,
        }

    runtime: Dict[str, Any] = {
        "status": "running",
        "pid": os.getpid(),
        "started_at": _iso(now_fn()),
        "updated_at": _iso(now_fn()),
        "cycles": 0,
        "restart_count": 0,
        "current_capture_pid": None,
        "last_heartbeat_action": "",
        "last_capture_returncode": None,
        "last_reason": "started",
        "stdout_path": paths["stdout_path"],
        "stderr_path": paths["stderr_path"],
    }
    _write_runtime(paths["runtime_path"], runtime, now_fn)
    _event(project_root, plan_id, session_index, "capture_watchdog_started", status="running")

    worker = None
    worker_stdout = None
    worker_stderr = None
    worker_started_once = False
    last_progress_at = now_fn()
    last_heartbeat: Optional[Dict[str, Any]] = None
    finish_reason = ""
    finish_status = "finished"

    try:
        while True:
            runtime["cycles"] = int(runtime.get("cycles") or 0) + 1
            heartbeat = visual_scheduler.heartbeat_daily_collection(
                raw_input_file=raw_input_file,
                plan_id=plan_id,
                session_index=session_index,
                config_file=config_path,
                mode="all",
            )
            last_heartbeat = heartbeat
            action = str(heartbeat.get("action") or "")
            runtime["last_heartbeat_action"] = action
            dispatch = heartbeat.get("dispatch") or {}
            reason = _heartbeat_reason(heartbeat, dispatch)
            runtime["last_reason"] = reason or action or "heartbeat"
            _write_runtime(paths["runtime_path"], runtime, now_fn)
            _event(
                project_root,
                plan_id,
                session_index,
                "capture_watchdog_cycle",
                cycle=runtime["cycles"],
                heartbeat_action=action,
                reason=runtime["last_reason"],
                capture_start_allowed=bool(dispatch.get("capture_start_allowed")),
            )

            capture_command = (dispatch.get("worker_commands") or {}).get("capture")
            can_start_capture = bool(dispatch.get("capture_start_allowed")) and bool(capture_command)
            terminal = _terminal_reason(heartbeat, dispatch)
            if terminal and not _should_ignore_terminal_for_allowed_capture(
                terminal,
                heartbeat,
                dispatch,
                can_start_capture=can_start_capture,
            ):
                finish_reason = terminal
                break

            if action and action not in {"noop", "dispatch_advised"}:
                last_progress_at = now_fn()
            if not start:
                finish_reason = "dry_run"
                break

            if worker is not None:
                returncode = worker.poll()
                if returncode is None:
                    runtime["current_capture_pid"] = getattr(worker, "pid", None)
                    _write_runtime(paths["runtime_path"], runtime, now_fn)
                    sleep_fn(poll_seconds)
                    returncode = worker.poll()
                if returncode is None:
                    continue

                runtime["last_capture_returncode"] = returncode
                runtime["current_capture_pid"] = None
                worker = None
                _write_runtime(paths["runtime_path"], runtime, now_fn)
                _event(
                    project_root,
                    plan_id,
                    session_index,
                    "capture_watchdog_worker_exited",
                    returncode=returncode,
                )
                _close_quietly(worker_stdout)
                _close_quietly(worker_stderr)
                worker_stdout = None
                worker_stderr = None
                sync_result = visual_scheduler.heartbeat_daily_collection(
                    raw_input_file=raw_input_file,
                    plan_id=plan_id,
                    session_index=session_index,
                    config_file=config_path,
                    mode="sync",
                )
                last_heartbeat = sync_result
                runtime["last_heartbeat_action"] = str(sync_result.get("action") or "sync")
                runtime["last_reason"] = sync_result.get("reason") or runtime["last_heartbeat_action"]
                _write_runtime(paths["runtime_path"], runtime, now_fn)
                last_progress_at = now_fn()
                continue

            if can_start_capture and capture_command:
                if worker_started_once and int(runtime.get("restart_count") or 0) >= max_restarts:
                    finish_reason = "max_restarts_reached"
                    finish_status = "needs_review"
                    _event(
                        project_root,
                        plan_id,
                        session_index,
                        "capture_watchdog_restart_blocked",
                        restart_count=runtime.get("restart_count", 0),
                        max_restarts=max_restarts,
                    )
                    break
                if worker_started_once:
                    runtime["restart_count"] = int(runtime.get("restart_count") or 0) + 1
                worker_stdout = open(paths["stdout_path"], "ab")
                worker_stderr = open(paths["stderr_path"], "ab")
                worker_started_once = True
                try:
                    worker = popen_factory(
                        shlex.split(capture_command),
                        cwd=project_root,
                        stdout=worker_stdout,
                        stderr=worker_stderr,
                    )
                except OSError as exc:
                    runtime["last_capture_returncode"] = -1
                    runtime["current_capture_pid"] = None
                    runtime["last_reason"] = f"capture_worker_popen_failed:{exc}"
                    _write_runtime(paths["runtime_path"], runtime, now_fn)
                    _event(
                        project_root,
                        plan_id,
                        session_index,
                        "capture_watchdog_worker_exited",
                        returncode=-1,
                        error=str(exc),
                    )
                    _close_quietly(worker_stdout)
                    _close_quietly(worker_stderr)
                    worker_stdout = None
                    worker_stderr = None
                    last_progress_at = now_fn()
                    continue
                runtime["current_capture_pid"] = getattr(worker, "pid", None)
                runtime["last_reason"] = "capture_worker_started"
                _write_runtime(paths["runtime_path"], runtime, now_fn)
                _event(
                    project_root,
                    plan_id,
                    session_index,
                    "capture_watchdog_started_worker",
                    command=capture_command,
                    capture_pid=runtime["current_capture_pid"],
                    restart_count=runtime.get("restart_count", 0),
                )
                last_progress_at = now_fn()
                continue

            if _elapsed_seconds(last_progress_at, now_fn()) >= idle_timeout_seconds:
                finish_reason = "idle_timeout"
                finish_status = "needs_review"
                break

            no_work_reason = _no_work_reason(heartbeat, dispatch)
            if no_work_reason:
                finish_reason = no_work_reason
                break

            sleep_fn(poll_seconds)

    finally:
        _close_quietly(worker_stdout)
        _close_quietly(worker_stderr)
        _release_watchdog_lock(paths["lock_path"])

    runtime["status"] = finish_status
    runtime["last_reason"] = finish_reason or "finished"
    runtime["current_capture_pid"] = None
    _write_runtime(paths["runtime_path"], runtime, now_fn)
    _event(
        project_root,
        plan_id,
        session_index,
        "capture_watchdog_finished",
        status=finish_status,
        reason=runtime["last_reason"],
        cycles=runtime.get("cycles", 0),
        restart_count=runtime.get("restart_count", 0),
    )
    return {
        "ok": True,
        "action": "capture_watchdog",
        "plan_id": plan_id,
        "session_index": session_index,
        "status": finish_status,
        "reason": runtime["last_reason"],
        "cycles": runtime.get("cycles", 0),
        "restart_count": runtime.get("restart_count", 0),
        "last_capture_returncode": runtime.get("last_capture_returncode"),
        "runtime_path": paths["runtime_path"],
        "stdout_path": paths["stdout_path"],
        "stderr_path": paths["stderr_path"],
        "lock_path": paths["lock_path"],
        "last_heartbeat": last_heartbeat,
    }


def _watchdog_paths(project_root: str, plan_id: str, session_index: int) -> Dict[str, str]:
    task_dir = os.path.join(project_root, "data", "tasks", plan_id)
    session_dir = os.path.join(task_dir, "sessions", f"session_{int(session_index):02d}")
    return {
        "task_dir": task_dir,
        "session_dir": session_dir,
        "runtime_path": os.path.join(session_dir, "capture_watchdog_runtime.json"),
        "lock_path": os.path.join(session_dir, "capture_watchdog.lock"),
        "stdout_path": os.path.join(session_dir, "capture_watchdog.stdout.log"),
        "stderr_path": os.path.join(session_dir, "capture_watchdog.stderr.log"),
    }


def _watchdog_config(config_path: str) -> Dict[str, Any]:
    config = ConfigManager(config_path)
    section = "CAPTURE_WATCHDOG"
    return {
        "poll_seconds": max(0.1, config.getfloat(section, "poll_seconds", fallback=30.0)),
        "idle_timeout_seconds": max(
            1.0,
            config.getfloat(section, "idle_timeout_seconds", fallback=900.0),
        ),
        "max_restarts": max(0, config.getint(section, "max_restarts", fallback=2)),
    }


def _heartbeat_reason(heartbeat: Dict[str, Any], dispatch: Dict[str, Any]) -> str:
    return str(
        heartbeat.get("reason")
        or dispatch.get("reason")
        or (heartbeat.get("block") or {}).get("reason")
        or ""
    )


def _terminal_reason(heartbeat: Dict[str, Any], dispatch: Dict[str, Any]) -> str:
    action = str(heartbeat.get("action") or "")
    reason = _heartbeat_reason(heartbeat, dispatch)
    if action == "paused":
        return reason or "control_blocked"
    if reason.startswith("session_result:"):
        pass
    elif _matches_any(reason, HUMAN_OR_CONTROL_REASONS):
        return reason

    liveness = dispatch.get("capture_worker_liveness") or {}
    session_status = str(liveness.get("session_result_status") or "").strip().lower()
    session_payload = liveness.get("session_result_payload") or {}
    payload_status = str(session_payload.get("status") or "").strip().lower()
    failure_reason = str(session_payload.get("failure_reason") or "").strip().lower()
    for value in (session_status, payload_status, failure_reason):
        if _matches_any(value, HUMAN_OR_CONTROL_REASONS):
            return value
    if session_status in TERMINAL_SESSION_STATUSES:
        return "session_complete"

    manifest_state = dispatch.get("manifest_recovery_state") or {}
    by_status = manifest_state.get("by_status") or {}
    if any(_matches_any(str(status), HUMAN_OR_CONTROL_REASONS) for status in by_status):
        return "manual_or_control_blocked"
    return ""


def _should_ignore_terminal_for_allowed_capture(
    terminal: str,
    heartbeat: Dict[str, Any],
    dispatch: Dict[str, Any],
    can_start_capture: bool,
) -> bool:
    if not can_start_capture:
        return False
    action = str(heartbeat.get("action") or "")
    if action == "paused":
        return False
    reason = _heartbeat_reason(heartbeat, dispatch).strip().lower()
    if _matches_any(reason, HUMAN_OR_CONTROL_REASONS) and not reason.startswith("session_result:"):
        return False
    liveness = dispatch.get("capture_worker_liveness") or {}
    session_status = str(liveness.get("session_result_status") or "").strip().lower()
    session_payload = liveness.get("session_result_payload") or {}
    payload_status = str(session_payload.get("status") or "").strip().lower()
    failure_reason = str(session_payload.get("failure_reason") or "").strip().lower()
    manifest_state = dispatch.get("manifest_recovery_state") or {}
    by_status = manifest_state.get("by_status") or {}
    stale_session_result_values = {session_status, payload_status, failure_reason}
    if terminal in stale_session_result_values:
        return True
    if reason.startswith("session_result:") and reason.split(":", 1)[1] == terminal:
        return True
    if terminal == "manual_or_control_blocked" and any(
        _matches_any(str(status), HUMAN_OR_CONTROL_REASONS) for status in by_status
    ):
        return True
    return False


def _no_work_reason(heartbeat: Dict[str, Any], dispatch: Dict[str, Any]) -> str:
    if not dispatch:
        return str(heartbeat.get("reason") or "no_dispatch")
    if dispatch.get("capture_start_allowed"):
        return ""
    manifest_state = dispatch.get("manifest_recovery_state") or {}
    runnable_count = int(manifest_state.get("runnable_count") or 0)
    liveness = dispatch.get("capture_worker_liveness") or {}
    if bool(liveness.get("active")):
        return ""
    if bool(liveness.get("session_result_success")):
        return "session_complete"
    if runnable_count <= 0:
        return "no_runnable_keywords"
    if not dispatch.get("contract_exists"):
        return "no_prepared_contract"
    return ""


def _matches_any(value: str, needles: set) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return text in needles or any(needle in text for needle in needles)


def _event(
    project_root: str,
    plan_id: str,
    session_index: int,
    event: str,
    **extra: Any,
) -> None:
    task_dir = os.path.join(project_root, "data", "tasks", plan_id)
    write_task_event(task_dir, event, run_id=plan_id, session_index=session_index, **extra)


def _write_runtime(path: str, payload: Dict[str, Any], now_fn: NowFn) -> None:
    ensure_dir(os.path.dirname(path))
    payload["updated_at"] = _iso(now_fn())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _acquire_watchdog_lock(
    lock_path: str,
    plan_id: str,
    session_index: int,
    now_fn: NowFn,
    pid_exists_fn: PidExistsFn,
) -> tuple[bool, str]:
    payload = {
        "pid": os.getpid(),
        "plan_id": plan_id,
        "session_index": int(session_index),
        "started_at": _iso(now_fn()),
    }
    lock_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    for attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if attempt > 0:
                return False, "capture_watchdog_already_running"
            if not _reclaim_stale_watchdog_lock(lock_path, pid_exists_fn):
                return False, "capture_watchdog_already_running"
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(lock_bytes)
        return True, "acquired"
    return False, "capture_watchdog_already_running"


def _reclaim_stale_watchdog_lock(lock_path: str, pid_exists_fn: PidExistsFn) -> bool:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    try:
        pid = int(payload.get("pid"))
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        pid_exists = pid_exists_fn(pid)
    except Exception:
        return False
    if pid_exists:
        return False
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _release_watchdog_lock(lock_path: str) -> None:
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _elapsed_seconds(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds())


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _close_quietly(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.close()
    except Exception:
        pass
