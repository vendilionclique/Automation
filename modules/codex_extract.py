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
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from modules.page_sampling import page_sampling_config_from_settings, write_task_event, write_tile_summary
from modules.session_capsule import session_dir_for
from modules.utils import ConfigManager, ensure_dir, get_project_root, sanitize_filename
from modules.visual_capture import keyword_evidence_dir, maybe_delete_screenshot
from modules.visual_control import write_worker_runtime
from modules.visual_pipeline import load_visual_manifest, save_visual_manifest, task_dir_for_run
from modules.vision_extract import export_jsonl_to_excel, ingest_rows, load_rows


READY_CAPTURE_STATUSES = {"captured", "completed", "success"}
REQUEST_SCHEMA = "taobao_codex_extract_request_v1"
RESULT_SCHEMA = "taobao_codex_extract_rows_v1"


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
        screenshots = _collect_screenshots(keyword_result, record)
        screenshots = [path for path in screenshots if os.path.exists(path)]
        if not screenshots:
            skipped.append({"keyword": keyword, "reason": "no_existing_screenshots"})
            continue

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
    active_workers = _active_launch_count(plan_id, session_index)
    dispatch_limit = max(0, int(limit)) if limit is not None else len(requests)
    if start:
        capacity = max(0, int(extract_cfg["max_parallel"]) - active_workers)
        dispatch_limit = min(dispatch_limit, capacity)
    requests = requests[:dispatch_limit]
    launched = []
    for request_path in requests:
        state_path = os.path.join(os.path.dirname(request_path), "launch_state.json")
        state = _load_json_if_exists(state_path)
        if _launch_active(state):
            launched.append({"request": request_path, "status": "already_running", "state": state})
            continue
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
    rows_file = rows_file or request.get("rows_output")
    rows = load_rows(rows_file=rows_file)
    config = ConfigManager(config_file)
    confidence_threshold = float(
        request.get("confidence_threshold")
        or config.getfloat("VISUAL_CAPTURE", "confidence_threshold", fallback=0.80)
    )
    target_limit = int(request.get("target_limit") or 0)
    plan_id = str(request["plan_id"])
    session_index = int(request["session_index"])
    keyword = str(request["keyword"])
    task_dir = str(request["task_dir"])
    screenshots = [os.path.abspath(path) for path in request.get("screenshots", []) if path]
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
            "rows": rows,
        },
    )
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
    deleted = _delete_screenshots(screenshots) if ingest.ok and not retain_screenshots else []
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
        "rows_received": ingest.rows_received,
        "rows_written": ingest.rows_written,
        "screenshots": screenshots,
        "screenshots_deleted": deleted,
        "screenshots_retained": retained,
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
    requests = []
    for dirpath, _, filenames in os.walk(root):
        if "extract_request.json" not in filenames:
            continue
        request_path = os.path.join(dirpath, "extract_request.json")
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
    with open(stdout_path, "ab") as stdout, open(stderr_path, "ab") as stderr:
        proc = subprocess.Popen(
            command,
            cwd=get_project_root(),
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    state = {
        "status": "running",
        "pid": proc.pid,
        "request": request_path,
        "command": command,
        "stdout": stdout_path,
        "stderr": stderr_path,
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
    if extract_cfg.get("approval_policy"):
        command.extend(["-a", extract_cfg["approval_policy"]])
    if extract_cfg.get("json"):
        command.append("--json")
    if extract_cfg.get("ephemeral"):
        command.append("--ephemeral")
    for image in screenshots:
        command.extend(["-i", image])
    command.append(_read_text(prompt_path))
    return command


def _codex_extract_config(config: ConfigManager) -> Dict[str, Any]:
    section = "CODEX_EXTRACT"
    return {
        "codex_bin": config.get(section, "codex_bin", fallback=_default_codex_bin()).strip() or _default_codex_bin(),
        "profile": config.get(section, "profile", fallback="taobao_visual_extract").strip(),
        "model": config.get(section, "model", fallback="gpt-5.5").strip(),
        "sandbox": config.get(section, "sandbox", fallback="danger-full-access").strip(),
        "approval_policy": config.get(section, "approval_policy", fallback="never").strip(),
        "json": config.getboolean(section, "json_events", fallback=True),
        "ephemeral": config.getboolean(section, "ephemeral", fallback=True),
        "max_parallel": max(1, config.getint(section, "max_parallel", fallback=1)),
    }


def _default_codex_bin() -> str:
    bundled = "/Applications/Codex.app/Contents/Resources/codex"
    return bundled if os.path.exists(bundled) else "codex"


def _build_extract_prompt(request: Dict[str, Any]) -> str:
    rows_output = request["rows_output"]
    apply_command = request["commands"]["apply"]
    screenshots = "\n".join(f"- {path}" for path in request.get("screenshots", []))
    return f"""# Codex Extract Worker

You are a short-lived Codex extract worker for Taobao MTG visible-price evidence.

Request JSON: {request_path_label(request)}
Plan/session: {request["plan_id"]} / {request["session_index"]}
Keyword: {request["keyword"]}
Rows output: {rows_output}

Screenshots attached to this run are the only source of product data:
{screenshots}

Rules:
- Extract product rows only from visible screenshot pixels.
- Do not open or control Chrome.
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


def _screenshot_path(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("path") or value.get("image_path") or "").strip()
    return str(value or "").strip()


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


def _launch_active(state: Dict[str, Any]) -> bool:
    pid = state.get("pid")
    if not pid or str(state.get("status") or "") != "running":
        return False


def _active_launch_count(plan_id: str, session_index: int) -> int:
    root = _extract_root(plan_id, session_index)
    if not os.path.exists(root):
        return 0
    count = 0
    for dirpath, _, filenames in os.walk(root):
        if "launch_state.json" not in filenames:
            continue
        if _launch_active(_load_json_if_exists(os.path.join(dirpath, "launch_state.json"))):
            count += 1
    return count
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


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
