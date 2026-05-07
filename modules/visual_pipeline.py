"""
Visual collection orchestration.
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional

from modules.browser_use_driver import browser_use_config_from_settings, write_browser_use_request
from modules.session_state import initial_session_state, session_policy_from_settings
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
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = task_dir_for_run(run_id)
    evidence_dir = keyword_evidence_dir(task_dir, keyword)
    ensure_dir(task_dir)
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {"keyword": keyword, "config": os.path.abspath(config_file)},
        "workflow": "browser_use_login_state_capture",
        "legacy_collection_disabled": True,
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
                "profile_id": None,
                "proxy": None,
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
    launch: bool = True,
) -> Dict:
    config = ConfigManager(config_file)
    browser_use_config = browser_use_config_from_settings(config)
    policy = session_policy_from_settings(config)
    manifest = load_visual_manifest(run_id)
    manifest.setdefault("session", initial_session_state(policy))
    task_dir = task_dir_for_run(run_id)

    processed = 0
    results = []
    for record in manifest.get("records", []):
        if limit is not None and processed >= limit:
            break
        if record.get("status") not in ("pending", "cooldown", "failed", "needs_codex_browser_use"):
            continue

        keyword = record["keyword"]
        record["status"] = "needs_codex_browser_use"
        record["started_at"] = record.get("started_at") or datetime.now().isoformat(timespec="seconds")
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record["last_action"] = "browser_use_mcp_request_prepared"
        save_visual_manifest(run_id, manifest)

        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        request = write_browser_use_request(
            run_id=run_id,
            keyword=keyword,
            evidence_dir=evidence_dir,
            config=browser_use_config,
            manual_state=manual_state,
        )
        record["status"] = request.status
        record["failure_reason"] = None
        record["evidence_dir"] = evidence_dir
        record["last_action"] = "browser_use_mcp_request_prepared"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record.setdefault("extra", {})
        record["extra"]["browser_use_request"] = request.request_path
        record["extra"]["browser_use_instructions"] = request.instruction_path
        record["extra"]["target_url"] = request.url
        record["extra"]["expected_screenshot"] = request.screenshot_path

        session = manifest.setdefault("session", initial_session_state(policy))
        session["status"] = "awaiting_codex_browser_use"
        session["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_visual_manifest(run_id, manifest)
        results.append(
            {
                "keyword": keyword,
                "status": request.status,
                "request": request.request_path,
                "instructions": request.instruction_path,
                "target_url": request.url,
            }
        )
        processed += 1

    summary_path = write_json(
        os.path.join(task_dir, "visual_run_summary.json"),
        {
            "run_id": run_id,
            "processed": processed,
            "results": results,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return {"run_id": run_id, "processed": processed, "summary": summary_path, "results": results}


def export_raw_rows(run_id: str) -> Dict:
    task_dir = task_dir_for_run(run_id)
    raw_jsonl = os.path.join(task_dir, "raw_rows.jsonl")
    raw_excel = os.path.join(task_dir, "raw_results.xlsx")
    export_jsonl_to_excel(raw_jsonl, raw_excel)
    return {"run_id": run_id, "raw_jsonl": raw_jsonl, "raw_excel": raw_excel}


def update_manifest_after_ingest(run_id: str, keyword: str, ingest_result: Dict) -> str:
    manifest = load_visual_manifest(run_id)
    now = datetime.now().isoformat(timespec="seconds")
    for record in manifest.get("records", []):
        if record.get("keyword") != keyword:
            continue
        record["status"] = "extracted" if ingest_result.get("ok") else "needs_review"
        record["failure_reason"] = None if ingest_result.get("ok") else ingest_result.get("error")
        record["last_action"] = "visual_rows_ingested"
        record["updated_at"] = now
        record.setdefault("extra", {})
        record["extra"]["ingest_result"] = ingest_result
        if ingest_result.get("ok"):
            record["finished_at"] = now
        screenshot_path = ingest_result.get("screenshot_path") or record.get("extra", {}).get("expected_screenshot", "")
        if screenshot_path:
            capture = CaptureRecord(
                run_id=run_id,
                keyword=keyword,
                evidence_dir=record.get("evidence_dir") or keyword_evidence_dir(task_dir_for_run(run_id), keyword),
                screenshot_path=screenshot_path,
                status=record["status"],
                page_state={
                    "status": record["status"],
                    "reason": "codex_browser_use_mcp_ingested_rows",
                    "rows_written": ingest_result.get("rows_written", 0),
                },
                retained=True,
                notes="codex_browser_use_mcp",
            )
            write_capture_manifest(capture)
        break
    return save_visual_manifest(run_id, manifest)
