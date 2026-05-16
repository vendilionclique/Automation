import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from modules import codex_extract
from modules import visual_control
from modules import visual_scheduler
from modules import visual_capture_worker as worker
from modules import visual_pipeline
from modules.session_capsule import RUNNABLE_STATUSES


class FakeClient:
    def __init__(self, act_result, assert_result=None, stderr_tail=""):
        self.act_result = act_result
        self.assert_result = assert_result
        self.stderr_tail = stderr_tail
        self.calls = []

    def call_tool(self, name, arguments, **kwargs):
        self.calls.append({"name": name, "arguments": arguments, "kwargs": kwargs})
        if name == "act":
            return self.act_result
        if name == "assert":
            return self.assert_result or {"content": [{"type": "text", "text": "true"}]}
        raise AssertionError(f"unexpected tool: {name}")

    def capture_screenshot(self, path, **kwargs):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake-png")
        return {"path": path, "mime_type": "image/png"}

    def _stderr_tail(self):
        return self.stderr_tail


class DummyStdin:
    def write(self, value):
        self.last = value

    def flush(self):
        pass


class DummyProcess:
    def __init__(self):
        self.stdin = DummyStdin()

    def poll(self):
        return None


class VisualCaptureWorkerTests(unittest.TestCase):
    def test_midscene_act_stop_failure_text_is_abnormal(self):
        result = {
            "content": [
                {
                    "type": "text",
                    "text": "Task finished, message: stop and report failure: captcha visible",
                }
            ]
        }

        classified = worker.classify_midscene_act_result(result, default_context="search")

        self.assertTrue(classified["abnormal"])
        self.assertEqual(classified["stop_reason"], "captcha_required")
        self.assertEqual(classified["rough_state"], "captcha_required")

    def test_midscene_act_no_captcha_text_is_not_abnormal(self):
        result = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Task finished, message: 页面显示正常，无登录、验证码或其他安全提示出现"
                    ),
                }
            ]
        }

        classified = worker.classify_midscene_act_result(result, default_context="scroll")

        self.assertFalse(classified["abnormal"])
        self.assertEqual(classified["stop_reason"], "")
        self.assertEqual(classified["rough_state"], "act_completed")

    def test_keyword_capture_does_not_mark_abnormal_act_as_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
                "capture_plan": {"max_tiles_per_keyword": 1, "tile_scroll_distance_px": 500},
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "Task finished, message: login required, stop and report failure",
                        }
                    ]
                }
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot"],
                )

            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "login_required")
            self.assertTrue(os.path.exists(task["result_path"]))
            self.assertTrue(os.path.exists(task["abnormal_screenshot_path"]))

    def test_keyword_capture_does_not_mark_unknown_page_state_as_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {"max_tiles_per_keyword": 1, "tile_scroll_distance_px": 500},
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient({"content": [{"type": "text", "text": "search completed"}]})

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    return_value={
                        "status": "unknown",
                        "confidence": 0.35,
                        "reason": "heuristics_inconclusive",
                        "metrics": {},
                    },
                ):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "manual_review_needed")
            self.assertEqual(payload["rough_state"], "unknown")
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "unknown")
            self.assertTrue(os.path.exists(payload["screenshots"][0]["path"]))
            self.assertNotEqual(payload["status"], "captured")

    def test_keyword_capture_stops_when_visible_keyword_assertion_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 撼地灵",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
                "capture_plan": {
                    "max_tiles_per_keyword": 2,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "<complete success=\"true\">done</complete>"}]},
                assert_result={"content": [{"type": "text", "text": "false"}]},
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    return_value={
                        "status": "visible_ready",
                        "confidence": 0.72,
                        "reason": "test_visible_results",
                        "metrics": {},
                    },
                ):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot", "assert"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "visible_keyword_mismatch")
            self.assertEqual(payload["rough_state"], "keyword_mismatch")
            self.assertEqual(payload["diagnostics"]["post_act_verification"]["expected_keyword"], "万智牌 撼地灵")
            self.assertTrue(os.path.exists(task["capture_plan"]["primary_screenshot_path"]))
            self.assertTrue(os.path.exists(task["abnormal_screenshot_path"]))
            self.assertEqual(
                [call["name"] for call in client.calls],
                ["act", "assert"],
            )

    def test_keyword_capture_stops_when_screenshot_keyword_hint_mismatches_without_assert(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 撼地灵",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient({"content": [{"type": "text", "text": "search completed"}]})

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    return_value={
                        "status": "visible_ready",
                        "confidence": 0.72,
                        "reason": "test_visible_results",
                        "visible_search_keyword": "万智牌 闪电击",
                        "metrics": {},
                    },
                ):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "visible_keyword_mismatch")
            self.assertEqual(payload["rough_state"], "keyword_mismatch")
            self.assertNotEqual(payload["status"], "captured")
            self.assertEqual(
                payload["diagnostics"]["post_act_verification"]["screenshot_keyword"]["observed_keyword"],
                "万智牌 闪电击",
            )

    def test_runtime_progress_update_is_written_after_tile_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient({"content": [{"type": "text", "text": "search completed"}]})

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(worker, "write_worker_runtime") as write_runtime, \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    return_value={
                        "status": "visible_ready",
                        "confidence": 0.72,
                        "reason": "test_visible_results",
                        "visible_search_keyword": "万智牌 中止",
                        "metrics": {},
                    },
                ):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot"],
                )

            self.assertEqual(result["status"], "captured")
            progress_calls = [
                call
                for call in write_runtime.call_args_list
                if call.kwargs.get("progress_event") == "tile_captured"
            ]
            self.assertGreaterEqual(len(progress_calls), 1)
            self.assertEqual(progress_calls[0].args[:4], ("run", 1, "capture", "running"))
            self.assertEqual(progress_calls[0].kwargs["current_keyword"], "万智牌 中止")
            self.assertEqual(progress_calls[0].kwargs["tile_id"], "tile_00")

    def test_midscene_429_stderr_stops_as_rate_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                stderr_tail="HTTP 429 from https://example.invalid/path?token=secret access_token=abcdef",
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    return_value={
                        "status": "visible_ready",
                        "confidence": 0.72,
                        "reason": "test_visible_results",
                        "visible_search_keyword": "万智牌 中止",
                        "metrics": {},
                    },
                ):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "rate_limited")
            self.assertEqual(payload["rough_state"], "rate_limited")
            self.assertTrue(payload["diagnostics"]["keyword_search_act"]["http_429_detected"])
            excerpt = payload["diagnostics"]["keyword_search_act"]["rate_limit_diagnostics"][0]["excerpt"]
            self.assertIn("[url]", excerpt)
            self.assertNotIn("secret", excerpt)

    def test_midscene_429_tool_error_is_rate_limited_hard_abnormal(self):
        classified = worker.classify_midscene_act_result(
            {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "429 too many requests: model quota exceeded",
                    }
                ],
            },
            default_context="search",
        )

        self.assertTrue(classified["abnormal"])
        self.assertEqual(classified["stop_reason"], "rate_limited")
        self.assertEqual(classified["rough_state"], "rate_limited")
        self.assertIn("rate_limited", worker.HARD_ABNORMAL_REASONS)

    def test_midscene_429_exception_is_rate_limited_hard_abnormal(self):
        classified = worker.classify_midscene_exception(RuntimeError("rate limit quota exceeded"))

        self.assertTrue(classified["abnormal"])
        self.assertEqual(classified["stop_reason"], "rate_limited")
        self.assertEqual(classified["rough_state"], "rate_limited")
        self.assertIn("rate_limited", worker.HARD_ABNORMAL_REASONS)

    def test_real_not_available_sync_becomes_non_runnable_human_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "needs_midscene_computer",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            keyword_result = {
                "status": "real_not_available",
                "rough_state": "not_started",
                "stop_reason": "midscene_mcp_launcher_missing",
                "screenshots": [],
            }
            session_result = {"status": "real_not_available"}
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)
            worker._write_json(os.path.join(session_dir, "session_worker_result.json"), session_result)

            with mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), mock.patch.object(
                visual_pipeline,
                "session_dir_for",
                return_value=session_dir,
            ):
                sync = visual_pipeline.sync_midscene_worker_results(run_id, 1)

            self.assertTrue(sync["ok"])
            updated = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            status = updated["records"][0]["status"]
            self.assertEqual(status, "paused_needs_human")
            self.assertNotIn(status, RUNNABLE_STATUSES)

    def test_heartbeat_sync_consumes_keyword_result_before_session_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            screenshot_path = os.path.join(evidence_dir, "tile_00.png")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            keyword_result = {
                "schema": "taobao_visual_capture_keyword_result_v1",
                "keyword": "万智牌 中止",
                "status": "captured",
                "rough_state": "visible_ready",
                "stop_reason": "completed",
                "screenshots": [
                    {
                        "tile_id": "tile_00",
                        "path": screenshot_path,
                        "captured_at": "2026-05-15T10:00:00",
                    }
                ],
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)
            with open(screenshot_path, "wb") as f:
                f.write(b"fake-png")

            with mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir):
                sync = visual_scheduler._sync_existing_worker_results(run_id, 1)
                prepared = codex_extract.prepare_codex_extract_requests(run_id, 1)

            self.assertEqual(len(sync), 1)
            self.assertEqual(sync[0]["updated"], 1)
            self.assertEqual(prepared["prepared"], 1)
            self.assertTrue(os.path.exists(prepared["requests"][0]["request"]))

    def test_heartbeat_dispatch_marks_missing_pid_capture_worker_stale_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            runtime = {
                "plan_id": run_id,
                "session_index": 1,
                "worker_kind": "capture",
                "status": "running",
                "pid": 999999,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(contract_path, {"run_id": run_id, "session_index": 1})
            worker._write_json(os.path.join(session_dir, "capture_worker_runtime.json"), runtime)

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch("modules.session_capsule.get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control.os, "kill", side_effect=ProcessLookupError):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertEqual(result["action"], "dispatch_advised")
            self.assertTrue(result["dispatch"]["capture_worker_stale"])
            self.assertIn("pid_not_active", result["reason"])
            updated_runtime = worker._read_json(os.path.join(session_dir, "capture_worker_runtime.json"))
            self.assertEqual(updated_runtime["status"], "failed_recoverable")
            self.assertEqual(updated_runtime["failure_reason"], "capture_worker_stale")
            self.assertEqual(updated_runtime["stale_original_pid"], 999999)
            self.assertEqual(updated_runtime["stale_original_runtime"]["status"], "running")
            updated_manifest = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            self.assertEqual(updated_manifest["records"][0]["status"], "needs_midscene_computer")
            self.assertIsNone(updated_manifest["records"][0]["failure_reason"])
            self.assertTrue(result["dispatch"]["capture_start_allowed"])
            self.assertIn("capture", result["dispatch"]["worker_commands"])
            self.assertEqual(result["dispatch"]["manifest_recovery_state"]["runnable_count"], 1)
            self.assertEqual(result["dispatch"]["recovery_prepare_result"]["processed"], 1)

    def test_heartbeat_sync_marks_old_live_capture_worker_stale_by_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            config_path = os.path.join(tmp, "settings.ini")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            old_time = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            runtime = {
                "plan_id": run_id,
                "session_index": 1,
                "worker_kind": "capture",
                "status": "running",
                "pid": os.getpid(),
                "updated_at": old_time,
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(os.path.join(session_dir, "capture_worker_runtime.json"), runtime)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[SCHEDULER]\ncapture_worker_stale_after_minutes = 1\n")

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control.os, "kill", return_value=None):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="sync",
                    config_file=config_path,
                )

            self.assertEqual(result["action"], "stale_recovered")
            self.assertEqual(result["stale_workers"][0]["stale_reason"], "ttl_exceeded")
            updated_runtime = worker._read_json(os.path.join(session_dir, "capture_worker_runtime.json"))
            self.assertEqual(updated_runtime["status"], "failed_recoverable")
            self.assertEqual(updated_runtime["stale_reason"], "ttl_exceeded")

    def test_heartbeat_dispatch_does_not_advise_duplicate_capture_when_worker_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            runtime = {
                "plan_id": run_id,
                "session_index": 1,
                "worker_kind": "capture",
                "status": "running",
                "pid": os.getpid(),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(contract_path, {"run_id": run_id, "session_index": 1})
            worker._write_json(os.path.join(session_dir, "capture_worker_runtime.json"), runtime)

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control.os, "kill", return_value=None):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertEqual(result["action"], "dispatch_advised")
            self.assertTrue(result["dispatch"]["contract_exists"])
            self.assertFalse(result["dispatch"]["capture_start_allowed"])
            self.assertTrue(result["dispatch"]["capture_worker_liveness"]["active"])
            self.assertNotIn("capture", result["dispatch"]["worker_commands"])
            first_runtime = worker._read_json(os.path.join(session_dir, "capture_worker_runtime.json"))
            self.assertEqual(first_runtime["status"], "running")
            self.assertEqual(first_runtime["pid"], os.getpid())
            self.assertTrue(os.path.exists(os.path.join(session_dir, "heartbeat_worker_runtime.json")))

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control.os, "kill", return_value=None):
                second = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertFalse(second["dispatch"]["capture_start_allowed"])
            self.assertNotIn("capture", second["dispatch"]["worker_commands"])
            second_runtime = worker._read_json(os.path.join(session_dir, "capture_worker_runtime.json"))
            self.assertEqual(second_runtime["status"], "running")
            self.assertEqual(second_runtime["pid"], os.getpid())

    def test_heartbeat_dispatch_does_not_advise_capture_when_session_result_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "captured",
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            runtime = {
                "plan_id": run_id,
                "session_index": 1,
                "worker_kind": "capture",
                "status": "running",
                "pid": 999999,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(contract_path, {"run_id": run_id, "session_index": 1})
            worker._write_json(os.path.join(session_dir, "capture_worker_runtime.json"), runtime)
            worker._write_json(
                os.path.join(session_dir, "session_worker_result.json"),
                {"status": "completed"},
            )

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertEqual(result["action"], "dispatch_advised")
            self.assertFalse(result["dispatch"]["capture_start_allowed"])
            self.assertTrue(result["dispatch"]["capture_worker_liveness"]["session_result_exists"])
            self.assertTrue(result["dispatch"]["capture_worker_liveness"]["session_result_success"])
            self.assertEqual(result["dispatch"]["capture_worker_liveness"]["session_result_status"], "completed")
            self.assertNotIn("capture", result["dispatch"]["worker_commands"])
            updated_runtime = worker._read_json(os.path.join(session_dir, "capture_worker_runtime.json"))
            self.assertEqual(updated_runtime["status"], "running")
            self.assertNotIn("stale", updated_runtime)

    def test_heartbeat_dispatch_does_not_advise_capture_for_old_contract_without_runnable_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "captured",
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(
                contract_path,
                {
                    "run_id": run_id,
                    "session_index": 1,
                    "keyword_tasks": [{"keyword": "万智牌 中止"}],
                },
            )

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertEqual(result["action"], "dispatch_advised")
            self.assertTrue(result["dispatch"]["contract_exists"])
            self.assertEqual(result["dispatch"]["manifest_recovery_state"]["runnable_count"], 0)
            self.assertFalse(result["dispatch"]["capture_start_allowed"])
            self.assertNotIn("capture", result["dispatch"]["worker_commands"])
            self.assertNotIn("capture_recoverable_restart", result["dispatch"]["worker_commands"])

    def test_heartbeat_dispatch_allows_capture_when_session_result_failed_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "failed_recoverable",
                        "failure_reason": "capture_worker_stale",
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(contract_path, {"run_id": run_id, "session_index": 1, "keywords": ["old"]})
            worker._write_json(
                os.path.join(session_dir, "session_worker_result.json"),
                {"status": "failed_recoverable", "stop_reason": "capture_worker_stale"},
            )

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch("modules.session_capsule.get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            liveness = result["dispatch"]["capture_worker_liveness"]
            self.assertTrue(liveness["session_result_exists"])
            self.assertFalse(liveness["session_result_success"])
            self.assertEqual(liveness["session_result_status"], "failed_recoverable")
            self.assertEqual(result["dispatch"]["reason"], "session_result:failed_recoverable")
            self.assertTrue(result["dispatch"]["capture_start_allowed"])
            self.assertIn("capture", result["dispatch"]["worker_commands"])
            self.assertEqual(result["dispatch"]["recovery_prepare_result"]["processed"], 1)
            updated_manifest = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            self.assertEqual(updated_manifest["records"][0]["status"], "needs_midscene_computer")
            fresh_contract = worker._read_json(contract_path)
            self.assertEqual(fresh_contract["keyword_count"], 1)
            self.assertEqual(
                [item["keyword"] for item in fresh_contract["keyword_tasks"]],
                ["万智牌 中止"],
            )

    def test_stale_manifest_does_not_override_records_with_keyword_result_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            evidence_dir_missing = os.path.join(task_dir, "evidence", "kw_missing")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(evidence_dir_missing, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "session": {"status": "running", "worker_status": "running"},
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    },
                    {
                        "keyword": "万智牌 闪电击",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir_missing,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            runtime = {
                "plan_id": run_id,
                "session_index": 1,
                "worker_kind": "capture",
                "status": "running",
                "pid": 999999,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            keyword_result = {
                "schema": "taobao_visual_keyword_result_v1",
                "keyword": "万智牌 中止",
                "status": "captured",
                "rough_state": "visible_ready",
                "screenshots": [],
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(contract_path, {"run_id": run_id, "session_index": 1})
            worker._write_json(os.path.join(session_dir, "capture_worker_runtime.json"), runtime)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch("modules.session_capsule.get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control.os, "kill", side_effect=ProcessLookupError):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="dispatch",
                )

            self.assertTrue(result["dispatch"]["capture_worker_stale"])
            self.assertEqual(result["dispatch"]["capture_worker_liveness"]["stale_reason"], "pid_not_active")
            updated_manifest = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            self.assertEqual(updated_manifest["records"][0]["status"], "running")
            self.assertEqual(updated_manifest["records"][1]["status"], "needs_midscene_computer")
            self.assertTrue(result["dispatch"]["capture_start_allowed"])
            self.assertEqual(
                result["dispatch"]["manifest_recovery_state"]["stale_manifest_update"]["updated"],
                1,
            )
            self.assertEqual(
                result["dispatch"]["manifest_recovery_state"]["stale_manifest_update"]["skipped_keyword_results"],
                1,
            )
            fresh_contract = worker._read_json(contract_path)
            self.assertEqual(
                [item["keyword"] for item in fresh_contract["keyword_tasks"]],
                ["万智牌 闪电击"],
            )

    def test_keyword_result_mismatch_does_not_prepare_extract_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            screenshot_path = os.path.join(evidence_dir, "tile_00.png")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "captured",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            keyword_result = {
                "schema": "taobao_visual_capture_keyword_result_v1",
                "keyword": "万智牌 闪电击",
                "status": "captured",
                "rough_state": "visible_ready",
                "stop_reason": "completed",
                "screenshots": [
                    {
                        "tile_id": "tile_00",
                        "path": screenshot_path,
                        "captured_at": "2026-05-15T10:00:00",
                    }
                ],
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)
            with open(screenshot_path, "wb") as f:
                f.write(b"fake-png")

            with mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir):
                prepared = codex_extract.prepare_codex_extract_requests(run_id, 1)

            extract_root = os.path.join(session_dir, "codex_extract")
            self.assertEqual(prepared["prepared"], 0)
            self.assertEqual(prepared["skipped"][0]["reason"], "keyword_result_keyword_mismatch")
            self.assertFalse(os.path.exists(extract_root))
            updated = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            self.assertNotIn("codex_extract_request", updated["records"][0].get("extra", {}))

    def test_extract_drain_exits_on_capture_needs_review_without_dispatching_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "plan"
            task_dir = os.path.join(tmp, "data", "tasks", run_id)
            evidence_dir = os.path.join(task_dir, "evidence", "kw")
            session_dir = os.path.join(task_dir, "sessions", "session_01")
            config_path = os.path.join(tmp, "settings.ini")
            os.makedirs(evidence_dir, exist_ok=True)
            os.makedirs(session_dir, exist_ok=True)
            manifest = {
                "run_id": run_id,
                "records": [
                    {
                        "keyword": "万智牌 中止",
                        "status": "running",
                        "failure_reason": None,
                        "evidence_dir": evidence_dir,
                        "extra": {"daily_session_index": 1},
                    }
                ],
            }
            keyword_result = {
                "schema": "taobao_visual_capture_keyword_result_v1",
                "keyword": "万智牌 中止",
                "status": "needs_review",
                "rough_state": "unknown",
                "stop_reason": "manual_review_needed",
                "screenshots": [],
            }
            session_result = {
                "schema": "taobao_visual_capture_session_result_v1",
                "status": "needs_review",
                "stop_reason": "manual_review_needed",
            }
            os.makedirs(task_dir, exist_ok=True)
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)
            worker._write_json(os.path.join(session_dir, "session_worker_result.json"), session_result)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[CODEX_EXTRACT]\nmax_parallel = 1\n")

            with mock.patch.object(codex_extract, "get_project_root", return_value=tmp), \
                mock.patch.object(codex_extract, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "session_dir_for", return_value=session_dir), \
                mock.patch.object(codex_extract, "_start_codex_worker") as start_worker:
                result = codex_extract.run_codex_extract_drain(
                    run_id,
                    1,
                    config_file=config_path,
                    start=True,
                )

            self.assertEqual(result["reason"], "session_result:needs_review")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["prepared_total"], 0)
            self.assertEqual(result["dispatched_total"], 0)
            self.assertEqual(result["last_dispatch"]["count"], 0)
            start_worker.assert_not_called()

    def test_keyword_timeout_is_recoverable_abnormal(self):
        with self.assertRaises(worker.KeywordTimeout):
            worker._raise_if_keyword_timeout(started=0.0, timeout_seconds=0.01, keyword="万智牌 中止")

        task = {"capture_plan": {"timeout_seconds": 2}}
        contract = {"hard_stop_policy": {"timeout_per_keyword_seconds": 180}}
        self.assertEqual(worker._keyword_timeout_seconds(task, contract), 10.0)

    def test_mcp_request_exits_on_control_interrupt_while_waiting(self):
        client = worker.MidsceneStdioClient(["dummy"], cwd="/tmp", timeout_seconds=60)
        client.process = DummyProcess()

        def raise_interrupt():
            raise worker.WorkerControlInterrupt("paused", status="paused_needs_supervisor")

        with self.assertRaises(worker.WorkerControlInterrupt):
            client.request(
                "tools/call",
                {"name": "act", "arguments": {}},
                interrupt_check=raise_interrupt,
            )

    def test_mcp_request_exits_on_keyword_deadline_while_waiting(self):
        client = worker.MidsceneStdioClient(["dummy"], cwd="/tmp", timeout_seconds=60)
        client.process = DummyProcess()
        started = worker.time.monotonic()

        with self.assertRaises(worker.KeywordTimeout):
            client.request(
                "tools/call",
                {"name": "act", "arguments": {}},
                keyword_deadline=started + 0.05,
                keyword="万智牌 中止",
            )

        self.assertLess(worker.time.monotonic() - started, 0.5)

    def test_act_timeout_uses_keyword_budget_instead_of_default_client_timeout(self):
        client = FakeClient({"content": [{"type": "text", "text": "done"}]})

        worker._call_act(
            client,
            "search",
            keyword_deadline=worker.time.monotonic() + 120,
            keyword="万智牌 中止",
            timeout_seconds=240,
        )

        timeout = client.calls[0]["kwargs"]["timeout_seconds"]
        self.assertGreater(timeout, 100)
        self.assertLessEqual(timeout, 120)

    def test_mcp_request_timeout_is_hard_abnormal_reason(self):
        self.assertIn("midscene_mcp_request_timeout", worker.HARD_ABNORMAL_REASONS)


if __name__ == "__main__":
    unittest.main()
