"""
Capture worker for Taobao visual collection contracts.

The worker executes a bounded session contract through the Midscene computer MCP
over stdio: system screenshots in, system mouse/keyboard/scroll actions out. It
does not read browser DOM, HTML, network, storage, cookies, CDP, or page source.
"""
import base64
import json
import os
import queue
import random
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.page_sampling import write_task_event, write_tile_summary
from modules.page_state import (
    CAPTCHA_REQUIRED,
    CLOSEABLE_POPUP_OVERLAY,
    EMPTY_RESULT,
    LOGIN_REQUIRED,
    UNKNOWN,
    VISIBLE_READY,
    WHITE_SKELETON,
    detect_page_state,
    verify_visible_keyword,
)
from modules.page_state_classifier import (
    PageStateClassifierUnavailable,
    classify_screenshot_json,
)
from modules.utils import ensure_dir
from modules.visual_control import (
    apply_control_action,
    control_interrupt_for_worker,
    write_worker_runtime,
)

try:
    from modules.visual_goal_contract import (
        build_evidence_check as build_goal_evidence_check,
        build_goal_contract,
        decide_capture_gate,
    )
except ImportError:  # pragma: no cover - paired worker may add this module later.
    build_goal_contract = None
    build_goal_evidence_check = None
    decide_capture_gate = None


MCP_REQUIRED_TOOLS = {
    "computer_connect",
    "take_screenshot",
    "act",
}
MCP_OPTIONAL_TOOLS: set = set()
REAL_NOT_AVAILABLE_STATUS = "real_not_available"
CAPTURED_STATUSES = {"captured"}
CAPTURABLE_PAGE_STATES = {
    VISIBLE_READY,
    EMPTY_RESULT,
    "results_end",
    "results_page",
    "search_results",
    "visible_results",
}
CLASSIFIER_KEYWORD_BOUNDARY_STATES = CAPTURABLE_PAGE_STATES - {EMPTY_RESULT}
FOREGROUND_RECOVERY_STOP_REASON = "foreground_recovery_exhausted"
FOREGROUND_NOT_READY_REASON = "chrome_not_foreground"
HARD_ABNORMAL_REASONS = {
    "login_required",
    "captcha_required",
    "captcha_or_risk",
    "risk_suspected",
    "popup_blocked",
    "white_skeleton",
    "page_not_loaded",
    "account_state_changed_or_unusual",
    "automation_permission_blocked",
    "keyword_timeout",
    "midscene_mcp_request_timeout",
    "keyword_mismatch",
    "visible_keyword_mismatch",
    "visible_keyword_unverified",
    "search_submit_unconfirmed",
    "search_results_structure_unverified",
    "rate_limited",
    "manual_review_needed",
    "page_state_detection_failed",
    "home_entry_reset_failed",
}


class WorkerControlInterrupt(RuntimeError):
    def __init__(self, reason: str, status: str = "paused_needs_supervisor"):
        super().__init__(reason)
        self.reason = reason
        self.status = status


class KeywordTimeout(RuntimeError):
    pass


class MCPRequestTimeout(TimeoutError):
    pass


