"""
Codex visual extraction contracts and deterministic row application.

The Codex extract worker is the only component that should read screenshots and
infer product rows. This module keeps the boring parts durable: request files,
launch advice, leases, and applying already-extracted rows to the existing raw
assets. It does not open a browser, inspect DOM, or contact Taobao.
"""
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from modules.page_sampling import page_sampling_config_from_settings, write_task_event, write_tile_summary
from modules.session_capsule import session_dir_for
from modules.utils import ConfigManager, ensure_dir, get_project_root, sanitize_filename
from modules.visual_capture import keyword_evidence_dir, maybe_delete_screenshot
from modules.visual_control import control_interrupt_for_worker, load_worker_runtime, write_worker_runtime
from modules.visual_pipeline import load_visual_manifest, save_visual_manifest, task_dir_for_run
from modules.vision_extract import export_jsonl_to_excel, ingest_rows


READY_CAPTURE_STATUSES = {"captured", "completed", "success"}
REQUEST_SCHEMA = "taobao_codex_extract_request_v1"
RESULT_SCHEMA = "taobao_codex_extract_rows_v1"
DEFAULT_WORKER_STALE_AFTER_MINUTES = 180
DEFAULT_DRAIN_POLL_SECONDS = 20
DEFAULT_DRAIN_IDLE_TIMEOUT_SECONDS = 900


