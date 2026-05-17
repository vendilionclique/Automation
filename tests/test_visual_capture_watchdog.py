import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from modules import visual_capture_watchdog


"""
Contract tests for modules.visual_capture_watchdog.

The production module is expected to expose run_capture_watchdog(...) with
sleep_fn/popen_factory/now_fn injection points and use
visual_scheduler.heartbeat_daily_collection so tests can monkeypatch heartbeat
without starting Chrome, Midscene, or a real subprocess.
"""


CAPTURE_COMMAND = (
    "python3 harness.py visual-capture-worker "
    "--contract 'data/tasks/daily_20260516/sessions/session_01/midscene_session_worker_request.json'"
)


class FakeClock:
    def __init__(self, start=1_000.0):
        self.value = datetime(2026, 5, 16, 9, 0, 0) + timedelta(seconds=float(start))

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += timedelta(seconds=float(seconds))


class FakeProcess:
    def __init__(self, returncode=0, polls=None, pid=4242):
        self.returncode = returncode
        self.polls = list(polls or [])
        self.pid = pid
        self.wait_calls = []

    def poll(self):
        if self.polls:
            value = self.polls.pop(0)
            if value is not None:
                self.returncode = value
            return value
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        while self.polls:
            value = self.poll()
            if value is None:
                continue
            return value
        return self.returncode


class HeartbeatScript:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError(f"unexpected heartbeat call: {kwargs}")
        response = self.responses.pop(0)
        if callable(response):
            response = response(kwargs)
        return response

    @property
    def modes(self):
        return [call.get("mode") for call in self.calls]


class PopenFactory:
    def __init__(self, *processes):
        self.processes = list(processes)
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if not self.processes:
            raise AssertionError(f"unexpected worker start: {args}")
        return self.processes.pop(0)


def heartbeat_allowed(reason=""):
    return {
        "ok": True,
        "action": "dispatch_advised",
        "plan_id": "daily_20260516",
        "session_index": 1,
        "dispatch": {
            "capture_start_allowed": True,
            "reason": reason,
            "worker_commands": {"capture": CAPTURE_COMMAND},
            "capture_worker_liveness": {"active": False},
            "manifest_recovery_state": {"runnable_count": 1},
            "contract_exists": True,
        },
    }


def heartbeat_allowed_with_old_paused_result():
    heartbeat = heartbeat_allowed("session_result:paused_needs_supervisor")
    heartbeat["dispatch"]["capture_worker_liveness"] = {
        "active": False,
        "session_result_status": "paused_needs_supervisor",
        "session_result_success": False,
        "session_result_payload": {
            "status": "paused_needs_supervisor",
            "stop_reason": "paused",
        },
    }
    heartbeat["dispatch"]["manifest_recovery_state"] = {
        "runnable_count": 1,
        "by_status": {"paused_needs_supervisor": 1, "needs_midscene_computer": 1},
    }
    return heartbeat


def heartbeat_allowed_but_control_paused():
    heartbeat = heartbeat_allowed("paused")
    heartbeat["action"] = "paused"
    return heartbeat


def heartbeat_blocked(reason, action="dispatch_advised", status=None):
    return {
        "ok": True,
        "action": action,
        "plan_id": "daily_20260516",
        "session_index": 1,
        "reason": reason if action != "dispatch_advised" else "",
        "dispatch": {
            "capture_start_allowed": False,
            "reason": reason,
            "worker_commands": {"capture": CAPTURE_COMMAND},
            "capture_worker_liveness": {"active": reason == "capture_worker_active"},
            "manifest_recovery_state": {"runnable_count": 1},
            "contract_exists": True,
        },
        "status": status or {},
    }


def heartbeat_done(reason="session_complete"):
    liveness = {"active": False}
    if reason == "session_complete":
        liveness["session_result_success"] = True
    return {
        "ok": True,
        "action": "noop",
        "plan_id": "daily_20260516",
        "session_index": 1,
        "reason": reason,
        "dispatch": {
            "capture_start_allowed": False,
            "reason": reason,
            "worker_commands": {},
            "capture_worker_liveness": liveness,
            "manifest_recovery_state": {"runnable_count": 0},
            "contract_exists": True,
        },
        "status": {
            "by_session": {
                "1": {
                    "captured": 1,
                    "success": 1,
                    "pending": 0,
                    "failed_recoverable": 0,
                }
            }
        },
    }


