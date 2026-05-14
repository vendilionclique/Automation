"""
Session-level visual extract worker.

This worker consumes screenshots already captured by the Midscene computer
worker. It does not open a browser, inspect DOM/HTML/network/storage, or call an
external model in v1. By default it writes supervisor review artifacts with
empty rows; tests and manual dry runs can pass rows_file to simulate extraction.
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from modules.page_sampling import (
    page_sampling_config_from_settings,
    write_task_event,
    write_tile_summary,
)
from modules.session_capsule import session_dir_for
from modules.utils import ConfigManager, ensure_dir, get_project_root
from modules.visual_capture import keyword_evidence_dir, maybe_delete_screenshot
from modules.visual_control import write_worker_runtime
from modules.vision_extract import export_jsonl_to_excel, ingest_rows


READY_CAPTURE_STATUSES = {"captured", "completed", "success"}


def run_extract_worker(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    rows_file: Optional[str] = None,
    simulate_empty: bool = True,
) -> Dict[str, Any]:
    """Review captured keyword screenshots and ingest simulated rows.

    Args:
        plan_id: Daily visual plan/run id under data/tasks.
        session_index: Daily session number.
        config_file: settings.ini path.
        rows_file: Optional JSON rows payload used as a simulated extraction.
        simulate_empty: When true and rows_file is absent, do not call any model;
            write empty pending rows and mark the keyword for supervisor review.
    """
    task_dir = _task_dir(plan_id)
    session_index = int(session_index)
    session_dir = session_dir_for(plan_id, session_index)
    ensure_dir(session_dir)
    manifest_path = os.path.join(task_dir, "visual_tasks.json")
    manifest = _load_json(manifest_path)
    config = ConfigManager(config_file)
    sampling_config = page_sampling_config_from_settings(config)
    confidence_threshold = config.getfloat(
        "VISUAL_CAPTURE", "confidence_threshold", fallback=0.80
    )
    rows_payload = _load_rows_payload(rows_file) if rows_file else None
    started_at = _now()

    write_worker_runtime(
        plan_id,
        session_index,
        "extract",
        "running",
        started_at=started_at,
        rows_file=os.path.abspath(rows_file) if rows_file else "",
        simulate_empty=bool(simulate_empty),
    )
    write_task_event(
        task_dir,
        event="extract_worker_started",
        run_id=plan_id,
        session_index=session_index,
        rows_file=os.path.abspath(rows_file) if rows_file else "",
        simulate_empty=bool(simulate_empty),
    )

    records = [
        record
        for record in manifest.get("records", [])
        if int(record.get("extra", {}).get("daily_session_index") or 0) == session_index
    ]
    results: List[Dict[str, Any]] = []
    processed = 0
    waiting = 0
    needs_review = 0
    failed = 0

    try:
        for record in records:
            result = _process_record(
                task_dir=task_dir,
                plan_id=plan_id,
                session_index=session_index,
                record=record,
                rows_payload=rows_payload,
                simulate_empty=simulate_empty,
                confidence_threshold=confidence_threshold,
                target_limit=sampling_config.target_listings_per_keyword,
            )
            results.append(result)
            status = str(result.get("status") or "")
            if status == "waiting_capture":
                waiting += 1
            elif status in {"needs_supervisor", "needs_review"}:
                needs_review += 1
                processed += 1
            elif status == "failed":
                failed += 1
                processed += 1
            else:
                processed += 1

        raw_jsonl = os.path.join(task_dir, "raw_rows.jsonl")
        raw_excel = os.path.join(task_dir, "raw_results.xlsx")
        export_jsonl_to_excel(raw_jsonl, raw_excel)
        manifest.setdefault("session", {})
        manifest["session"]["extract_worker_result"] = os.path.join(
            session_dir, "extract_worker_result.json"
        )
        manifest["session"]["extract_worker_status"] = _overall_status(
            processed, waiting, needs_review, failed
        )
        manifest["session"]["updated_at"] = _now()
        _write_json(manifest_path, manifest)

        summary = {
            "ok": failed == 0,
            "plan_id": plan_id,
            "session_index": session_index,
            "status": manifest["session"]["extract_worker_status"],
            "started_at": started_at,
            "updated_at": _now(),
            "processed_keywords": processed,
            "waiting_keywords": waiting,
            "needs_review_keywords": needs_review,
            "failed_keywords": failed,
            "rows_file": os.path.abspath(rows_file) if rows_file else "",
            "simulate_empty": bool(simulate_empty),
            "raw_jsonl": raw_jsonl,
            "raw_excel": raw_excel,
            "keyword_results": results,
        }
        result_path = os.path.join(session_dir, "extract_worker_result.json")
        _write_json(result_path, summary)
        write_worker_runtime(
            plan_id,
            session_index,
            "extract",
            summary["status"],
            result_path=result_path,
            processed_keywords=processed,
            waiting_keywords=waiting,
            needs_review_keywords=needs_review,
            failed_keywords=failed,
            raw_jsonl=raw_jsonl,
            raw_excel=raw_excel,
        )
        write_task_event(
            task_dir,
            event="extract_worker_finished",
            level="warning" if needs_review or failed else "info",
            run_id=plan_id,
            session_index=session_index,
            status=summary["status"],
            processed_keywords=processed,
            waiting_keywords=waiting,
            needs_review_keywords=needs_review,
            failed_keywords=failed,
        )
        return {**summary, "result_path": result_path}
    except Exception as exc:
        write_worker_runtime(
            plan_id,
            session_index,
            "extract",
            "failed",
            error=str(exc),
        )
        write_task_event(
            task_dir,
            event="extract_worker_failed",
            level="error",
            run_id=plan_id,
            session_index=session_index,
            error=str(exc),
        )
        raise


def _process_record(
    task_dir: str,
    plan_id: str,
    session_index: int,
    record: Dict[str, Any],
    rows_payload: Optional[Any],
    simulate_empty: bool,
    confidence_threshold: float,
    target_limit: int,
) -> Dict[str, Any]:
    keyword = str(record.get("keyword") or "").strip()
    evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
    keyword_result_path = record.get("extra", {}).get("keyword_result") or os.path.join(
        evidence_dir, "keyword_result.json"
    )
    keyword_result = _load_json_if_exists(keyword_result_path)
    capture_status = str(keyword_result.get("status") or "").strip().lower()
    screenshots = _collect_screenshots(keyword_result, record)
    rows_pending_path = os.path.join(evidence_dir, "rows_pending.json")
    extract_result_path = os.path.join(evidence_dir, "extract_result.json")

    if capture_status not in READY_CAPTURE_STATUSES:
        result = {
            "keyword": keyword,
            "status": "waiting_capture",
            "ok": False,
            "capture_status": capture_status,
            "keyword_result": keyword_result_path,
            "screenshots": screenshots,
            "rows_pending": "",
            "extract_result": extract_result_path,
            "error": "keyword_result_not_ready",
        }
        _write_json(extract_result_path, result)
        write_task_event(
            task_dir,
            event="extract_waiting_capture",
            level="warning",
            run_id=plan_id,
            session_index=session_index,
            keyword=keyword,
            capture_status=capture_status,
            keyword_result_path=keyword_result_path,
        )
        return result

    rows = _rows_for_keyword(rows_payload, keyword)
    if rows_payload is None and simulate_empty:
        rows = []
    pending = {
        "schema": "taobao_visual_rows_pending_v1",
        "plan_id": plan_id,
        "session_index": session_index,
        "keyword": keyword,
        "created_at": _now(),
        "source": "rows_file" if rows_payload is not None else "simulate_empty",
        "keyword_result": keyword_result_path,
        "screenshots": screenshots,
        "rows": rows,
    }
    _write_json(rows_pending_path, pending)

    if not rows:
        _mark_record_needs_review(record, "manual_review_needed")
        result = {
            "keyword": keyword,
            "status": "needs_supervisor",
            "ok": False,
            "capture_status": capture_status,
            "keyword_result": keyword_result_path,
            "screenshots": screenshots,
            "rows_pending": rows_pending_path,
            "extract_result": extract_result_path,
            "rows_received": 0,
            "rows_written": 0,
            "screenshots_deleted": [],
            "screenshots_retained": screenshots,
            "error": "empty_rows_need_supervisor",
        }
        _write_json(extract_result_path, result)
        _write_extract_observability(
            task_dir,
            plan_id,
            session_index,
            keyword,
            result,
            rough_state="needs_supervisor",
            stop_reason="empty_rows_need_supervisor",
        )
        return result

    ingest = ingest_rows(
        task_dir=task_dir,
        keyword=keyword,
        rows=rows,
        screenshot_path=screenshots[0] if screenshots else "",
        confidence_threshold=confidence_threshold,
        retain_screenshot=True,
        target_limit=target_limit,
        dedupe=True,
    )
    ingest_payload = ingest.to_dict()
    deleted = _delete_screenshots(screenshots) if ingest.ok else []
    retained = [path for path in screenshots if path not in deleted]
    if ingest.ok:
        _mark_record_extracted(record, ingest_payload)
    else:
        _mark_record_needs_review(record, ingest.error or "manual_review_needed")

    result = {
        "keyword": keyword,
        "status": "extracted" if ingest.ok else "needs_review",
        "ok": bool(ingest.ok),
        "capture_status": capture_status,
        "keyword_result": keyword_result_path,
        "screenshots": screenshots,
        "rows_pending": rows_pending_path,
        "extract_result": extract_result_path,
        "ingest_result": ingest_payload,
        "rows_received": ingest.rows_received,
        "rows_written": ingest.rows_written,
        "screenshots_deleted": deleted,
        "screenshots_retained": retained,
        "error": ingest.error,
    }
    _write_json(extract_result_path, result)
    _write_extract_observability(
        task_dir,
        plan_id,
        session_index,
        keyword,
        result,
        rough_state=result["status"],
        stop_reason="ingest_ok" if ingest.ok else "ingest_needs_review",
    )
    return result


def _write_extract_observability(
    task_dir: str,
    plan_id: str,
    session_index: int,
    keyword: str,
    result: Dict[str, Any],
    rough_state: str,
    stop_reason: str,
) -> None:
    level = "info" if result.get("ok") else "warning"
    screenshots = list(result.get("screenshots") or [])
    retained = set(result.get("screenshots_retained") or screenshots)
    write_task_event(
        task_dir,
        event="extract_keyword_finished",
        level=level,
        run_id=plan_id,
        session_index=session_index,
        keyword=keyword,
        status=result.get("status", ""),
        rows_received=result.get("rows_received", 0),
        rows_written=result.get("rows_written", 0),
        screenshots_count=len(screenshots),
        screenshots_deleted=len(result.get("screenshots_deleted") or []),
        stop_reason=stop_reason,
        error=result.get("error"),
    )
    for index, path in enumerate(screenshots):
        tile_id = os.path.splitext(os.path.basename(path))[0] or f"tile_{index:02d}"
        write_tile_summary(
            task_dir,
            run_id=plan_id,
            keyword=keyword,
            tile_id=tile_id,
            rough_state=rough_state,
            image_path=path,
            image_retained=path in retained and os.path.exists(path),
            rows_extracted=int(result.get("rows_received") or 0),
            new_rows_after_dedupe=int(result.get("rows_written") or 0),
            stop_reason=stop_reason,
            notes="extract_worker",
        )


def _rows_for_keyword(payload: Optional[Any], keyword: str) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return _filter_rows(payload, keyword)
    if isinstance(payload, dict):
        if isinstance(payload.get("keywords"), dict):
            return [dict(row) for row in payload["keywords"].get(keyword, [])]
        if isinstance(payload.get(keyword), list):
            return [dict(row) for row in payload.get(keyword, [])]
        if isinstance(payload.get("rows"), list):
            return _filter_rows(payload.get("rows", []), keyword)
    return []


def _filter_rows(rows: Iterable[Any], keyword: str) -> List[Dict[str, Any]]:
    normalized = [dict(row) for row in rows if isinstance(row, dict)]
    matching = [
        row
        for row in normalized
        if str(row.get("搜索关键词") or row.get("keyword") or "").strip() == keyword
    ]
    if matching:
        return matching
    without_keyword = [
        row
        for row in normalized
        if not str(row.get("搜索关键词") or row.get("keyword") or "").strip()
    ]
    return without_keyword if len(normalized) == len(without_keyword) else []


def _collect_screenshots(keyword_result: Dict[str, Any], record: Dict[str, Any]) -> List[str]:
    screenshots: List[str] = []
    for value in keyword_result.get("screenshots", []) or []:
        path = _screenshot_path(value)
        if path:
            screenshots.append(os.path.abspath(path))
    abnormal = keyword_result.get("abnormal_screenshot")
    if abnormal:
        screenshots.append(os.path.abspath(str(abnormal)))
    if not screenshots:
        for value in record.get("extra", {}).get("screenshots", []) or []:
            path = _screenshot_path(value)
            if path:
                screenshots.append(os.path.abspath(path))
    return _dedupe_keep_order(screenshots)


def _screenshot_path(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("path") or value.get("image_path") or "").strip()
    return str(value or "").strip()


def _delete_screenshots(screenshots: Iterable[str]) -> List[str]:
    deleted = []
    for path in _dedupe_keep_order([os.path.abspath(str(item)) for item in screenshots if item]):
        if maybe_delete_screenshot(path):
            deleted.append(path)
    return deleted


def _mark_record_extracted(record: Dict[str, Any], ingest_result: Dict[str, Any]) -> None:
    now = _now()
    record["status"] = "extracted"
    record["failure_reason"] = None
    record["last_action"] = "extract_worker_ingested_rows"
    record["finished_at"] = now
    record["updated_at"] = now
    record.setdefault("extra", {})
    record["extra"]["extract_ingest_result"] = ingest_result


def _mark_record_needs_review(record: Dict[str, Any], reason: str) -> None:
    record["status"] = "needs_review"
    record["failure_reason"] = reason
    record["last_action"] = "extract_worker_needs_supervisor"
    record["updated_at"] = _now()


def _overall_status(processed: int, waiting: int, needs_review: int, failed: int) -> str:
    if failed:
        return "failed"
    if needs_review:
        return "needs_review"
    if waiting and not processed:
        return "waiting_capture"
    if waiting:
        return "completed_with_waiting"
    return "completed"


def _load_rows_payload(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json_if_exists(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _task_dir(plan_id: str) -> str:
    return os.path.join(get_project_root(), "data", "tasks", plan_id)


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