class MidsceneActionAbnormal(RuntimeError):
    def __init__(
        self,
        reason: str,
        rough_state: str,
        message: str,
        diagnostics: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.rough_state = rough_state
        self.message = message
        self.diagnostics = diagnostics or {}


def run_capture_worker(contract_path: str) -> Dict[str, Any]:
    """Run the capture worker against a contract JSON file.

    The worker tries to execute the contract through the local Midscene computer
    MCP stdio launcher. If that environment is not available, it writes explicit
    real_not_available results instead of pretending a capture occurred.
    """
    started = time.monotonic()
    contract = _read_json(contract_path)
    run_id = str(contract.get("run_id") or "")
    session_index = int(contract.get("session_index") or 0)
    task_dir = str(contract.get("task_dir") or os.path.dirname(os.path.dirname(contract_path)))
    session_dir = str(contract.get("session_dir") or os.path.dirname(contract_path))
    session_result_path = str(
        contract.get("session_result_path")
        or os.path.join(session_dir, "session_worker_result.json")
    )
    keyword_tasks = contract.get("keyword_tasks") or []
    now = _now()

    write_worker_runtime(
        run_id,
        session_index,
        "capture",
        "running",
        contract_path=contract_path,
        worker_role="visual_capture_worker",
        schema="taobao_visual_capture_worker_v1",
        started_at=now,
    )
    write_task_event(
        task_dir,
        event="visual_capture_worker_started",
        run_id=run_id,
        session_index=session_index,
        contract_path=contract_path,
        keyword_count=len(keyword_tasks),
    )

    real_result = _run_real_capture_contract(
        contract=contract,
        contract_path=contract_path,
        run_id=run_id,
        session_index=session_index,
        task_dir=task_dir,
        keyword_tasks=keyword_tasks,
    )
    keyword_results = real_result["keyword_results"]
    session_status = real_result["status"]
    stop_reason = real_result["stop_reason"]
    notes = real_result["notes"]

    elapsed_seconds = round(time.monotonic() - started, 3)
    session_result = {
        "schema": "taobao_visual_capture_worker_result_v1",
        "run_id": run_id,
        "session_index": session_index,
        "worker_role": "visual_capture_worker",
        "status": session_status,
        "processed_keywords": len(keyword_results),
        "stop_reason": stop_reason,
        "keyword_results": keyword_results,
        "elapsed_seconds": elapsed_seconds,
        "notes": notes,
        "created_at": now,
        "updated_at": _now(),
    }
    _write_json(session_result_path, session_result)
    write_task_event(
        task_dir,
        event="visual_capture_worker_finished",
        level="info" if session_status == "captured" else "warning",
        run_id=run_id,
        session_index=session_index,
        status=session_status,
        stop_reason=stop_reason,
        processed_keywords=len(keyword_results),
        session_result_path=session_result_path,
    )
    write_worker_runtime(
        run_id,
        session_index,
        "capture",
        session_status,
        contract_path=contract_path,
        session_result_path=session_result_path,
        processed_keywords=len(keyword_results),
        stop_reason=stop_reason,
        elapsed_seconds=elapsed_seconds,
        finished_at=_now(),
    )
    return {
        "ok": True,
        "run_id": run_id,
        "session_index": session_index,
        "status": session_status,
        "session_result": session_result_path,
        "processed_keywords": len(keyword_results),
    }


def _run_real_capture_contract(
    contract: Dict[str, Any],
    contract_path: str,
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword_tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    initial_interrupt = _control_interrupt(run_id, session_index)
    if initial_interrupt:
        return {
            "status": initial_interrupt.status,
            "stop_reason": initial_interrupt.reason,
            "keyword_results": [],
            "notes": "Capture worker did not start because supervisor control blocked dispatch.",
        }

    launcher = _mcp_launcher_path()
    if not launcher:
        return _real_unavailable_results(
            keyword_tasks,
            run_id,
            session_index,
            task_dir,
            stop_reason="midscene_mcp_launcher_missing",
            notes="Real capture requires local/start_midscene_computer_mcp.sh.",
        )

    try:
        with MidsceneStdioClient(_mcp_command(launcher), cwd=_project_root()) as client:
            _raise_if_controlled(run_id, session_index)
            tools = client.list_tools(interrupt_check=lambda: _raise_if_controlled(run_id, session_index))
            missing = sorted(MCP_REQUIRED_TOOLS - set(tools))
            if missing:
                return _real_unavailable_results(
                    keyword_tasks,
                    run_id,
                    session_index,
                    task_dir,
                    stop_reason="midscene_mcp_tools_missing",
                    notes=f"Midscene MCP missing required tools: {', '.join(missing)}.",
                )

            write_task_event(
                task_dir,
                event="visual_capture_real_mcp_connected",
                run_id=run_id,
                session_index=session_index,
                contract_path=contract_path,
                tools=sorted(set(tools) & (MCP_REQUIRED_TOOLS | MCP_OPTIONAL_TOOLS)),
            )
            client.call_tool(
                "computer_connect",
                {},
                interrupt_check=lambda: _raise_if_controlled(run_id, session_index),
            )

            keyword_results = []
            consecutive_abnormal = 0
            abnormal_limit = _consecutive_abnormal_limit(contract)
            for fallback_index, task in enumerate(keyword_tasks, start=1):
                _raise_if_controlled(run_id, session_index)
                _refresh_capture_runtime(
                    run_id,
                    session_index,
                    contract_path,
                    current_keyword=str(task.get("keyword") or ""),
                    progress_event="keyword_started",
                    keyword_index=fallback_index,
                )
                if fallback_index > 1:
                    _sleep_between_keywords(contract, run_id, session_index, task_dir, task)
                    _raise_if_controlled(run_id, session_index)
                keyword_result = _capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id=run_id,
                    session_index=session_index,
                    task_dir=task_dir,
                    fallback_index=fallback_index,
                    tools=tools,
                )
                keyword_results.append(keyword_result)
                _refresh_capture_runtime(
                    run_id,
                    session_index,
                    contract_path,
                    current_keyword=str(task.get("keyword") or ""),
                    progress_event="keyword_finished",
                    keyword_index=fallback_index,
                    last_keyword_status=keyword_result.get("status"),
                    last_stop_reason=keyword_result.get("stop_reason"),
                    processed_keywords=len(keyword_results),
                )
                if _should_run_post_keyword_cleanup(keyword_result, has_next=fallback_index < len(keyword_tasks)):
                    cleanup_payload = _post_keyword_cleanup_after_success(
                        client=client,
                        task=task,
                        contract=contract,
                        run_id=run_id,
                        session_index=session_index,
                        task_dir=task_dir,
                        tools=tools,
                    )
                    _append_keyword_result_diagnostic(
                        keyword_result,
                        "post_keyword_cleanup",
                        cleanup_payload,
                    )
                status = str(keyword_result.get("status") or "")
                reason = str(keyword_result.get("stop_reason") or "")
                if status in CAPTURED_STATUSES:
                    consecutive_abnormal = 0
                elif status in {"skipped"}:
                    continue
                else:
                    consecutive_abnormal += 1

                if status in {"paused_needs_human", "paused_needs_supervisor"}:
                    return {
                        "status": status,
                        "stop_reason": reason or status,
                        "keyword_results": keyword_results,
                        "notes": "Real Midscene computer MCP capture interrupted by supervisor control.",
                    }
                if status == "failed" and reason in {"stopped", "stop_or_locked"}:
                    return {
                        "status": "failed",
                        "stop_reason": reason,
                        "keyword_results": keyword_results,
                        "notes": "Real Midscene computer MCP capture stopped by supervisor control.",
                    }
                if status == "needs_review" and reason in {"home_entry_unverified", "home_entry_not_reached", "home_entry_reset_failed"}:
                    return {
                        "status": "needs_review",
                        "stop_reason": reason,
                        "keyword_results": keyword_results,
                        "notes": (
                            "Pre-keyword home-entry failed after bounded reset; "
                            "stopped the session before the next keyword to avoid context pollution."
                        ),
                    }
                if _should_stop_immediately(status, reason):
                    _request_worker_cooldown(run_id, session_index, reason)
                    return {
                        "status": "needs_review",
                        "stop_reason": reason or "keyword_needs_review",
                        "keyword_results": keyword_results,
                        "notes": "Real Midscene computer MCP capture stopped for human-in-the-loop review.",
                    }
                if consecutive_abnormal >= abnormal_limit:
                    stop_reason = reason or "consecutive_abnormal_limit"
                    _request_worker_cooldown(run_id, session_index, stop_reason)
                    return {
                        "status": "cooldown",
                        "stop_reason": "consecutive_abnormal_limit",
                        "keyword_results": keyword_results,
                        "notes": (
                            "Real Midscene computer MCP capture reached the consecutive abnormal "
                            "limit and requested session cooldown."
                        ),
                    }

            session_status = (
                "captured"
                if keyword_results and all(item.get("status") == "captured" for item in keyword_results)
                else "failed"
            )
            return {
                "status": session_status,
                "stop_reason": "completed" if session_status == "captured" else "no_keywords_captured",
                "keyword_results": keyword_results,
                "notes": (
                    "Real Midscene computer MCP capture completed. Product rows are still "
                    "owned by extract/ingest from retained visible screenshots."
                ),
            }
    except WorkerControlInterrupt as exc:
        return {
            "status": exc.status,
            "stop_reason": exc.reason,
            "keyword_results": [],
            "notes": "Real Midscene computer MCP capture interrupted by supervisor control.",
        }
    except Exception as exc:
        return _real_unavailable_results(
            keyword_tasks,
            run_id,
            session_index,
            task_dir,
            stop_reason="midscene_mcp_stdio_unavailable",
            notes=f"Midscene computer MCP was not usable from this Python worker: {exc}",
        )


def _capture_keyword_with_mcp(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    tools: List[str],
) -> Dict[str, Any]:
    return _capture_keyword_from_home_with_mcp(
        client=client,
        task=task,
        contract=contract,
        run_id=run_id,
        session_index=session_index,
        task_dir=task_dir,
        fallback_index=fallback_index,
        tools=tools,
    )


def _should_run_post_keyword_cleanup(keyword_result: Dict[str, Any], *, has_next: bool) -> bool:
    if not has_next:
        return False
    return (
        str(keyword_result.get("status") or "") == "captured"
        and str(keyword_result.get("stop_reason") or "") == "captured"
    )


def _require_initial_home_entry(contract: Dict[str, Any]) -> bool:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    return bool(hard_stop.get("require_initial_home_entry") or config.get("require_initial_home_entry"))


def _three_stage_business_boundaries_enabled(contract: Dict[str, Any]) -> bool:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    if "three_stage_business_boundaries" in hard_stop:
        return _config_bool(hard_stop.get("three_stage_business_boundaries"))
    if "three_stage_business_boundaries" in config:
        return _config_bool(config.get("three_stage_business_boundaries"))
    return True


def _post_keyword_cleanup_after_success(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    tools: List[str],
) -> Dict[str, Any]:
    keyword = str(task.get("keyword") or "")
    keyword_index = int(task.get("keyword_index") or task.get("index") or 0)
    evidence_dir = str(task.get("evidence_dir") or "")
    if not evidence_dir:
        evidence_dir = os.path.join(task_dir, "evidence", f"keyword_{keyword_index:03d}")
    ensure_dir(evidence_dir)
    capture_plan = task.get("capture_plan") or {}
    timeout_seconds = _mcp_request_timeout_seconds(contract)
    keyword_deadline = time.monotonic() + timeout_seconds
    diagnostics: Dict[str, Any] = {}
    foreground_recovery: Dict[str, Any] = {"events_used": 0}

    def interrupt_check() -> None:
        _raise_if_controlled(run_id, session_index)

    try:
        result = _call_act_with_foreground_recovery(
            client=client,
            contract=contract,
            prompt=_post_keyword_cleanup_prompt(keyword=keyword, contract=contract),
            stage="post_keyword_cleanup",
            keyword=keyword,
            capture_plan=capture_plan,
            tools=tools,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )
        action_diagnostics = _home_entry_action_diagnostics(result, client=client)
        _record_action_trace(
            evidence_dir=evidence_dir,
            keyword=keyword,
            action="post_keyword_cleanup",
            tile_id="post_keyword_cleanup",
            payload=action_diagnostics,
            diagnostics=diagnostics,
        )
        _raise_if_rate_limited_diagnostics(action_diagnostics, "post_keyword_cleanup")
        _raise_if_abnormal_act(result, default_context="post_keyword_cleanup")
        _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_post_keyword_cleanup")

        verification_path = os.path.join(evidence_dir, "post_keyword_cleanup.png")
        screenshot, page_state = _capture_and_classify_with_foreground_recovery(
            client=client,
            contract=contract,
            capture_plan=capture_plan,
            tools=tools,
            path=verification_path,
            tile_id="post_keyword_cleanup",
            keyword=keyword,
            evidence_dir=evidence_dir,
            stage="post_keyword_cleanup_verification",
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )
        review_reason = _home_entry_review_reason(page_state)
        return {
            "status": "verified" if not review_reason else "blocked",
            "mode": "post_keyword_cleanup",
            "stop_reason": review_reason,
            "steps": {"act": action_diagnostics},
            "verification_screenshot": verification_path,
            "screenshot": {
                "path": verification_path,
                "mime_type": screenshot.get("mime_type") or "image/png",
            },
            "page_state": page_state,
            "diagnostics": diagnostics,
            "gate": _home_entry_gate_policy(),
        }
    except WorkerControlInterrupt:
        raise
    except MidsceneActionAbnormal as exc:
        return {
            "status": "blocked",
            "mode": "post_keyword_cleanup",
            "stop_reason": exc.reason or "post_keyword_cleanup_failed",
            "rough_state": exc.rough_state,
            "message": exc.message,
            "diagnostics": _merge_diagnostics(diagnostics, exc.diagnostics),
            "gate": _home_entry_gate_policy(),
        }
    except Exception as exc:
        classification = classify_midscene_exception(exc)
        return {
            "status": "blocked",
            "mode": "post_keyword_cleanup",
            "stop_reason": classification.get("stop_reason") or "post_keyword_cleanup_failed",
            "rough_state": classification.get("rough_state") or UNKNOWN,
            "message": f"Post-keyword cleanup failed after captured evidence was saved: {exc}",
            "diagnostics": _merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
            "gate": _home_entry_gate_policy(),
        }


def _append_keyword_result_diagnostic(
    keyword_result: Dict[str, Any],
    key: str,
    payload: Dict[str, Any],
) -> None:
    diagnostics = keyword_result.setdefault("diagnostics", {})
    diagnostics[key] = payload
    result_path = str(keyword_result.get("result_path") or "")
    if not result_path:
        return
    try:
        stored = _read_json(result_path)
        diagnostics = stored.setdefault("diagnostics", {})
        diagnostics[key] = payload
        stored["updated_at"] = _now()
        _write_json(result_path, stored)
    except Exception:
        return


def _capture_keyword_from_home_with_mcp(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    tools: List[str],
) -> Dict[str, Any]:
    """Capture one keyword from an existing Taobao home/search-entry boundary."""
    keyword = str(task.get("keyword") or "")
    keyword_index = int(task.get("keyword_index") or task.get("index") or fallback_index)
    capture_plan = task.get("capture_plan") or {}
    evidence_dir = str(task.get("evidence_dir") or "")
    if not evidence_dir:
        evidence_dir = os.path.join(task_dir, "evidence", f"keyword_{keyword_index:03d}")
    ensure_dir(evidence_dir)
    started = time.monotonic()
    screenshots: List[Dict[str, Any]] = []
    diagnostics: Dict[str, Any] = {}
    foreground_recovery: Dict[str, Any] = {"events_used": 0}
    goal_contract = _write_goal_contract_artifact(
        evidence_dir=evidence_dir,
        task=task,
        contract=contract,
        keyword=keyword,
        keyword_index=keyword_index,
        capture_plan=capture_plan,
        diagnostics=diagnostics,
    )
    max_tiles = int(capture_plan.get("max_tiles_per_keyword") or 1)
    max_tiles = max(1, max_tiles)
    min_retained_tiles = int(capture_plan.get("min_retained_tiles_per_keyword") or 3)
    min_retained_tiles = max(1, min(min_retained_tiles, max_tiles))
    scroll_distance = int(capture_plan.get("tile_scroll_distance_px") or 0)
    scroll_distance = max(1, scroll_distance)
    page_load_wait = float((contract.get("config") or {}).get("page_load_wait") or 8.0)
    allow_act = bool((contract.get("model_boundary") or {}).get("allow_midscene_act", True))
    timeout_seconds = _keyword_timeout_seconds(task, contract)
    keyword_deadline = started + timeout_seconds
    mcp_timeout_seconds = _mcp_request_timeout_seconds(contract)

    def interrupt_check() -> None:
        _raise_if_controlled(run_id, session_index)

    try:
        _raise_if_controlled(run_id, session_index)
        _raise_if_keyword_timeout(started, timeout_seconds, keyword)
        if not allow_act:
            raise RuntimeError("midscene_act_disabled_for_real_capture")
        foreground_record = _run_initial_foreground_recovery(
            client=client,
            contract=contract,
            capture_plan=capture_plan,
            tools=tools,
            keyword=keyword,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=mcp_timeout_seconds,
        )
        diagnostics["initial_foreground_recovery"] = foreground_record
        if _three_stage_business_boundaries_enabled(contract) or _require_initial_home_entry(contract):
            home_entry_diagnostics = _prepare_home_entry_before_keyword(
                client=client,
                contract=contract,
                task=task,
                capture_plan=capture_plan,
                keyword=keyword,
                tools=tools,
                diagnostics=diagnostics,
                foreground_recovery=foreground_recovery,
                evidence_dir=evidence_dir,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=mcp_timeout_seconds,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
            )
            _merge_diagnostics_in_place(diagnostics, {"pre_keyword_home_entry": home_entry_diagnostics})
        search_diagnostics = _perform_search_submit_boundary(
            client=client,
            contract=contract,
            keyword=keyword,
            scroll_distance=scroll_distance,
            capture_plan=capture_plan,
            tools=tools,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=mcp_timeout_seconds,
        )
        _merge_diagnostics_in_place(diagnostics, {"search_submit_boundary": search_diagnostics})
        _record_action_trace(
            evidence_dir=evidence_dir,
            keyword=keyword,
            action="search_submit_boundary",
            tile_id="tile_00",
            payload=search_diagnostics,
            diagnostics=diagnostics,
        )
        for step_name, step_diagnostics in search_diagnostics.get("steps", {}).items():
            _raise_if_rate_limited_diagnostics(step_diagnostics, f"search_submit_boundary:{step_name}")
        _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_keyword_search_act")
        _interruptible_sleep(
            page_load_wait,
            run_id,
            session_index,
            task_dir,
            keyword=keyword,
            reason="page_load_wait",
            started=started,
            timeout_seconds=timeout_seconds,
        )
        search_verification = _verify_keyword_after_act(
            client=client,
            task=task,
            capture_plan=capture_plan,
            evidence_dir=evidence_dir,
            keyword=keyword,
            tools=tools,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            mcp_timeout_seconds=mcp_timeout_seconds,
            contract=contract,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
        )
        search_observation = _observation_from_search_verification(
            keyword=keyword,
            stage="search_submit_boundary_verification",
            verification=search_verification,
            action_payload=search_diagnostics,
        )
        search_decision = _record_observation_artifacts(
            evidence_dir=evidence_dir,
            keyword=keyword,
            observation=search_observation,
            goal_state="SEARCH_SUBMIT_BOUNDARY",
            goal_contract=goal_contract,
            diagnostics=diagnostics,
            boundary=True,
        )
        search_verification.setdefault("diagnostics", {})["capture_decision"] = search_decision
        if search_verification["screenshot"]:
            screenshots.append(search_verification["screenshot"])
            _refresh_capture_runtime(
                run_id,
                session_index,
                "",
                current_keyword=keyword,
                progress_event="tile_captured",
                tile_id="tile_00",
                captured_tiles=len(screenshots),
            )
            write_tile_summary(
                task_dir=task_dir,
                run_id=run_id,
                keyword=keyword,
                tile_id="tile_00",
                scroll_distance_px=0,
                rough_state=search_verification["page_state"]["status"],
                image_path=search_verification["screenshot"]["path"],
                image_retained=True,
                notes=search_verification["page_state"].get("reason") or "post_act_keyword_verification",
            )
        if not search_verification["ok"]:
            retry_verification = _reset_and_retry_keyword_search_once(
                client=client,
                task=task,
                capture_plan=capture_plan,
                evidence_dir=evidence_dir,
                keyword=keyword,
                search_verification=search_verification,
                contract=contract,
                tools=tools,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                screenshots=screenshots,
                diagnostics=diagnostics,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=mcp_timeout_seconds,
                foreground_recovery=foreground_recovery,
                goal_contract=goal_contract,
                gate_decision=search_decision,
            )
            if retry_verification:
                search_verification = retry_verification
                if screenshots:
                    screenshots[-1] = search_verification["screenshot"]
                else:
                    screenshots.append(search_verification["screenshot"])
                retry_observation = _observation_from_search_verification(
                    keyword=keyword,
                    stage="search_submit_boundary_retry_verification",
                    verification=search_verification,
                    action_payload=(diagnostics.get("post_act_reset_retry") or {}).get("steps", {}).get("act") or {},
                )
                retry_decision = _record_observation_artifacts(
                    evidence_dir=evidence_dir,
                    keyword=keyword,
                    observation=retry_observation,
                    goal_state="SEARCH_SUBMIT_BOUNDARY",
                    goal_contract=goal_contract,
                    diagnostics=diagnostics,
                    boundary=True,
                    repair_attempted=True,
                )
                search_verification.setdefault("diagnostics", {})["capture_decision"] = retry_decision
            if search_verification["ok"]:
                _merge_diagnostics_in_place(
                    diagnostics,
                    {
                        "post_act_reset_retry": {
                            "status": "recovered",
                            "recovered": {
                                "status": "recovered",
                                "message": (
                                    "A single bounded home-entry retry opened a fresh Taobao search "
                                    "and produced a verified capturable state."
                                ),
                            },
                            "message": (
                                "A single bounded home-entry retry opened a fresh Taobao search "
                                "and produced a verified capturable state."
                            ),
                        }
                    },
                )
            else:
                raise MidsceneActionAbnormal(
                    reason=search_verification["stop_reason"],
                    rough_state=search_verification["rough_state"],
                    message=search_verification["message"],
                    diagnostics={"post_act_verification": search_verification["diagnostics"]},
                )

        for tile_index in range(1, max_tiles):
            _raise_if_controlled(run_id, session_index)
            _raise_if_keyword_timeout(started, timeout_seconds, keyword)
            _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, f"before_scroll_{tile_index}")
            scroll_result = _perform_page_scroll(
                client=client,
                contract=contract,
                keyword=keyword,
                tile_index=tile_index,
                scroll_distance=scroll_distance,
                capture_plan=capture_plan,
                tools=tools,
                diagnostics=diagnostics,
                foreground_recovery=foreground_recovery,
                evidence_dir=evidence_dir,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=mcp_timeout_seconds,
            )
            _merge_diagnostics_in_place(
                diagnostics,
                {f"scroll_tile_{tile_index}": scroll_result},
            )
            _record_action_trace(
                evidence_dir=evidence_dir,
                keyword=keyword,
                action=f"scroll_tile_{tile_index}",
                tile_id=f"tile_{tile_index:02d}",
                payload=scroll_result,
                diagnostics=diagnostics,
            )
            _raise_if_rate_limited_diagnostics(
                diagnostics.get(f"scroll_tile_{tile_index}"),
                f"scroll_tile_{tile_index}",
            )
            _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, f"after_scroll_act_{tile_index}")
            tile_id = f"tile_{tile_index:02d}"
            tile_path = _tile_path(capture_plan, evidence_dir, tile_index)
            screenshot, page_state = _capture_and_classify_with_foreground_recovery(
                client=client,
                path=tile_path,
                contract=contract,
                capture_plan=capture_plan,
                tools=tools,
                tile_id=tile_id,
                keyword=keyword,
                evidence_dir=evidence_dir,
                stage=f"tile_{tile_index:02d}_verification",
                diagnostics=diagnostics,
                foreground_recovery=foreground_recovery,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=mcp_timeout_seconds,
            )
            screenshots.append(
                {
                    "tile_id": tile_id,
                    "path": tile_path,
                    "mime_type": screenshot.get("mime_type") or "image/png",
                    "captured_at": _now(),
                    "page_state": page_state,
                }
            )
            tile_observation = _observation_from_tile_classification(
                keyword=keyword,
                stage=f"tile_{tile_index:02d}_verification",
                tile_id=tile_id,
                tile_path=tile_path,
                screenshot=screenshot,
                page_state=page_state,
                action_payload=scroll_result,
            )
            tile_decision = _record_observation_artifacts(
                evidence_dir=evidence_dir,
                keyword=keyword,
                observation=tile_observation,
                goal_state="CAPTURE_TILES_BOUNDARY",
                goal_contract=goal_contract,
                diagnostics=diagnostics,
                boundary=page_state.get("status") == "results_end",
            )
            diagnostics[f"{tile_id}_capture_decision"] = tile_decision
            _refresh_capture_runtime(
                run_id,
                session_index,
                "",
                current_keyword=keyword,
                progress_event="tile_captured",
                tile_id=tile_id,
                captured_tiles=len(screenshots),
            )
            write_tile_summary(
                task_dir=task_dir,
                run_id=run_id,
                keyword=keyword,
                tile_id=tile_id,
                scroll_distance_px=0 if tile_index == 0 else scroll_distance,
                rough_state=page_state["status"],
                image_path=tile_path,
                image_retained=True,
                notes=page_state.get("reason") or "captured_by_midscene_computer_mcp",
            )
            review_reason = _page_state_review_reason(page_state)
            if (
                review_reason == "manual_review_needed"
                and page_state.get("status") == UNKNOWN
                and _has_capturable_screenshot(screenshots[:-1])
            ):
                diagnostics[f"{tile_id}_page_state"] = page_state
                diagnostics["partial_capture_stop"] = {
                    "tile_id": tile_id,
                    "reason": "later_tile_unknown_after_capturable_tiles",
                    "message": "Stopped scrolling after an inconclusive later tile; earlier result-page evidence is retained.",
                }
                break
            if review_reason:
                raise MidsceneActionAbnormal(
                    reason=review_reason,
                    rough_state=page_state["status"],
                    message=f"Screenshot coarse state requires review: {page_state.get('reason') or review_reason}",
                    diagnostics={f"{tile_id}_page_state": page_state},
                )
            if page_state.get("status") == "results_end":
                boundary_verification = _verify_results_end_keyword_boundary(
                    tile_path=tile_path,
                    tile_id=tile_id,
                    page_state=page_state,
                    screenshot_payload=screenshots[-1],
                    keyword=keyword,
                )
                diagnostics[f"{tile_id}_results_end_boundary"] = {
                    "ok": boundary_verification["ok"],
                    "stop_reason": boundary_verification.get("stop_reason") or "",
                    "rough_state": boundary_verification.get("rough_state") or "",
                    "message": boundary_verification.get("message") or "",
                    **(boundary_verification.get("diagnostics") or {}),
                }
                diagnostics["capture_stop"] = {
                    "tile_id": tile_id,
                    "reason": "results_end",
                    "keyword_boundary_ok": boundary_verification["ok"],
                    "message": (
                        "Visible JSON page-state classifier reported the bottom/end of results; retained this tile "
                        "and moved to the next keyword without resetting the current keyword."
                    ),
                }
                break
            similar_stop = _maybe_stop_for_similar_adjacent_tile(
                previous=screenshots[-2] if len(screenshots) >= 2 else None,
                current=screenshots[-1],
                capture_plan=capture_plan,
                diagnostics=diagnostics,
                retained_count=len(screenshots),
                min_retained_tiles=min_retained_tiles,
            )
            if similar_stop.get("stopped"):
                screenshots.pop()
                write_tile_summary(
                    task_dir=task_dir,
                    run_id=run_id,
                    keyword=keyword,
                    tile_id=tile_id,
                    scroll_distance_px=0 if tile_index == 0 else scroll_distance,
                    rough_state=page_state["status"],
                    image_path=tile_path,
                    image_retained=False,
                    notes="Removed highly similar adjacent tile after retaining the previous screenshot.",
                )
                break

        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="captured",
            rough_state="visible_results_unverified",
            stop_reason="captured",
            notes="Captured viewport tiles through Midscene computer MCP; product extraction is deferred.",
            screenshots=screenshots,
            elapsed_seconds=elapsed,
            diagnostics=diagnostics,
        )
    except WorkerControlInterrupt as exc:
        elapsed = round(time.monotonic() - started, 3)
        if _has_capturable_screenshot(screenshots):
            diagnostics["partial_capture_stop"] = {
                "reason": "supervisor_interrupt_after_capturable_tiles",
                "message": "Capture was interrupted by supervisor control after result-page evidence had already been captured.",
                "control_reason": exc.reason,
                "control_status": exc.status,
            }
            return _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status="captured",
                rough_state="visible_results_unverified",
                stop_reason="captured_partial_supervisor_interrupt",
                notes=(
                    "Captured viewport tiles before supervisor control interrupted the keyword; "
                    "product extraction is deferred to retained screenshot evidence."
                ),
                screenshots=screenshots,
                elapsed_seconds=elapsed,
                diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
            )
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status=exc.status,
            rough_state=exc.reason,
            stop_reason=exc.reason,
            notes="Keyword capture interrupted by supervisor control.",
            screenshots=screenshots,
            elapsed_seconds=elapsed,
            diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
        )
    except KeywordTimeout as exc:
        elapsed = round(time.monotonic() - started, 3)
        if _has_capturable_screenshot(screenshots):
            diagnostics["partial_capture_stop"] = {
                "reason": "keyword_timeout_after_capturable_tiles",
                "message": "Keyword timed out after result-page evidence had already been captured.",
            }
            return _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status="captured",
                rough_state="visible_results_unverified",
                stop_reason="captured_partial_keyword_timeout",
                notes=(
                    "Captured viewport tiles before the keyword timeout; product extraction is deferred "
                    "to retained screenshot evidence."
                ),
                screenshots=screenshots,
                elapsed_seconds=elapsed,
                diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
            )
        abnormal_screenshot = _capture_abnormal_screenshot(
            client,
            task,
            capture_plan,
            evidence_dir,
            timeout_seconds=0.5,
        )
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="failed_recoverable",
            rough_state="keyword_timeout",
            stop_reason="keyword_timeout",
            notes=str(exc),
            screenshots=screenshots,
            abnormal_screenshot=abnormal_screenshot,
            elapsed_seconds=elapsed,
            diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
        )
    except MCPRequestTimeout as exc:
        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="needs_review",
            rough_state="mcp_request_timeout",
            stop_reason="midscene_mcp_request_timeout",
            notes=(
                f"Real MCP request timed out and the MCP server may still be acting; "
                f"session must stop before the next keyword. {exc}"
            ),
            screenshots=screenshots,
            abnormal_screenshot="",
            elapsed_seconds=elapsed,
            diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
        )
    except MidsceneActionAbnormal as exc:
        if (
            exc.reason in {"midscene_mcp_action_failed", FOREGROUND_RECOVERY_STOP_REASON}
            and _has_capturable_screenshot(screenshots)
        ):
            partial_reason = (
                "foreground_recovery_exhausted_after_capturable_tiles"
                if exc.reason == FOREGROUND_RECOVERY_STOP_REASON
                else "mcp_action_failed_after_capturable_tiles"
            )
            diagnostics["partial_capture_stop"] = {
                "reason": partial_reason,
                "message": (
                    "A later Midscene action could not continue after result-page evidence had already been captured."
                ),
            }
            elapsed = round(time.monotonic() - started, 3)
            stop_reason = (
                "captured_partial_foreground_recovery_exhausted"
                if exc.reason == FOREGROUND_RECOVERY_STOP_REASON
                else "captured_partial_mcp_action_failed"
            )
            return _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status="captured",
                rough_state="visible_results_unverified",
                stop_reason=stop_reason,
                notes=(
                    "Captured viewport tiles before a later Midscene action could not continue; "
                    "product extraction is deferred to retained screenshot evidence."
                ),
                screenshots=screenshots,
                elapsed_seconds=elapsed,
                diagnostics=_merge_diagnostics(diagnostics, exc.diagnostics),
            )
        abnormal_screenshot = _capture_abnormal_screenshot(client, task, capture_plan, evidence_dir)
        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="needs_review",
            rough_state=exc.rough_state,
            stop_reason=exc.reason,
            notes=exc.message,
            screenshots=screenshots,
            abnormal_screenshot=abnormal_screenshot,
            elapsed_seconds=elapsed,
            diagnostics=_merge_diagnostics(diagnostics, exc.diagnostics),
        )
    except Exception as exc:
        classification = classify_midscene_exception(exc)
        if (
            classification["stop_reason"] == "midscene_mcp_action_failed"
            and _has_capturable_screenshot(screenshots)
        ):
            diagnostics["partial_capture_stop"] = {
                "reason": "mcp_action_failed_after_capturable_tiles",
                "message": (
                    "A later Midscene action failed after result-page evidence had already been captured."
                ),
            }
            elapsed = round(time.monotonic() - started, 3)
            return _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status="captured",
                rough_state="visible_results_unverified",
                stop_reason="captured_partial_mcp_action_failed",
                notes=(
                    "Captured viewport tiles before a later Midscene action failed; "
                    "product extraction is deferred to retained screenshot evidence."
                ),
                screenshots=screenshots,
                elapsed_seconds=elapsed,
                diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
            )
        abnormal_screenshot = _capture_abnormal_screenshot(client, task, capture_plan, evidence_dir)
        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="needs_review",
            rough_state=classification["rough_state"],
            stop_reason=classification["stop_reason"],
            notes=f"Real MCP action failed before completing keyword capture: {exc}",
            screenshots=screenshots,
            abnormal_screenshot=abnormal_screenshot,
            elapsed_seconds=elapsed,
            diagnostics=_merge_diagnostics(diagnostics, _midscene_exception_diagnostics(exc)),
        )


def _has_capturable_screenshot(screenshots: List[Dict[str, Any]]) -> bool:
    for screenshot in screenshots:
        page_state = screenshot.get("page_state") or {}
        if page_state.get("status") in CAPTURABLE_PAGE_STATES:
            return True
    return False


