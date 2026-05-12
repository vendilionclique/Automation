"""
Visual collection orchestration.
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional

from modules.midscene_computer_driver import (
    midscene_computer_config_from_settings,
    write_midscene_computer_request,
)
from modules.page_sampling import (
    page_sampling_config_from_settings,
    write_task_event,
    write_tile_summary,
)
from modules.session_state import initial_session_state, session_policy_from_settings
from modules.session_capsule import (
    acquire_session_lease,
    build_session_capsule,
    complete_session_lease,
    heartbeat_session_lease,
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_visual_manifest(run_id: str, manifest: Dict) -> str:
    task_dir = task_dir_for_run(run_id)
    path = os.path.join(task_dir, "visual_tasks.json")
    ensure_dir(task_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
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
    capsule = None
    lease_acquired = False
    if session_index is not None:
        capsule = build_session_capsule(
            run_id,
            session_index,
            config_file=config_file,
            limit=limit,
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
    run_status = "requests_prepared"
    try:
        for record in manifest.get("records", []):
            if limit is not None and processed >= limit:
                break
            if session_index is not None:
                record_session = record.get("extra", {}).get("daily_session_index")
                if int(record_session or 0) != int(session_index):
                    continue
            if record.get("status") not in (
                "pending",
                "cooldown",
                "failed",
                "needs_midscene_computer",
            ):
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
        if lease_acquired:
            complete_session_lease(
                run_id,
                session_index,
                status=run_status,
                summary={
                    "processed": processed,
                    "result_count": len(results),
                    "results": results,
                },
            )

    summary_path = write_json(
        os.path.join(task_dir, "visual_run_summary.json"),
        {
            "run_id": run_id,
            "processed": processed,
            "session_index": session_index,
            "session_capsule": capsule,
            "results": results,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return {
        "run_id": run_id,
        "processed": processed,
        "session_index": session_index,
        "session_capsule": capsule,
        "summary": summary_path,
        "results": results,
    }


def export_raw_rows(run_id: str) -> Dict:
    task_dir = task_dir_for_run(run_id)
    raw_jsonl = os.path.join(task_dir, "raw_rows.jsonl")
    raw_excel = os.path.join(task_dir, "raw_results.xlsx")
    export_jsonl_to_excel(raw_jsonl, raw_excel)
    return {"run_id": run_id, "raw_jsonl": raw_jsonl, "raw_excel": raw_excel}


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