def run_codex_extract_drain(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    start: bool = True,
    poll_seconds: Optional[float] = None,
    idle_timeout_seconds: Optional[float] = None,
    max_cycles: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Keep the extract side alive while capture is producing screenshots.

    The resident drain process is only a scheduler/dispatcher. The actual
    screenshot-reading Codex workers remain short-lived keyword workers because
    their attached image inputs are fixed at launch.
    """
    config = ConfigManager(config_file)
    extract_cfg = _codex_extract_config(config)
    poll_seconds = float(
        poll_seconds
        if poll_seconds is not None
        else extract_cfg.get("drain_poll_seconds", DEFAULT_DRAIN_POLL_SECONDS)
    )
    idle_timeout_seconds = float(
        idle_timeout_seconds
        if idle_timeout_seconds is not None
        else extract_cfg.get("drain_idle_timeout_seconds", DEFAULT_DRAIN_IDLE_TIMEOUT_SECONDS)
    )
    poll_seconds = max(0.1, poll_seconds)
    idle_timeout_seconds = max(1.0, idle_timeout_seconds)
    started_at = time.monotonic()
    last_activity_at = started_at
    cycles = 0
    prepared_total = 0
    dispatched_total = 0
    sync_total = 0
    final_reason = ""
    last_sync: Dict[str, Any] = {}
    last_prepare: Dict[str, Any] = {}
    last_dispatch: Dict[str, Any] = {}

    write_worker_runtime(
        plan_id,
        session_index,
        "codex_extract",
        "draining",
        start=bool(start),
        poll_seconds=poll_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        started_at=_now(),
    )

    while True:
        cycles += 1
        interrupt = control_interrupt_for_worker(plan_id, session_index)
        if interrupt.get("interrupted"):
            final_reason = interrupt.get("reason") or "control_interrupted"
            break

        last_sync = _sync_capture_outputs_for_extract(plan_id, session_index)
        last_prepare = prepare_codex_extract_requests(plan_id, session_index, config_file=config_file)
        last_dispatch = dispatch_codex_extract_requests(
            plan_id,
            session_index,
            config_file=config_file,
            start=start,
        )

        prepared = int(last_prepare.get("prepared") or 0)
        dispatched = int(last_dispatch.get("count") or 0)
        synced = int(last_sync.get("updated") or 0)
        active = _active_launch_count(
            plan_id,
            session_index,
            stale_after_seconds=float(extract_cfg["stale_after_minutes"]) * 60,
        )
        pending = len(_pending_requests(plan_id, session_index))
        prepared_total += prepared
        dispatched_total += dispatched
        sync_total += synced

        if prepared or dispatched or synced or active or pending:
            last_activity_at = time.monotonic()

        capture_state = _capture_source_state(plan_id, session_index)
        if active <= 0 and pending <= 0 and capture_state.get("closed"):
            final_reason = capture_state.get("reason") or "capture_closed_and_extract_queue_empty"
            break

        idle_for = time.monotonic() - last_activity_at
        if active <= 0 and pending <= 0 and idle_for >= idle_timeout_seconds:
            final_reason = "idle_timeout_waiting_for_capture_output"
            break

        if max_cycles is not None and cycles >= int(max_cycles):
            final_reason = "max_cycles_reached"
            break

        write_worker_runtime(
            plan_id,
            session_index,
            "codex_extract",
            "waiting_for_capture_or_workers",
            cycles=cycles,
            prepared_total=prepared_total,
            dispatched_total=dispatched_total,
            sync_total=sync_total,
            active_workers=active,
            pending_requests=pending,
            capture_state=capture_state,
            last_sync=last_sync,
            last_prepare={
                "prepared": last_prepare.get("prepared", 0),
                "skipped_count": len(last_prepare.get("skipped") or []),
            },
            last_dispatch={
                "count": last_dispatch.get("count", 0),
                "active_workers": last_dispatch.get("active_workers", 0),
            },
        )
        time.sleep(poll_seconds)

    elapsed_seconds = round(time.monotonic() - started_at, 3)
    result = {
        "ok": True,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "start": bool(start),
        "status": "completed" if final_reason != "idle_timeout_waiting_for_capture_output" else "needs_review",
        "reason": final_reason,
        "cycles": cycles,
        "prepared_total": prepared_total,
        "dispatched_total": dispatched_total,
        "sync_total": sync_total,
        "elapsed_seconds": elapsed_seconds,
        "last_sync": last_sync,
        "last_prepare": last_prepare,
        "last_dispatch": last_dispatch,
        "capture_state": _capture_source_state(plan_id, session_index),
    }
    write_worker_runtime(
        plan_id,
        session_index,
        "codex_extract",
        result["status"],
        drain_result=result,
        finished_at=_now(),
    )
    return result


def prepare_codex_extract_requests(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    limit: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Create keyword-level Codex extract contracts for captured screenshots."""
    task_dir = task_dir_for_run(plan_id)
    manifest = load_visual_manifest(plan_id)
    config = ConfigManager(config_file)
    sampling = page_sampling_config_from_settings(config)
    confidence_threshold = config.getfloat("VISUAL_CAPTURE", "confidence_threshold", fallback=0.80)
    selected = []
    skipped = []

    for record in manifest.get("records", []):
        if int(record.get("extra", {}).get("daily_session_index") or 0) != int(session_index):
            continue
        if str(record.get("status") or "").strip() != "captured":
            continue
        keyword = str(record.get("keyword") or "").strip()
        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        keyword_result_path = record.get("extra", {}).get("keyword_result") or os.path.join(
            evidence_dir, "keyword_result.json"
        )
        keyword_result = _load_json_if_exists(keyword_result_path)
        capture_status = str(keyword_result.get("status") or "").strip().lower()
        if capture_status not in READY_CAPTURE_STATUSES:
            skipped.append({"keyword": keyword, "reason": "keyword_result_not_ready"})
            continue
        result_keyword = str(keyword_result.get("keyword") or "").strip()
        if result_keyword and result_keyword != keyword:
            skipped.append(
                {
                    "keyword": keyword,
                    "reason": "keyword_result_keyword_mismatch",
                    "keyword_result": keyword_result_path,
                    "result_keyword": result_keyword,
                }
            )
            continue
        screenshot_records = _collect_screenshot_records(keyword_result, record)
        screenshot_records = [item for item in screenshot_records if os.path.exists(str(item.get("path") or ""))]
        if not screenshot_records:
            skipped.append({"keyword": keyword, "reason": "no_existing_screenshots"})
            continue
        screenshots = [str(item["path"]) for item in screenshot_records]

        contract_dir = _contract_dir(plan_id, session_index, keyword)
        request_path = os.path.join(contract_dir, "extract_request.json")
        rows_output_path = os.path.join(contract_dir, "rows_result.json")
        apply_result_path = os.path.join(contract_dir, "apply_result.json")
        worker_result_path = os.path.join(contract_dir, "codex_worker_result.json")
        prompt_path = os.path.join(contract_dir, "extract_prompt.md")
        if os.path.exists(apply_result_path) and not force:
            apply_result = _load_json_if_exists(apply_result_path)
            if apply_result.get("ok"):
                skipped.append({"keyword": keyword, "reason": "already_applied", "request": request_path})
                continue
        request = {
            "schema": REQUEST_SCHEMA,
            "plan_id": plan_id,
            "session_index": int(session_index),
            "keyword": keyword,
            "created_at": _now(),
            "task_dir": task_dir,
            "evidence_dir": evidence_dir,
            "keyword_result": keyword_result_path,
            "screenshots": screenshots,
            "screenshot_records": screenshot_records,
            "rows_output": rows_output_path,
            "apply_result": apply_result_path,
            "worker_result": worker_result_path,
            "prompt": prompt_path,
            "confidence_threshold": confidence_threshold,
            "target_limit": sampling.target_listings_per_keyword,
            "commands": {
                "apply": (
                    f"python3 harness.py visual-apply-extracted-rows "
                    f"--request {json.dumps(request_path, ensure_ascii=False)}"
                )
            },
            "boundaries": {
                "worker_role": "Codex extract worker: infer rows only from attached visible screenshots.",
                "forbidden": [
                    "open or control Chrome",
                    "read DOM/HTML/AX tree/selector maps",
                    "read network/API/cookies/storage/page source",
                    "mutate Taobao account state",
                ],
            },
        }
        ensure_dir(contract_dir)
        _write_json(request_path, request)
        _write_text(prompt_path, _build_extract_prompt(request))
        record.setdefault("extra", {})
        record["extra"]["codex_extract_request"] = request_path
        record["last_action"] = "codex_extract_request_prepared"
        record["updated_at"] = _now()
        selected.append(
            {
                "keyword": keyword,
                "request": request_path,
                "prompt": prompt_path,
                "rows_output": rows_output_path,
                "screenshots": screenshots,
            }
        )
        write_task_event(
            task_dir,
            event="codex_extract_request_prepared",
            run_id=plan_id,
            session_index=session_index,
            keyword=keyword,
            request_path=request_path,
            screenshots_count=len(screenshots),
        )
        if limit is not None and len(selected) >= int(limit):
            break

    save_visual_manifest(plan_id, manifest)
    return {
        "ok": True,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "prepared": len(selected),
        "skipped": skipped,
        "requests": selected,
        "extract_root": _extract_root(plan_id, session_index),
    }


def dispatch_codex_extract_requests(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    limit: Optional[int] = None,
    start: bool = False,
) -> Dict[str, Any]:
    """Return launch commands, and optionally start bounded codex exec workers."""
    config = ConfigManager(config_file)
    extract_cfg = _codex_extract_config(config)
    requests = _pending_requests(plan_id, session_index)
    stale_after_seconds = float(extract_cfg["stale_after_minutes"]) * 60
    active_workers = _active_launch_count(plan_id, session_index, stale_after_seconds=stale_after_seconds)
    dispatch_limit = max(0, int(limit)) if limit is not None else len(requests)
    if start:
        capacity = max(0, int(extract_cfg["max_parallel"]) - active_workers)
        dispatch_limit = min(dispatch_limit, capacity)
    requests = requests[:dispatch_limit]
    launched = []
    for request_path in requests:
        state_path = os.path.join(os.path.dirname(request_path), "launch_state.json")
        state = _load_json_if_exists(state_path)
        if _launch_active(state, stale_after_seconds=stale_after_seconds):
            launched.append({"request": request_path, "status": "already_running", "state": state})
            continue
        if state.get("status") == "running":
            _mark_launch_stale(state_path, state, reason=_launch_stale_reason(state, stale_after_seconds))
        command = _launch_command(request_path, extract_cfg)
        item = {"request": request_path, "command": command, "status": "advised"}
        if start:
            item.update(_start_codex_worker(request_path, command))
        launched.append(item)
    summary = {
        "ok": True,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "start": bool(start),
        "count": len(launched),
        "active_workers": active_workers,
        "max_parallel": int(extract_cfg["max_parallel"]),
        "workers": launched,
    }
    write_worker_runtime(
        plan_id,
        session_index,
        "codex_extract",
        "started" if start and launched else "dispatch_advised",
        start=bool(start),
        active_workers=active_workers,
        max_parallel=int(extract_cfg["max_parallel"]),
        dispatched=len(launched),
    )
    return summary


def _sync_capture_outputs_for_extract(plan_id: str, session_index: int) -> Dict[str, Any]:
    from modules.visual_pipeline import sync_midscene_worker_results

    if not _has_syncable_capture_output(plan_id, session_index):
        return {"ok": True, "updated": 0, "missing": 0, "reason": "no_capture_output_yet"}
    return sync_midscene_worker_results(plan_id, session_index)


def _has_syncable_capture_output(plan_id: str, session_index: int) -> bool:
    session_dir = session_dir_for(plan_id, session_index)
    if os.path.exists(os.path.join(session_dir, "session_worker_result.json")):
        return True
    try:
        task_dir = task_dir_for_run(plan_id)
        manifest = load_visual_manifest(plan_id)
    except Exception:
        return False
    for record in manifest.get("records", []):
        if int(record.get("extra", {}).get("daily_session_index") or 0) != int(session_index):
            continue
        keyword = record.get("keyword", "")
        evidence_dir = record.get("evidence_dir") or keyword_evidence_dir(task_dir, keyword)
        if os.path.exists(os.path.join(evidence_dir, "keyword_result.json")):
            return True
    return False


def _capture_source_state(plan_id: str, session_index: int) -> Dict[str, Any]:
    session_dir = session_dir_for(plan_id, session_index)
    session_result_path = os.path.join(session_dir, "session_worker_result.json")
    session_result = _load_json_if_exists(session_result_path)
    if session_result:
        status = str(session_result.get("status") or "").strip()
        return {
            "closed": True,
            "reason": f"session_result:{status or 'written'}",
            "status": status,
            "session_result": session_result_path,
        }

    runtime = load_worker_runtime(plan_id, session_index, "capture")
    runtime_status = str(runtime.get("status") or "").strip()
    if runtime_status and runtime_status not in {"prepared", "running", "draining"}:
        return {
            "closed": True,
            "reason": f"capture_runtime:{runtime_status}",
            "status": runtime_status,
            "runtime": runtime,
        }
    return {
        "closed": False,
        "reason": "capture_still_open",
        "status": runtime_status or "unknown",
        "runtime": runtime,
    }


def apply_codex_extracted_rows(
    request_path: str,
    rows_file: Optional[str] = None,
    config_file: str = "config/settings.ini",
    retain_screenshots: bool = False,
) -> Dict[str, Any]:
    """Apply rows produced by a Codex worker to raw_rows/raw_results and manifest."""
    request = _load_json(request_path)
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"未知 Codex extract request schema: {request.get('schema')}")
    existing_apply_result = _load_successful_apply_result(str(request.get("apply_result") or ""))
    if existing_apply_result:
        return existing_apply_result
    rows_file = rows_file or request.get("rows_output")
    config = ConfigManager(config_file)
    confidence_threshold = float(
        request.get("confidence_threshold")
        or config.getfloat("VISUAL_CAPTURE", "confidence_threshold", fallback=0.80)
    )
    fuzzy_dedupe_enabled = config.getboolean("VISUAL_DEDUPE", "fuzzy_enabled", fallback=True)
    fuzzy_store_similarity_threshold = config.getfloat(
        "VISUAL_DEDUPE",
        "store_similarity_threshold",
        fallback=0.70,
    )
    fuzzy_title_similarity_threshold = config.getfloat(
        "VISUAL_DEDUPE",
        "title_similarity_threshold",
        fallback=0.95,
    )
    fuzzy_examples_limit = config.getint("VISUAL_DEDUPE", "fuzzy_examples_limit", fallback=20)
    target_limit = int(request.get("target_limit") or 0)
    plan_id = str(request["plan_id"])
    session_index = int(request["session_index"])
    keyword = str(request["keyword"])
    task_dir = str(request["task_dir"])
    screenshots = [os.path.abspath(path) for path in request.get("screenshots", []) if path]
    validation = _validate_apply_request(request, request_path, rows_file, screenshots)
    if not validation["ok"]:
        result = _apply_needs_review_result(
            request=request,
            request_path=request_path,
            rows_file=rows_file,
            screenshots=screenshots,
            error=validation["error"],
            warnings=validation.get("warnings", []),
        )
        _write_json(str(request.get("apply_result")), result)
        _write_json(str(request.get("worker_result")), result)
        _update_manifest_after_apply(plan_id, keyword, request_path, result)
        _write_observability(task_dir, plan_id, session_index, keyword, result)
        return result
    rows_payload = validation["rows_payload"]
    rows = validation["rows"]
    screenshot_capture_times, capture_warnings = _screenshot_capture_times(request, screenshots)
    rows_pending_path = os.path.join(str(request.get("evidence_dir") or ""), "rows_pending.json")
    _write_json(
        rows_pending_path,
        {
            "schema": RESULT_SCHEMA,
            "plan_id": plan_id,
            "session_index": session_index,
            "keyword": keyword,
            "created_at": _now(),
            "source": "codex_extract_worker",
            "request": request_path,
            "screenshots": screenshots,
            "screenshot_capture_times": screenshot_capture_times,
            "rows": rows,
        },
    )
    ingest = ingest_rows(
        task_dir=task_dir,
        keyword=keyword,
        rows=rows,
        screenshot_path=screenshots[0] if screenshots else "",
        screenshot_capture_times=screenshot_capture_times,
        confidence_threshold=confidence_threshold,
        retain_screenshot=True,
        target_limit=target_limit,
        dedupe=True,
        fuzzy_dedupe_enabled=fuzzy_dedupe_enabled,
        fuzzy_store_similarity_threshold=fuzzy_store_similarity_threshold,
        fuzzy_title_similarity_threshold=fuzzy_title_similarity_threshold,
        fuzzy_examples_limit=fuzzy_examples_limit,
    )
    ingest_payload = ingest.to_dict()
    should_retain_for_review = any(
        str(item).startswith("low_confidence_rows") for item in ingest_payload.get("warnings", [])
    )
    deleted = _delete_screenshots(screenshots) if ingest.ok and not retain_screenshots and not should_retain_for_review else []
    retained = [path for path in screenshots if path not in deleted]
    result = {
        "schema": "taobao_codex_extract_apply_result_v1",
        "ok": bool(ingest.ok),
        "status": "extracted" if ingest.ok else "needs_review",
        "plan_id": plan_id,
        "session_index": session_index,
        "keyword": keyword,
        "request": request_path,
        "rows_file": os.path.abspath(rows_file) if rows_file else "",
        "rows_pending": rows_pending_path,
        "ingest_result": ingest_payload,
        "rows_result_schema": rows_payload.get("schema", ""),
        "rows_received": ingest.rows_received,
        "rows_written": ingest.rows_written,
        "screenshots": screenshots,
        "screenshots_deleted": deleted,
        "screenshots_retained": retained,
        "screenshot_capture_times": screenshot_capture_times,
        "warnings": validation.get("warnings", []) + (ingest_payload.get("warnings") or []) + capture_warnings,
        "updated_at": _now(),
        "error": ingest.error,
    }
    _write_json(str(request.get("apply_result")), result)
    _write_json(str(request.get("worker_result")), result)
    _update_manifest_after_apply(plan_id, keyword, request_path, result)
    _write_observability(task_dir, plan_id, session_index, keyword, result)
    export_jsonl_to_excel(os.path.join(task_dir, "raw_rows.jsonl"), os.path.join(task_dir, "raw_results.xlsx"))
    return result