def _maybe_stop_for_similar_adjacent_tile(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    capture_plan: Dict[str, Any],
    diagnostics: Dict[str, Any],
    retained_count: Optional[int] = None,
    min_retained_tiles: Optional[int] = None,
) -> Dict[str, Any]:
    if not previous:
        return {"stopped": False, "reason": "no_previous_tile"}
    previous_state = (previous.get("page_state") or {}).get("status")
    current_state = (current.get("page_state") or {}).get("status")
    if current_state == "results_end":
        return {"stopped": False, "reason": "results_end_tile_retained"}
    if previous_state not in CAPTURABLE_PAGE_STATES or current_state not in CAPTURABLE_PAGE_STATES:
        return {"stopped": False, "reason": "non_capturable_state"}
    comparison = _compare_screenshot_similarity(
        str(previous.get("path") or ""),
        str(current.get("path") or ""),
        threshold=float(capture_plan.get("similar_tile_stop_threshold") or 0.985),
    )
    diagnostics[f"{current.get('tile_id')}_adjacent_similarity"] = comparison
    if not comparison.get("similar"):
        return {"stopped": False, "reason": "below_threshold", "comparison": comparison}
    retained = int(retained_count if retained_count is not None else 2)
    minimum = int(min_retained_tiles or capture_plan.get("min_retained_tiles_per_keyword") or 3)
    minimum = max(1, minimum)
    if retained - 1 < minimum:
        return {
            "stopped": False,
            "reason": "min_retained_tiles_not_met",
            "comparison": comparison,
            "retained_count": retained,
            "min_retained_tiles": minimum,
        }

    removed = _remove_file_if_exists(str(current.get("path") or ""))
    diagnostics["capture_stop"] = {
        "tile_id": current.get("tile_id"),
        "reason": "similar_adjacent_tile",
        "message": (
            "Stopped scrolling because the latest tile was highly similar to the previous "
            "capturable tile; retained the first screenshot and removed the duplicate."
        ),
        "previous_tile_id": previous.get("tile_id"),
        "removed_path": current.get("path") if removed else "",
        "similarity": comparison.get("similarity"),
        "threshold": comparison.get("threshold"),
        "min_retained_tiles": minimum,
        "retained_count_before_removal": retained,
    }
    return {"stopped": True, "comparison": comparison, "removed": removed}


def _compare_screenshot_similarity(
    previous_path: str,
    current_path: str,
    threshold: float = 0.985,
    sample_size: Tuple[int, int] = (64, 64),
) -> Dict[str, Any]:
    if not previous_path or not current_path:
        return {"similar": False, "reason": "missing_path", "threshold": threshold}
    try:
        from PIL import Image
    except Exception as exc:
        return {"similar": False, "reason": "pillow_unavailable", "error": str(exc), "threshold": threshold}
    try:
        with Image.open(previous_path) as previous_img, Image.open(current_path) as current_img:
            previous_sample = previous_img.convert("L").resize(sample_size)
            current_sample = current_img.convert("L").resize(sample_size)
            previous_pixels = previous_sample.tobytes()
            current_pixels = current_sample.tobytes()
    except Exception as exc:
        return {"similar": False, "reason": "image_read_failed", "error": str(exc), "threshold": threshold}
    if not previous_pixels or len(previous_pixels) != len(current_pixels):
        return {"similar": False, "reason": "sample_mismatch", "threshold": threshold}

    mean_abs_delta = sum(abs(a - b) for a, b in zip(previous_pixels, current_pixels)) / len(previous_pixels)
    similarity = max(0.0, min(1.0, 1.0 - (mean_abs_delta / 255.0)))
    return {
        "similar": similarity >= threshold,
        "similarity": round(similarity, 6),
        "mean_abs_delta": round(mean_abs_delta, 6),
        "threshold": threshold,
        "sample_size": list(sample_size),
    }


