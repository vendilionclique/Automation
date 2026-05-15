"""
Session capsule and lease helpers for bounded Codex runs.

A capsule is the small, durable context a fresh Codex thread needs to continue a
scheduled collection session without relying on chat history. It lives under the
task directory and is safe to regenerate.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from modules.page_sampling import write_task_event
from modules.utils import ensure_dir, get_project_root


RUNNABLE_STATUSES = {
    "pending",
    "cooldown",
    "failed",
    "needs_midscene_computer",
}


def session_dir_for(plan_id: str, session_index: int) -> str:
    return os.path.join(
        get_project_root(),
        "data",
        "tasks",
        plan_id,
        "sessions",
        f"session_{int(session_index):02d}",
    )


def build_session_capsule(
    plan_id: str,
    session_index: int,
    config_file: str = "config/settings.ini",
    limit: Optional[int] = None,
    manual_state: Optional[str] = None,
) -> Dict[str, Any]:
    task_dir = os.path.join(get_project_root(), "data", "tasks", plan_id)
    manifest_path = os.path.join(task_dir, "visual_tasks.json")
    plan_path = os.path.join(task_dir, "daily_plan.json")
    manifest = _load_json(manifest_path)
    plan = _load_json(plan_path) if os.path.exists(plan_path) else {}

    all_records = [
        record for record in manifest.get("records", [])
        if int(record.get("extra", {}).get("daily_session_index") or 0) == int(session_index)
    ]
    runnable_records = [
        record for record in all_records
        if str(record.get("status") or "") in RUNNABLE_STATUSES
    ]
    selected_records = runnable_records[:limit] if limit is not None else runnable_records
    keywords = [record.get("keyword", "") for record in selected_records if record.get("keyword")]

    session_dir = session_dir_for(plan_id, session_index)
    ensure_dir(session_dir)
    now = _now()
    request_path = os.path.join(session_dir, "session_request.json")
    prompt_path = os.path.join(session_dir, "session_prompt.md")
    lease_path = os.path.join(session_dir, "lease.json")
    summary_path = os.path.join(session_dir, "summary.json")
    events_path = os.path.join(session_dir, "events.jsonl")

    request = {
        "schema": "taobao_visual_session_request_v1",
        "plan_id": plan_id,
        "session_index": int(session_index),
        "created_at": now,
        "task_dir": task_dir,
        "manifest_path": manifest_path,
        "daily_plan_path": plan_path if os.path.exists(plan_path) else "",
        "config_file": os.path.abspath(config_file),
        "limit": limit,
        "manual_state": manual_state or "",
        "selected_keyword_count": len(keywords),
        "keywords": keywords,
        "records": [
            {
                "keyword": record.get("keyword", ""),
                "status": record.get("status", ""),
                "failure_reason": record.get("failure_reason"),
                "evidence_dir": record.get("evidence_dir", ""),
                "last_action": record.get("last_action"),
                "extra": record.get("extra", {}),
            }
            for record in selected_records
        ],
        "boundaries": {
            "codex_context": "Fresh Codex threads should read this capsule and local artifacts, not old chat history.",
            "recognition_context": "Use one visual recognition context per keyword; include that keyword's 3-4 viewport tiles together when available.",
            "state_source": "visual_tasks.json, task_events.jsonl, tile_summary.jsonl, raw_rows.jsonl, and this capsule.",
            "forbidden": [
                "DOM/HTML/network/storage extraction",
                "CDP/full-page screenshot as Taobao mainline",
                "automatic login/captcha/security handling",
                "account-state-changing actions",
            ],
        },
        "expected_outputs": {
            "midscene_session_worker": "visual-session-run writes sessions/session_NN/midscene_session_worker_request.json for bounded small-session execution.",
            "midscene_requests": "Each runnable keyword also keeps evidence/*/midscene_computer_request.json for compatibility and per-keyword recovery.",
            "worker_result": "Midscene writes session_worker_result.json plus each evidence/*/keyword_result.json after screenshot capture.",
            "rows": "After screenshot capture, use visual-codex-extract-prepare / visual-codex-extract-dispatch for screenshot recognition, then visual-apply-extracted-rows for deterministic persistence.",
            "events": "Append structured session events to this session events.jsonl and task_events.jsonl.",
            "summary": summary_path,
        },
    }

    prompt = _build_session_prompt(request)
    summary = {
        "plan_id": plan_id,
        "session_index": int(session_index),
        "status": "prepared",
        "created_at": now,
        "updated_at": now,
        "selected_keyword_count": len(keywords),
        "processed": 0,
        "needs_review": 0,
        "failed": 0,
        "notes": "",
    }
    lease = {
        "plan_id": plan_id,
        "session_index": int(session_index),
        "status": "prepared",
        "owner": "",
        "pid": None,
        "created_at": now,
        "updated_at": now,
        "expires_at": "",
        "request_path": request_path,
        "prompt_path": prompt_path,
    }

    _write_json(request_path, request)
    _write_text(prompt_path, prompt)
    if not os.path.exists(lease_path):
        _write_json(lease_path, lease)
    _write_json(summary_path, summary)
    if not os.path.exists(events_path):
        _write_text(events_path, "")

    _append_session_event(
        session_dir,
        "session_capsule_prepared",
        selected_keyword_count=len(keywords),
        limit=limit,
    )
    write_task_event(
        task_dir,
        event="session_capsule_prepared",
        run_id=plan_id,
        session_index=int(session_index),
        capsule_dir=session_dir,
        selected_keyword_count=len(keywords),
    )
    _update_daily_plan_session(plan_path, int(session_index), "prepared", session_dir)

    return {
        "ok": True,
        "plan_id": plan_id,
        "session_index": int(session_index),
        "session_dir": session_dir,
        "request": request_path,
        "prompt": prompt_path,
        "lease": lease_path,
        "events": events_path,
        "summary": summary_path,
        "selected_keyword_count": len(keywords),
        "keywords": keywords,
    }


def acquire_session_lease(
    plan_id: str,
    session_index: int,
    owner: str = "codex",
    ttl_minutes: int = 240,
    force: bool = False,
) -> Dict[str, Any]:
    session_dir = session_dir_for(plan_id, session_index)
    ensure_dir(session_dir)
    lease_path = os.path.join(session_dir, "lease.json")
    now = datetime.now()
    lease = _load_json(lease_path) if os.path.exists(lease_path) else {}
    if _lease_active(lease, now) and not force:
        raise RuntimeError(
            f"session lease still active for {plan_id} session {session_index}: {lease_path}"
        )
    lease.update(
        {
            "plan_id": plan_id,
            "session_index": int(session_index),
            "status": "active",
            "owner": owner,
            "pid": os.getpid(),
            "updated_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(minutes=max(1, int(ttl_minutes)))).isoformat(timespec="seconds"),
        }
    )
    lease.setdefault("created_at", lease["updated_at"])
    _write_json(lease_path, lease)
    _append_session_event(session_dir, "session_lease_acquired", owner=owner, ttl_minutes=ttl_minutes)
    _update_daily_plan_session(
        os.path.join(get_project_root(), "data", "tasks", plan_id, "daily_plan.json"),
        int(session_index),
        "active",
        session_dir,
    )
    return {"ok": True, "lease": lease_path, "lease_state": lease}


def heartbeat_session_lease(plan_id: str, session_index: int, ttl_minutes: int = 240) -> Dict[str, Any]:
    session_dir = session_dir_for(plan_id, session_index)
    lease_path = os.path.join(session_dir, "lease.json")
    lease = _load_json(lease_path)
    now = datetime.now()
    lease["updated_at"] = now.isoformat(timespec="seconds")
    lease["expires_at"] = (now + timedelta(minutes=max(1, int(ttl_minutes)))).isoformat(timespec="seconds")
    _write_json(lease_path, lease)
    _append_session_event(session_dir, "session_lease_heartbeat")
    return {"ok": True, "lease": lease_path, "lease_state": lease}


def complete_session_lease(
    plan_id: str,
    session_index: int,
    status: str = "completed",
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session_dir = session_dir_for(plan_id, session_index)
    lease_path = os.path.join(session_dir, "lease.json")
    lease = _load_json(lease_path) if os.path.exists(lease_path) else {}
    now = _now()
    lease.update({"status": status, "updated_at": now, "expires_at": ""})
    _write_json(lease_path, lease)
    if summary is not None:
        summary_path = os.path.join(session_dir, "summary.json")
        existing = _load_json(summary_path) if os.path.exists(summary_path) else {}
        existing.update(summary)
        existing["status"] = status
        existing["updated_at"] = now
        _write_json(summary_path, existing)
    _append_session_event(session_dir, "session_lease_completed", status=status)
    _update_daily_plan_session(
        os.path.join(get_project_root(), "data", "tasks", plan_id, "daily_plan.json"),
        int(session_index),
        status,
        session_dir,
    )
    return {"ok": True, "lease": lease_path, "lease_state": lease}


def inspect_session_lease(plan_id: str, session_index: int) -> Dict[str, Any]:
    session_dir = session_dir_for(plan_id, session_index)
    lease_path = os.path.join(session_dir, "lease.json")
    if not os.path.exists(lease_path):
        return {"ok": True, "exists": False, "active": False, "lease": lease_path}
    lease = _load_json(lease_path)
    return {
        "ok": True,
        "exists": True,
        "active": _lease_active(lease, datetime.now()),
        "lease": lease_path,
        "lease_state": lease,
    }


def _build_session_prompt(request: Dict[str, Any]) -> str:
    command = (
        f"python3 harness.py visual-session-run {request['plan_id']} "
        f"--session {request['session_index']}"
    )
    if request.get("limit") is not None:
        command += f" --limit {int(request['limit'])}"
    if request.get("manual_state"):
        command += f" --state {json.dumps(request['manual_state'], ensure_ascii=False)}"
    return f"""# Codex Session Capsule

