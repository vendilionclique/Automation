import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from modules import codex_extract
from modules import visual_control
from modules import visual_pipeline
from modules.vision_extract import ingest_rows


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class CodexExtractTests(unittest.TestCase):
    def test_extract_drain_waits_when_capture_is_open_and_no_screenshots_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", plan_id)
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            config_path = os.path.join(tmp, "settings.ini")
            write_json(os.path.join(task_dir, "visual_tasks.json"), {"run_id": plan_id, "records": []})
            os.makedirs(session_dir, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    "[CODEX_EXTRACT]\n"
                    "max_parallel = 1\n"
                    "drain_poll_seconds = 1\n"
                    "drain_idle_timeout_seconds = 60\n"
                )

            with mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "session_dir_for", return_value=session_dir):
                result = codex_extract.run_codex_extract_drain(
                    plan_id,
                    1,
                    config_file=config_path,
                    start=False,
                    max_cycles=1,
                )

            self.assertEqual(result["reason"], "max_cycles_reached")
            self.assertEqual(result["prepared_total"], 0)
            self.assertEqual(result["dispatched_total"], 0)
            self.assertFalse(result["capture_state"]["closed"])

    def test_extract_drain_exits_when_capture_closed_and_queue_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", plan_id)
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            config_path = os.path.join(tmp, "settings.ini")
            write_json(os.path.join(task_dir, "visual_tasks.json"), {"run_id": plan_id, "records": []})
            write_json(os.path.join(session_dir, "session_worker_result.json"), {"status": "captured"})
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[CODEX_EXTRACT]\nmax_parallel = 1\n")

            with mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "session_dir_for", return_value=session_dir):
                result = codex_extract.run_codex_extract_drain(
                    plan_id,
                    1,
                    config_file=config_path,
                    start=False,
                )

            self.assertEqual(result["reason"], "session_result:captured")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["prepared_total"], 0)

    def test_extract_drain_default_does_not_start_codex_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_id = "plan"
            session_dir = os.path.join(tmp, "data", "tasks", plan_id, "sessions", "session_01")
            contract_dir = os.path.join(session_dir, "codex_extract", "kw")
            request_path = os.path.join(contract_dir, "extract_request.json")
            prompt_path = os.path.join(contract_dir, "extract_prompt.md")
            rows_path = os.path.join(contract_dir, "rows_result.json")
            apply_path = os.path.join(contract_dir, "apply_result.json")
            config_path = os.path.join(tmp, "settings.ini")
            write_json(
                request_path,
                {
                    "schema": codex_extract.REQUEST_SCHEMA,
                    "plan_id": plan_id,
                    "session_index": 1,
                    "keyword": "kw",
                    "prompt": prompt_path,
                    "rows_output": rows_path,
                    "apply_result": apply_path,
                    "screenshots": [],
                },
            )
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
                    "ignore_rules = false\n"
                    "json_events = false\n"
                    "ephemeral = false\n"
                    "max_parallel = 1\n"
                    "drain_poll_seconds = 1\n"
                    "drain_idle_timeout_seconds = 60\n"
                )
            manifest = {
                "records": [
                    {
                        "keyword": "kw",
                        "status": "captured",
                        "extra": {"daily_session_index": 1, "codex_extract_request": request_path},
                    }
                ]
            }

            with mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir), \
                mock.patch.object(codex_extract, "load_visual_manifest", return_value=manifest), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "session_dir_for", return_value=session_dir), \
                mock.patch.object(codex_extract, "_start_codex_worker") as start_worker:
                result = codex_extract.run_codex_extract_drain(
                    plan_id,
                    1,
                    config_file=config_path,
                    max_cycles=1,
                )

            self.assertFalse(result["start"])
            self.assertEqual(result["last_dispatch"]["start"], False)
            self.assertEqual(result["dispatched_total"], 1)
            self.assertEqual(result["last_dispatch"]["workers"][0]["status"], "advised")
            start_worker.assert_not_called()

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

    def test_zombie_launch_does_not_count_as_active(self):
        with mock.patch.object(codex_extract.os, "kill"), \
            mock.patch.object(codex_extract.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout="Z+\n")

            active = codex_extract._launch_active({"status": "running", "pid": "12345"})

        self.assertFalse(active)

    def test_invalid_launch_pid_does_not_count_as_active(self):
        active = codex_extract._launch_active({"status": "running", "pid": "not-a-pid"})

        self.assertFalse(active)

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
                    "ignore_rules = false\n"
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

    def test_launch_command_uses_config_overrides_supported_by_current_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = os.path.join(tmp, "extract_request.json")
            prompt_path = os.path.join(tmp, "extract_prompt.md")
            image_path = os.path.join(tmp, "tile_00.png")
            write_json(
                request_path,
                {
                    "schema": codex_extract.REQUEST_SCHEMA,
                    "prompt": prompt_path,
                    "screenshots": [image_path],
                },
            )
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write("extract")
            with open(image_path, "wb") as f:
                f.write(b"png")

            command = codex_extract._launch_command(
                request_path,
                {
                    "codex_bin": "codex",
                    "profile": "taobao_visual_extract",
                    "model": "gpt-5.5",
                    "sandbox": "danger-full-access",
                    "approval_policy": "never",
                    "ignore_rules": True,
                    "json": True,
                    "ephemeral": True,
                },
            )

            self.assertNotIn("-a", command)
            self.assertIn("--ignore-rules", command)
            self.assertIn("sandbox_mode=\"danger-full-access\"", command)
            self.assertIn("approval_policy=\"never\"", command)
            self.assertNotIn("extract", command)

    def test_fuzzy_dedupe_skips_near_duplicate_store_and_title_same_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_rows(
                task_dir=tmp,
                keyword="万智牌 中止",
                rows=[
                    {
                        "商品名称": "万智牌 中止 中文 闪",
                        "现价": "12.00",
                        "店铺名称": "小蓝牌店",
                        "识别置信度": 0.99,
                    },
                    {
                        "商品名称": "万智牌中止中文闪",
                        "现价": "12.00",
                        "店铺名称": "小蓝脾店",
                        "识别置信度": 0.99,
                    },
                ],
                captured_at="2026-05-15 10:00:00",
                retain_screenshot=True,
            )

            rows = read_jsonl(os.path.join(tmp, "raw_rows.jsonl"))
            self.assertTrue(result.ok)
            self.assertEqual(result.rows_written, 1)
            self.assertEqual(result.fuzzy_duplicates_removed, 1)
            self.assertEqual(len(result.fuzzy_duplicate_examples), 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["店铺名称"], "小蓝牌店")

    def test_fuzzy_dedupe_keeps_same_store_price_when_title_similarity_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_rows(
                task_dir=tmp,
                keyword="万智牌 中止",
                rows=[
                    {
                        "商品名称": "万智牌 中止 中文 闪 单卡",
                        "现价": "12.00",
                        "店铺名称": "小蓝牌店",
                        "识别置信度": 0.99,
                    },
                    {
                        "商品名称": "万智牌 中止 英文 普通 现货",
                        "现价": "12.00",
                        "店铺名称": "小蓝牌店",
                        "识别置信度": 0.99,
                    },
                ],
                captured_at="2026-05-15 10:00:00",
                retain_screenshot=True,
            )

            rows = read_jsonl(os.path.join(tmp, "raw_rows.jsonl"))
            self.assertTrue(result.ok)
            self.assertEqual(result.rows_written, 2)
            self.assertEqual(result.fuzzy_duplicates_removed, 0)
            self.assertEqual(len(rows), 2)

    def test_fuzzy_dedupe_keeps_different_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_rows(
                task_dir=tmp,
                keyword="万智牌 中止",
                rows=[
                    {
                        "商品名称": "万智牌 中止 中文 闪",
                        "现价": "12.00",
                        "店铺名称": "小蓝牌店",
                        "识别置信度": 0.99,
                    },
                    {
                        "商品名称": "万智牌中止中文闪",
                        "现价": "13.00",
                        "店铺名称": "小蓝脾店",
                        "识别置信度": 0.99,
                    },
                ],
                captured_at="2026-05-15 10:00:00",
                retain_screenshot=True,
            )

            rows = read_jsonl(os.path.join(tmp, "raw_rows.jsonl"))
            self.assertTrue(result.ok)
            self.assertEqual(result.rows_written, 2)
            self.assertEqual(result.fuzzy_duplicates_removed, 0)
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
