"""
Framework capture worker for Taobao visual collection contracts.

This v1 worker intentionally performs no browser, DOM, CDP, network, storage,
or Midscene actions. It validates the file contract surface and writes the same
result artifacts that a future real pure-vision worker will write.
"""
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from modules.page_sampling import write_task_event
from modules.utils import ensure_dir
from modules.visual_control import write_worker_runtime


def run_capture_worker(contract_path: str, simulate: bool = True) -> Dict[str, Any]:
    """Run the capture-worker framework against a contract JSON file.

    In simulate mode, each keyword is marked skipped with a simulated stop
    reason. In non-simulate mode, v1 still refuses real capture and writes
    failed_recoverable framework results.
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
        simulate=simulate,
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
        simulate=simulate,
        keyword_count=len(keyword_tasks),
    )

    keyword_results: List[Dict[str, Any]] = []
    for fallback_index, task in enumerate(keyword_tasks, start=1):
        result = _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            simulate=simulate,
        )
        keyword_results.append(result)

    elapsed_seconds = round(time.monotonic() - started, 3)
    session_status = "simulated" if simulate else "failed_recoverable"
    stop_reason = "simulated_framework_only" if simulate else "real_capture_not_implemented"
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
        "notes": (
            "Framework-only capture worker. No Midscene, browser, DOM, CDP, "
            "network, storage, or Taobao actions were performed."
        ),
        "created_at": now,
        "updated_at": _now(),
    }
    _write_json(session_result_path, session_result)
    write_task_event(
        task_dir,
        event="visual_capture_worker_finished",
        level="info" if simulate else "warning",
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
        simulate=simulate,
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


def _write_keyword_result(
    task: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    simulate: bool,
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
    status = "skipped" if simulate else "failed_recoverable"
    stop_reason = "simulated_framework_only" if simulate else "real_capture_not_implemented"
    rough_state = "simulated" if simulate else "not_started"
    now = _now()
    payload = {
        "schema": "taobao_visual_capture_keyword_result_v1",
        "task_id": task.get("task_id") or f"{run_id}-s{session_index:02d}-k{keyword_index:03d}",
        "keyword_index": keyword_index,
        "keyword": keyword,
        "status": status,
        "rough_state": rough_state,
        "screenshots": [],
        "abnormal_screenshot": "",
        "abnormal_screenshot_path": task.get("abnormal_screenshot_path")
        or capture_plan.get("abnormal_screenshot_path")
        or "",
        "elapsed_seconds": 0,
        "stop_reason": stop_reason,
        "notes": (
            "Simulated framework result; no real Taobao/Midscene action was performed."
            if simulate
            else "Recoverable framework failure; real capture is not implemented in v1."
        ),
        "capture_plan": capture_plan,
        "result_path": result_path,
        "created_at": now,
        "updated_at": now,
    }
    _write_json(result_path, payload)
    write_task_event(
        task_dir,
        event="visual_capture_keyword_result_written",
        level="info" if simulate else "warning",
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
        "result_path": result_path,
        "stop_reason": stop_reason,
    }


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
