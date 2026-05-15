import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from modules import codex_extract


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


class CodexExtractTests(unittest.TestCase):
    def test_repeat_apply_returns_existing_success_after_screenshots_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = os.path.join(tmp, "extract_request.json")
            rows_path = os.path.join(tmp, "rows_result.json")
            apply_path = os.path.join(tmp, "apply_result.json")
            worker_path = os.path.join(tmp, "codex_worker_result.json")
            deleted_screenshot = os.path.join(tmp, "evidence", "tile_00.png")
            existing_result = {
                "schema": "taobao_codex_extract_apply_result_v1",
                "ok": True,
                "status": "extracted",
                "plan_id": "plan",
                "session_index": 1,
                "keyword": "万智牌 中止",
                "request": request_path,
                "rows_file": rows_path,
                "screenshots": [deleted_screenshot],
                "screenshots_deleted": [deleted_screenshot],
                "updated_at": "2026-05-14T10:00:00",
            }
            request = {
                "schema": codex_extract.REQUEST_SCHEMA,
                "plan_id": "plan",
                "session_index": 1,
                "keyword": "万智牌 中止",
                "task_dir": tmp,
                "evidence_dir": os.path.join(tmp, "evidence"),
                "screenshots": [deleted_screenshot],
                "rows_output": rows_path,
                "apply_result": apply_path,
                "worker_result": worker_path,
            }
            write_json(request_path, request)
            write_json(rows_path, {"schema": codex_extract.RESULT_SCHEMA, "keyword": "万智牌 中止", "rows": []})
            write_json(apply_path, existing_result)

            with mock.patch.object(codex_extract, "_update_manifest_after_apply") as update_manifest:
                result = codex_extract.apply_codex_extracted_rows(
                    request_path,
                    config_file=os.path.join(tmp, "settings.ini"),
                )

            self.assertEqual(result, existing_result)
            update_manifest.assert_not_called()
            self.assertFalse(os.path.exists(deleted_screenshot))
            with open(apply_path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), existing_result)

    def test_stale_running_launch_with_live_pid_is_cleaned_by_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = os.path.join(tmp, "data", "tasks", "plan", "sessions", "session_01")
            contract_dir = os.path.join(session_dir, "codex_extract", "kw")
            state_path = os.path.join(contract_dir, "launch_state.json")
            state = {
                "status": "running",
                "pid": os.getpid(),
                "launched_at": (datetime.now() - timedelta(hours=4)).isoformat(timespec="seconds"),
                "updated_at": (datetime.now() - timedelta(hours=4)).isoformat(timespec="seconds"),
            }
            write_json(state_path, state)

            with mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir):
                active = codex_extract._active_launch_count("plan", 1, stale_after_seconds=60)

            self.assertEqual(active, 0)
            with open(state_path, "r", encoding="utf-8") as f:
                updated = json.load(f)
            self.assertEqual(updated["status"], "stale")
            self.assertEqual(updated["stale_reason"], "ttl_exceeded")
            self.assertIn("stale_detected_at", updated)

    def test_dispatch_advises_when_old_running_state_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = os.path.join(tmp, "data", "tasks", "plan", "sessions", "session_01")
            contract_dir = os.path.join(session_dir, "codex_extract", "kw")
            request_path = os.path.join(contract_dir, "extract_request.json")
            prompt_path = os.path.join(contract_dir, "extract_prompt.md")
            rows_path = os.path.join(contract_dir, "rows_result.json")
            apply_path = os.path.join(contract_dir, "apply_result.json")
            state_path = os.path.join(contract_dir, "launch_state.json")
            config_path = os.path.join(tmp, "settings.ini")
            request = {
                "schema": codex_extract.REQUEST_SCHEMA,
                "plan_id": "plan",
                "session_index": 1,
                "keyword": "kw",
                "prompt": prompt_path,
                "rows_output": rows_path,
                "apply_result": apply_path,
                "screenshots": [],
            }
            manifest = {
                "records": [
                    {
                        "keyword": "kw",
                        "status": "captured",
                        "extra": {"daily_session_index": 1, "codex_extract_request": request_path},
                    }
                ]
            }
            state = {
                "status": "running",
                "pid": os.getpid(),
                "launched_at": (datetime.now() - timedelta(hours=4)).isoformat(timespec="seconds"),
            }
            write_json(request_path, request)
            write_json(state_path, state)
            os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write("extract")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    "[CODEX_EXTRACT]\n"
                    "codex_bin = codex\n"
                    "profile = \n"
                    "model = \n"
                    "sandbox = \n"
                    "approval_policy = \n"
                    "json_events = false\n"
                    "ephemeral = false\n"
                    "max_parallel = 1\n"
                    "worker_stale_after_minutes = 1\n"
                )

            with mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir), mock.patch.object(
                codex_extract,
                "load_visual_manifest",
                return_value=manifest,
            ):
                result = codex_extract.dispatch_codex_extract_requests("plan", 1, config_file=config_path)

            self.assertEqual(result["workers"][0]["status"], "advised")
            with open(state_path, "r", encoding="utf-8") as f:
                updated = json.load(f)
            self.assertEqual(updated["status"], "stale")
            self.assertEqual(updated["stale_reason"], "ttl_exceeded")


if __name__ == "__main__":
    unittest.main()
