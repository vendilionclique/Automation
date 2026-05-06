"""
Visual collection orchestration.
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

from modules.page_state import (
    CAPTCHA_REQUIRED,
    LOGIN_REQUIRED,
    POPUP_BLOCKED,
    VISIBLE_READY,
    WHITE_SKELETON,
    detect_page_state,
)
from modules.session_state import initial_session_state, session_policy_from_settings
from modules.utils import ConfigManager, ensure_dir, get_project_root
from modules.visual_capture import (
    CaptureRecord,
    keyword_evidence_dir,
    screenshot_path_for,
    write_capture_manifest,
    write_json,
)
from modules.visual_driver import VisualDriver, chrome_config_from_settings
from modules.vision_extract import export_jsonl_to_excel


ABNORMAL_STATES = {LOGIN_REQUIRED, CAPTCHA_REQUIRED, POPUP_BLOCKED, WHITE_SKELETON}


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
        "workflow": "visual_login_state_capture",
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
    chrome_config = chrome_config_from_settings(config)
    policy = session_policy_from_settings(config)
    manifest = load_visual_manifest(run_id)
    manifest.setdefault("session", initial_session_state(policy))
    task_dir = task_dir_for_run(run_id)

    driver = VisualDriver(chrome_config)
    if launch:
        driver.launch_chrome()

    processed = 0
    results = []
    max_abnormal = policy.max_consecutive_abnormal
    for record in manifest.get("records", []):
        if limit is not None and processed >= limit:
            break
        if record.get("status") not in ("pending", "cooldown", "failed"):
            continue

        keyword = record["keyword"]
        record["status"] = "opening_search"
        record["started_at"] = record.get("started_at") or datetime.now().isoformat(timespec="seconds")
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record["last_action"] = "visual_search_started"
        save_visual_manifest(run_id, manifest)

        driver.search_keyword(keyword)
        record["status"] = "page_loading"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_visual_manifest(run_id, manifest)
        time.sleep(max(0.0, config.getfloat("VISUAL_CAPTURE", "post_search_wait", fallback=2.0)))

        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        screenshot_path = screenshot_path_for(evidence_dir, keyword)
        driver.capture_screen(screenshot_path)
        page_state = detect_page_state(screenshot_path, manual_state=manual_state)

        capture = CaptureRecord(
            run_id=run_id,
            keyword=keyword,
            evidence_dir=evidence_dir,
            screenshot_path=screenshot_path,
            status=page_state.status,
            page_state=page_state.to_dict(),
            retained=True,
        )
        write_capture_manifest(capture)

        record["status"] = "captured" if page_state.status == VISIBLE_READY else "needs_review"
        record["failure_reason"] = None if page_state.status == VISIBLE_READY else page_state.status
        record["evidence_dir"] = evidence_dir
        record["last_action"] = "screenshot_captured"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record.setdefault("extra", {})
        record["extra"]["last_screenshot"] = screenshot_path
        record["extra"]["page_state"] = page_state.to_dict()

        session = manifest.setdefault("session", initial_session_state(policy))
        if page_state.status in ABNORMAL_STATES:
            session["consecutive_abnormal"] = int(session.get("consecutive_abnormal", 0)) + 1
            if session["consecutive_abnormal"] >= max_abnormal:
                session["status"] = "cooling_down"
                record["status"] = "cooldown"
                record["last_action"] = "cooldown_after_consecutive_abnormal"
        else:
            session["consecutive_abnormal"] = 0
            session["status"] = "healthy"

        session["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_visual_manifest(run_id, manifest)
        results.append({"keyword": keyword, "screenshot": screenshot_path, "page_state": page_state.to_dict()})
        processed += 1

        if manifest["session"].get("status") == "cooling_down":
            break

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
        break
    return save_visual_manifest(run_id, manifest)
