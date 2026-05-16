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
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from modules.page_sampling import write_task_event, write_tile_summary
from modules.page_state import (
    CAPTCHA_REQUIRED,
    EMPTY_RESULT,
    LOGIN_REQUIRED,
    UNKNOWN,
    VISIBLE_READY,
    WHITE_SKELETON,
    detect_page_state,
    verify_visible_keyword,
)
from modules.utils import ensure_dir
from modules.visual_control import (
    apply_control_action,
    control_interrupt_for_worker,
    write_worker_runtime,
)


MCP_REQUIRED_TOOLS = {
    "computer_connect",
    "take_screenshot",
    "act",
}
MCP_OPTIONAL_TOOLS = {"assert"}
REAL_NOT_AVAILABLE_STATUS = "real_not_available"
CAPTURED_STATUSES = {"captured"}
CAPTURABLE_PAGE_STATES = {
    VISIBLE_READY,
    EMPTY_RESULT,
    "results_page",
    "search_results",
    "visible_results",
}
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
    "rate_limited",
    "manual_review_needed",
    "page_state_detection_failed",
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
    max_tiles = int(capture_plan.get("max_tiles_per_keyword") or 1)
    max_tiles = max(1, max_tiles)
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
        search_result = _call_act(
            client,
            _keyword_search_prompt(keyword=keyword, scroll_distance=scroll_distance),
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
            timeout_seconds=mcp_timeout_seconds,
        )
        _merge_diagnostics_in_place(
            diagnostics,
            {"keyword_search_act": _midscene_text_diagnostics(search_result, client=client)},
        )
        _raise_if_rate_limited_diagnostics(diagnostics.get("keyword_search_act"), "keyword_search")
        _raise_if_abnormal_act(search_result, default_context="keyword_search")
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
        )
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
            scroll_result = _call_act(
                client,
                _next_tile_prompt(
                    keyword=keyword,
                    tile_index=tile_index,
                    scroll_distance=scroll_distance,
                ),
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                keyword=keyword,
                timeout_seconds=mcp_timeout_seconds,
            )
            _merge_diagnostics_in_place(
                diagnostics,
                {f"scroll_tile_{tile_index}_act": _midscene_text_diagnostics(scroll_result, client=client)},
            )
            _raise_if_rate_limited_diagnostics(
                diagnostics.get(f"scroll_tile_{tile_index}_act"),
                f"scroll_tile_{tile_index}",
            )
            _raise_if_abnormal_act(scroll_result, default_context=f"scroll_tile_{tile_index}")
            _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, f"after_scroll_act_{tile_index}")
            tile_id = f"tile_{tile_index:02d}"
            tile_path = _tile_path(capture_plan, evidence_dir, tile_index)
            screenshot = client.capture_screenshot(
                tile_path,
                interrupt_check=interrupt_check,
                keyword_deadline=keyword_deadline,
                keyword=keyword,
            )
            page_state = _classify_screenshot(tile_path, contract)
            screenshots.append(
                {
                    "tile_id": tile_id,
                    "path": tile_path,
                    "mime_type": screenshot.get("mime_type") or "image/png",
                    "captured_at": _now(),
                    "page_state": page_state,
                }
            )
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
            if review_reason:
                raise MidsceneActionAbnormal(
                    reason=review_reason,
                    rough_state=page_state["status"],
                    message=f"Screenshot coarse state requires review: {page_state.get('reason') or review_reason}",
                )

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
        abnormal_screenshot = _capture_abnormal_screenshot(
            client,
            task,
            capture_plan,
            evidence_dir,
            timeout_seconds=0.5,
        )
        elapsed = round(time.monotonic() - started, 3)
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