def _pending_requests(plan_id: str, session_index: int) -> List[str]:
    root = _extract_root(plan_id, session_index)
    if not os.path.exists(root):
        return []
    manifest = load_visual_manifest(plan_id)
    expected_by_keyword = {}
    for record in manifest.get("records", []):
        if int(record.get("extra", {}).get("daily_session_index") or 0) != int(session_index):
            continue
        keyword = str(record.get("keyword") or "").strip()
        expected = str(record.get("extra", {}).get("codex_extract_request") or "").strip()
        if keyword:
            expected_by_keyword[keyword] = os.path.abspath(expected) if expected else ""
    requests = []
    for dirpath, _, filenames in os.walk(root):
        if "extract_request.json" not in filenames:
            continue
        request_path = os.path.join(dirpath, "extract_request.json")
        request = _load_json_if_exists(request_path)
        if request.get("schema") != REQUEST_SCHEMA:
            continue
        if str(request.get("plan_id") or "") != str(plan_id) or int(request.get("session_index") or 0) != int(session_index):
            continue
        keyword = str(request.get("keyword") or "").strip()
        expected = expected_by_keyword.get(keyword)
        if expected is None:
            continue
        if expected and expected != os.path.abspath(request_path):
            continue
        apply_path = os.path.join(dirpath, "apply_result.json")
        apply_result = _load_json_if_exists(apply_path)
        if apply_result.get("ok"):
            continue
        requests.append(request_path)
    return sorted(requests)


