import configparser
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from modules.midscene_computer_driver import (
    midscene_computer_config_from_settings,
    write_midscene_computer_request,
)


ROOT = Path(__file__).resolve().parents[1]


class MidsceneConfigTests(unittest.TestCase):
    def test_tracked_examples_do_not_contain_personal_absolute_paths(self):
        personal_path = re.compile(r"/Users/[^/\"'\s]+|/home/[^/\"'\s]+|[A-Za-z]:\\Users\\[^\\\"'\s]+")
        checked = [
            ROOT / "config" / "settings.example.ini",
            ROOT / "local" / "midscene-computer.env.example",
        ]

        for path in checked:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(personal_path.search(text), f"personal absolute path leaked in {path}")

    def test_glm_flash_env_example_points_to_local_secret_env(self):
        text = (ROOT / "local" / "midscene-computer.env.example").read_text(encoding="utf-8")

        self.assertIn('MIDSCENE_MODEL_NAME="glm-4.6v-flash"', text)
        self.assertIn('MIDSCENE_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"', text)
        self.assertIn('MIDSCENE_MODEL_FAMILY="glm-v"', text)
        self.assertIn('MIDSCENE_MODEL_API_KEY=""', text)
        self.assertNotIn("ZHIPU_API_KEY", text)

    def test_setup_warning_still_points_to_local_midscene_env(self):
        text = (ROOT / "harness.py").read_text(encoding="utf-8")

        self.assertIn("local/midscene-computer.env.example", text)
        self.assertIn("midscene-computer.env", text)
        self.assertIn("复制 local/midscene-computer.env.example", text)

    def test_midscene_glm_model_config_is_written_to_request_manifest(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer
confidence_threshold = 0.80
screenshot_retention = false

[MIDSCENE_COMPUTER]
window_width = 1600
window_height = 1000
max_scrolls_per_keyword = 2
page_load_wait = 8
session_keyword_limit = 3
keyword_timeout_seconds = 180
mcp_request_timeout_seconds = 240
consecutive_abnormal_stop = 2
min_rows_per_keyword = 5
screenshot_prefixes = initial,results,scroll_1

[MIDSCENE_MODEL]
enabled = true
model_name = glm-4.6v-flash
model_family = glm-v
base_url = https://open.bigmodel.cn/api/paas/v4
api_key_env = MIDSCENE_MODEL_API_KEY
allow_midscene_act = true
allow_midscene_query = false
final_extraction_owner = codex
"""
        )
        config = midscene_computer_config_from_settings(parser)

        with tempfile.TemporaryDirectory() as tmp:
            request = write_midscene_computer_request(
                run_id="run",
                keyword="万智牌 中止",
                evidence_dir=os.path.join(tmp, "evidence"),
                config=config,
            )
            with open(request.request_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

        self.assertEqual(payload["config"]["model_name"], "glm-4.6v-flash")
        self.assertEqual(payload["config"]["model_family"], "glm-v")
        self.assertEqual(payload["config"]["model_base_url"], "https://open.bigmodel.cn/api/paas/v4")
        self.assertEqual(payload["config"]["mcp_request_timeout_seconds"], 240)
        self.assertTrue(payload["model_boundary"]["midscene_vlm_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_name"], "glm-4.6v-flash")
        self.assertEqual(payload["model_boundary"]["midscene_model_family"], "glm-v")
        self.assertEqual(
            payload["model_boundary"]["midscene_model_base_url"],
            "https://open.bigmodel.cn/api/paas/v4",
        )
        self.assertEqual(payload["model_boundary"]["midscene_api_key_env"], "MIDSCENE_MODEL_API_KEY")
        self.assertTrue(payload["model_boundary"]["allow_midscene_act"])
        self.assertFalse(payload["model_boundary"]["allow_midscene_query"])
        self.assertEqual(payload["model_boundary"]["final_extraction_owner"], "codex")


if __name__ == "__main__":
    unittest.main()
