"""
Visual collection orchestration.
"""
import json
import os
import tempfile
from datetime import datetime
from typing import Dict, Optional

from modules.midscene_computer_driver import (
    midscene_computer_config_from_settings,
    write_midscene_computer_request,
    write_midscene_session_worker_contract,
)
from modules.page_sampling import (
    page_sampling_config_from_settings,
    write_task_event,
    write_tile_summary,
)
from modules.session_state import initial_session_state, session_policy_from_settings
from modules.session_capsule import (
    RUNNABLE_STATUSES,
    acquire_session_lease,
    build_session_capsule,
    complete_session_lease,
    heartbeat_session_lease,
    session_dir_for,
)
from modules.utils import ConfigManager, ensure_dir, get_project_root
from modules.visual_capture import (
    CaptureRecord,
    keyword_evidence_dir,
    write_capture_manifest,
    write_json,
)
from modules.vision_extract import export_jsonl_to_excel


def task_dir_for_run(run_id: str) -> str:
    root = get_project_root()
    return os.path.join(root, "data", "tasks", run_id)


def load_visual_manifest(run_id: str) -> Dict:
    task_dir = task_dir_for_run(run_id)
    path = os.path.join(task_dir, "visual_tasks.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到视觉任务清单: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"读取视觉任务清单 JSON 失败: {path}: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc


def save_visual_manifest(run_id: str, manifest: Dict) -> str:
    task_dir = task_dir_for_run(run_id)
    path = os.path.join(task_dir, "visual_tasks.json")
    ensure_dir(task_dir)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=task_dir,
            prefix="visual_tasks.",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_path = f.name
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
        try:
            dir_fd = os.open(task_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return path


def prepare_single_keyword_run(keyword: str, config_file: str = "config/settings.ini") -> Dict:
    ConfigManager(config_file)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = task_dir_for_run(run_id)
    evidence_dir = keyword_evidence_dir(task_dir, keyword)
    ensure_dir(task_dir)
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {"keyword": keyword, "config": os.path.abspath(config_file)},
        "workflow": "midscene_computer_visual_capture",
        "keywords": [keyword],
        "records": [
            {
                "keyword": keyword,
                "status": "pending",
                "failure_reason": None,
                "error": None,
                "evidence_dir": evidence_dir,
                "retry_count": 0,
                "last_action": "visual_task_prepared",
                "agent_notes": "",
                "started_at": None,
                "finished_at": None,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "extra": {},
            }
        ],
    }
    save_visual_manifest(run_id, manifest)
    return manifest


def run_visual_collection(
    run_id: str,
    config_file: str = "config/settings.ini",
    limit: Optional[int] = None,
    manual_state: Optional[str] = None,
    session_index: Optional[int] = None,
    force_lease: bool = False,
) -> Dict:
    config = ConfigManager(config_file)
    midscene_config = midscene_computer_config_from_settings(config)
    sampling_config = page_sampling_config_from_settings(config)
    policy = session_policy_from_settings(config)
    manifest = load_visual_manifest(run_id)
    manifest.setdefault("session", initial_session_state(policy))
    task_dir = task_dir_for_run(run_id)
    effective_limit = limit
    if session_index is not None:
        if effective_limit is None:
            effective_limit = midscene_config.session_keyword_limit
        else:
            effective_limit = min(int(effective_limit), midscene_config.session_keyword_limit)
    capsule = None
    lease_acquired = False
    if session_index is not None:
        capsule = build_session_capsule(
            run_id,
            session_index,
            config_file=config_file,
            limit=effective_limit,
            manual_state=manual_state,
        )
        acquire_session_lease(
            run_id,
            session_index,
            owner="visual_pipeline",
            ttl_minutes=max(60, policy.cooldown_minutes * 4),
            force=force_lease,
        )
        lease_acquired = True

    processed = 0
    results = []
    session_records = []
    worker_contract = None
    run_status = "requests_prepared"
    try:
        for record in manifest.get("records", []):
            if effective_limit is not None and processed >= effective_limit:
                break
            if session_index is not None:
                record_session = record.get("extra", {}).get("daily_session_index")
                if int(record_session or 0) != int(session_index):
                    continue
            if record.get("status") not in RUNNABLE_STATUSES:
                continue

            keyword = record["keyword"]
            record_session = record.get("extra", {}).get("daily_session_index")
            write_task_event(
                task_dir,
                event="keyword_request_started",
                run_id=run_id,
                session_index=record_session,
                keyword=keyword,
                provider="midscene_computer",
            )
            record["status"] = "needs_midscene_computer"
            record["started_at"] = record.get("started_at") or datetime.now().isoformat(timespec="seconds")
            record["updated_at"] = datetime.now().isoformat(timespec="seconds")
            record["last_action"] = "midscene_computer_request_prepared"
            save_visual_manifest(run_id, manifest)

            evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
            request = write_midscene_computer_request(
                run_id=run_id,
                keyword=keyword,
                evidence_dir=evidence_dir,
                config=midscene_config,
                sampling_config=sampling_config,
                manual_state=manual_state,
            )
            target = request.start_url

            record["status"] = request.status
            record["failure_reason"] = None
            record["evidence_dir"] = evidence_dir
            record["last_action"] = "midscene_computer_request_prepared"
            record["updated_at"] = datetime.now().isoformat(timespec="seconds")
            record.setdefault("extra", {})
            record["extra"]["midscene_computer_request"] = request.request_path
            record["extra"]["midscene_computer_instructions"] = request.instruction_path
            record["extra"]["target_url"] = target
            record["extra"]["expected_screenshot"] = request.screenshot_path
            record["extra"]["sampling"] = sampling_config.to_dict()

            result_payload = {
                "keyword": keyword,
                "status": request.status,
                "request": request.request_path,
                "instructions": request.instruction_path,
                "target_url": target,
                "provider": "midscene_computer",
            }

            session = manifest.setdefault("session", initial_session_state(policy))
            session["status"] = "awaiting_midscene_computer"
            session["updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_visual_manifest(run_id, manifest)
            write_task_event(
                task_dir,
                event="keyword_request_prepared",
                run_id=run_id,
                session_index=record_session,
                keyword=keyword,
                status=record["status"],
                request_path=request.request_path,
                instructions_path=request.instruction_path,
            )
            results.append(result_payload)
            session_records.append(record)
            processed += 1
            if session_index is not None:
                heartbeat_session_lease(
                    run_id,
                    session_index,
                    ttl_minutes=max(60, policy.cooldown_minutes * 4),
                )
    except Exception:
        run_status = "failed"
        raise
    finally:
        if session_index is not None and session_records:
            session_dir = session_dir_for(run_id, session_index)
            worker_contract = write_midscene_session_worker_contract(
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                session_dir=session_dir,
                records=session_records,
                config=midscene_config,
                sampling_config=sampling_config,
                manual_state=manual_state,
            )
            manifest.setdefault("session", initial_session_state(policy))
            manifest["session"]["worker_contract"] = worker_contract
            manifest["session"]["status"] = "awaiting_midscene_session_worker"
            manifest["session"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
            for record in session_records:
                record.setdefault("extra", {})
                record["extra"]["midscene_session_worker_contract"] = worker_contract["contract"]
                record["extra"]["midscene_session_worker_result"] = worker_contract["result"]
                record["last_action"] = "midscene_session_worker_contract_prepared"
                record["updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_visual_manifest(run_id, manifest)
            write_task_event(
                task_dir,
                event="midscene_session_worker_contract_prepared",
                run_id=run_id,
                session_index=session_index,
                contract_path=worker_contract["contract"],
                instructions_path=worker_contract["instructions"],
                result_path=worker_contract["result"],
                keyword_count=worker_contract["keyword_count"],
            )
        if lease_acquired:
            complete_session_lease(
                run_id,
                session_index,
                status=run_status,
                summary={
                    "processed": processed,
                    "result_count": len(results),
                    "results": results,
                    "worker_contract": worker_contract,
                },
            )

    summary_path = write_json(
        os.path.join(task_dir, "visual_run_summary.json"),
        {
            "run_id": run_id,
            "processed": processed,
            "session_index": session_index,
            "limit": effective_limit,
            "session_capsule": capsule,
            "worker_contract": worker_contract,
            "results": results,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return {
        "run_id": run_id,
        "processed": processed,
        "session_index": session_index,
        "limit": effective_limit,
        "session_capsule": capsule,
        "worker_contract": worker_contract,
        "summary": summary_path,
        "results": results,
    }


def export_raw_rows(run_id: str) -> Dict:
    task_dir = task_dir_for_run(run_id)
    raw_jsonl = os.path.join(task_dir, "raw_rows.jsonl")
    raw_excel = os.path.join(task_dir, "raw_results.xlsx")
    export_jsonl_to_excel(raw_jsonl, raw_excel)
    return {"run_id": run_id, "raw_jsonl": raw_jsonl, "raw_excel": raw_excel}


def sync_midscene_worker_results(run_id: str, session_index: int) -> Dict:
    task_dir = task_dir_for_run(run_id)
    manifest = load_visual_manifest(run_id)
    session_dir = session_dir_for(run_id, session_index)
    worker_result_path = os.path.join(session_dir, "session_worker_result.json")
    worker_result = _load_json_if_exists(worker_result_path)
    updated = 0
    missing = 0
    results = []

    for record in manifest.get("records", []):
        record_session = record.get("extra", {}).get("daily_session_index")
        if int(record_session or 0) != int(session_index):
            continue
        keyword = record.get("keyword", "")
        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        keyword_result_path = os.path.join(evidence_dir, "keyword_result.json")
        keyword_result = _load_json_if_exists(keyword_result_path)
        if not keyword_result:
            missing += 1
            continue

        status = str(keyword_result.get("status") or "").strip().lower()
        rough_state = str(keyword_result.get("rough_state") or "").strip()
        if status in {"captured", "completed", "success"}:
            record["status"] = "captured"
            record["failure_reason"] = None
        elif status in {"needs_review", "review"}:
            record["status"] = "needs_review"
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or "needs_review"
        elif status in {"real_not_available"}:
            record["status"] = "paused_needs_human"
            record["failure_reason"] = (
                keyword_result.get("stop_reason") or rough_state or "real_capture_not_available"
            )
        elif status in {"paused_needs_human", "paused_needs_supervisor"}:
            record["status"] = status
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or status
        elif status in {"cooldown", "cooling_down"}:
            record["status"] = "cooldown"
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or "cooldown"
        elif status in {"failed_recoverable"}:
            record["status"] = "failed_recoverable"
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or "worker_failed"
        elif status in {"failed_hard"}:
            record["status"] = "failed_hard"
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or "worker_failed_hard"
        elif status in {"skipped"}:
            record["status"] = "skipped"
            record["failure_reason"] = keyword_result.get("stop_reason") or "skipped"
        else:
            record["status"] = "failed"
            record["failure_reason"] = keyword_result.get("stop_reason") or rough_state or "worker_failed"

        record["last_action"] = "midscene_worker_result_synced"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record.setdefault("extra", {})
        record["extra"]["keyword_result"] = keyword_result_path
        record["extra"]["worker_status"] = status
        record["extra"]["rough_state"] = rough_state
        record["extra"]["screenshots"] = keyword_result.get("screenshots", [])
        updated += 1
        results.append(
            {
                "keyword": keyword,
                "status": record["status"],
                "rough_state": rough_state,
                "keyword_result": keyword_result_path,
            }
        )
        write_task_event(
            task_dir,
            event="midscene_worker_result_synced",
            level="info" if record["status"] == "captured" else "warning",
            run_id=run_id,
            session_index=session_index,
            keyword=keyword,
            status=record["status"],
            rough_state=rough_state,
            keyword_result_path=keyword_result_path,
            stop_reason=keyword_result.get("stop_reason", ""),
        )

    session = manifest.setdefault("session", {})
    session["worker_result"] = worker_result_path
    session["worker_status"] = worker_result.get("status", "") if worker_result else ""
    session["status"] = "worker_results_synced"
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path = save_visual_manifest(run_id, manifest)
    summary_path = write_json(
        os.path.join(session_dir, "worker_sync_summary.json"),
        {
            "run_id": run_id,
            "session_index": session_index,
            "worker_result": worker_result_path,
            "worker_result_exists": bool(worker_result),
            "updated": updated,
            "missing": missing,
            "results": results,
            "manifest": manifest_path,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return {
        "ok": True,
        "run_id": run_id,
        "session_index": session_index,
        "updated": updated,
        "missing": missing,
        "worker_result_exists": bool(worker_result),
        "summary": summary_path,
        "results": results,
    }


def update_manifest_after_ingest(run_id: str, keyword: str, ingest_result: Dict) -> str:
    manifest = load_visual_manifest(run_id)
    task_dir = task_dir_for_run(run_id)
    now = datetime.now().isoformat(timespec="seconds")
    updated_record = False
    for record in manifest.get("records", []):
        if record.get("keyword") != keyword:
            continue
        updated_record = True
        record["status"] = "extracted" if ingest_result.get("ok") else "needs_review"
        record["failure_reason"] = None if ingest_result.get("ok") else ingest_result.get("error")
        record["last_action"] = "visual_rows_ingested"
        record["updated_at"] = now
        record.setdefault("extra", {})
        record["extra"]["ingest_result"] = ingest_result
        record_session = record.get("extra", {}).get("daily_session_index")
        if ingest_result.get("ok"):
            record["finished_at"] = now
        screenshot_path = ingest_result.get("screenshot_path") or record.get("extra", {}).get("expected_screenshot", "")
        retained = bool(ingest_result.get("screenshot_retained", False))
        write_task_event(
            task_dir,
            event="visual_rows_ingested",
            level="info" if ingest_result.get("ok") else "warning",
            run_id=run_id,
            session_index=record_session,
            keyword=keyword,
            status=record["status"],
            rows_written=ingest_result.get("rows_written", 0),
            screenshot_path=screenshot_path,
            screenshot_retained=retained,
            rows_received=ingest_result.get("rows_received", ingest_result.get("rows_written", 0)),
            duplicates_removed=ingest_result.get("duplicates_removed", 0),
            rows_dropped_by_limit=ingest_result.get("rows_dropped_by_limit", 0),
            error=ingest_result.get("error"),
        )
        write_tile_summary(
            task_dir,
            run_id=run_id,
            keyword=keyword,
            tile_id="batch_ingest",
            rough_state=record["status"],
            image_path=screenshot_path,
            image_retained=retained,
            rows_extracted=int(ingest_result.get("rows_received", ingest_result.get("rows_written", 0)) or 0),
            new_rows_after_dedupe=int(ingest_result.get("rows_written", 0) or 0),
            stop_reason="ingest_ok" if ingest_result.get("ok") else "ingest_needs_review",
            notes="batch_tiles_or_single_screenshot_ingested",
        )
        if screenshot_path:
            capture = CaptureRecord(
                run_id=run_id,
                keyword=keyword,
                evidence_dir=record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword),
                screenshot_path=screenshot_path,
                status=record["status"],
                page_state={
                    "status": record["status"],
                    "reason": "codex_visual_mcp_ingested_rows",
                    "rows_written": ingest_result.get("rows_written", 0),
                },
                retained=retained,
                notes="codex_visual_mcp",
            )
            write_capture_manifest(capture)
        break
    if updated_record:
        session = manifest.setdefault("session", {})
        session["status"] = "healthy" if ingest_result.get("ok") else "needs_review"
        session["updated_at"] = now
    return save_visual_manifest(run_id, manifest)


def _load_json_if_exists(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