def _start_codex_worker(request_path: str, command: List[str]) -> Dict[str, Any]:
    contract_dir = os.path.dirname(request_path)
    stdout_path = os.path.join(contract_dir, "codex_worker.stdout.jsonl")
    stderr_path = os.path.join(contract_dir, "codex_worker.stderr.log")
    state_path = os.path.join(contract_dir, "launch_state.json")
    request = _load_json(request_path)
    prompt = _read_text(str(request.get("prompt") or ""))
    with open(stdout_path, "wb") as stdout, open(stderr_path, "wb") as stderr:
        proc = subprocess.Popen(
            command,
            cwd=get_project_root(),
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        if proc.stdin:
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.close()
    state = {
        "status": "running",
        "pid": proc.pid,
        "request": request_path,
        "command": command,
        "stdout": stdout_path,
        "stderr": stderr_path,
        "launched_at": _now(),
        "started_at": _now(),
        "updated_at": _now(),
    }
    _write_json(state_path, state)
    return {"status": "started", "pid": proc.pid, "state": state_path, "stdout": stdout_path, "stderr": stderr_path}


def _launch_command(request_path: str, extract_cfg: Dict[str, Any]) -> List[str]:
    request = _load_json(request_path)
    prompt_path = str(request.get("prompt") or "")
    screenshots = [path for path in request.get("screenshots", []) if os.path.exists(str(path))]
    command = [extract_cfg["codex_bin"], "exec", "-C", get_project_root()]
    if extract_cfg.get("profile"):
        command.extend(["-p", extract_cfg["profile"]])
    if extract_cfg.get("model"):
        command.extend(["-m", extract_cfg["model"]])
    if extract_cfg.get("sandbox"):
        command.extend(["-s", extract_cfg["sandbox"]])
        command.extend(["-c", f"sandbox_mode={json.dumps(extract_cfg['sandbox'])}"])
    if extract_cfg.get("approval_policy"):
        command.extend(["-c", f"approval_policy={json.dumps(extract_cfg['approval_policy'])}"])
    if extract_cfg.get("ignore_rules"):
        command.append("--ignore-rules")
    if extract_cfg.get("json"):
        command.append("--json")
    if extract_cfg.get("ephemeral"):
        command.append("--ephemeral")
    for image in screenshots:
        command.extend(["-i", image])
    return command


def _codex_extract_config(config: ConfigManager) -> Dict[str, Any]:
    section = "CODEX_EXTRACT"
    return {
        "codex_bin": config.get(section, "codex_bin", fallback=_default_codex_bin()).strip() or _default_codex_bin(),
        "profile": config.get(section, "profile", fallback="taobao_visual_extract").strip(),
        "model": config.get(section, "model", fallback="gpt-5.5").strip(),
        "sandbox": config.get(section, "sandbox", fallback="danger-full-access").strip(),
        "approval_policy": config.get(section, "approval_policy", fallback="never").strip(),
        "ignore_rules": config.getboolean(section, "ignore_rules", fallback=True),
        "json": config.getboolean(section, "json_events", fallback=True),
        "ephemeral": config.getboolean(section, "ephemeral", fallback=True),
        "max_parallel": max(1, config.getint(section, "max_parallel", fallback=1)),
        "stale_after_minutes": max(
            1,
            config.getint(
                section,
                "worker_stale_after_minutes",
                fallback=DEFAULT_WORKER_STALE_AFTER_MINUTES,
            ),
        ),
        "drain_poll_seconds": max(
            1,
            config.getint(section, "drain_poll_seconds", fallback=DEFAULT_DRAIN_POLL_SECONDS),
        ),
        "drain_idle_timeout_seconds": max(
            1,
            config.getint(
                section,
                "drain_idle_timeout_seconds",
                fallback=DEFAULT_DRAIN_IDLE_TIMEOUT_SECONDS,
            ),
        ),
    }


def _default_codex_bin() -> str:
    bundled = "/Applications/Codex.app/Contents/Resources/codex"
    return bundled if os.path.exists(bundled) else "codex"


def _build_extract_prompt(request: Dict[str, Any]) -> str:
    rows_output = request["rows_output"]
    apply_command = request["commands"]["apply"]
    screenshots = "\n".join(f"- {path}" for path in request.get("screenshots", []))
    return f"""# Screenshot Rows Worker

You are a short-lived OCR-style worker for visible screenshot price evidence.

This prompt is self-contained. Do not use skills, plugins, AGENTS.md, project docs, tests, source modules, or the request JSON to decide what to extract. The request JSON path is only for the deterministic apply command after you have written rows.

Request JSON for apply only: {request_path_label(request)}
Plan/session: {request["plan_id"]} / {request["session_index"]}
Keyword: {request["keyword"]}
Rows output: {rows_output}

Screenshots attached to this run are the only source of product data:
{screenshots}

Rules:
- Extract product rows only from visible screenshot pixels.
- Do not open or control Chrome.
- Do not inspect repository files, project rules, tests, source code, docs, or skills.
- Do not read DOM, HTML, AX tree, selector maps, cookies, storage, network payloads, page source, or JavaScript-evaluated page data.
- Do not perform business filtering; just transcribe visible product rows.
- Use one row per visible product card with a visible title and price.
- If a field is not visible, leave it empty.
- Price must be numeric text only; for a visible price range, use the lowest visible price.
- Use confidence from 0 to 1. Be conservative when small text is uncertain.

Write this exact JSON shape to `{rows_output}`:

```json
{{
  "schema": "{RESULT_SCHEMA}",
  "keyword": "{request["keyword"]}",
  "rows": [
    {{
      "搜索关键词": "{request["keyword"]}",
      "采集时间": "",
      "商品名称": "",
      "现价": "",
      "店铺名称": "",
      "付款人数": "",
      "地区": "",
      "截图文件": "",
      "截图坐标": "",
      "识别置信度": 0.0,
      "识别备注": ""
    }}
  ]
}}
```

After writing the rows file, run this deterministic apply command:

```bash
{apply_command}
```

Then finish. Keep your final message short and include the apply result path.
"""


def request_path_label(request: Dict[str, Any]) -> str:
    return os.path.join(os.path.dirname(str(request["rows_output"])), "extract_request.json")


def _update_manifest_after_apply(plan_id: str, keyword: str, request_path: str, result: Dict[str, Any]) -> None:
    manifest = load_visual_manifest(plan_id)
    now = _now()
    for record in manifest.get("records", []):
        if str(record.get("keyword") or "") != keyword:
            continue
        expected_request = str(record.get("extra", {}).get("codex_extract_request") or "")
        if expected_request and os.path.abspath(expected_request) != os.path.abspath(request_path):
            continue
        record["status"] = "extracted" if result.get("ok") else "needs_review"
        record["failure_reason"] = None if result.get("ok") else result.get("error") or "codex_extract_needs_review"
        record["last_action"] = "codex_extract_rows_applied"
        record["updated_at"] = now
        if result.get("ok"):
            record["finished_at"] = now
        record.setdefault("extra", {})
        record["extra"]["codex_extract_request"] = request_path
        record["extra"]["codex_extract_apply_result"] = result.get("apply_result") or os.path.join(
            os.path.dirname(request_path), "apply_result.json"
        )
        record["extra"]["ingest_result"] = result.get("ingest_result", {})
        record["extra"]["codex_extract_warnings"] = result.get("warnings", [])
        break
    manifest.setdefault("session", {})
    manifest["session"]["updated_at"] = now
    save_visual_manifest(plan_id, manifest)


def _write_observability(
    task_dir: str,
    plan_id: str,
    session_index: int,
    keyword: str,
    result: Dict[str, Any],
) -> None:
    write_task_event(
        task_dir,
        event="codex_extract_rows_applied",
        level="info" if result.get("ok") else "warning",
        run_id=plan_id,
        session_index=session_index,
        keyword=keyword,
        status=result.get("status"),
        rows_received=result.get("rows_received", 0),
        rows_written=result.get("rows_written", 0),
        screenshots_deleted=len(result.get("screenshots_deleted") or []),
        error=result.get("error"),
    )
    retained = set(result.get("screenshots_retained") or [])
    for index, path in enumerate(result.get("screenshots") or []):
        write_tile_summary(
            task_dir,
            run_id=plan_id,
            keyword=keyword,
            tile_id=os.path.splitext(os.path.basename(path))[0] or f"tile_{index:02d}",
            rough_state=result.get("status", ""),
            image_path=path,
            image_retained=path in retained and os.path.exists(path),
            rows_extracted=int(result.get("rows_received") or 0),
            new_rows_after_dedupe=int(result.get("rows_written") or 0),
            stop_reason="codex_extract_applied" if result.get("ok") else "codex_extract_needs_review",
            notes="codex_extract_worker",
        )


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


def _collect_screenshot_records(keyword_result: Dict[str, Any], record: Dict[str, Any]) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for value in keyword_result.get("screenshots", []) or []:
        path = _screenshot_path(value)
        if path:
            records.append(
                {
                    "path": os.path.abspath(path),
                    "captured_at": _screenshot_captured_at(value),
                    "tile_id": str(value.get("tile_id") or "") if isinstance(value, dict) else "",
                }
            )
    abnormal = keyword_result.get("abnormal_screenshot")
    if abnormal:
        records.append({"path": os.path.abspath(str(abnormal)), "captured_at": "", "tile_id": "abnormal"})
    if not records:
        for value in record.get("extra", {}).get("screenshots", []) or []:
            path = _screenshot_path(value)
            if path:
                records.append(
                    {
                        "path": os.path.abspath(path),
                        "captured_at": _screenshot_captured_at(value),
                        "tile_id": str(value.get("tile_id") or "") if isinstance(value, dict) else "",
                    }
                )
    deduped = []
    seen = set()
    for item in records:
        path = item["path"]
        if path in seen:
            continue
        seen.add(path)
        deduped.append(item)
    return deduped


def _screenshot_path(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("path") or value.get("image_path") or "").strip()
    return str(value or "").strip()


def _screenshot_captured_at(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("captured_at") or value.get("created_at") or "").strip()
    return ""


def _screenshot_capture_times(request: Dict[str, Any], screenshots: List[str]) -> (Dict[str, str], List[str]):
    records = request.get("screenshot_records") or []
    capture_times: Dict[str, str] = {}
    warnings: List[str] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        captured_at = str(item.get("captured_at") or "").strip()
        if not path or not captured_at:
            continue
        abs_path = os.path.abspath(path)
        capture_times[abs_path] = captured_at
        capture_times[path] = captured_at
        capture_times[os.path.basename(path)] = captured_at
    if not capture_times:
        keyword_result = _load_json_if_exists(str(request.get("keyword_result") or ""))
        for item in keyword_result.get("screenshots", []) or []:
            path = _screenshot_path(item)
            captured_at = _screenshot_captured_at(item)
            if path and captured_at:
                abs_path = os.path.abspath(path)
                capture_times[abs_path] = captured_at
                capture_times[path] = captured_at
                capture_times[os.path.basename(path)] = captured_at
    if not capture_times:
        fallback = _now()
        warnings.append("missing_screenshot_captured_at_fallback_now")
        for path in screenshots:
            capture_times[path] = fallback
            capture_times[os.path.basename(path)] = fallback
    return capture_times, warnings


def _validate_apply_request(
    request: Dict[str, Any],
    request_path: str,
    rows_file: Optional[str],
    screenshots: List[str],
) -> Dict[str, Any]:
    warnings: List[str] = []
    if not rows_file or not os.path.exists(str(rows_file)):
        return {"ok": False, "error": "rows_result_missing", "warnings": warnings}
    missing_screenshots = [path for path in screenshots if not os.path.exists(path)]
    if missing_screenshots:
        return {
            "ok": False,
            "error": "request_screenshot_missing",
            "warnings": [f"missing_screenshot:{path}" for path in missing_screenshots],
        }
    try:
        rows_payload = _load_json(str(rows_file))
    except Exception as exc:
        return {"ok": False, "error": f"rows_result_malformed:{exc}", "warnings": warnings}
    if not isinstance(rows_payload, dict):
        return {"ok": False, "error": "rows_result_not_object", "warnings": warnings}
    schema = rows_payload.get("schema")
    if schema and schema != RESULT_SCHEMA:
        return {"ok": False, "error": f"rows_result_schema_mismatch:{schema}", "warnings": warnings}
    expected_keyword = str(request.get("keyword") or "").strip()
    result_keyword = str(rows_payload.get("keyword") or "").strip()
    if result_keyword and result_keyword != expected_keyword:
        return {"ok": False, "error": "rows_result_keyword_mismatch", "warnings": warnings}
    rows = rows_payload.get("rows")
    if not isinstance(rows, list):
        return {"ok": False, "error": "rows_result_rows_not_list", "warnings": warnings}
    for row in rows:
        if not isinstance(row, dict):
            return {"ok": False, "error": "rows_result_row_not_object", "warnings": warnings}
        row_keyword = str(row.get("搜索关键词") or "").strip()
        if row_keyword and row_keyword != expected_keyword:
            return {"ok": False, "error": "rows_result_row_keyword_mismatch", "warnings": warnings}
        row_screenshot = str(row.get("截图文件") or "").strip()
        if row_screenshot and not _row_screenshot_matches_request(row_screenshot, screenshots):
            warnings.append(f"row_screenshot_not_in_request:{row_screenshot}")
    return {"ok": True, "rows_payload": rows_payload, "rows": [dict(row) for row in rows], "warnings": warnings}


def _row_screenshot_matches_request(row_screenshot: str, screenshots: List[str]) -> bool:
    requested = set()
    for path in screenshots:
        requested.add(path)
        requested.add(os.path.abspath(path))
        requested.add(os.path.basename(path))
    return row_screenshot in requested or os.path.abspath(row_screenshot) in requested or os.path.basename(row_screenshot) in requested


def _apply_needs_review_result(
    request: Dict[str, Any],
    request_path: str,
    rows_file: Optional[str],
    screenshots: List[str],
    error: str,
    warnings: List[str],
) -> Dict[str, Any]:
    return {
        "schema": "taobao_codex_extract_apply_result_v1",
        "ok": False,
        "status": "needs_review",
        "plan_id": str(request.get("plan_id") or ""),
        "session_index": int(request.get("session_index") or 0),
        "keyword": str(request.get("keyword") or ""),
        "request": request_path,
        "rows_file": os.path.abspath(str(rows_file)) if rows_file else "",
        "rows_pending": "",
        "ingest_result": {},
        "rows_received": 0,
        "rows_written": 0,
        "screenshots": screenshots,
        "screenshots_deleted": [],
        "screenshots_retained": screenshots,
        "warnings": warnings,
        "updated_at": _now(),
        "error": error,
    }


def _contract_dir(plan_id: str, session_index: int, keyword: str) -> str:
    return os.path.join(_extract_root(plan_id, session_index), sanitize_filename(keyword)[:80] or "keyword")


def _extract_root(plan_id: str, session_index: int) -> str:
    return os.path.join(session_dir_for(plan_id, session_index), "codex_extract")


def _delete_screenshots(screenshots: Iterable[str]) -> List[str]:
    deleted = []
    for path in _dedupe_keep_order([os.path.abspath(str(item)) for item in screenshots if item]):
        if maybe_delete_screenshot(path):
            deleted.append(path)
    return deleted


def _load_successful_apply_result(path: str) -> Dict[str, Any]:
    result = _load_json_if_exists(path)
    if not result.get("ok"):
        return {}
    status = str(result.get("status") or "").strip()
    if status and status not in {"applied", "extracted", "success"}:
        return {}
    return result


def _launch_active(state: Dict[str, Any], stale_after_seconds: Optional[float] = None) -> bool:
    pid = state.get("pid")
    if not pid or str(state.get("status") or "") != "running":
        return False
    if _launch_stale_reason(state, stale_after_seconds):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _active_launch_count(
    plan_id: str,
    session_index: int,
    stale_after_seconds: Optional[float] = None,
) -> int:
    root = _extract_root(plan_id, session_index)
    if not os.path.exists(root):
        return 0
    count = 0
    for dirpath, _, filenames in os.walk(root):
        if "launch_state.json" not in filenames:
            continue
        state_path = os.path.join(dirpath, "launch_state.json")
        state = _load_json_if_exists(state_path)
        if _launch_active(state, stale_after_seconds=stale_after_seconds):
            count += 1
        elif state.get("status") == "running":
            _mark_launch_stale(state_path, state, reason=_launch_stale_reason(state, stale_after_seconds))
    return count


def _launch_stale_reason(state: Dict[str, Any], stale_after_seconds: Optional[float]) -> str:
    if not stale_after_seconds or stale_after_seconds <= 0:
        return ""
    launched_at = str(state.get("launched_at") or state.get("started_at") or "").strip()
    if not launched_at:
        return "missing_launched_at"
    try:
        launched = datetime.fromisoformat(launched_at)
    except ValueError:
        return "invalid_launched_at"
    if datetime.now() - launched > timedelta(seconds=float(stale_after_seconds)):
        return "ttl_exceeded"
    return ""


def _mark_launch_stale(state_path: str, state: Dict[str, Any], reason: str = "") -> None:
    state["status"] = "stale"
    state["stale_reason"] = reason or "pid_not_active"
    state["stale_detected_at"] = _now()
    state["updated_at"] = _now()
    _write_json(state_path, state)


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json_if_exists(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _write_text(path: str, content: str) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