def _remove_file_if_exists(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _reset_and_retry_keyword_search_once(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    capture_plan: Dict[str, Any],
    evidence_dir: str,
    keyword: str,
    search_verification: Dict[str, Any],
    contract: Dict[str, Any],
    tools: List[str],
    run_id: str,
    session_index: int,
    task_dir: str,
    screenshots: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
    foreground_recovery: Optional[Dict[str, Any]] = None,
    initial_diagnostics_key: str = "post_act_verification_initial",
    preserve_label: str = "tile_00_initial_failed",
    replace_existing_screenshots: bool = True,
    goal_contract: Optional[Dict[str, Any]] = None,
    gate_decision: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not _should_reset_retry_search(search_verification, gate_decision=gate_decision):
        return None
    preservation = _preserve_failed_verification_screenshot(search_verification, preserve_label)
    initial_diagnostics = dict(search_verification.get("diagnostics") or {})
    if preservation:
        initial_diagnostics["failed_screenshot_preservation"] = preservation
    diagnostics[initial_diagnostics_key] = initial_diagnostics
    previous_home_entry_diagnostics = diagnostics.get("pre_keyword_home_entry")
    home_entry_retry = _prepare_home_entry_before_keyword(
        client=client,
        contract=contract,
        task=task,
        capture_plan=capture_plan,
        keyword=keyword,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery or {"events_used": 0},
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
        run_id=run_id,
        session_index=session_index,
        task_dir=task_dir,
    )
    if previous_home_entry_diagnostics:
        diagnostics["pre_keyword_home_entry"] = previous_home_entry_diagnostics
    submit_retry = _perform_search_submit_boundary(
        client=client,
        contract=contract,
        keyword=keyword,
        scroll_distance=int((capture_plan or {}).get("tile_scroll_distance_px") or 1),
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery or {"events_used": 0},
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    diagnostics["post_act_reset_retry"] = {
        "status": "attempted",
        "mode": "home_entry_then_search_submit_retry",
        "trigger": {
            "stop_reason": search_verification.get("stop_reason") or "",
            "rough_state": search_verification.get("rough_state") or "",
            "screenshot_keyword": (search_verification.get("diagnostics") or {}).get("screenshot_keyword") or {},
            "failed_screenshot_preservation": preservation,
        },
        "attempted": {
            "status": "attempted",
            "mode": "home_entry_then_search_submit_retry",
            "steps": {"home_entry_boundary": home_entry_retry, "search_submit_boundary": submit_retry},
            "failed_screenshot_preservation": preservation,
        },
        "steps": {"home_entry_boundary": home_entry_retry, "search_submit_boundary": submit_retry},
    }
    _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_search_reset_retry")
    retry_verification = _verify_keyword_after_act(
        client=client,
        task=task,
        capture_plan=capture_plan,
        evidence_dir=evidence_dir,
        keyword=keyword,
        tools=tools,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        mcp_timeout_seconds=timeout_seconds,
        contract=contract,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
    )
    if retry_verification.get("screenshot"):
        if replace_existing_screenshots:
            screenshots[:] = [retry_verification["screenshot"]]
        elif screenshots:
            screenshots[-1] = retry_verification["screenshot"]
        else:
            screenshots.append(retry_verification["screenshot"])
        diagnostics["post_act_reset_retry"]["recovered"] = {
            "status": "recovered" if retry_verification.get("ok") else "verification_failed",
            "mode": "home_entry_retry",
            "screenshot_path": retry_verification["screenshot"].get("path") or "",
            "page_state": retry_verification.get("page_state") or {},
            "stop_reason": retry_verification.get("stop_reason") or "",
        }
        _refresh_capture_runtime(
            run_id,
            session_index,
            "",
            current_keyword=keyword,
            progress_event="tile_captured",
            tile_id="tile_00",
            captured_tiles=len(screenshots),
        )
        write_tile_summary(
            task_dir=task_dir,
            run_id=run_id,
            keyword=keyword,
            tile_id="tile_00",
            scroll_distance_px=0,
            rough_state=retry_verification["page_state"]["status"],
            image_path=retry_verification["screenshot"]["path"],
            image_retained=True,
            notes=retry_verification["page_state"].get("reason") or "post_act_reset_retry_verification",
        )
    return retry_verification


def _prepare_home_entry_before_keyword(
    client: "MidsceneStdioClient",
    contract: Dict[str, Any],
    task: Dict[str, Any],
    capture_plan: Dict[str, Any],
    keyword: str,
    tools: List[str],
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
    run_id: str,
    session_index: int,
    task_dir: str,
) -> Dict[str, Any]:
    """Leave any previous results page and verify a homepage/search-entry boundary."""
    result = _call_act_with_foreground_recovery(
        client=client,
        contract=contract,
        prompt=_pre_keyword_home_entry_prompt(keyword=keyword, contract=contract),
        stage="pre_keyword_home_entry",
        keyword=keyword,
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    action_diagnostics = _home_entry_action_diagnostics(result, client=client)
    _record_action_trace(
        evidence_dir=evidence_dir,
        keyword=keyword,
        action="pre_keyword_home_entry",
        tile_id="home_entry",
        payload=action_diagnostics,
        diagnostics=diagnostics,
    )
    diagnostics["pre_keyword_home_entry"] = {
        "status": "action_attempted",
        "mode": "pre_keyword_home_entry",
        "gate": _home_entry_gate_policy(),
        "steps": {"act": action_diagnostics},
    }
    _raise_if_rate_limited_diagnostics(action_diagnostics, "pre_keyword_home_entry")
    _raise_if_abnormal_act(result, default_context="pre_keyword_home_entry")
    _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_pre_keyword_home_entry")

    verification_path = os.path.join(evidence_dir, "home_entry_prepared.png")
    screenshot, page_state = _capture_and_classify_with_foreground_recovery(
        client=client,
        contract=contract,
        capture_plan=capture_plan,
        tools=tools,
        path=verification_path,
        tile_id="home_entry",
        keyword=keyword,
        evidence_dir=evidence_dir,
        stage="pre_keyword_home_entry_verification",
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    review_reason = _home_entry_review_reason(page_state)
    payload = {
        "status": "verified" if not review_reason else "blocked",
        "mode": "pre_keyword_home_entry",
        "gate": _home_entry_gate_policy(),
        "steps": {"act": action_diagnostics},
        "verification_screenshot": verification_path,
        "screenshot": {
            "path": verification_path,
            "mime_type": screenshot.get("mime_type") or "image/png",
        },
        "page_state": page_state,
        "stop_reason": review_reason,
    }
    if review_reason and _should_retry_pre_keyword_home_entry(review_reason, page_state):
        retry_payload = _retry_prepare_home_entry_before_keyword_once(
            client=client,
            contract=contract,
            task=task,
            capture_plan=capture_plan,
            keyword=keyword,
            tools=tools,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            initial_payload=payload,
        )
        if retry_payload.get("status") == "verified":
            return retry_payload
        payload = retry_payload
        review_reason = str(payload.get("stop_reason") or review_reason)
        if review_reason in {"home_entry_unverified", "home_entry_not_reached"}:
            payload["stop_reason"] = "home_entry_reset_failed"
            review_reason = "home_entry_reset_failed"
    if review_reason:
        raise MidsceneActionAbnormal(
            reason=review_reason,
            rough_state=str(page_state.get("status") or UNKNOWN),
            message=(
                "Pre-keyword home-entry gate did not reach the normal Taobao "
                f"homepage/search-entry before searching {keyword!r}."
            ),
            diagnostics={"pre_keyword_home_entry": payload},
        )
    return payload


def _retry_prepare_home_entry_before_keyword_once(
    client: "MidsceneStdioClient",
    contract: Dict[str, Any],
    task: Dict[str, Any],
    capture_plan: Dict[str, Any],
    keyword: str,
    tools: List[str],
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
    run_id: str,
    session_index: int,
    task_dir: str,
    initial_payload: Dict[str, Any],
) -> Dict[str, Any]:
    result = _call_act_with_foreground_recovery(
        client=client,
        contract=contract,
        prompt=_pre_keyword_home_entry_retry_prompt(keyword=keyword, contract=contract),
        stage="pre_keyword_home_entry_retry",
        keyword=keyword,
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    retry_action_diagnostics = _home_entry_action_diagnostics(result, client=client)
    _record_action_trace(
        evidence_dir=evidence_dir,
        keyword=keyword,
        action="pre_keyword_home_entry_retry",
        tile_id="home_entry",
        payload=retry_action_diagnostics,
        diagnostics=diagnostics,
    )
    diagnostics["pre_keyword_home_entry_retry"] = {
        "status": "action_attempted",
        "mode": "pre_keyword_home_entry_retry",
        "trigger": {
            "stop_reason": initial_payload.get("stop_reason") or "",
            "page_state": initial_payload.get("page_state") or {},
            "verification_screenshot": initial_payload.get("verification_screenshot") or "",
        },
        "gate": dict(initial_payload.get("gate") or {}),
        "steps": {
            "initial": initial_payload,
            "repair_act": retry_action_diagnostics,
        },
    }
    _raise_if_rate_limited_diagnostics(retry_action_diagnostics, "pre_keyword_home_entry_retry")
    _raise_if_abnormal_act(result, default_context="pre_keyword_home_entry_retry")
    _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_pre_keyword_home_entry_retry")

    verification_path = os.path.join(evidence_dir, "home_entry_prepared_retry.png")
    screenshot, page_state = _capture_and_classify_with_foreground_recovery(
        client=client,
        contract=contract,
        capture_plan=capture_plan,
        tools=tools,
        path=verification_path,
        tile_id="home_entry_retry",
        keyword=keyword,
        evidence_dir=evidence_dir,
        stage="pre_keyword_home_entry_retry_verification",
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    review_reason = _home_entry_review_reason(page_state)
    payload = {
        "status": "verified" if not review_reason else "blocked",
        "mode": "pre_keyword_home_entry_retry",
        "trigger": {
            "stop_reason": initial_payload.get("stop_reason") or "",
            "page_state": initial_payload.get("page_state") or {},
            "verification_screenshot": initial_payload.get("verification_screenshot") or "",
        },
        "gate": dict(initial_payload.get("gate") or {}),
        "steps": {
            "initial": initial_payload,
            "repair_act": retry_action_diagnostics,
        },
        "verification_screenshot": verification_path,
        "screenshot": {
            "path": verification_path,
            "mime_type": screenshot.get("mime_type") or "image/png",
        },
        "page_state": page_state,
        "stop_reason": review_reason,
    }
    diagnostics["pre_keyword_home_entry_retry"] = payload
    return payload


def _home_entry_gate_policy() -> Dict[str, Any]:
    return {
        "allowed_statuses": ["visible_ready"],
        "requires_home_entry_ready": True,
        "requires_home_url_status": "normal_taobao_home",
        "requires_home_structure_status": "ordinary_home_search_entry",
        "allows_homepage_placeholder_or_suggestion": True,
        "requires_no_actual_old_query": False,
        "blocks_results_page_states": [
            "results_end",
            "results_page",
            "search_results",
            "visible_results",
        ],
        "pure_vision_boundary": True,
    }


def _home_entry_review_reason(page_state: Dict[str, Any]) -> str:
    status = str(page_state.get("status") or UNKNOWN)
    if status == UNKNOWN:
        return "home_entry_unverified"
    review_reason = _page_state_review_reason(page_state)
    if review_reason:
        return review_reason
    explicit_issue = _explicit_home_entry_evidence_issue(page_state)
    if explicit_issue:
        return explicit_issue
    if status in {"results_end", "results_page", "search_results", "visible_results"}:
        return "home_entry_not_reached"
    if status == "visible_ready" and _home_entry_has_non_ordinary_taobao_evidence(page_state):
        return "home_entry_unverified"
    if status != "visible_ready":
        return "home_entry_unverified"
    return ""


def _explicit_home_entry_evidence_issue(page_state: Dict[str, Any]) -> str:
    if not _has_explicit_home_entry_evidence(page_state):
        return ""
    hard_blocking_reason = str((page_state or {}).get("hard_blocking_reason") or "").strip()
    if hard_blocking_reason:
        return hard_blocking_reason
    source_state = str((page_state or {}).get("source_state") or "").strip()
    if source_state == "chrome_not_foreground":
        return FOREGROUND_NOT_READY_REASON
    if source_state == "hard_blocked":
        return "manual_review_needed"
    if (page_state or {}).get("home_entry_ready") is not True:
        return "home_entry_unverified"
    if str((page_state or {}).get("home_url_status") or "") != "normal_taobao_home":
        return "home_entry_unverified"
    if str((page_state or {}).get("home_structure_status") or "") != "ordinary_home_search_entry":
        return "home_entry_unverified"
    if float((page_state or {}).get("confidence") or 0.0) < 0.70:
        return "home_entry_unverified"
    return ""


def _has_explicit_home_entry_evidence(page_state: Dict[str, Any]) -> bool:
    keys = {
        "source_state",
        "home_entry_ready",
        "home_url_status",
        "home_structure_status",
        "hard_blocking_reason",
    }
    return any(key in (page_state or {}) and (page_state or {}).get(key) not in {None, ""} for key in keys)


def _home_entry_has_non_ordinary_taobao_evidence(page_state: Dict[str, Any]) -> bool:
    evidence = _page_state_text_list((page_state or {}).get("url_or_page_evidence"))
    raw_text = str((page_state or {}).get("raw_text") or "")
    reason = str((page_state or {}).get("reason") or "")
    text = " ".join([*evidence, raw_text, reason]).lower()
    if not text:
        return False
    markers = {
        "huodong.taobao.com",
        "dailygroup",
        "s.taobao.com/search",
        "world.taobao.com",
        "tmall.com",
        "采购优选",
        "活动页",
        "活动会场",
        "会场页",
        "activity page",
        "campaign page",
        "purchase-selection",
    }
    return any(marker in text for marker in markers)


def _search_box_text_kind(page_state: Dict[str, Any]) -> str:
    text = str((page_state or {}).get("search_box_text_kind") or "").strip().lower()
    text = text.replace("-", "_").replace(" ", "_")
    aliases = {
        "actual": "actual_input",
        "typed": "actual_input",
        "typed_value": "actual_input",
        "input": "actual_input",
        "query": "actual_input",
        "submitted_query": "actual_input",
        "recommendation": "suggestion",
        "recommended": "suggestion",
        "recommendation_text": "suggestion",
        "placeholder_text": "placeholder",
        "hot": "hot_search",
        "hotsearch": "hot_search",
        "hot_search_text": "hot_search",
    }
    text = aliases.get(text, text)
    if text in {"actual_input", "placeholder", "suggestion", "hot_search", "unreadable", "none"}:
        return text
    return ""


def _boundary_search_submission_issue(page_state: Dict[str, Any]) -> str:
    """Return the tile_00 boundary reason when submitted search structure is unproven."""
    search_submitted = (page_state or {}).get("search_submitted")
    is_home_feed = (page_state or {}).get("is_home_feed")
    if is_home_feed is None:
        is_home_feed = (page_state or {}).get("home_feed")
    if is_home_feed is True:
        return "search_submit_unconfirmed"
    if search_submitted is not True:
        return "search_submit_unconfirmed"
    if _search_box_text_kind(page_state) != "actual_input":
        return "search_submit_unconfirmed"
    result_evidence = _page_state_text_list(page_state.get("result_page_evidence"))
    url_evidence = _page_state_text_list(page_state.get("url_or_page_evidence"))
    if not result_evidence and not url_evidence:
        return "search_results_structure_unverified"
    return ""


def _page_state_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]
    return [str(item or "").strip() for item in raw_items if str(item or "").strip()]


def _should_retry_pre_keyword_home_entry(review_reason: str, page_state: Dict[str, Any]) -> bool:
    if review_reason in HARD_ABNORMAL_REASONS:
        return False
    if _foreground_loss_detected(page_state):
        return False
    status = str((page_state or {}).get("status") or UNKNOWN)
    if review_reason == "home_entry_unverified":
        return True
    if review_reason == "home_entry_not_reached":
        return status in {"results_end", "results_page", "search_results", "visible_results"}
    return False


def _preserve_failed_verification_screenshot(
    verification: Dict[str, Any],
    preserve_label: str,
) -> Dict[str, Any]:
    screenshot = verification.get("screenshot") or {}
    source_path = str(
        screenshot.get("path")
        or (verification.get("diagnostics") or {}).get("verification_screenshot")
        or ""
    )
    if not source_path:
        return {"status": "missing_source_path", "source_path": "", "preserved_path": ""}
    directory, filename = os.path.split(source_path)
    base, ext = os.path.splitext(filename)
    suffix = preserve_label.strip("_") or "initial_failed"
    if base == suffix:
        preserved_path = source_path
    elif suffix.startswith(f"{base}_"):
        preserved_path = os.path.join(directory, f"{suffix}{ext or '.png'}")
    else:
        preserved_path = os.path.join(directory, f"{base}_{suffix}{ext or '.png'}")
    payload = {
        "status": "not_preserved",
        "source_path": source_path,
        "preserved_path": preserved_path,
    }
    if not os.path.exists(source_path):
        payload["reason"] = "source_missing"
        return payload
    try:
        ensure_dir(os.path.dirname(preserved_path))
        shutil.copy2(source_path, preserved_path)
    except OSError as exc:
        payload["reason"] = str(exc)
        return payload
    payload["status"] = "preserved"
    return payload


def _should_reset_retry_search(
    search_verification: Dict[str, Any],
    gate_decision: Optional[Dict[str, Any]] = None,
) -> bool:
    if gate_decision is not None:
        gate = str(gate_decision.get("gate_decision") or gate_decision.get("action") or "")
        if gate:
            return gate == "repair_once"
    stop_reason = str(search_verification.get("stop_reason") or "")
    rough_state = str(search_verification.get("rough_state") or "")
    page_state = search_verification.get("page_state") or {}
    status = str(page_state.get("status") or rough_state or "")
    diagnostics = search_verification.get("diagnostics") or {}
    screenshot_keyword = diagnostics.get("screenshot_keyword") or {}
    screenshot_keyword_status = str(screenshot_keyword.get("status") or "")
    hard_reset_blockers = HARD_ABNORMAL_REASONS - {
        "manual_review_needed",
        "page_state_detection_failed",
        "visible_keyword_mismatch",
        "visible_keyword_unverified",
        "search_submit_unconfirmed",
        "search_results_structure_unverified",
    }
    if stop_reason in hard_reset_blockers or status in hard_reset_blockers:
        return False
    if stop_reason in {
        "visible_keyword_mismatch",
        "visible_keyword_unverified",
        "search_submit_unconfirmed",
        "search_results_structure_unverified",
    }:
        return status in CAPTURABLE_PAGE_STATES or rough_state in {
            "keyword_mismatch",
            "keyword_unverified",
            "search_submit_unconfirmed",
            "search_results_structure_unverified",
        }
    if stop_reason in {"manual_review_needed", "page_state_detection_failed"}:
        return status in CAPTURABLE_PAGE_STATES and screenshot_keyword_status in {"mismatch", "unknown"}
    return False


def _verify_results_end_keyword_boundary(
    tile_path: str,
    tile_id: str,
    page_state: Dict[str, Any],
    screenshot_payload: Dict[str, Any],
    keyword: str,
) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "expected_keyword": keyword,
        "verification_screenshot": tile_path,
        "tile_id": tile_id,
        "page_state": page_state,
    }
    screenshot_keyword = verify_visible_keyword(tile_path, keyword, page_state=page_state).to_dict()
    diagnostics["screenshot_keyword"] = screenshot_keyword
    keyword_match = page_state.get("keyword_match")
    explicit_match = screenshot_keyword.get("status") == "matched" and keyword_match is not False
    if explicit_match:
        return {
            "ok": True,
            "stop_reason": "",
            "rough_state": "results_end",
            "message": "Results-end keyword boundary verified.",
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }
    visible_keyword = str(page_state.get("visible_search_keyword") or "").strip()
    mismatch = screenshot_keyword.get("status") == "mismatch" or (keyword_match is False and bool(visible_keyword))
    stop_reason = "visible_keyword_mismatch" if mismatch else "visible_keyword_unverified"
    rough_state = "keyword_mismatch" if mismatch else "keyword_unverified"
    return {
        "ok": False,
        "stop_reason": stop_reason,
        "rough_state": rough_state,
        "message": (
            "Visible results_end reached the bottom of the current captured keyword, but the search "
            "box keyword was not verified. This is diagnostic-only for the current keyword."
        ),
        "screenshot": screenshot_payload,
        "page_state": page_state,
        "diagnostics": diagnostics,
    }


def _sleep_between_keywords(
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    task: Dict[str, Any],
) -> None:
    behavior = contract.get("visual_behavior") or {}
    bounds = behavior.get("inter_keyword_pause_seconds") or [8, 18]
    try:
        low, high = float(bounds[0]), float(bounds[1])
    except Exception:
        low, high = 30.0, 60.0
    seconds = random.uniform(max(0.0, low), max(low, high))
    keyword = str(task.get("keyword") or "")
    write_task_event(
        task_dir,
        event="visual_capture_inter_keyword_pause",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        seconds=round(seconds, 3),
    )
    _interruptible_sleep(seconds, run_id, session_index, task_dir, keyword=keyword, reason="inter_keyword_pause")


def _sleep_micro_pause(
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword: str,
    reason: str,
) -> None:
    seconds = _sample_micro_pause_seconds(contract.get("visual_behavior") or {})
    write_task_event(
        task_dir,
        event="visual_capture_micro_pause",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        reason=reason,
        seconds=round(seconds, 3),
    )
    _interruptible_sleep(seconds, run_id, session_index, task_dir, keyword=keyword, reason=reason)


def _sample_micro_pause_seconds(behavior: Dict[str, Any]) -> float:
    distribution = behavior.get("micro_pause_distribution") or {
        "short": "0.2,0.8,0.90",
        "medium": "0.8,1.5,0.08",
        "long": "1.5,2.5,0.02",
    }
    segments = []
    for value in distribution.values():
        try:
            low, high, weight = [float(part) for part in str(value).split(",", 2)]
            if weight > 0:
                segments.append((max(0.0, low), max(low, high), weight))
        except Exception:
            continue
    if not segments:
        segments = [(0.2, 0.8, 1.0)]
    total = sum(item[2] for item in segments)
    pick = random.uniform(0, total)
    acc = 0.0
    for low, high, weight in segments:
        acc += weight
        if pick <= acc:
            return random.uniform(low, high)
    low, high, _ = segments[-1]
    return random.uniform(low, high)


def _interruptible_sleep(
    seconds: float,
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword: str = "",
    reason: str = "sleep",
    started: Optional[float] = None,
    timeout_seconds: Optional[float] = None,
) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        _raise_if_controlled(run_id, session_index)
        if started is not None and timeout_seconds is not None:
            _raise_if_keyword_timeout(started, timeout_seconds, keyword)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(1.0, remaining))


def _control_interrupt(run_id: str, session_index: int) -> Optional[WorkerControlInterrupt]:
    interrupt = control_interrupt_for_worker(run_id, session_index)
    if not interrupt.get("interrupted"):
        return None
    reason = str(interrupt.get("reason") or "control_blocked")
    status = "paused_needs_supervisor"
    if reason in {"stopped", "stop_or_locked"}:
        status = "failed"
    elif reason in {"cooling_down"}:
        status = "cooldown"
    elif reason in {"locked"}:
        status = "paused_needs_human"
    return WorkerControlInterrupt(reason=reason, status=status)


def _raise_if_controlled(run_id: str, session_index: int) -> None:
    interrupt = _control_interrupt(run_id, session_index)
    if interrupt:
        raise interrupt


def _keyword_timeout_seconds(task: Dict[str, Any], contract: Dict[str, Any]) -> float:
    capture_plan = task.get("capture_plan") or {}
    hard_stop = contract.get("hard_stop_policy") or {}
    value = (
        task.get("timeout_seconds")
        or capture_plan.get("timeout_seconds")
        or hard_stop.get("timeout_per_keyword_seconds")
        or (contract.get("config") or {}).get("keyword_timeout_seconds")
        or 180
    )
    try:
        return max(10.0, float(value))
    except (TypeError, ValueError):
        return 180.0


def _mcp_request_timeout_seconds(contract: Dict[str, Any]) -> float:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    value = (
        hard_stop.get("mcp_request_timeout_seconds")
        or config.get("mcp_request_timeout_seconds")
        or hard_stop.get("timeout_per_keyword_seconds")
        or config.get("keyword_timeout_seconds")
        or 240
    )
    try:
        return max(30.0, float(value))
    except (TypeError, ValueError):
        return 240.0


def _raise_if_keyword_timeout(started: float, timeout_seconds: float, keyword: str) -> None:
    if time.monotonic() - started > timeout_seconds:
        raise KeywordTimeout(f"Keyword capture timed out after {timeout_seconds:.1f}s: {keyword}")


def _consecutive_abnormal_limit(contract: Dict[str, Any]) -> int:
    hard_stop = contract.get("hard_stop_policy") or {}
    try:
        return max(1, int(hard_stop.get("stop_after_consecutive_abnormal") or 2))
    except (TypeError, ValueError):
        return 2


def _should_stop_immediately(status: str, reason: str) -> bool:
    if status in {"paused_needs_human", "paused_needs_supervisor", "failed_hard", "cooldown"}:
        return True
    return reason in HARD_ABNORMAL_REASONS


def _request_worker_cooldown(run_id: str, session_index: int, reason: str) -> None:
    try:
        apply_control_action(
            run_id,
            "cooldown",
            session_index=session_index,
            reason=f"capture_worker:{reason}",
            cooldown_minutes=60,
        )
    except Exception:
        pass


def _refresh_capture_runtime(
    run_id: str,
    session_index: int,
    contract_path: str = "",
    **progress: Any,
) -> None:
    payload = {
        key: value
        for key, value in progress.items()
        if value not in (None, "")
    }
    if contract_path:
        payload["contract_path"] = contract_path
    try:
        write_worker_runtime(
            run_id,
            session_index,
            "capture",
            "running",
            **payload,
        )
    except Exception:
        pass


def _merge_diagnostics(*items: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for item in items:
        _merge_diagnostics_in_place(merged, item)
    return merged


def _merge_diagnostics_in_place(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    for key, value in (incoming or {}).items():
        if value in ({}, [], None, ""):
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_diagnostics_in_place(target[key], value)
        else:
            target[key] = value


def _midscene_text_diagnostics(
    result: Optional[Dict[str, Any]] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    sources = []
    if result:
        text = _tool_text(result)
        if text:
            sources.append({"source": "tool_text", "text": text})
    tail = _client_stderr_tail(client)
    if tail:
        sources.append({"source": "stderr_tail", "text": tail})

    rate_limit_sources = []
    for item in sources:
        text = str(item.get("text") or "")
        if _is_rate_limited_text(text):
            rate_limit_sources.append(
                {
                    "source": item.get("source") or "unknown",
                    "excerpt": _sanitize_diagnostic_text(text),
                }
            )
    if not rate_limit_sources:
        return {}
    return {
        "rate_limited": True,
        "http_429_detected": True,
        "rate_limit_diagnostics": rate_limit_sources,
    }


def _parse_reported_bool_flag(text: str, name: str) -> Optional[bool]:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return None
    pattern = rf"\b{re.escape(name.lower())}\s*[:=]\s*(true|false)\b"
    match = re.search(pattern, normalized)
    if not match:
        return None
    return match.group(1) == "true"


def _home_entry_action_diagnostics(
    result: Optional[Dict[str, Any]] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    diagnostics = _midscene_text_diagnostics(result=result, client=client)
    text = _tool_text(result or {})
    for flag in (
        "home_entry_prepared",
        "home_entry_used",
        "bookmark_home_entry_used",
        "recovered_from_old_results",
        "current_results_tab_closed",
    ):
        parsed = _parse_reported_bool_flag(text, flag)
        if parsed is not None:
            diagnostics[f"reported_{flag}"] = parsed
    diagnostics["home_entry_policy"] = {
        "goal": "normal_taobao_homepage_or_search_entry_before_keyword_search",
        "forbidden": "typing_next_keyword_into_old_results_page_search_box",
    }
    return diagnostics


def _search_submission_diagnostics(
    result: Optional[Dict[str, Any]] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    diagnostics = _home_entry_action_diagnostics(result=result, client=client)
    diagnostics["submission_policy"] = {
        "preferred": "visible_search_button_click",
        "enter_fallback_allowed_only_when": "visible_search_button_unavailable_or_not_clickable",
        "reported_method_hint": "act prompt asks for submission_method=search_button or submission_method=enter_fallback",
    }
    reported_method = _parse_reported_search_submission_method(_tool_text(result or {}))
    if reported_method:
        diagnostics["reported_submission_method"] = reported_method
    return diagnostics


def _parse_reported_search_submission_method(text: str) -> str:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return ""
    match = re.search(
        r"\bsubmission[_ -]?method(?:\s*[:=]\s*|\s+|-)"
        r"(search[_ -]?button|enter[_ -]?fallback)\b",
        normalized,
    )
    if match:
        return match.group(1).strip().replace("-", "_").replace(" ", "_")
    return ""


def _midscene_exception_diagnostics(exc: BaseException) -> Dict[str, Any]:
    text = str(exc or "")
    if not _is_rate_limited_text(text):
        return {}
    return {
        "exception": {
            "rate_limited": True,
            "http_429_detected": True,
            "rate_limit_diagnostics": [
                {
                    "source": exc.__class__.__name__,
                    "excerpt": _sanitize_diagnostic_text(text),
                }
            ],
        }
    }


def _client_stderr_tail(client: Optional[Any]) -> str:
    if not client:
        return ""
    tail = getattr(client, "_stderr_tail", None)
    if callable(tail):
        try:
            return str(tail() or "")
        except Exception:
            return ""
    return ""


def _sanitize_diagnostic_text(text: str) -> str:
    import re

    value = " ".join(str(text or "").split())
    value = re.sub(r"https?://\S+", "[url]", value)
    value = re.sub(r"(?i)(authorization|bearer|api[-_]?key|access[-_]?token|cookie)[:=]\s*\S+", r"\1=[redacted]", value)
    value = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[redacted]", value)
    return value[:240]


def _raise_if_rate_limited_diagnostics(diagnostics: Optional[Dict[str, Any]], default_context: str) -> None:
    if not diagnostics or not diagnostics.get("rate_limited"):
        return
    raise MidsceneActionAbnormal(
        reason="rate_limited",
        rough_state="rate_limited",
        message=f"Midscene/VLM rate limit detected during {default_context}.",
        diagnostics={default_context: diagnostics},
    )


def _capture_abnormal_screenshot(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    capture_plan: Dict[str, Any],
    evidence_dir: str,
    timeout_seconds: float = 3.0,
) -> str:
    abnormal_path = (
        task.get("abnormal_screenshot_path")
        or capture_plan.get("abnormal_screenshot_path")
        or os.path.join(evidence_dir, "abnormal_state.png")
    )
    try:
        client.capture_screenshot(str(abnormal_path), timeout_seconds=timeout_seconds)
        return str(abnormal_path)
    except Exception:
        return ""


def _verify_keyword_after_act(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    capture_plan: Dict[str, Any],
    evidence_dir: str,
    keyword: str,
    tools: List[str],
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    mcp_timeout_seconds: float,
    contract: Dict[str, Any],
    diagnostics: Optional[Dict[str, Any]] = None,
    foreground_recovery: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Capture tile_00 and verify the visible search query before trusting act complete."""
    tile_path = _tile_path(capture_plan, evidence_dir, 0)
    screenshot, page_state = _capture_and_classify_with_foreground_recovery(
        client=client,
        contract=contract,
        capture_plan=capture_plan,
        tools=tools,
        path=tile_path,
        tile_id="tile_00",
        keyword=keyword,
        evidence_dir=evidence_dir,
        stage="search_submit_boundary_verification",
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=mcp_timeout_seconds,
    )
    screenshot_payload = {
        "tile_id": "tile_00",
        "path": tile_path,
        "mime_type": screenshot.get("mime_type") or "image/png",
        "captured_at": _now(),
        "page_state": page_state,
    }
    verification_diagnostics: Dict[str, Any] = {
        "expected_keyword": keyword,
        "verification_screenshot": tile_path,
        "page_state": page_state,
    }

    screenshot_keyword = verify_visible_keyword(tile_path, keyword, page_state=page_state).to_dict()
    verification_diagnostics["screenshot_keyword"] = screenshot_keyword
    review_reason = _page_state_review_reason(page_state)
    if review_reason:
        verification_diagnostics["reason"] = review_reason
        return {
            "ok": False,
            "stop_reason": review_reason,
            "rough_state": page_state.get("status") or UNKNOWN,
            "message": f"Screenshot coarse state requires review: {page_state.get('reason') or review_reason}",
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": verification_diagnostics,
        }
    if screenshot_keyword["status"] == "mismatch":
        return {
            "ok": False,
            "stop_reason": "visible_keyword_mismatch",
            "rough_state": "keyword_mismatch",
            "message": (
                "Visible screenshot search keyword mismatched the current keyword after Midscene act complete; "
                "a bounded reset/retry is required before trusting this keyword evidence."
            ),
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": verification_diagnostics,
        }
    if screenshot_keyword["status"] != "matched":
        return {
            "ok": False,
            "stop_reason": "visible_keyword_unverified",
            "rough_state": "keyword_unverified",
            "message": (
                "Visible screenshot did not confirm the current keyword after Midscene act complete; "
                "a bounded reset/retry is required before trusting this keyword evidence."
            ),
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": verification_diagnostics,
        }

    submission_issue = _boundary_search_submission_issue(page_state)
    if submission_issue:
        verification_diagnostics["reason"] = submission_issue
        verification_diagnostics["search_submission_gate"] = {
            "search_submitted": page_state.get("search_submitted"),
            "is_home_feed": page_state.get("is_home_feed"),
            "search_box_text_kind": _search_box_text_kind(page_state),
            "result_page_evidence": _page_state_text_list(page_state.get("result_page_evidence")),
            "url_or_page_evidence": _page_state_text_list(page_state.get("url_or_page_evidence")),
        }
        if page_state.get("is_home_feed") is True:
            verification_diagnostics["search_submission_gate"]["home_feed_blocked"] = True
        message = (
            "Visible screenshot confirmed the keyword text, but did not prove the search was submitted "
            "into a Taobao results-page structure; a bounded home-entry retry is required before capture."
        )
        if submission_issue == "search_results_structure_unverified":
            message = (
                "Visible screenshot confirmed the keyword text and submitted-search flag, but did not show "
                "explicit Taobao results-page structure evidence; a bounded home-entry retry is required."
            )
        return {
            "ok": False,
            "stop_reason": submission_issue,
            "rough_state": submission_issue,
            "message": message,
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": verification_diagnostics,
        }

    return {
        "ok": True,
        "stop_reason": "",
        "rough_state": page_state.get("status") or VISIBLE_READY,
        "message": "Post-act screenshot keyword and page state verified.",
        "screenshot": screenshot_payload,
        "page_state": page_state,
        "diagnostics": verification_diagnostics,
    }


def _capture_and_classify_with_foreground_recovery(
    client: "MidsceneStdioClient",
    contract: Dict[str, Any],
    capture_plan: Dict[str, Any],
    tools: List[str],
    path: str,
    tile_id: str,
    keyword: str,
    evidence_dir: str,
    stage: str,
    diagnostics: Optional[Dict[str, Any]],
    foreground_recovery: Optional[Dict[str, Any]],
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    while True:
        screenshot = client.capture_screenshot(
            path,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
        )
        page_state = _classify_screenshot_page_state(
            client=client,
            path=path,
            contract=contract,
            capture_plan=capture_plan,
            tools=tools,
            tile_id=tile_id,
            keyword=keyword,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )
        if page_state.get("status") == CLOSEABLE_POPUP_OVERLAY:
            _maybe_close_closeable_popup_overlay(
                client=client,
                contract=contract,
                stage=stage,
                keyword=keyword,
                diagnostics=diagnostics,
                evidence_dir=evidence_dir,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=timeout_seconds,
                trigger_page_state=page_state,
            )
            continue
        if not _foreground_loss_detected(page_state):
            return screenshot, page_state
        _maybe_recover_foreground(
            client=client,
            contract=contract,
            capture_plan=capture_plan,
            tools=tools,
            stage=stage,
            keyword=keyword,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )


def _maybe_close_closeable_popup_overlay(
    client: "MidsceneStdioClient",
    contract: Dict[str, Any],
    stage: str,
    keyword: str,
    diagnostics: Optional[Dict[str, Any]],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
    trigger_page_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    records = _closeable_popup_records(diagnostics)
    budget = _closeable_popup_repair_budget(contract)
    if len(records) >= budget:
        raise MidsceneActionAbnormal(
            reason=CLOSEABLE_POPUP_OVERLAY,
            rough_state=CLOSEABLE_POPUP_OVERLAY,
            message="Closeable Taobao popup overlay repair budget exhausted.",
            diagnostics={"closeable_popup_overlay_repairs": records},
        )
    repair_index = len(records) + 1
    record: Dict[str, Any] = {
        "stage": stage,
        "status": "attempting",
        "repair_index": repair_index,
        "budget": budget,
        "trigger_page_state": trigger_page_state or {},
    }
    records.append(record)
    result = _call_act_with_rate_limit_retry(
        client=client,
        contract=contract,
        prompt=_closeable_popup_overlay_prompt(keyword=keyword, stage=stage, repair_index=repair_index),
        stage=f"{stage}_closeable_popup_overlay_repair",
        keyword=keyword,
        diagnostics=diagnostics,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    action_diagnostics = _midscene_text_diagnostics(result, client=client)
    action_diagnostics["repair_policy"] = {
        "state": CLOSEABLE_POPUP_OVERLAY,
        "target": "modal_or_overlay_gray_x_close_control",
        "forbidden": "browser_window_close_or_account_state_changing_controls",
    }
    record["act"] = action_diagnostics
    _record_action_trace(
        evidence_dir=evidence_dir,
        keyword=keyword,
        action=f"{stage}_closeable_popup_overlay_repair_{repair_index}",
        tile_id=f"{stage}_closeable_popup_overlay",
        payload=action_diagnostics,
        diagnostics=diagnostics,
    )
    classification = classify_midscene_act_result(result, default_context="closeable_popup_overlay_repair")
    record["classification"] = classification
    if classification["abnormal"]:
        record["status"] = "blocked"
        record["reason"] = classification["stop_reason"]
        raise MidsceneActionAbnormal(
            reason=classification["stop_reason"],
            rough_state=classification["rough_state"],
            message=classification["message"],
            diagnostics={"closeable_popup_overlay_repairs": records},
        )
    record["status"] = "attempted"
    return record


def _closeable_popup_records(diagnostics: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if diagnostics is None:
        return []
    records = diagnostics.setdefault("closeable_popup_overlay_repairs", [])
    if isinstance(records, list):
        return records
    diagnostics["closeable_popup_overlay_repairs"] = []
    return diagnostics["closeable_popup_overlay_repairs"]


def _closeable_popup_repair_budget(contract: Dict[str, Any]) -> int:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    value = (
        hard_stop.get("closeable_popup_overlay_repairs_per_keyword")
        or config.get("closeable_popup_overlay_repairs_per_keyword")
        or hard_stop.get("popup_repairs_per_keyword")
        or config.get("popup_repairs_per_keyword")
        or 1
    )
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 1


def _classify_screenshot_page_state(
    client: "MidsceneStdioClient",
    path: str,
    contract: Dict[str, Any],
    capture_plan: Dict[str, Any],
    tools: List[str],
    tile_id: str,
    keyword: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    del client, tools, interrupt_check
    if not _allow_json_page_state_classifier(contract, capture_plan):
        return _heuristic_page_state_fallback(path, contract, "classifier_disabled")

    try:
        request_timeout = min(max(float(timeout_seconds or 1.0), 1.0), 30.0)
        if keyword_deadline is not None:
            remaining = max(0.0, float(keyword_deadline) - time.monotonic())
            if remaining <= 0:
                raise KeywordTimeout(f"Keyword capture timed out before page-state classifier: {keyword}")
            request_timeout = min(request_timeout, remaining)
        state = classify_screenshot_json(
            path,
            contract=contract,
            keyword=keyword,
            timeout_seconds=request_timeout,
        )
        state["tile_id"] = tile_id
        return state
    except PageStateClassifierUnavailable as exc:
        fallback_reason = str(exc) or "classifier_unavailable"
    except (WorkerControlInterrupt, KeywordTimeout):
        raise
    except Exception as exc:
        fallback_reason = f"classifier_error:{type(exc).__name__}"

    if _is_rate_limited_text(fallback_reason):
        return {
            "status": "rate_limited",
            "confidence": 0.1,
            "reason": "page_state_json_classifier_rate_limited",
            "metrics": {},
            "source": "json_classifier",
            "raw_text": "",
            "fallback_reason": fallback_reason,
        }

    state = _classify_screenshot(path, contract)
    state["source"] = "heuristic"
    state["raw_text"] = ""
    state["fallback_reason"] = fallback_reason
    state["classifier_diagnostics"] = {
        "status": "fallback",
        "fallback_reason": fallback_reason,
        "tile_id": tile_id,
    }
    return state


def _allow_json_page_state_classifier(contract: Dict[str, Any], capture_plan: Dict[str, Any]) -> bool:
    page_sampling = contract.get("page_sampling") or {}
    if "allow_page_state_json_classifier" in page_sampling:
        return _config_bool(page_sampling.get("allow_page_state_json_classifier"))
    if "allow_page_state_json_classifier" in capture_plan:
        return _config_bool(capture_plan.get("allow_page_state_json_classifier"))
    if "allow_midscene_page_state_probe" in page_sampling:
        return _config_bool(page_sampling.get("allow_midscene_page_state_probe"))
    if "allow_midscene_page_state_probe" in capture_plan:
        return _config_bool(capture_plan.get("allow_midscene_page_state_probe"))
    return False


def _config_bool(value: Any) -> bool:
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


def _heuristic_page_state_fallback(
    path: str,
    contract: Dict[str, Any],
    fallback_reason: str,
) -> Dict[str, Any]:
    state = _classify_screenshot(path, contract)
    state["source"] = "heuristic"
    state["raw_text"] = ""
    state["fallback_reason"] = fallback_reason
    return state


def _page_state_review_reason(page_state: Dict[str, Any]) -> str:
    status = str(page_state.get("status") or UNKNOWN)
    reason = str(page_state.get("reason") or "")
    if status == CLOSEABLE_POPUP_OVERLAY:
        return CLOSEABLE_POPUP_OVERLAY
    if status in {LOGIN_REQUIRED, CAPTCHA_REQUIRED, WHITE_SKELETON, "risk_suspected", "popup_blocked", "rate_limited"}:
        return status
    if reason.startswith("page_state_detection_failed"):
        return "page_state_detection_failed"
    if status not in CAPTURABLE_PAGE_STATES:
        return "manual_review_needed"
    return ""


def _real_unavailable_results(
    keyword_tasks: List[Dict[str, Any]],
    run_id: str,
    session_index: int,
    task_dir: str,
    stop_reason: str,
    notes: str,
) -> Dict[str, Any]:
    results = []
    for fallback_index, task in enumerate(keyword_tasks, start=1):
        results.append(
            _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status=REAL_NOT_AVAILABLE_STATUS,
                rough_state="not_started",
                stop_reason=stop_reason,
                notes=notes,
            )
        )
    return {
        "status": REAL_NOT_AVAILABLE_STATUS,
        "stop_reason": stop_reason,
        "keyword_results": results,
        "notes": notes,
    }


def _write_keyword_result(
    task: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    mode: str,
    status: str,
    rough_state: str,
    stop_reason: str,
    notes: str,
    screenshots: Optional[List[Dict[str, Any]]] = None,
    abnormal_screenshot: str = "",
    elapsed_seconds: float = 0,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    keyword = str(task.get("keyword") or "")
    keyword_index = int(task.get("keyword_index") or task.get("index") or fallback_index)
    evidence_dir = str(task.get("evidence_dir") or "")
    if not evidence_dir:
        evidence_dir = os.path.join(task_dir, "evidence", f"keyword_{keyword_index:03d}")
    result_path = str(
        task.get("result_path")
        or task.get("keyword_result_path")
        or os.path.join(evidence_dir, "keyword_result.json")
    )
    capture_plan = task.get("capture_plan") or {}
    now = _now()
    payload = {
        "schema": "taobao_visual_capture_keyword_result_v1",
        "task_id": task.get("task_id") or f"{run_id}-s{session_index:02d}-k{keyword_index:03d}",
        "keyword_index": keyword_index,
        "keyword": keyword,
        "status": status,
        "rough_state": rough_state,
        "mode": mode,
        "screenshots": screenshots or [],
        "abnormal_screenshot": abnormal_screenshot,
        "abnormal_screenshot_path": task.get("abnormal_screenshot_path")
        or capture_plan.get("abnormal_screenshot_path")
        or "",
        "elapsed_seconds": elapsed_seconds,
        "stop_reason": stop_reason,
        "notes": notes,
        "diagnostics": diagnostics or {},
        "capture_plan": capture_plan,
        "result_path": result_path,
        "created_at": now,
        "updated_at": now,
    }
    _write_json(result_path, payload)
    write_task_event(
        task_dir,
        event="visual_capture_keyword_result_written",
        level="info" if status == "captured" else "warning",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        task_id=payload["task_id"],
        keyword_index=keyword_index,
        status=status,
        rough_state=rough_state,
        stop_reason=stop_reason,
        result_path=result_path,
    )
    return {
        "task_id": payload["task_id"],
        "keyword_index": keyword_index,
        "keyword": keyword,
        "status": status,
        "rough_state": rough_state,
        "mode": mode,
        "result_path": result_path,
        "stop_reason": stop_reason,
    }


def _artifact_path(evidence_dir: str, filename: str) -> str:
    return os.path.join(evidence_dir, filename)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        f.write("\n")
    return path


def _record_action_trace(
    evidence_dir: str,
    keyword: str,
    action: str,
    tile_id: str,
    payload: Dict[str, Any],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    record = {
        "schema": "taobao_visual_action_trace_v1",
        "recorded_at": _now(),
        "keyword": keyword,
        "action": action,
        "tile_id": tile_id,
        "payload": payload or {},
    }
    path = _artifact_path(evidence_dir, "action_trace.jsonl")
    _append_jsonl(path, record)
    _remember_artifact_path(diagnostics, "action_trace", path)
    return record


def _write_goal_contract_artifact(
    evidence_dir: str,
    task: Dict[str, Any],
    contract: Dict[str, Any],
    keyword: str,
    keyword_index: int,
    capture_plan: Dict[str, Any],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if build_goal_contract is not None:
        try:
            goal_contract = build_goal_contract(
                {
                    "task": task,
                    "contract": contract,
                    "keyword": keyword,
                    "keyword_index": keyword_index,
                    "capture_plan": capture_plan,
                }
            )
        except TypeError:
            goal_contract = build_goal_contract(
                task=task,
                contract=contract,
                keyword=keyword,
                keyword_index=keyword_index,
                capture_plan=capture_plan,
            )
        if not isinstance(goal_contract, dict):
            goal_contract = {}
    else:
        goal_contract = {}
    if not goal_contract:
        goal_contract = _fallback_goal_contract(
            task=task,
            contract=contract,
            keyword=keyword,
            keyword_index=keyword_index,
            capture_plan=capture_plan,
        )
    goal_contract.setdefault("schema", "taobao_visual_goal_contract_v1")
    goal_contract.setdefault("created_at", _now())
    goal_contract.setdefault("keyword", keyword)
    path = _artifact_path(evidence_dir, "goal_contract.json")
    _write_json(path, goal_contract)
    _remember_artifact_path(diagnostics, "goal_contract", path)
    return goal_contract


def _fallback_goal_contract(
    task: Dict[str, Any],
    contract: Dict[str, Any],
    keyword: str,
    keyword_index: int,
    capture_plan: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema": "taobao_visual_goal_contract_v1",
        "keyword": keyword,
        "keyword_index": keyword_index,
        "task_id": task.get("task_id") or "",
        "run_id": contract.get("run_id") or "",
        "session_index": contract.get("session_index") or 0,
        "acceptance": {
            "home_entry_boundary": "ordinary Taobao homepage/search-entry must be verified before typing a keyword",
            "search_submit_boundary": "tile_00 must verify submitted current-keyword Taobao results before capture",
            "capture_tiles_boundary": "retain visible result-page tiles only within the accepted current-keyword results page; results_end ends only the current keyword",
            "tile_00": "search submit boundary accepted first result viewport",
        },
        "repair_policy": {
            "boundary_repair_limit": 1,
            "allowed_repair": "home_entry_retry",
            "hard_abnormal_states_stop": sorted(HARD_ABNORMAL_REASONS),
        },
        "capture_plan": {
            "max_tiles_per_keyword": capture_plan.get("max_tiles_per_keyword"),
            "min_retained_tiles_per_keyword": capture_plan.get("min_retained_tiles_per_keyword"),
            "tile_scroll_distance_px": capture_plan.get("tile_scroll_distance_px"),
            "estimated_tile_scroll_distance_px": capture_plan.get("estimated_tile_scroll_distance_px"),
            "max_tile_scroll_distance_px": capture_plan.get("max_tile_scroll_distance_px"),
        },
    }


def _build_evidence_check(
    keyword: str,
    goal_state: str,
    goal_contract: Optional[Dict[str, Any]],
    observation: Dict[str, Any],
    boundary: bool,
) -> Dict[str, Any]:
    if build_goal_evidence_check is not None:
        try:
            result = build_goal_evidence_check(
                {
                    "keyword": keyword,
                    "goal_state": goal_state,
                    "goal_contract": goal_contract or {},
                    "observation": observation,
                    "boundary": boundary,
                }
            )
        except TypeError:
            result = build_goal_evidence_check(
                keyword=keyword,
                goal_state=goal_state,
                goal_contract=goal_contract or {},
                observation=observation,
                boundary=boundary,
            )
        if isinstance(result, dict):
            return {
                "schema": "taobao_visual_evidence_check_v1",
                "checked_at": _now(),
                "keyword": keyword,
                "goal_state": goal_state,
                **result,
            }
    return _fallback_evidence_check(keyword, goal_state, goal_contract or {}, observation, boundary)


def _fallback_evidence_check(
    keyword: str,
    goal_state: str,
    goal_contract: Dict[str, Any],
    observation: Dict[str, Any],
    boundary: bool,
) -> Dict[str, Any]:
    page_state = observation.get("page_state") or {}
    verification = observation.get("verification") or {}
    state = str(page_state.get("status") or verification.get("rough_state") or UNKNOWN)
    screenshot_keyword = verification.get("screenshot_keyword") or {}
    keyword_status = str(screenshot_keyword.get("status") or "")
    keyword_match = page_state.get("keyword_match")
    review_reason = _page_state_review_reason(page_state)
    checks = {
        "visible_results_state": state in CAPTURABLE_PAGE_STATES,
        "keyword_verified": keyword_status == "matched" and keyword_match is not False,
        "keyword_mismatch": keyword_status == "mismatch" or keyword_match is False,
        "review_required": bool(review_reason),
        "results_end": state == "results_end",
    }
    if goal_state in {"CAPTURING", "CAPTURE_TILES_BOUNDARY"} and state in CAPTURABLE_PAGE_STATES and not review_reason:
        checks["keyword_verified"] = keyword_match is not False
    status = "pass"
    reason = "evidence_matches_goal"
    if review_reason:
        status = "stop"
        reason = review_reason
    elif goal_state in {"BOUNDARY_VERIFY", "SEARCH_SUBMIT_BOUNDARY"} and checks["keyword_mismatch"]:
        status = "repairable"
        reason = "visible_keyword_mismatch"
    elif goal_state in {"BOUNDARY_VERIFY", "SEARCH_SUBMIT_BOUNDARY"} and not checks["keyword_verified"]:
        status = "repairable"
        reason = "visible_keyword_unverified"
    elif not checks["visible_results_state"]:
        status = "stop"
        reason = "non_capturable_page_state"
    elif state == "results_end":
        reason = "results_end"
    return {
        "schema": "taobao_visual_evidence_check_v1",
        "checked_at": _now(),
        "keyword": keyword,
        "goal_state": goal_state,
        "goal_contract_schema": goal_contract.get("schema") or "",
        "tile_id": observation.get("tile_id") or "",
        "stage": observation.get("stage") or "",
        "screenshot_path": observation.get("screenshot_path") or "",
        "boundary": boundary,
        "status": status,
        "reason": reason,
        "observed_state": state,
        "checks": checks,
        "page_state_source": page_state.get("source") or "",
    }


def _record_observation_artifacts(
    evidence_dir: str,
    keyword: str,
    observation: Dict[str, Any],
    goal_state: str,
    goal_contract: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
    boundary: bool = False,
    repair_attempted: bool = False,
) -> Dict[str, Any]:
    page_state_path = _artifact_path(evidence_dir, "page_state_v2.jsonl")
    _append_jsonl(page_state_path, observation)
    _remember_artifact_path(diagnostics, "page_state_v2", page_state_path)

    evidence_check = _build_evidence_check(
        keyword=keyword,
        goal_state=goal_state,
        goal_contract=goal_contract,
        observation=observation,
        boundary=boundary,
    )
    evidence_check_path = _artifact_path(evidence_dir, "evidence_check.jsonl")
    _append_jsonl(evidence_check_path, evidence_check)
    _remember_artifact_path(diagnostics, "evidence_check", evidence_check_path)

    decision = _reconcile_observation(
        keyword=keyword,
        goal_state=goal_state,
        observation=observation,
        evidence_check=evidence_check,
        goal_contract=goal_contract,
        repair_attempted=repair_attempted,
    )
    decision_path = _artifact_path(evidence_dir, "capture_decision.jsonl")
    _append_jsonl(decision_path, decision)
    _remember_artifact_path(diagnostics, "capture_decision", decision_path)

    if boundary:
        boundary_payload = _keyword_boundary_payload(keyword, observation, decision, goal_state)
        boundary_path = _artifact_path(evidence_dir, "keyword_boundary.json")
        _write_json(boundary_path, boundary_payload)
        _remember_artifact_path(diagnostics, "keyword_boundary", boundary_path)
    return decision


def _observation_from_search_verification(
    keyword: str,
    stage: str,
    verification: Dict[str, Any],
    action_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    screenshot = verification.get("screenshot") or {}
    page_state = verification.get("page_state") or {}
    diagnostics = verification.get("diagnostics") or {}
    return _observation_payload(
        keyword=keyword,
        stage=stage,
        tile_id=str(screenshot.get("tile_id") or "tile_00"),
        screenshot_path=str(screenshot.get("path") or diagnostics.get("verification_screenshot") or ""),
        page_state=page_state,
        action_payload=action_payload,
        verification={
            "ok": bool(verification.get("ok")),
            "stop_reason": verification.get("stop_reason") or "",
            "rough_state": verification.get("rough_state") or "",
            "message": verification.get("message") or "",
            "screenshot_keyword": diagnostics.get("screenshot_keyword") or {},
        },
    )


def _observation_from_tile_classification(
    keyword: str,
    stage: str,
    tile_id: str,
    tile_path: str,
    screenshot: Dict[str, Any],
    page_state: Dict[str, Any],
    action_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _observation_payload(
        keyword=keyword,
        stage=stage,
        tile_id=tile_id,
        screenshot_path=tile_path,
        page_state=page_state,
        action_payload=action_payload,
        verification={
            "ok": not bool(_page_state_review_reason(page_state)),
            "rough_state": page_state.get("status") or UNKNOWN,
            "mime_type": screenshot.get("mime_type") or "image/png",
        },
    )


def _observation_payload(
    keyword: str,
    stage: str,
    tile_id: str,
    screenshot_path: str,
    page_state: Dict[str, Any],
    action_payload: Optional[Dict[str, Any]],
    verification: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema": "taobao_visual_page_state_observation_v2",
        "observed_at": _now(),
        "keyword": keyword,
        "stage": stage,
        "tile_id": tile_id,
        "screenshot_path": screenshot_path,
        "page_state": page_state or {},
        "action": action_payload or {},
        "verification": verification or {},
    }


def _reconcile_observation(
    keyword: str,
    goal_state: str,
    observation: Dict[str, Any],
    evidence_check: Optional[Dict[str, Any]] = None,
    goal_contract: Optional[Dict[str, Any]] = None,
    repair_attempted: bool = False,
) -> Dict[str, Any]:
    if decide_capture_gate is not None:
        try:
            result = decide_capture_gate(
                {
                    "keyword": keyword,
                    "goal_state": goal_state,
                    "observation": observation,
                    "evidence_check": evidence_check or {},
                    "goal_contract": goal_contract or {},
                    "repair_attempted": repair_attempted,
                }
            )
        except TypeError:
            result = decide_capture_gate(
                keyword=keyword,
                goal_state=goal_state,
                observation=observation,
                evidence_check=evidence_check or {},
                goal_contract=goal_contract or {},
                repair_attempted=repair_attempted,
            )
        if isinstance(result, dict):
            return {
                "schema": "taobao_visual_capture_decision_v1",
                "decided_at": _now(),
                "keyword": keyword,
                "goal_state": goal_state,
                **result,
            }
    return _fallback_capture_decision(
        keyword,
        goal_state,
        observation,
        evidence_check=evidence_check,
        repair_attempted=repair_attempted,
    )


def _fallback_capture_decision(
    keyword: str,
    goal_state: str,
    observation: Dict[str, Any],
    evidence_check: Optional[Dict[str, Any]] = None,
    repair_attempted: bool = False,
) -> Dict[str, Any]:
    page_state = observation.get("page_state") or {}
    verification = observation.get("verification") or {}
    state = str(page_state.get("status") or verification.get("rough_state") or UNKNOWN)
    keyword_match = page_state.get("keyword_match")
    review_reason = _page_state_review_reason(page_state)
    if review_reason:
        decision = "needs_review"
        gate_decision = "stop"
        reason = review_reason
    elif verification.get("ok") is False:
        reason = str(verification.get("stop_reason") or "verification_failed")
        if goal_state in {"BOUNDARY_VERIFY", "SEARCH_SUBMIT_BOUNDARY"} and not repair_attempted and reason in {
            "visible_keyword_mismatch",
            "visible_keyword_unverified",
            "search_submit_unconfirmed",
            "search_results_structure_unverified",
            "manual_review_needed",
            "page_state_detection_failed",
        }:
            decision = "repair_once"
            gate_decision = "repair_once"
        else:
            decision = "blocked"
            gate_decision = "stop"
        reason = str(verification.get("stop_reason") or "verification_failed")
    elif state == "results_end":
        decision = "keyword_end"
        gate_decision = "accept"
        reason = "results_end"
    elif state in CAPTURABLE_PAGE_STATES and keyword_match is not False:
        decision = "continue_capture"
        gate_decision = "accept"
        reason = "capturable_page_state"
    else:
        decision = "needs_review"
        gate_decision = "stop"
        reason = "uncertain_page_state"
    evidence_check_status = ""
    if evidence_check:
        evidence_check_status = str(evidence_check.get("status") or "")
    return {
        "schema": "taobao_visual_capture_decision_v1",
        "decided_at": _now(),
        "keyword": keyword,
        "goal_state": goal_state,
        "decision": decision,
        "gate_decision": gate_decision,
        "reason": reason,
        "evidence_check_status": evidence_check_status,
        "repair_attempted": repair_attempted,
        "observed_state": state,
        "tile_id": observation.get("tile_id") or "",
    }


def _keyword_boundary_payload(
    keyword: str,
    observation: Dict[str, Any],
    decision: Dict[str, Any],
    goal_state: str,
) -> Dict[str, Any]:
    page_state = observation.get("page_state") or {}
    verification = observation.get("verification") or {}
    return {
        "schema": "taobao_visual_keyword_boundary_v1",
        "updated_at": _now(),
        "keyword": keyword,
        "goal_state": goal_state,
        "tile_id": observation.get("tile_id") or "",
        "screenshot_path": observation.get("screenshot_path") or "",
        "page_state": page_state,
        "verification": verification,
        "decision": decision,
    }


def _remember_artifact_path(
    diagnostics: Optional[Dict[str, Any]],
    key: str,
    path: str,
) -> None:
    if diagnostics is None:
        return
    artifacts = diagnostics.setdefault("artifacts", {})
    artifacts[key] = path


class MidsceneStdioClient:
    """Tiny MCP stdio client for the local midscene-computer server."""

    def __init__(self, command: List[str], cwd: str, timeout_seconds: float = 60.0):
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.process: Optional[subprocess.Popen] = None
        self._next_id = 1
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._stderr_lines: "queue.Queue[str]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def __enter__(self) -> "MidsceneStdioClient":
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "taobao_visual_capture_worker",
                    "version": "1.0",
                },
            },
        )
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()

    def list_tools(self, interrupt_check: Optional[Callable[[], None]] = None) -> List[str]:
        result = self.request("tools/list", {}, interrupt_check=interrupt_check)
        return [item.get("name") for item in result.get("tools", []) if item.get("name")]

    def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
        interrupt_check: Optional[Callable[[], None]] = None,
        keyword_deadline: Optional[float] = None,
        keyword: str = "",
    ) -> Dict[str, Any]:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout_seconds=timeout_seconds,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
        )
        if result.get("isError"):
            raise RuntimeError(_tool_text(result) or f"MCP tool failed: {name}")
        return result

    def capture_screenshot(
        self,
        path: str,
        timeout_seconds: Optional[float] = None,
        interrupt_check: Optional[Callable[[], None]] = None,
        keyword_deadline: Optional[float] = None,
        keyword: str = "",
    ) -> Dict[str, Any]:
        result = self.call_tool(
            "take_screenshot",
            {},
            timeout_seconds=timeout_seconds,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
        )
        image = _first_image(result)
        if not image:
            raise RuntimeError("take_screenshot returned no image content")
        ensure_dir(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(base64.b64decode(image["data"]))
        return {"path": path, "mime_type": image.get("mimeType") or "image/png"}

    def request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
        interrupt_check: Optional[Callable[[], None]] = None,
        keyword_deadline: Optional[float] = None,
        keyword: str = "",
    ) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        started = time.monotonic()
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        timeout = self.timeout_seconds if timeout_seconds is None else max(0.0, float(timeout_seconds))
        request_deadline = time.monotonic() + timeout
        while time.monotonic() < request_deadline:
            if interrupt_check:
                interrupt_check()
            if keyword_deadline is not None and time.monotonic() >= keyword_deadline:
                raise KeywordTimeout(f"Keyword capture timed out while waiting for MCP request: {keyword or method}")
            self._raise_if_dead()
            wait_until = request_deadline
            if keyword_deadline is not None:
                wait_until = min(wait_until, keyword_deadline)
            remaining = wait_until - time.monotonic()
            if remaining <= 0:
                break
            try:
                message = self._responses.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"].get("message") or message["error"])
            return message.get("result") or {}
        if interrupt_check:
            interrupt_check()
        if keyword_deadline is not None and time.monotonic() >= keyword_deadline:
            raise KeywordTimeout(f"Keyword capture timed out while waiting for MCP request: {keyword or method}")
        elapsed = time.monotonic() - started
        tool_name = ""
        if method == "tools/call":
            tool_name = str((params.get("name") if isinstance(params, dict) else "") or "")
        raise MCPRequestTimeout(
            f"MCP request timed out after {elapsed:.1f}s: {method}"
            f"{':' + tool_name if tool_name else ''}; request_id={request_id}; "
            f"timeout_seconds={timeout:.1f}; stderr={self._stderr_tail()}"
        )

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process is not running")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._responses.put(json.loads(line))
            except json.JSONDecodeError:
                self._stderr_lines.put(f"non-json stdout: {line[:500]}")

    def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        for line in self.process.stderr:
            if line.strip():
                self._stderr_lines.put(line.strip())

    def _raise_if_dead(self) -> None:
        if self.process and self.process.poll() is not None:
            raise RuntimeError(f"MCP process exited with {self.process.returncode}: {self._stderr_tail()}")

    def _stderr_tail(self) -> str:
        items = []
        while True:
            try:
                items.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "\n".join(items[-8:])


def _call_act(
    client: MidsceneStdioClient,
    prompt: str,
    interrupt_check: Optional[Callable[[], None]] = None,
    keyword_deadline: Optional[float] = None,
    keyword: str = "",
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    effective_timeout = timeout_seconds
    if keyword_deadline is not None:
        remaining = max(0.0, keyword_deadline - time.monotonic())
        effective_timeout = min(float(effective_timeout or remaining), remaining)
    return client.call_tool(
        "act",
        {"prompt": prompt},
        timeout_seconds=effective_timeout,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        keyword=keyword,
    )


def _rate_limit_retry_policy(contract: Dict[str, Any]) -> Dict[str, Any]:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    attempts = hard_stop.get("rate_limit_retry_attempts")
    if attempts is None:
        attempts = config.get("rate_limit_retry_attempts", 2)
    cooldown = hard_stop.get("rate_limit_cooldown")
    if cooldown is None:
        cooldown = config.get("rate_limit_cooldown", 180.0)
    backoff = hard_stop.get("rate_limit_backoff")
    if backoff is None:
        backoff = config.get("rate_limit_backoff", 1.5)
    try:
        attempts_int = max(0, int(attempts))
    except (TypeError, ValueError):
        attempts_int = 2
    try:
        cooldown_float = max(0.0, float(cooldown))
    except (TypeError, ValueError):
        cooldown_float = 180.0
    try:
        backoff_float = max(1.0, float(backoff))
    except (TypeError, ValueError):
        backoff_float = 1.5
    return {
        "attempts": attempts_int,
        "cooldown": cooldown_float,
        "backoff": backoff_float,
    }


def _call_act_with_rate_limit_retry(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    prompt: str,
    stage: str,
    keyword: str,
    diagnostics: Optional[Dict[str, Any]],
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    policy = _rate_limit_retry_policy(contract)
    max_retries = int(policy["attempts"])
    attempts = max_retries + 1
    records = _rate_limit_retry_records(diagnostics)
    last_exception: Optional[BaseException] = None
    for attempt_index in range(1, attempts + 1):
        try:
            result = _call_act(
                client,
                prompt,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                keyword=keyword,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            exception_diagnostics = _midscene_exception_diagnostics(exc).get("exception") or {}
            if not exception_diagnostics.get("rate_limited"):
                raise
            last_exception = exc
            record = _rate_limit_retry_record(
                stage=stage,
                source="exception",
                attempt_index=attempt_index,
                max_retries=max_retries,
                diagnostics=exception_diagnostics,
                policy=policy,
            )
            records.append(record)
            if attempt_index > max_retries:
                break
            _sleep_rate_limit_cooldown(
                record=record,
                run_id=str((contract or {}).get("run_id") or ""),
                session_index=int((contract or {}).get("session_index") or 0),
                task_dir=str((contract or {}).get("task_dir") or ""),
                keyword=keyword,
                started=time.monotonic(),
                timeout_seconds=None,
            )
            continue

        action_diagnostics = _midscene_text_diagnostics(result, client=client)
        if not action_diagnostics.get("rate_limited"):
            return result
        record = _rate_limit_retry_record(
            stage=stage,
            source="act_result",
            attempt_index=attempt_index,
            max_retries=max_retries,
            diagnostics=action_diagnostics,
            policy=policy,
        )
        records.append(record)
        if attempt_index > max_retries:
            return result
        _sleep_rate_limit_cooldown(
            record=record,
            run_id=str((contract or {}).get("run_id") or ""),
            session_index=int((contract or {}).get("session_index") or 0),
            task_dir=str((contract or {}).get("task_dir") or ""),
            keyword=keyword,
            started=time.monotonic(),
            timeout_seconds=None,
        )

    final_diagnostics: Dict[str, Any] = {}
    if last_exception is not None:
        final_diagnostics = _midscene_exception_diagnostics(last_exception).get("exception") or {}
    raise MidsceneActionAbnormal(
        reason="rate_limited",
        rough_state="rate_limited",
        message=f"Midscene/VLM rate limit persisted after retries during {stage}.",
        diagnostics={stage: final_diagnostics, "rate_limit_retries": records},
    )


def _rate_limit_retry_records(diagnostics: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if diagnostics is None:
        return []
    records = diagnostics.setdefault("rate_limit_retries", [])
    if isinstance(records, list):
        return records
    diagnostics["rate_limit_retries"] = []
    return diagnostics["rate_limit_retries"]


def _rate_limit_retry_record(
    stage: str,
    source: str,
    attempt_index: int,
    max_retries: int,
    diagnostics: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    wait_seconds = float(policy["cooldown"]) * (float(policy["backoff"]) ** max(0, attempt_index - 1))
    return {
        "stage": stage,
        "source": source,
        "attempt_index": attempt_index,
        "max_retries": max_retries,
        "will_retry": attempt_index <= max_retries,
        "cooldown_seconds": round(wait_seconds, 3) if attempt_index <= max_retries else 0,
        "diagnostics": diagnostics,
    }


def _sleep_rate_limit_cooldown(
    record: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword: str,
    started: Optional[float],
    timeout_seconds: Optional[float],
) -> None:
    seconds = float(record.get("cooldown_seconds") or 0.0)
    if seconds <= 0:
        return
    if task_dir:
        write_task_event(
            task_dir,
            event="visual_capture_rate_limit_cooldown",
            run_id=run_id,
            session_index=session_index,
            keyword=keyword,
            stage=record.get("stage") or "",
            attempt_index=record.get("attempt_index") or 0,
            seconds=round(seconds, 3),
        )
    _interruptible_sleep(
        seconds,
        run_id,
        session_index,
        task_dir,
        keyword=keyword,
        reason=f"rate_limit_cooldown:{record.get('stage') or ''}",
        started=started,
        timeout_seconds=timeout_seconds,
    )


def _call_act_with_foreground_recovery(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    prompt: str,
    stage: str,
    keyword: str,
    capture_plan: Optional[Dict[str, Any]],
    tools: Optional[List[str]],
    diagnostics: Optional[Dict[str, Any]],
    foreground_recovery: Optional[Dict[str, Any]],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    while True:
        try:
            result = _call_act_with_rate_limit_retry(
                client=client,
                contract=contract,
                prompt=prompt,
                stage=stage,
                keyword=keyword,
                diagnostics=diagnostics,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            recovered = _maybe_recover_foreground_after_act_exception(
                client=client,
                exc=exc,
                contract=contract,
                capture_plan=capture_plan or {},
                tools=tools or [],
                stage=stage,
                keyword=keyword,
                diagnostics=diagnostics,
                foreground_recovery=foreground_recovery,
                evidence_dir=evidence_dir,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                timeout_seconds=timeout_seconds,
            )
            if recovered:
                continue
            raise
        if not _foreground_loss_detected(result):
            return result
        _maybe_recover_foreground(
            client=client,
            contract=contract,
            capture_plan=capture_plan,
            tools=tools,
            stage=stage,
            keyword=keyword,
            diagnostics=diagnostics,
            foreground_recovery=foreground_recovery,
            evidence_dir=evidence_dir,
            trigger=result,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )


def _maybe_recover_foreground_after_act_exception(
    client: MidsceneStdioClient,
    exc: BaseException,
    contract: Dict[str, Any],
    capture_plan: Dict[str, Any],
    tools: List[str],
    stage: str,
    keyword: str,
    diagnostics: Optional[Dict[str, Any]],
    foreground_recovery: Optional[Dict[str, Any]],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> bool:
    classification = classify_midscene_exception(exc)
    if classification.get("stop_reason") != "midscene_mcp_action_failed":
        return False
    exception_reports_foreground_loss = _foreground_loss_detected(str(exc))
    path = _foreground_exception_screenshot_path(evidence_dir, stage)
    screenshot: Dict[str, Any] = {}
    page_state: Dict[str, Any] = {}
    try:
        screenshot = client.capture_screenshot(
            path,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
        )
        page_state = _classify_screenshot_page_state(
            client=client,
            path=path,
            contract=contract,
            capture_plan={
                **(capture_plan or {}),
                "allow_page_state_json_classifier": True,
            },
            tools=tools,
            tile_id=f"{stage}_act_exception",
            keyword=keyword,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )
    except Exception as classifier_exc:
        if diagnostics is not None:
            diagnostics.setdefault("foreground_recovery_exception_checks", []).append(
                {
                    "stage": stage,
                    "status": "classifier_check_failed",
                    "exception": str(exc),
                    "classifier_error": str(classifier_exc),
                    "screenshot_path": path,
                }
            )
        return False
    record = {
        "stage": stage,
        "status": "checked",
        "exception": str(exc),
        "screenshot": screenshot,
        "page_state": page_state,
    }
    if diagnostics is not None:
        diagnostics.setdefault("foreground_recovery_exception_checks", []).append(record)
    if page_state.get("status") == CLOSEABLE_POPUP_OVERLAY:
        _maybe_close_closeable_popup_overlay(
            client=client,
            contract=contract,
            stage=f"{stage}_act_exception",
            keyword=keyword,
            diagnostics=diagnostics,
            evidence_dir=evidence_dir,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
            trigger_page_state=page_state,
        )
        record["status"] = "closeable_popup_overlay_repaired"
        return True
    if not _foreground_loss_detected(page_state):
        if not exception_reports_foreground_loss:
            return False
        if _page_state_blocks_foreground_exception_recovery(page_state):
            return False
        record["status"] = "checked_exception_foreground_override"
        record["foreground_recovery_trigger"] = "exception_text"
    _maybe_recover_foreground(
        client=client,
        contract=contract,
        capture_plan=capture_plan,
        tools=tools,
        stage=f"{stage}_act_exception",
        keyword=keyword,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        trigger={
            "content": [
                {
                    "type": "text",
                    "text": f"{FOREGROUND_NOT_READY_REASON}: act exception while non-Chrome foreground was visible; {exc}",
                }
            ],
            "page_state": page_state,
        },
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    record["status"] = "recovered"
    return True


def _foreground_exception_screenshot_path(evidence_dir: str, stage: str) -> str:
    safe_stage = re.sub(r"[^A-Za-z0-9_]+", "_", str(stage or "act_exception")).strip("_")
    return os.path.join(evidence_dir, f"foreground_exception_{safe_stage}.png")


def _foreground_recovery_limits(contract: Dict[str, Any]) -> Dict[str, Any]:
    hard_stop = contract.get("hard_stop_policy") or {}
    config = contract.get("config") or {}
    enabled_value = hard_stop.get("foreground_recovery_enabled")
    if enabled_value is None:
        enabled_value = config.get("foreground_recovery_enabled", True)
    attempts = hard_stop.get("foreground_recovery_attempts_per_event")
    if attempts is None:
        attempts = config.get("foreground_recovery_attempts_per_event", 3)
    events = hard_stop.get("foreground_recovery_events_per_keyword")
    if events is None:
        events = config.get("foreground_recovery_events_per_keyword", 2)
    try:
        attempts_int = max(1, int(attempts))
    except (TypeError, ValueError):
        attempts_int = 3
    try:
        events_int = max(0, int(events))
    except (TypeError, ValueError):
        events_int = 2
    return {
        "enabled": _config_bool(enabled_value),
        "attempts_per_event": attempts_int,
        "events_per_keyword": events_int,
    }


def _maybe_recover_foreground(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    capture_plan: Optional[Dict[str, Any]],
    tools: Optional[List[str]],
    stage: str,
    keyword: str,
    diagnostics: Optional[Dict[str, Any]],
    foreground_recovery: Optional[Dict[str, Any]],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
    trigger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    limits = _foreground_recovery_limits(contract)
    state = foreground_recovery if foreground_recovery is not None else {}
    state.setdefault("events_used", 0)
    records = _foreground_recovery_records(diagnostics)
    if not limits["enabled"] or state["events_used"] >= limits["events_per_keyword"]:
        record = {
            "stage": stage,
            "status": "exhausted",
            "reason": FOREGROUND_RECOVERY_STOP_REASON,
            "events_used": state["events_used"],
            "limits": limits,
            "trigger": _foreground_trigger_summary(trigger),
        }
        records.append(record)
        raise MidsceneActionAbnormal(
            reason=FOREGROUND_RECOVERY_STOP_REASON,
            rough_state=FOREGROUND_NOT_READY_REASON,
            message="Foreground recovery budget exhausted before Chrome/Taobao could be re-verified.",
            diagnostics={"foreground_recovery_attempts": records},
        )
    state["events_used"] += 1
    event_index = state["events_used"]
    event_record: Dict[str, Any] = {
        "stage": stage,
        "status": "attempting",
        "event_index": event_index,
        "limits": limits,
        "trigger": _foreground_trigger_summary(trigger),
        "attempts": [],
    }
    records.append(event_record)
    for attempt_index in range(1, limits["attempts_per_event"] + 1):
        before_path = _foreground_recovery_screenshot_path(evidence_dir, stage, event_index, attempt_index, "before")
        after_path = _foreground_recovery_screenshot_path(evidence_dir, stage, event_index, attempt_index, "after")
        attempt: Dict[str, Any] = {
            "attempt_index": attempt_index,
            "before_screenshot": before_path,
            "after_screenshot": after_path,
        }
        event_record["attempts"].append(attempt)
        try:
            client.capture_screenshot(
                before_path,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                keyword=keyword,
            )
        except Exception as exc:
            attempt["before_error"] = str(exc)
        result = _call_act_with_rate_limit_retry(
            client=client,
            contract=contract,
            prompt=_foreground_recovery_prompt(keyword=keyword, stage=stage, attempt_index=attempt_index),
            stage=f"{stage}_foreground_recovery",
            keyword=keyword,
            diagnostics=diagnostics,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            timeout_seconds=timeout_seconds,
        )
        attempt["act"] = _midscene_text_diagnostics(result, client=client)
        _record_action_trace(
            evidence_dir=evidence_dir,
            keyword=keyword,
            action=f"{stage}_foreground_recovery_attempt_{attempt_index}",
            tile_id=f"{stage}_foreground_recovery",
            payload=attempt["act"],
            diagnostics=diagnostics,
        )
        try:
            client.capture_screenshot(
                after_path,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                keyword=keyword,
            )
        except Exception as exc:
            attempt["after_error"] = str(exc)
        after_page_state: Dict[str, Any] = {}
        if "after_error" not in attempt:
            try:
                after_page_state = _classify_screenshot_page_state(
                    client=client,
                    path=after_path,
                    contract=contract,
                    capture_plan={
                        **(capture_plan or {}),
                        "allow_page_state_json_classifier": True,
                    },
                    tools=tools or [],
                    tile_id=f"{stage}_foreground_recovery_after",
                    keyword=keyword,
                    interrupt_check=interrupt_check,
                    keyword_deadline=keyword_deadline,
                    timeout_seconds=timeout_seconds,
                )
                attempt["after_page_state"] = after_page_state
            except Exception as exc:
                attempt["after_page_state_error"] = str(exc)
        classification = classify_midscene_act_result(result, default_context="foreground_recovery")
        attempt["classification"] = classification
        if classification["abnormal"] and classification["stop_reason"] not in {
            FOREGROUND_NOT_READY_REASON,
            "midscene_reported_failure",
            "midscene_mcp_action_failed",
        }:
            event_record["status"] = "blocked"
            event_record["reason"] = classification["stop_reason"]
            raise MidsceneActionAbnormal(
                reason=classification["stop_reason"],
                rough_state=classification["rough_state"],
                message=classification["message"],
                diagnostics={"foreground_recovery_attempts": records},
            )
        if _foreground_recovery_result_ok(result) and _foreground_recovery_after_state_ok(after_page_state):
            event_record["status"] = "recovered"
            event_record["recovered_attempt"] = attempt_index
            return event_record
        if _foreground_recovery_result_ok(result):
            attempt["after_verification"] = (
                "still_not_foreground" if _foreground_loss_detected(after_page_state) else "not_confirmed"
            )
    event_record["status"] = "exhausted"
    event_record["reason"] = FOREGROUND_RECOVERY_STOP_REASON
    raise MidsceneActionAbnormal(
        reason=FOREGROUND_RECOVERY_STOP_REASON,
        rough_state=FOREGROUND_NOT_READY_REASON,
        message="Foreground recovery attempts were exhausted for this event.",
        diagnostics={"foreground_recovery_attempts": records},
    )


def _foreground_recovery_records(diagnostics: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if diagnostics is None:
        return []
    records = diagnostics.setdefault("foreground_recovery_attempts", [])
    if isinstance(records, list):
        return records
    diagnostics["foreground_recovery_attempts"] = []
    return diagnostics["foreground_recovery_attempts"]


def _page_state_blocks_foreground_exception_recovery(page_state: Dict[str, Any]) -> bool:
    """Keep real account/security blockers from being masked by foreground recovery."""
    status = str((page_state or {}).get("status") or "")
    if status in CAPTURABLE_PAGE_STATES:
        return True
    return status in {
        "login_required",
        "captcha_required",
        "captcha_or_risk",
        "risk_suspected",
        "popup_blocked",
        WHITE_SKELETON,
        "account_state_changed_or_unusual",
        "automation_permission_blocked",
        "rate_limited",
    }


def _foreground_recovery_after_state_ok(page_state: Dict[str, Any]) -> bool:
    if not page_state:
        return False
    if str(page_state.get("source") or "") == "heuristic":
        return False
    status = str(page_state.get("status") or "")
    if not status:
        return False
    if status == FOREGROUND_NOT_READY_REASON:
        return False
    if status == WHITE_SKELETON:
        return False
    if status == UNKNOWN:
        return _page_state_mentions_chrome_foreground(page_state)
    if status in HARD_ABNORMAL_REASONS:
        return False
    if status in CAPTURABLE_PAGE_STATES:
        return True
    if _foreground_loss_detected(page_state) and not _page_state_mentions_chrome_foreground(page_state):
        return False
    return True


def _page_state_mentions_chrome_foreground(page_state: Dict[str, Any]) -> bool:
    if str((page_state or {}).get("source") or "") == "heuristic":
        return False
    texts = [
        str(page_state.get("reason") or ""),
        str(page_state.get("raw_text") or ""),
    ]
    diagnostics = page_state.get("probe_diagnostics")
    if isinstance(diagnostics, dict):
        texts.append(str(diagnostics.get("raw_text") or ""))
    normalized = " ".join(" ".join(texts).lower().split())
    if not normalized:
        return False
    chrome_needles = [
        "chrome browser",
        "chrome is foreground",
        "chrome new tab",
        "google search",
        "google homepage",
        "google new tab",
        "chrome在前台",
        "chrome浏览器",
        "当前可见的前台窗口是chrome",
        "当前显示的是chrome",
        "google搜索主页",
        "google新标签页",
        "chrome的新标签页",
        "chrome 新标签页",
    ]
    return any(needle in normalized for needle in chrome_needles)


def _foreground_recovery_screenshot_path(
    evidence_dir: str,
    stage: str,
    event_index: int,
    attempt_index: int,
    suffix: str,
) -> str:
    safe_stage = re.sub(r"[^A-Za-z0-9_]+", "_", str(stage or "foreground")).strip("_")
    return os.path.join(
        evidence_dir,
        f"foreground_recovery_{safe_stage}_event{event_index:02d}_attempt{attempt_index:02d}_{suffix}.png",
    )


def _foreground_trigger_summary(trigger: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not trigger:
        return {}
    return {
        "text": _tool_text(trigger)[:500],
        "isError": bool(trigger.get("isError")),
    }


def _foreground_recovery_result_ok(result: Dict[str, Any]) -> bool:
    text = _tool_text(result).lower()
    if not text:
        return False
    blocked = [
        "foreground_recovery=blocked",
        "chrome_not_foreground",
        "chrome not foreground",
        "not chrome foreground",
        "not foreground",
        "not visible",
        "foreground_recovery=blocked",
        "non-chrome",
        "wps",
        "无法",
        "不能",
    ]
    if any(item in text for item in blocked):
        return False
    success = [
        "foreground_recovery=recovered",
        "foreground recovered",
        "chrome is foreground",
        "chrome foreground",
        "taobao is visible",
        "淘宝页面可见",
        "已切回",
    ]
    return any(item in text for item in success)


def _foreground_recovery_prompt(keyword: str, stage: str, attempt_index: int) -> str:
    return (
        "Recover only the foreground window for the bounded Taobao visual capture. "
        "Use visible-screen reasoning only. The current keyword remains "
        f"{keyword!r}, and the current stage is {stage!r}; do not search, re-search, "
        "or submit the keyword. If Chrome with the dedicated Taobao collection page "
        "is already visible, leave it as is and report foreground_recovery=recovered. "
        "If another app such as WPS, Codex, Terminal, Cursor, or VS Code is foreground, "
        "you may click an already visible Chrome window, Dock icon, or taskbar icon, "
        "or use an OS-level app-switching shortcut to bring the existing Chrome window "
        "forward. Do not type into any non-Chrome app. Do not read DOM, HTML, network, "
        "cookies, storage, selector maps, page source, or JavaScript-evaluated data. "
        "Do not run launchers, do not use scripts, do not use the browser address bar, "
        "do not type a URL, do not open a new browser tab, do not navigate to Taobao "
        "home, and do not change account state. If Chrome/Taobao cannot be made visible "
        "within this bounded attempt, stop and report foreground_recovery=blocked. "
        f"This is foreground recovery attempt {attempt_index}."
    )


def _closeable_popup_overlay_prompt(keyword: str, stage: str, repair_index: int) -> str:
    return (
        "Handle one normal Taobao in-page closeable popup overlay using only visible-screen "
        "reasoning and system mouse actions. The current keyword remains "
        f"{keyword!r}, and the current stage is {stage!r}; do not search, re-search, "
        "scroll, type, submit, navigate, use the browser address bar, open a new tab, "
        "or change account state. If the Taobao page is dimmed by a translucent overlay "
        "and there is a clear gray X close control around the popup or overlay itself, "
        "usually near that popup's own upper-right corner, click only that gray X. "
        "Do not click the Chrome/browser/window close button. Do not click login, "
        "captcha, security verification, permission, checkout, cart, favorite, reward "
        "claim, coupon-use, or account-state-changing controls. If the visible overlay "
        "does not clearly have a safe gray X close control, stop and report "
        "closeable_overlay_blocked. In the final action message include "
        "closeable_overlay_closed=true or closeable_overlay_closed=false. "
        f"This is closeable popup overlay repair {repair_index}."
    )


def _closeable_popup_overlay_toolbox_prompt() -> str:
    return (
        "Reusable visual tool for common Taobao overlays: before continuing the current "
        "business boundary, check whether a normal Taobao marketing/coupon/red-packet "
        "modal is dimming the page or covering the search box/results controls. Examples "
        "include 红包, 优惠券, 补贴, 领取, 即将过期, and similar promotion popups. "
        "If that popup has a clearly visible gray X close control on or near the popup's "
        "own upper-right corner, click only that popup/overlay gray X, wait for the overlay to "
        "disappear, and then continue the same boundary. Treat this as a local visual "
        "tool, not as a navigation or search step. Do not click the Chrome/window close "
        "button, login, captcha, security, permission, checkout, cart, favorite, reward "
        "claim, coupon-use, or account-state-changing controls. If the close control is "
        "not clearly safe, stop and report closeable_popup_overlay instead of exploring. "
    )


def _run_initial_foreground_recovery(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    capture_plan: Dict[str, Any],
    tools: List[str],
    keyword: str,
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    del client, capture_plan, tools, diagnostics, foreground_recovery, evidence_dir
    del interrupt_check, keyword_deadline, timeout_seconds
    return {
        "status": "armed",
        "mode": "bounded_foreground_recovery",
        "keyword": keyword,
        "message": (
            "Foreground recovery is the first armed boundary for this keyword; "
            "the following home-entry act must report chrome_not_foreground instead "
            "of typing into a non-Chrome app, and the act wrapper performs bounded recovery."
        ),
    }


def _perform_search_submit_boundary(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    keyword: str,
    scroll_distance: int,
    capture_plan: Optional[Dict[str, Any]],
    tools: Optional[List[str]],
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    del scroll_distance
    search_result = _call_act_with_foreground_recovery(
        client=client,
        contract=contract,
        prompt=_search_submit_boundary_prompt(keyword=keyword, contract=contract),
        stage="search_submit_boundary",
        keyword=keyword,
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    act_diagnostics = _search_submission_diagnostics(search_result, client=client)
    payload = {
        "mode": "bounded_act_search_submit",
        "boundary": "search_submit",
        "retry_from_act_exception": False,
        "steps": {"act": act_diagnostics},
    }
    diagnostics["search_submit_boundary"] = payload
    _raise_if_rate_limited_diagnostics(act_diagnostics, "search_submit_boundary")
    _raise_if_abnormal_act(search_result, default_context="search_submit_boundary")
    return payload


def _perform_keyword_search(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    keyword: str,
    scroll_distance: int,
    capture_plan: Optional[Dict[str, Any]],
    tools: Optional[List[str]],
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    return _perform_search_submit_boundary(
        client=client,
        contract=contract,
        keyword=keyword,
        scroll_distance=scroll_distance,
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )


def _perform_page_scroll(
    client: MidsceneStdioClient,
    contract: Dict[str, Any],
    keyword: str,
    tile_index: int,
    scroll_distance: int,
    capture_plan: Optional[Dict[str, Any]],
    tools: Optional[List[str]],
    diagnostics: Dict[str, Any],
    foreground_recovery: Dict[str, Any],
    evidence_dir: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    result = _call_act_with_foreground_recovery(
        client=client,
        contract=contract,
        prompt=_next_tile_prompt(
            keyword=keyword,
            tile_index=tile_index,
            scroll_distance=scroll_distance,
        ),
        stage=f"scroll_tile_{tile_index}",
        keyword=keyword,
        capture_plan=capture_plan,
        tools=tools,
        diagnostics=diagnostics,
        foreground_recovery=foreground_recovery,
        evidence_dir=evidence_dir,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=timeout_seconds,
    )
    diagnostics = _midscene_text_diagnostics(result, client=client)
    _raise_if_rate_limited_diagnostics(diagnostics, f"scroll_tile_{tile_index}")
    _raise_if_abnormal_act(result, default_context=f"scroll_tile_{tile_index}")
    return {"mode": "bounded_act_scroll", "steps": {"act": diagnostics}}


def _raise_if_abnormal_act(result: Dict[str, Any], default_context: str) -> None:
    classification = classify_midscene_act_result(result, default_context=default_context)
    if classification["abnormal"]:
        raise MidsceneActionAbnormal(
            reason=classification["stop_reason"],
            rough_state=classification["rough_state"],
            message=classification["message"],
        )


def _is_home_entry_retryable_act_exception(
    exc: BaseException,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> bool:
    text = str(exc or "")
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    latest_page_state = _latest_foreground_exception_page_state(diagnostics)
    if _foreground_loss_detected(text):
        return _is_home_entry_retryable_exception_page_state(latest_page_state)
    if _is_rate_limited_text(text):
        return False
    security_needles = [
        "captcha",
        "验证码",
        "滑块",
        "security verification",
        "安全验证",
        "risk",
        "风控",
        "风险",
        "unusual account",
        "异常账号",
        "账号异常",
        "login required",
        "please login",
        "sign in",
        "登录",
        "请登录",
        "重新登录",
        "white skeleton",
        "白屏",
        "骨架屏",
        "blank page",
    ]
    if any(needle in normalized for needle in security_needles):
        return False
    old_results_needles = [
        "old results",
        "old keyword",
        "results page",
        "results-page",
        "old results-page",
        "旧结果",
        "旧关键词",
        "搜索结果页面",
        "搜索关键词不正确",
        "关键词不正确",
        "关键词不符",
        "与任务要求",
        "不符合",
        "不匹配",
        "返回淘宝首页重新搜索",
        "回到淘宝首页",
        "返回首页",
        "重新搜索正确",
    ]
    return any(needle in normalized for needle in old_results_needles)


def _latest_foreground_exception_page_state(
    diagnostics: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return {}
    checks = diagnostics.get("foreground_recovery_exception_checks")
    if not isinstance(checks, list):
        return {}
    for check in reversed(checks):
        if isinstance(check, dict) and isinstance(check.get("page_state"), dict):
            return check["page_state"]
    return {}


def _is_home_entry_retryable_exception_page_state(page_state: Dict[str, Any]) -> bool:
    status = str((page_state or {}).get("status") or "")
    if not status:
        return False
    if _foreground_loss_detected(page_state):
        return False
    if status in HARD_ABNORMAL_REASONS:
        return False
    return status in CLASSIFIER_KEYWORD_BOUNDARY_STATES


def classify_midscene_exception(exc: BaseException) -> Dict[str, Any]:
    text = str(exc or "")
    if _is_rate_limited_text(text):
        return {
            "abnormal": True,
            "rough_state": "rate_limited",
            "stop_reason": "rate_limited",
            "message": text or "Midscene/VLM rate limit detected.",
        }
    return {
        "abnormal": True,
        "rough_state": "mcp_action_failed",
        "stop_reason": "midscene_mcp_action_failed",
        "message": text,
    }


def classify_midscene_act_result(result: Dict[str, Any], default_context: str = "act") -> Dict[str, Any]:
    """Classify the MCP `act` ToolResult without trusting it as product data."""
    text = _tool_text(result)
    normalized = " ".join(text.lower().split())
    if _foreground_loss_detected(text):
        return {
            "abnormal": True,
            "rough_state": FOREGROUND_NOT_READY_REASON,
            "stop_reason": FOREGROUND_NOT_READY_REASON,
            "message": text or f"Chrome/Taobao was not foreground during {default_context}.",
        }
    if _is_rate_limited_text(text):
        return {
            "abnormal": True,
            "rough_state": "rate_limited",
            "stop_reason": "rate_limited",
            "message": text or f"Midscene/VLM rate limit detected during {default_context}.",
        }
    if result.get("isError"):
        return {
            "abnormal": True,
            "rough_state": "mcp_action_failed",
            "stop_reason": "midscene_mcp_action_failed",
            "message": text or f"Midscene act failed during {default_context}.",
        }

    security_negated = _is_security_abnormal_negated(normalized)
    patterns = [
        ("captcha_required", ["captcha", "验证码", "滑块", "security verification", "安全验证"]),
        ("login_required", ["login required", "please login", "sign in", "登录", "请登录", "重新登录"]),
        ("risk_suspected", ["risk", "风控", "风险", "unusual account", "异常账号", "账号异常", "安全检查"]),
        ("popup_blocked", ["permission panel", "automation permission", "权限", "弹窗", "blocked", "拦截"]),
        ("white_skeleton", ["white skeleton", "白屏", "骨架屏", "skeleton", "blank page"]),
        ("page_not_loaded", ["page not loaded", "加载失败", "无法打开", "chrome/taobao is unavailable"]),
        ("midscene_reported_failure", ["stop and report failure", "report failure", "failed to", "cannot", "unable to"]),
    ]
    for reason, needles in patterns:
        if reason in {"captcha_required", "login_required", "risk_suspected"} and security_negated:
            continue
        if any(needle in normalized for needle in needles):
            rough_state = "captcha_required" if reason == "captcha_required" else reason
            if reason == "midscene_reported_failure":
                rough_state = "mcp_reported_failure"
            return {
                "abnormal": True,
                "rough_state": rough_state,
                "stop_reason": reason,
                "message": text or f"Midscene reported abnormal state during {default_context}.",
            }

    return {
        "abnormal": False,
        "rough_state": "act_completed",
        "stop_reason": "",
        "message": text,
    }


def _foreground_loss_detected(value: Any) -> bool:
    if isinstance(value, dict):
        texts = [
            str(value.get("status") or ""),
            str(value.get("state") or ""),
            str(value.get("reason") or ""),
            str(value.get("raw_text") or ""),
            str(value.get("fallback_reason") or ""),
        ]
        if "content" in value:
            texts.append(_tool_text(value))
        diagnostics = value.get("probe_diagnostics")
        if isinstance(diagnostics, dict):
            texts.append(str(diagnostics.get("raw_text") or ""))
            texts.append(str(diagnostics.get("fallback_reason") or ""))
        text = " ".join(texts)
    else:
        text = str(value or "")
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    needles = [
        FOREGROUND_NOT_READY_REASON,
        "not foreground",
        "non-chrome",
        "non chrome",
        "chrome is not visible",
        "chrome not visible",
        "foreground_recovery=blocked",
        "codex is visible",
        "terminal is visible",
        "cursor is visible",
        "vs code is visible",
        "wps is visible",
        "wps office",
        "非 chrome",
        "非chrome",
        "不是 chrome",
        "不是chrome",
    ]
    return any(needle in normalized for needle in needles)


def _is_security_abnormal_negated(normalized: str) -> bool:
    """Avoid treating 'no captcha/login/security prompt' success text as abnormal."""
    text = str(normalized or "")
    if not text:
        return False
    negative_markers = [
        "无登录",
        "无验证码",
        "无安全提示",
        "无其他安全提示",
        "没有登录",
        "没有验证码",
        "没有安全提示",
        "未出现登录",
        "未出现验证码",
        "未出现安全提示",
        "no login",
        "no captcha",
        "no security",
        "without login",
        "without captcha",
        "without security",
    ]
    return any(marker in text for marker in negative_markers)


def _is_rate_limited_text(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    needles = [
        "429",
        "rate limit",
        "rate-limit",
        "rate_limited",
        "ratelimit",
        "rate limited",
        "too many requests",
        "quota",
        "访问量过大",
        "额度",
        "限流",
    ]
    return any(needle in normalized for needle in needles)


def _classify_screenshot(path: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    manual_state = str(contract.get("manual_state") or "").strip() or None
    try:
        state = detect_page_state(path, manual_state=manual_state).to_dict()
    except Exception as exc:
        return {
            "status": "unknown",
            "confidence": 0.0,
            "reason": f"page_state_detection_failed:{exc}",
            "metrics": {},
        }
    return state


def _keyword_search_prompt(keyword: str, scroll_distance: int) -> str:
    del scroll_distance
    return _search_submit_boundary_prompt(keyword)


def _allow_bookmark_home_entry_repair(contract: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(contract, dict):
        return False
    config = contract.get("config") or {}
    policy = contract.get("hard_stop_policy") or {}
    return bool(
        config.get("allow_bookmark_home_entry_repair")
        or policy.get("allow_bookmark_home_entry_repair")
    )


def _bookmark_home_entry_repair_prompt(contract: Optional[Dict[str, Any]] = None) -> str:
    if not _allow_bookmark_home_entry_repair(contract):
        return (
            "Do not use the browser address bar, do not type a URL, do not open "
            "a new browser tab, do not run scripts, and do not force browser "
            "activation outside visible low-frequency actions. "
        )
    return (
        "Do not use the browser address bar, do not type a URL, do not paste a "
        "URL, and do not run scripts. A limited home-entry repair is allowed "
        "when the current visible page is an old Taobao results page, a "
        "bottom-of-results page, or another old-keyword Taobao page: click the "
        "visible browser new tab plus button with the mouse, then click the "
        "visible Taobao bookmark button in the bookmarks bar to open the normal "
        "Taobao homepage. If Chrome is already foreground on a visible new tab "
        "or start page and the Taobao bookmark button is visible in the bookmarks "
        "bar, click that Taobao bookmark directly to open the normal Taobao "
        "homepage; do not open another new tab first. Do not type anything into "
        "the address bar. Do not use a new tab for any other purpose. If the "
        "Taobao bookmark button is not visibly available, stop and report "
        "bookmark_home_entry_unavailable. "
        "After the bookmark repair succeeds, you may close an obsolete old-results "
        "tab only if the visible tab strip clearly shows more than one Chrome tab "
        "will remain. Never close the final remaining Chrome tab; if the tab count "
        "is unclear, leave the old tab open. "
    )


def _pre_keyword_home_entry_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    navigation_rule = _bookmark_home_entry_repair_prompt(contract)
    popup_tool = _closeable_popup_overlay_toolbox_prompt()
    return (
        "Prepare the Taobao homepage/search-entry boundary for the next keyword. "
        "The business rule is simple: the active page must be the ordinary taobao.com "
        "homepage before searching. If the current page is not the ordinary Taobao "
        "homepage, do not use its search box; leave it and open or return to the "
        "ordinary Taobao homepage. "
        "Use only visible-screen reasoning and system mouse/keyboard actions. Do "
        "not read DOM, HTML, network, cookies, storage, selector maps, page source, "
        "JS-evaluated data, or clipboard contents. Do not use short action APIs "
        "such as Tap, Input, KeyboardPress, Scroll, or ClearInput. "
        "Do not type the next keyword yet, do not submit a search, do not use the "
        "browser address bar, do not type a URL, and do not run scripts. "
        "If Codex, Terminal, Cursor, VS Code, WPS, or another non-Chrome app is "
        "visible, report chrome_not_foreground so the Python worker can recover "
        "foreground safely. If login, captcha, security verification, risk warning, "
        "unusual account state, or an automation permission panel is visible, stop "
        "and report failure. "
        f"{popup_tool}"
        f"{navigation_rule}"
        "If the current page is an old Taobao results page, bottom-of-results page, "
        "activity/campaign page, purchase-selection page, unrelated site, or any page "
        "whose visible search box is not the ordinary taobao.com homepage search box, "
        "leave that page first through a visible Taobao logo, Home/首页 entry, "
        "return-home control, already visible normal homepage tab, or the configured "
        "visible bookmark home-entry repair when it is allowed. Do not replace text "
        "inside an old, activity, campaign, or otherwise non-homepage search box. "
        "The prepared boundary must be the normal homepage/search-entry surface, "
        "not a results page, activity page, purchase-selection page, campaign page, "
        "or non-homepage search box. Homepage placeholder, recommendation, hot-search, "
        "or suggestion text is acceptable only on the ordinary taobao.com homepage. Stop after "
        "the ordinary Taobao homepage/search-entry search box is visible "
        f"and ready for the next keyword {keyword!r}. In the final action message, "
        "include home_entry_prepared=true, home_entry_used=true, "
        "recovered_from_old_results=true or false, and bookmark_home_entry_used=true "
        "or false. Do not output product rows."
    )


def _pre_keyword_home_entry_retry_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    navigation_rule = _bookmark_home_entry_repair_prompt(contract)
    popup_tool = _closeable_popup_overlay_toolbox_prompt()
    return (
        "The previous pre-keyword boundary check still saw an old results page, "
        "a bottom-of-results page, an activity/campaign page, an unrelated page, "
        "or a homepage/search-entry field that was not proven to be on the ordinary "
        "taobao.com homepage. Perform one bounded home-entry repair before "
        "the next keyword. Use only visible-screen reasoning and system mouse/"
        "keyboard actions. Do not read DOM, HTML, network, cookies, storage, "
        "selector maps, page source, JS-evaluated data, or clipboard contents. "
        "Do not use short action APIs such as Tap, Input, KeyboardPress, Scroll, "
        "or ClearInput. Do not type the next keyword yet, do not submit a search, "
        "do not use the browser address bar, do not type a URL, and do not run "
        "scripts. "
        "If login, captcha, security verification, risk warning, unusual account "
        "state, or an automation permission panel is visible, stop and report "
        "failure. If Codex, Terminal, Cursor, VS Code, WPS, or another non-Chrome "
        "app is visible, report chrome_not_foreground so the Python worker can "
        "recover foreground safely. "
        f"{popup_tool}"
        f"{navigation_rule}"
        "Leave the current non-homepage context through a visible Taobao logo, Home/首页 "
        "entry, return-home control, already visible normal homepage tab, or the "
        "configured visible bookmark home-entry repair when it is allowed. Do not "
        "replace text inside any current-page search box unless it is the ordinary "
        "taobao.com homepage search box. The repaired boundary must be the normal "
        "Taobao homepage/search-entry surface, not a results page, activity page, "
        "purchase-selection page, campaign page, or non-homepage search box. Homepage "
        "placeholder, recommendation, hot-search, or suggestion text is acceptable "
        "only on the ordinary taobao.com homepage. Stop ready "
        f"for the next keyword {keyword!r}. "
        "In the final action message, include home_entry_prepared=true, "
        "home_entry_used=true, recovered_from_old_results=true, and "
        "bookmark_home_entry_used=true or false. Do not output product rows."
    )


def _post_keyword_cleanup_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    navigation_rule = _bookmark_home_entry_repair_prompt(contract)
    return (
        "The current keyword capture has finished successfully. Clean up the current "
        "Taobao results page before the next keyword. Use only visible-screen reasoning "
        "and system mouse/keyboard actions. Do not read DOM, HTML, network, cookies, "
        "storage, selector maps, page source, JS-evaluated data, or clipboard contents. "
        "Do not use short action APIs such as Tap, Input, KeyboardPress, Scroll, or "
        "ClearInput. Do not use the browser address bar, do not type a URL, do not "
        "paste a URL, and do not run scripts. "
        "If login, captcha, security verification, risk warning, unusual account state, "
        "or an automation permission panel is visible, stop and report failure. If Codex, "
        "Terminal, Cursor, VS Code, WPS, or another non-Chrome app is visible, report "
        "chrome_not_foreground so the Python worker can recover foreground safely. "
        f"{navigation_rule}"
        "Close the current completed Taobao results tab with the normal browser close-tab "
        "keyboard shortcut: Command+W on macOS, or Ctrl+W on Windows/Linux. Use that "
        "shortcut once; do not close the browser window deliberately. If this reveals a "
        "normal Taobao homepage/search-entry tab, stop there. If it reveals a visible "
        "Chrome new tab/start page and the Taobao bookmark button is visible, click that "
        "visible Taobao bookmark to open the normal Taobao homepage; do not open extra "
        "tabs for any other purpose. If the normal Taobao homepage/search-entry is already "
        "visible, leave it ready. "
        f"Do not type the next keyword. Stop ready for the next keyword after cleaning up {keyword!r}. "
        "In the final action message, include home_entry_prepared=true or false, "
        "home_entry_used=true or false, current_results_tab_closed=true or false, and "
        "bookmark_home_entry_used=true or false. Do not output product rows."
    )


def _keyword_search_home_entry_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    return _search_submit_boundary_prompt(keyword=keyword, contract=contract)


def _search_submit_boundary_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    del contract
    popup_tool = _closeable_popup_overlay_toolbox_prompt()
    return (
        "Submit the current keyword search from the already verified ordinary Taobao homepage. "
        "This is the search_submit_boundary only; home-entry repair belongs to the previous "
        "home_entry_boundary and must not be performed in this step. Use only "
        "visible-screen reasoning and system mouse/keyboard actions. Do not read "
        "DOM, HTML, network, cookies, storage, selector maps, page source, JS "
        "evaluated data, or clipboard contents. Do not use short action APIs "
        "such as Tap, Input, KeyboardPress, Scroll, or ClearInput. If Codex, "
        "Terminal, Cursor, VS Code, WPS, or another "
        "non-Chrome app is visible, report chrome_not_foreground so the Python "
        "worker can run bounded foreground recovery; do not type, scroll, search, "
        "or navigate in that app. "
        "If Chrome/Taobao is unavailable, or login, captcha, security verification, "
        "risk warning, unusual account state, or an automation permission panel "
        "is visible, stop and report failure. "
        f"{popup_tool}"
        "The current page should already be the ordinary taobao.com homepage/search-entry "
        "surface. If it is not, stop and report search_submit_requires_home_entry. "
        "Do not use a Taobao logo, Home/首页 entry, return-home control, bookmark, new "
        "tab, old results-page search box, activity/campaign search box, browser address "
        "bar, or URL typing in this step. "
        "Click the ordinary Taobao homepage search box and search "
        f"exactly this keyword: {keyword!r}. After the search box visibly contains "
        "exactly this keyword, submit by mouse-clicking the visible search button "
        "as the preferred method. Use Enter only as a fallback when the search "
        "button is not visible or cannot be clicked. After submitting, wait until "
        "the page visibly becomes a Taobao search results structure, such as a search "
        "results URL/address cue, a results sort/filter bar like 综合/销量/价格/区间/筛选, "
        "or pagination/previous/next/jump controls. Do not scroll the homepage "
        "recommendation feed, hot recommendations, channels, campaigns, or 猜你喜欢. "
        "Do not report success merely because the search box contains the keyword or "
        "because product cards are visible on the homepage. If clicking the search "
        "button fails and the page remains a homepage/search-entry feed, stop and "
        "report search_submit_failed or submission_method=unconfirmed instead of "
        "starting capture. In the final action message, "
        "include search_submitted=true or false, submission_method=search_button "
        "or submission_method=enter_fallback, visible_search_keyword, "
        "result_page_ready=true or false, and blocker if any. "
        "Wait until visible search results settle. Leave the page positioned at "
        "the first results viewport. Do not output product rows."
    )


def _keyword_search_home_entry_retry_after_exception_prompt(
    keyword: str,
    contract: Optional[Dict[str, Any]] = None,
) -> str:
    return _search_submit_boundary_prompt(keyword=keyword, contract=contract)


def _keyword_search_reset_prompt(keyword: str) -> str:
    return _keyword_search_home_entry_prompt(keyword)


def _next_tile_prompt(keyword: str, tile_index: int, scroll_distance: int) -> str:
    return (
        "Continue the capture_tiles_boundary for the already accepted current-keyword "
        "Taobao results page using only "
        "visible-screen reasoning and system mouse/keyboard/scroll actions. The "
        f"current keyword is {keyword!r}. If Codex, Terminal, Cursor, VS Code, "
        "WPS, or another non-Chrome app is visible, report chrome_not_foreground "
        "so the Python worker can run bounded foreground recovery; do not type, "
        "scroll, search, or navigate in that app. If Chrome/Taobao is unavailable, or login, captcha, security/risk, "
        "unusual account state, white skeleton, or a permission panel is visible, "
        "stop and report failure. "
        "If the visible page already appears to be at the bottom of "
        "Taobao results, do not keep trying to scroll; report that the results end is visible. "
        "Bottom signals include a long pagination row, previous/next page buttons, page jump "
        "input, page count with current/total pages, footer columns, rules/agreements/help links, copyright/ICP/"
        "license/filing text, partner/friend links, or the scrollbar already at the bottom. "
        "During ordinary non-bottom scrolling, do not stop just because the search box text is not readable; "
        "keyword text confirmation belongs at results-end or keyword-boundary handling. "
        "Do not return home, do not repair home entry, do not type or submit a search, "
        "do not clear the search box, and do not use old-page recovery in this boundary. "
        "Otherwise move only one short step toward the next visible results "
        f"viewport for tile_{tile_index:02d}; use exactly one normal page-level "
        f"downward wheel/trackpad scroll of about {scroll_distance} px if appropriate. "
        "Do not chain multiple wheel ticks, do not repeat-scroll until the footer, "
        "and do not skip over intermediate result rows. Stop immediately after that "
        "single short scroll and wait only for visible content to settle so the "
        "Python worker can save the next screenshot at this intermediate position. "
        "Do not output product rows and do not change account state."
    )


def _first_image(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for item in result.get("content") or []:
        if item.get("type") == "image" and item.get("data"):
            return item
    return None


def _tool_text(result: Dict[str, Any]) -> str:
    texts = [
        str(item.get("text") or "")
        for item in result.get("content") or []
        if item.get("type") == "text"
    ]
    return "\n".join(text for text in texts if text)


def _tile_path(capture_plan: Dict[str, Any], evidence_dir: str, tile_index: int) -> str:
    if tile_index == 0 and capture_plan.get("primary_screenshot_path"):
        return str(capture_plan["primary_screenshot_path"])
    pattern = str(capture_plan.get("tile_path_pattern") or os.path.join(evidence_dir, "tile_<NN>.png"))
    return pattern.replace("<NN>", f"{tile_index:02d}")


def _mcp_launcher_path() -> str:
    launcher = os.environ.get("TAOBAO_MIDSCENE_MCP_LAUNCHER", "").strip()
    if launcher and os.path.exists(launcher):
        return launcher
    default = os.path.join(_project_root(), "local", "start_midscene_computer_mcp.sh")
    return default if os.path.exists(default) else ""


def _mcp_command(launcher: str) -> List[str]:
    if launcher.endswith(".sh"):
        return ["/bin/bash", launcher]
    return [launcher]


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
