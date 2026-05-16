import unittest
from unittest import mock

from modules import visual_automation_tick


class VisualAutomationTickTests(unittest.TestCase):
    def test_allowed_starts_capture_watchdog(self):
        all_result = {
            "action": "dispatch_advised",
            "plan_id": "daily_20260516",
            "session_index": 2,
            "dispatch": {
                "capture_start_allowed": True,
                "worker_commands": {
                    "capture": "python3 harness.py visual-capture-worker --contract 'data/tasks/demo/session contract.json'"
                },
            },
        }
        watchdog_result = {
            "ok": True,
            "action": "capture_watchdog",
            "plan_id": "daily_20260516",
            "session_index": 2,
            "status": "finished",
            "reason": "session_complete",
            "last_capture_returncode": 0,
            "last_heartbeat": {"action": "noop", "reason": "session_complete"},
        }

        with mock.patch.object(
            visual_automation_tick.visual_scheduler,
            "heartbeat_daily_collection",
            return_value=all_result,
        ) as heartbeat, mock.patch.object(
            visual_automation_tick,
            "run_capture_watchdog",
            return_value=watchdog_result,
        ) as watchdog:
            result = visual_automation_tick.run_visual_automation_tick(
                plan_id="daily_20260516",
                session_index=2,
                start_capture=True,
            )

        self.assertTrue(result["capture_start_allowed"])
        self.assertTrue(result["capture_started"])
        self.assertEqual(result["capture_returncode"], 0)
        self.assertEqual(result["watchdog_result"], watchdog_result)
        self.assertEqual(result["sync_result"], watchdog_result["last_heartbeat"])
        self.assertEqual(result["sync_reason"], "session_complete")
        watchdog.assert_called_once_with(
            plan_id="daily_20260516",
            session_index=2,
            start=True,
            config_file="config/settings.ini",
        )
        self.assertEqual(heartbeat.call_count, 1)
        self.assertEqual(heartbeat.call_args_list[0].kwargs["mode"], "all")

    def test_not_allowed_does_not_start_or_sync(self):
        all_result = {
            "action": "dispatch_advised",
            "plan_id": "daily_20260516",
            "session_index": 1,
            "dispatch": {
                "capture_start_allowed": False,
                "reason": "capture_worker_active",
                "worker_commands": {
                    "capture": "python3 harness.py visual-capture-worker --contract contract.json"
                },
            },
        }

        with mock.patch.object(
            visual_automation_tick.visual_scheduler,
            "heartbeat_daily_collection",
            return_value=all_result,
        ) as heartbeat, mock.patch.object(
            visual_automation_tick,
            "run_capture_watchdog",
        ) as watchdog:
            result = visual_automation_tick.run_visual_automation_tick(start_capture=True)

        self.assertFalse(result["capture_start_allowed"])
        self.assertFalse(result["capture_started"])
        self.assertIsNone(result["capture_returncode"])
        self.assertIsNone(result["sync_result"])
        self.assertEqual(result["sync_reason"], "capture_worker_active")
        watchdog.assert_not_called()
        heartbeat.assert_called_once()

    def test_missing_capture_command_does_not_start_or_sync(self):
        all_result = {
            "action": "dispatch_advised",
            "plan_id": "daily_20260516",
            "session_index": 1,
            "dispatch": {
                "capture_start_allowed": True,
                "worker_commands": {},
            },
        }

        with mock.patch.object(
            visual_automation_tick.visual_scheduler,
            "heartbeat_daily_collection",
            return_value=all_result,
        ) as heartbeat, mock.patch.object(
            visual_automation_tick,
            "run_capture_watchdog",
        ) as watchdog:
            result = visual_automation_tick.run_visual_automation_tick(start_capture=True)

        self.assertTrue(result["capture_start_allowed"])
        self.assertFalse(result["capture_command_exists"])
        self.assertFalse(result["capture_started"])
        self.assertIsNone(result["sync_result"])
        self.assertEqual(result["sync_reason"], "capture_command_missing")
        watchdog.assert_not_called()
        heartbeat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