Plan ID: {request["plan_id"]}
Session: {request["session_index"]}
Task dir: {request["task_dir"]}
Request JSON: {os.path.join(session_dir_for(request["plan_id"], request["session_index"]), "session_request.json")}

You are starting from a fresh context. Do not rely on previous chat history.
Read the local files named above, then run this bounded session:

```bash
{command}
```

Operational rules:
- Codex is a short-lived executor for this session. Durable state is in files.
- For large project development, use a subagent team by default. The main agent
  coordinates, reviews, integrates, and reports; bounded implementation,
  exploration, and test-fix work should go to worker/explorer subagents when
  available.
- If context is running low or compaction appears unreliable, save progress into
  this capsule, summary.json, events.jsonl, task_events.jsonl, control.json, or
  visual_tasks.json before continuing in a fresh thread. The fresh thread must
  read AGENTS.md and these files instead of relying on old chat history.
- visual-session-run prepares a bounded Midscene small-session worker contract.
  Midscene may continuously capture the selected keywords inside that contract,
  but it does not own daily scheduling, future retries, or final exception
  strategy.
- Use one visual recognition context per keyword. A keyword's viewport tiles can
  be reviewed together; do not split every tile into its own context by default.
- If login, captcha, security verification, white skeleton, repeated abnormal
  states, or account risk appears, stop, retain evidence, write events, and mark
  the affected keyword/session for review or cooldown.