def _sleep_between_keywords(
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    task: Dict[str, Any],
) -> None:
    behavior = contract.get("visual_behavior") or {}
    bounds = behavior.get("inter_keyword_pause_seconds") or [30, 60]
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
        "short": "0.8,3,0.82",
        "medium": "3,6,0.14",
        "long": "6,10,0.04",
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
        segments = [(0.8, 3.0, 1.0)]
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
) -> Dict[str, Any]:
    """Capture tile_00 and verify the visible search query before trusting act complete."""
    tile_path = _tile_path(capture_plan, evidence_dir, 0)
    screenshot = client.capture_screenshot(
        tile_path,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        keyword=keyword,
    )
    page_state = _classify_screenshot(tile_path, contract)
    screenshot_payload = {
        "tile_id": "tile_00",
        "path": tile_path,
        "mime_type": screenshot.get("mime_type") or "image/png",
        "captured_at": _now(),
        "page_state": page_state,
    }
    diagnostics: Dict[str, Any] = {
        "expected_keyword": keyword,
        "verification_screenshot": tile_path,
        "page_state": page_state,
    }

    screenshot_keyword = verify_visible_keyword(tile_path, keyword, page_state=page_state).to_dict()
    diagnostics["screenshot_keyword"] = screenshot_keyword
    if screenshot_keyword["status"] == "mismatch":
        return {
            "ok": False,
            "stop_reason": "visible_keyword_mismatch",
            "rough_state": "keyword_mismatch",
            "message": (
                "Visible screenshot search keyword mismatched the current keyword after Midscene act complete; "
                "session stopped to avoid evidence pollution."
            ),
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }

    if "assert" not in set(tools or []):
        if screenshot_keyword["status"] == "matched":
            review_reason = _page_state_review_reason(page_state)
            if not review_reason:
                return {
                    "ok": True,
                    "stop_reason": "",
                    "rough_state": page_state.get("status") or VISIBLE_READY,
                    "message": "Post-act screenshot keyword and page state verified.",
                    "screenshot": screenshot_payload,
                    "page_state": page_state,
                    "diagnostics": diagnostics,
                }
            diagnostics["keyword_match"] = "matched"
            diagnostics["reason"] = review_reason
            return {
                "ok": False,
                "stop_reason": review_reason,
                "rough_state": page_state.get("status") or UNKNOWN,
                "message": f"Screenshot coarse state requires review: {page_state.get('reason') or review_reason}",
                "screenshot": screenshot_payload,
                "page_state": page_state,
                "diagnostics": diagnostics,
            }
        diagnostics["keyword_match"] = "unknown"
        diagnostics["reason"] = "midscene_assert_tool_missing"
        return {
            "ok": False,
            "stop_reason": "manual_review_needed",
            "rough_state": page_state.get("status") or UNKNOWN,
            "message": "Post-act keyword verification unavailable: Midscene assert tool missing.",
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }

    assertion = _assert_visible_keyword(
        client=client,
        keyword=keyword,
        interrupt_check=interrupt_check,
        keyword_deadline=keyword_deadline,
        timeout_seconds=mcp_timeout_seconds,
    )
    diagnostics["keyword_assertion"] = assertion
    if assertion["status"] == "mismatch":
        return {
            "ok": False,
            "stop_reason": "visible_keyword_mismatch",
            "rough_state": "keyword_mismatch",
            "message": assertion["message"],
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }
    if assertion["status"] != "matched":
        return {
            "ok": False,
            "stop_reason": "manual_review_needed",
            "rough_state": page_state.get("status") or UNKNOWN,
            "message": assertion["message"],
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }

    review_reason = _page_state_review_reason(page_state)
    if review_reason:
        return {
            "ok": False,
            "stop_reason": review_reason,
            "rough_state": page_state.get("status") or UNKNOWN,
            "message": f"Screenshot coarse state requires review: {page_state.get('reason') or review_reason}",
            "screenshot": screenshot_payload,
            "page_state": page_state,
            "diagnostics": diagnostics,
        }

    return {
        "ok": True,
        "stop_reason": "",
        "rough_state": page_state.get("status") or VISIBLE_READY,
        "message": "Post-act screenshot verified against the current keyword.",
        "screenshot": screenshot_payload,
        "page_state": page_state,
        "diagnostics": diagnostics,
    }


def _assert_visible_keyword(
    client: "MidsceneStdioClient",
    keyword: str,
    interrupt_check: Optional[Callable[[], None]],
    keyword_deadline: float,
    timeout_seconds: float,
) -> Dict[str, Any]:
    prompt = (
        "Using only the current visible screenshot, assert whether the Taobao "
        f"search input box visibly contains exactly this keyword: {keyword!r}. "
        "Return true only if the visible text in the search box matches exactly. "
        "If a different keyword is visible, or if the text cannot be read, return false."
    )
    try:
        result = client.call_tool(
            "assert",
            {"prompt": prompt},
            timeout_seconds=timeout_seconds,
            interrupt_check=interrupt_check,
            keyword_deadline=keyword_deadline,
            keyword=keyword,
        )
    except Exception as exc:
        return {
            "status": "unknown",
            "message": f"Post-act keyword assertion failed: {exc}",
            "raw_text": "",
        }

    text = _tool_text(result)
    normalized = " ".join(text.lower().split())
    if result.get("isError"):
        return {
            "status": "unknown",
            "message": text or "Post-act keyword assertion returned an MCP error.",
            "raw_text": text,
        }
    if _assertion_text_is_true(normalized):
        return {
            "status": "matched",
            "message": "Visible search keyword matched current keyword.",
            "raw_text": text,
        }
    if _assertion_text_is_false(normalized):
        return {
            "status": "mismatch",
            "message": (
                "Visible search keyword did not match current keyword after Midscene act complete; "
                "session stopped to avoid evidence pollution."
            ),
            "raw_text": text,
        }
    return {
        "status": "unknown",
        "message": "Post-act keyword assertion was inconclusive.",
        "raw_text": text,
    }


