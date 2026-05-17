import os
import tempfile
import unittest
from unittest import mock

from modules import visual_scheduler


class VisualSchedulerCaptureOnlyTests(unittest.TestCase):
    def _dispatch_with_config(self, config_text):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = os.path.join(tmp, "data", "tasks", "plan", "sessions", "session_01")
            os.makedirs(session_dir, exist_ok=True)
            contract_path = os.path.join(session_dir, "midscene_session_worker_request.json")
            with open(contract_path, "w", encoding="utf-8") as f:
                f.write("{}")
            config_path = os.path.join(tmp, "settings.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_text)

            with mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(
                    visual_scheduler,
                    "capture_worker_liveness",
                    return_value={
                        "active": False,
                        "session_result_success": False,
                        "session_result_exists": False,
                    },
                ), \
                mock.patch.object(
                    visual_scheduler,
                    "_session_manifest_recovery_state",
                    return_value={"runnable_count": 1},
                ):
                return visual_scheduler._dispatch_advice("plan", 1, config_file=config_path)

    def test_dispatch_defaults_to_capture_only_without_extract_advice_config(self):
        result = self._dispatch_with_config("[SCHEDULER]\n")

        self.assertFalse(result["codex_extract_advice_enabled"])
        self.assertIn("capture", result["worker_commands"])
        self.assertNotIn("codex_extract_prepare", result["worker_commands"])
        self.assertNotIn("codex_extract_dispatch_advice", result["worker_commands"])
        self.assertNotIn("codex_extract_dispatch_start", result["worker_commands"])

    def test_dispatch_includes_extract_advice_when_enabled(self):
        result = self._dispatch_with_config("[CODEX_EXTRACT]\nadvice_enabled = true\n")

        self.assertTrue(result["codex_extract_advice_enabled"])
        self.assertIn("capture", result["worker_commands"])
        self.assertIn("codex_extract_prepare", result["worker_commands"])
        self.assertIn("codex_extract_dispatch_advice", result["worker_commands"])
        self.assertIn("codex_extract_dispatch_start", result["worker_commands"])


if __name__ == "__main__":
    unittest.main()