- Product fields must come from visible screenshots only.
- Do not read DOM, HTML, AX tree, selector maps, cookies, storage, network
  payloads, page source, or JavaScript-evaluated page data.
- Do not add to cart, favorite/unfavorite, claim rewards, checkout, pay, or
  otherwise change account state.

Completion:
- Update visual_tasks.json through the existing harness commands.
- Keep task_events.jsonl and this session's events.jsonl useful for recovery.
- Write or update summary.json before the session exits.
"""


def _lease_active(lease: Dict[str, Any], now: datetime) -> bool:
    if str(lease.get("status") or "") != "active":
        return False
    expires_at = str(lease.get("expires_at") or "")
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(expires_at) > now
    except ValueError:
        return True


def _update_daily_plan_session(plan_path: str, session_index: int, status: str, session_dir: str) -> None:
    if not os.path.exists(plan_path):
        return
    plan = _load_json(plan_path)
    for item in plan.get("sessions", []):
        if int(item.get("session_index") or 0) == int(session_index):
            item["status"] = status
            item["session_dir"] = session_dir
            item["updated_at"] = _now()
            break
    _write_json(plan_path, plan)


def _append_session_event(session_dir: str, event: str, **extra: Any) -> str:
    payload = {"time": _now(), "event": event, **extra}
    path = os.path.join(session_dir, "events.jsonl")
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _write_text(path: str, text: str) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