def _assertion_text_is_true(normalized_text: str) -> bool:
    positives = [
        '"success":true',
        '"success": true',
        '"passed":true',
        '"passed": true',
        "assertion passed",
        "true",
        "是",
        "匹配",
        "一致",
    ]
    negatives = ["false", "not match", "不匹配", "不一致", "无法", "不能", "未"]
    return any(item in normalized_text for item in positives) and not any(
        item in normalized_text for item in negatives
    )


def _assertion_text_is_false(normalized_text: str) -> bool:
    negatives = [
        '"success":false',
        '"success": false',
        '"passed":false',
        '"passed": false',
        "assertion failed",
        "false",
        "not match",
        "different keyword",
        "不匹配",
        "不一致",
        "不同",
    ]
    return any(item in normalized_text for item in negatives)


def _page_state_review_reason(page_state: Dict[str, Any]) -> str:
    status = str(page_state.get("status") or UNKNOWN)
    reason = str(page_state.get("reason") or "")
    if status in {LOGIN_REQUIRED, CAPTCHA_REQUIRED, WHITE_SKELETON, "risk_suspected", "popup_blocked"}:
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


def _raise_if_abnormal_act(result: Dict[str, Any], default_context: str) -> None:
    classification = classify_midscene_act_result(result, default_context=default_context)
    if classification["abnormal"]:
        raise MidsceneActionAbnormal(
            reason=classification["stop_reason"],
            rough_state=classification["rough_state"],
            message=classification["message"],
        )


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

    patterns = [
        ("captcha_required", ["captcha", "验证码", "滑块", "验证", "security verification", "安全验证"]),
        ("login_required", ["login required", "please login", "sign in", "登录", "请登录", "重新登录"]),
        ("risk_suspected", ["risk", "风控", "风险", "unusual account", "异常账号", "账号异常", "安全检查"]),
        ("popup_blocked", ["permission panel", "automation permission", "权限", "弹窗", "blocked", "拦截"]),
        ("white_skeleton", ["white skeleton", "白屏", "骨架屏", "skeleton", "blank page"]),
        ("page_not_loaded", ["page not loaded", "加载失败", "无法打开", "chrome/taobao is unavailable"]),
        ("midscene_reported_failure", ["stop and report failure", "report failure", "failed to", "cannot", "unable to"]),
    ]
    for reason, needles in patterns:
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


def _is_rate_limited_text(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    needles = [
        "429",
        "rate limit",
        "rate-limit",
        "ratelimit",
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
    return (
        "You are the bounded Taobao capture worker for one keyword. Use only "
        "visible-screen reasoning and system mouse/keyboard actions. Do not read "
        "DOM, HTML, network, cookies, storage, selector maps, page source, or JS "
        "evaluated data. Bring the existing Chrome window with the dedicated "
        "Taobao profile to the foreground if needed. If Codex, Terminal, Cursor, "
        "or another app is visible, switch to Chrome first and do not type the "
        "keyword into that app. If Chrome/Taobao is unavailable, or login, "
        "captcha, security verification, risk warning, unusual account state, "
        "or an automation permission panel is visible, stop and report failure. "
        "From the visible Taobao search box, search exactly this keyword: "
        f"{keyword!r}. Wait until visible search results settle. Leave the page "
        "positioned at the first results viewport. Do not output product rows. "
        f"Later tile captures will use about {scroll_distance} px between viewports."
    )


def _next_tile_prompt(keyword: str, tile_index: int, scroll_distance: int) -> str:
    return (
        "You are continuing the bounded Taobao capture session using only "
        "visible-screen reasoning and system mouse/keyboard/scroll actions. The "
        f"current keyword is {keyword!r}. If login, captcha, security/risk, "
        "unusual account state, white skeleton, or a permission panel is visible, "
        "stop and report failure. Otherwise move to the next visible results "
        f"viewport for tile_{tile_index:02d}; use a normal page-level downward "
        f"scroll of about {scroll_distance} px if appropriate, then wait for "
        "visible content to settle. Do not output product rows and do not change "
        "account state."
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