def heartbeat_sync(reason="synced", runnable_count=0):
    return {
        "ok": True,
        "action": "synced",
        "plan_id": "daily_20260516",
        "session_index": 1,
        "reason": reason,
        "sync": [{"ok": True, "reason": reason}],
        "dispatch": {
            "capture_start_allowed": False,
            "reason": reason,
            "manifest_recovery_state": {"runnable_count": runnable_count},
            "capture_worker_liveness": {"active": False},
            "contract_exists": True,
        },
    }


class VisualCaptureWatchdogTests(unittest.TestCase):
    def run_watchdog(self, heartbeat, popen=None, clock=None, **kwargs):
        clock = clock or FakeClock()
        popen = popen or PopenFactory()
        root = kwargs.pop("project_root", None)
        tempdir = None
        if root is None:
            tempdir = tempfile.TemporaryDirectory()
            self.addCleanup(tempdir.cleanup)
            root = tempdir.name
        with mock.patch.object(
            visual_capture_watchdog.visual_scheduler,
            "heartbeat_daily_collection",
            side_effect=heartbeat,
        ):
            return visual_capture_watchdog.run_capture_watchdog(
                plan_id="daily_20260516",
                session_index=1,
                start=True,
                poll_seconds=kwargs.pop("poll_seconds", 1),
                idle_timeout_seconds=kwargs.pop("idle_timeout_seconds", 60),
                max_restarts=kwargs.pop("max_restarts", 2),
                popen_factory=popen,
                sleep_fn=clock.sleep,
                now_fn=clock.now,
                project_root=root,
                **kwargs,
            )

    def read_runtime(self, result):
        with open(result["runtime_path"], "r", encoding="utf-8") as f:
            return json.load(f)

    def test_no_due_or_runnable_session_exits_without_worker(self):
        heartbeat = HeartbeatScript(heartbeat_done("no_due_session"))
        popen = PopenFactory()

        result = self.run_watchdog(heartbeat, popen=popen)

        self.assertEqual(result["reason"], "no_runnable_keywords")
        self.assertEqual(heartbeat.modes, ["all"])
        self.assertEqual(popen.calls, [])

    def test_allowed_capture_starts_once_then_syncs(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("session_complete"),
            heartbeat_done("session_complete"),
        )
        popen = PopenFactory(FakeProcess(returncode=0))

        result = self.run_watchdog(heartbeat, popen=popen)

        runtime = self.read_runtime(result)
        self.assertEqual(len(popen.calls), 1)
        self.assertEqual(runtime["last_capture_returncode"], 0)
        self.assertEqual(result["reason"], "session_complete")
        self.assertEqual(heartbeat.modes, ["all", "all", "sync", "all"])
        args, kwargs = popen.calls[0]
        self.assertIn("visual-capture-worker", args)
        self.assertIn("--contract", args)
        self.assertTrue(os.path.isdir(kwargs.get("cwd")))

    def test_allowed_capture_starts_despite_old_paused_session_result(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed_with_old_paused_result(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("session_complete"),
            heartbeat_done("session_complete"),
        )
        popen = PopenFactory(FakeProcess(returncode=0))

        result = self.run_watchdog(heartbeat, popen=popen)

        self.assertEqual(len(popen.calls), 1)
        self.assertEqual(result["reason"], "session_complete")
        self.assertEqual(heartbeat.modes, ["all", "all", "sync", "all"])

    def test_control_pause_still_wins_even_if_dispatch_claims_capture_allowed(self):
        heartbeat = HeartbeatScript(heartbeat_allowed_but_control_paused())
        popen = PopenFactory()

        result = self.run_watchdog(heartbeat, popen=popen)

        self.assertEqual(len(popen.calls), 0)
        self.assertEqual(result["reason"], "paused")
        self.assertEqual(heartbeat.modes, ["all"])

    def test_worker_exits_recoverable_restarts_once_after_sync(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("failed_recoverable", runnable_count=1),
            heartbeat_allowed("capture_worker_stale"),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("session_complete"),
            heartbeat_done("session_complete"),
        )
        popen = PopenFactory(FakeProcess(returncode=1), FakeProcess(returncode=0))

        result = self.run_watchdog(heartbeat, popen=popen, max_restarts=2)

        runtime = self.read_runtime(result)
        self.assertEqual(len(popen.calls), 2)
        self.assertEqual(result["restart_count"], 1)
        self.assertEqual(runtime["last_capture_returncode"], 0)
        self.assertEqual(result["reason"], "session_complete")
        self.assertEqual(heartbeat.modes, ["all", "all", "sync", "all", "all", "sync", "all"])

    def test_worker_active_does_not_start_duplicate(self):
        heartbeat = HeartbeatScript(
            heartbeat_blocked("capture_worker_active"),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_blocked("capture_worker_active"),
        )
        popen = PopenFactory()

        result = self.run_watchdog(heartbeat, popen=popen, poll_seconds=10, idle_timeout_seconds=20)

        self.assertEqual(result["reason"], "idle_timeout")
        self.assertEqual(popen.calls, [])

    def test_started_worker_is_polled_without_duplicate_start_until_exit(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("session_complete"),
            heartbeat_done("session_complete"),
        )
        popen = PopenFactory(FakeProcess(returncode=0, polls=[None, None, 0]))

        result = self.run_watchdog(heartbeat, popen=popen, poll_seconds=2)

        runtime = self.read_runtime(result)
        self.assertEqual(len(popen.calls), 1)
        self.assertEqual(runtime["last_capture_returncode"], 0)
        self.assertEqual(heartbeat.modes, ["all", "all", "all", "sync", "all"])

    def test_session_success_or_no_runnable_exits(self):
        for reason in ("session_complete", "no_runnable_keywords"):
            with self.subTest(reason=reason):
                heartbeat = HeartbeatScript(heartbeat_done(reason))
                popen = PopenFactory()

                result = self.run_watchdog(heartbeat, popen=popen)

                self.assertEqual(result["reason"], reason)
                self.assertEqual(popen.calls, [])

    def test_human_or_platform_terminal_reasons_do_not_restart(self):
        terminal_reasons = [
            "paused_needs_human",
            "login_required",
            "captcha_required",
            "risk_suspected",
            "real_not_available",
            "automation_permission_blocked",
        ]
        for reason in terminal_reasons:
            with self.subTest(reason=reason):
                heartbeat = HeartbeatScript(heartbeat_blocked(reason, action="paused"))
                popen = PopenFactory()

                result = self.run_watchdog(heartbeat, popen=popen)

                self.assertEqual(result["reason"], reason)
                self.assertEqual(popen.calls, [])

    def test_control_stop_pause_cooldown_lock_exit_without_start(self):
        for reason in ("stopped", "paused", "cooling_down", "locked", "stop_or_locked"):
            with self.subTest(reason=reason):
                heartbeat = HeartbeatScript(heartbeat_blocked(reason, action="paused"))
                popen = PopenFactory()

                result = self.run_watchdog(heartbeat, popen=popen)

                self.assertEqual(result["reason"], reason)
                self.assertEqual(popen.calls, [])

    def test_max_restarts_reached_exits_with_clear_reason(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("failed_recoverable", runnable_count=1),
            heartbeat_allowed("capture_worker_stale"),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("failed_recoverable", runnable_count=1),
            heartbeat_allowed("capture_worker_stale"),
        )
        popen = PopenFactory(FakeProcess(returncode=1), FakeProcess(returncode=1))

        result = self.run_watchdog(heartbeat, popen=popen, max_restarts=1)

        self.assertEqual(len(popen.calls), 2)
        self.assertEqual(result["restart_count"], 1)
        self.assertIn(result["status"], {"needs_review", "paused_needs_supervisor", "finished"})
        self.assertEqual(result["reason"], "max_restarts_reached")

    def test_idle_timeout_exits_with_clear_reason(self):
        clock = FakeClock()
        heartbeat = HeartbeatScript(
            heartbeat_blocked("waiting_for_progress"),
            heartbeat_blocked("waiting_for_progress"),
            heartbeat_blocked("waiting_for_progress"),
            heartbeat_blocked("waiting_for_progress"),
            heartbeat_blocked("waiting_for_progress"),
        )
        popen = PopenFactory()

        result = self.run_watchdog(
            heartbeat,
            popen=popen,
            clock=clock,
            poll_seconds=10,
            idle_timeout_seconds=20,
        )

        self.assertEqual(result["reason"], "idle_timeout")
        self.assertIn(result["status"], {"needs_review", "paused_needs_supervisor", "finished"})
        self.assertEqual(popen.calls, [])
        self.assertGreaterEqual(clock.value, datetime(2026, 5, 16, 9, 17, 0))

    def test_can_patch_default_scheduler_and_popen_dependencies(self):
        heartbeat = HeartbeatScript(
            heartbeat_allowed(),
            heartbeat_blocked("capture_worker_active"),
            heartbeat_sync("session_complete"),
            heartbeat_done("session_complete"),
        )

        with mock.patch.object(
            visual_capture_watchdog.visual_scheduler,
            "heartbeat_daily_collection",
            side_effect=heartbeat,
        ) as scheduler_heartbeat, mock.patch.object(
            visual_capture_watchdog.subprocess,
            "Popen",
            side_effect=PopenFactory(FakeProcess(returncode=0)),
        ) as popen:
            tempdir = tempfile.TemporaryDirectory()
            self.addCleanup(tempdir.cleanup)
            result = visual_capture_watchdog.run_capture_watchdog(
                plan_id="daily_20260516",
                session_index=1,
                start=True,
                poll_seconds=1,
                idle_timeout_seconds=60,
                max_restarts=2,
                sleep_fn=lambda _seconds: None,
                now_fn=FakeClock().now,
                project_root=tempdir.name,
            )

        self.assertEqual(len(popen.call_args_list), 1)
        self.assertEqual(scheduler_heartbeat.call_count, 4)

    def test_existing_watchdog_lock_blocks_without_starting_worker(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        paths = visual_capture_watchdog._watchdog_paths(tempdir.name, "daily_20260516", 1)
        os.makedirs(paths["session_dir"], exist_ok=True)
        with open(paths["lock_path"], "w", encoding="utf-8") as f:
            json.dump({"pid": 99999, "plan_id": "daily_20260516", "session_index": 1}, f)
        heartbeat = HeartbeatScript(heartbeat_allowed())
        popen = PopenFactory()

        result = self.run_watchdog(
            heartbeat,
            popen=popen,
            project_root=tempdir.name,
            pid_exists_fn=lambda pid: True,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "capture_watchdog_already_running")
        self.assertEqual(heartbeat.calls, [])
        self.assertEqual(popen.calls, [])
        self.assertTrue(os.path.exists(paths["lock_path"]))

    def test_stale_watchdog_lock_is_reclaimed(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        paths = visual_capture_watchdog._watchdog_paths(tempdir.name, "daily_20260516", 1)
        os.makedirs(paths["session_dir"], exist_ok=True)
        with open(paths["lock_path"], "w", encoding="utf-8") as f:
            json.dump({"pid": 99999, "plan_id": "daily_20260516", "session_index": 1}, f)
        heartbeat = HeartbeatScript(heartbeat_done("no_runnable_keywords"))
        popen = PopenFactory()

        result = self.run_watchdog(
            heartbeat,
            popen=popen,
            project_root=tempdir.name,
            pid_exists_fn=lambda pid: False,
        )

        self.assertEqual(result["reason"], "no_runnable_keywords")
        self.assertEqual(heartbeat.modes, ["all"])
        self.assertEqual(popen.calls, [])
        self.assertFalse(os.path.exists(paths["lock_path"]))


if __name__ == "__main__":
    unittest.main()
