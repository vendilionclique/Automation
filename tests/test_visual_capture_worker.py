import os
import tempfile
import unittest
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

    def test_midscene_429_is_recorded_as_diagnostic_not_captured_signal(self):
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
            self.assertEqual(result["status"], "captured")
            self.assertTrue(payload["diagnostics"]["keyword_search_act"]["http_429_detected"])
            excerpt = payload["diagnostics"]["keyword_search_act"]["rate_limit_diagnostics"][0]["excerpt"]
            self.assertIn("[url]", excerpt)
            self.assertNotIn("secret", excerpt)

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
