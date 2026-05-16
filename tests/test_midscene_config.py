import configparser
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from modules.midscene_computer_driver import (
    midscene_computer_config_from_settings,
    write_midscene_session_worker_contract,
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

    def test_glm_flashx_env_example_points_to_local_secret_env(self):
        text = (ROOT / "local" / "midscene-computer.env.example").read_text(encoding="utf-8")

        self.assertIn('MIDSCENE_MODEL_NAME="glm-4.6v-flashx"', text)
        self.assertIn('MIDSCENE_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"', text)
        self.assertIn('MIDSCENE_MODEL_FAMILY="glm-v"', text)
        self.assertIn('MIDSCENE_MODEL_REASONING_ENABLED="false"', text)
        self.assertIn('MIDSCENE_MODEL_TEMPERATURE="0"', text)
        self.assertIn('MIDSCENE_MODEL_API_KEY=""', text)
        self.assertNotIn("ZHIPU_API_KEY", text)

    def test_setup_warning_still_points_to_local_midscene_env(self):
        text = (ROOT / "harness.py").read_text(encoding="utf-8")

        self.assertIn("local/midscene-computer.env.example", text)
        self.assertIn("midscene-computer.env", text)
        self.assertIn("复制 local/midscene-computer.env.example", text)

    def test_sync_scripts_preapprove_only_bounded_act_mainline_tools(self):
        allowed = {
            "ListDisplays",
            "computer_connect",
            "computer_disconnect",
            "computer_list_displays",
            "take_screenshot",
            "act",
            "assert",
        }
        legacy_short_actions = {
            "Tap",
            "DoubleClick",
            "RightClick",
            "MouseMove",
            "Input",
            "Scroll",
            "KeyboardPress",
            "DragAndDrop",
            "ClearInput",
        }

        shell_text = (ROOT / "scripts" / "sync_agent_project_config.sh").read_text(encoding="utf-8")
        ps_text = (ROOT / "scripts" / "sync_agent_project_config.ps1").read_text(encoding="utf-8")

        self.assertNotIn("default_tools_approval_mode", shell_text)
        self.assertNotIn("default_tools_approval_mode", ps_text)
        for tool in allowed:
            self.assertIn(f'"{tool}"', shell_text)
            self.assertIn(f'"{tool}"', ps_text)
        for tool in legacy_short_actions:
            self.assertNotIn(f'"{tool}"', shell_text)
            self.assertNotIn(f'"{tool}"', ps_text)

    def test_session_worker_contract_carries_behavior_and_model_config(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer

[MIDSCENE_COMPUTER]
page_load_wait = 2
keyword_timeout_seconds = 180
mcp_request_timeout_seconds = 180

[MIDSCENE_MODEL]
enabled = true
model_name = glm-4.6v-flashx
model_family = glm-v
base_url = https://open.bigmodel.cn/api/paas/v4
api_key_env = MIDSCENE_MODEL_API_KEY
reasoning_enabled = false
temperature = 0

[VISUAL_BEHAVIOR]
micro_pause_short = 0.2,0.8,0.90
micro_pause_medium = 0.8,1.5,0.08
micro_pause_long = 1.5,2.5,0.02
inter_keyword_pause_min = 8
inter_keyword_pause_max = 18
"""
        )
        config = midscene_computer_config_from_settings(parser)

        with tempfile.TemporaryDirectory() as tmp:
            contract = write_midscene_session_worker_contract(
                run_id="run",
                session_index=1,
                task_dir=tmp,
                session_dir=os.path.join(tmp, "sessions", "session_01"),
                records=[{"keyword": "万智牌 中止", "status": "pending"}],
                config=config,
            )
            with open(contract["contract"], "r", encoding="utf-8") as f:
                payload = json.load(f)

        self.assertEqual(payload["config"]["page_load_wait"], 2.0)
        self.assertEqual(payload["config"]["model_name"], "glm-4.6v-flashx")
        self.assertFalse(payload["config"]["reasoning_enabled"])
        self.assertEqual(payload["config"]["temperature"], 0.0)
        self.assertTrue(payload["model_boundary"]["midscene_vlm_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_name"], "glm-4.6v-flashx")
        self.assertEqual(payload["model_boundary"]["midscene_model_family"], "glm-v")
        self.assertEqual(
            payload["model_boundary"]["midscene_model_base_url"],
            "https://open.bigmodel.cn/api/paas/v4",
        )
        self.assertEqual(payload["model_boundary"]["midscene_api_key_env"], "MIDSCENE_MODEL_API_KEY")
        self.assertFalse(payload["model_boundary"]["midscene_model_reasoning_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_temperature"], 0.0)
        self.assertEqual(payload["hard_stop_policy"]["mcp_request_timeout_seconds"], 180)
        self.assertEqual(payload["visual_behavior"]["inter_keyword_pause_seconds"], [8.0, 18.0])
        self.assertEqual(
            payload["visual_behavior"]["micro_pause_distribution"]["short"],
            "0.2,0.8,0.90",
        )

    def test_session_worker_contract_does_not_emit_legacy_per_keyword_request_fields(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer

[MIDSCENE_COMPUTER]
page_load_wait = 2
"""
        )
        config = midscene_computer_config_from_settings(parser)

        with tempfile.TemporaryDirectory() as tmp:
            contract = write_midscene_session_worker_contract(
                run_id="run",
                session_index=1,
                task_dir=tmp,
                session_dir=os.path.join(tmp, "sessions", "session_01"),
                records=[{"keyword": "万智牌 中止", "status": "pending"}],
                config=config,
            )
            with open(contract["contract"], "r", encoding="utf-8") as f:
                payload = json.load(f)

        task = payload["keyword_tasks"][0]
        self.assertNotIn("midscene_computer_request", task)
        self.assertNotIn("expected_screenshot", task)

    def test_default_inter_keyword_pause_is_minute_level(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer

[MIDSCENE_COMPUTER]
page_load_wait = 2
"""
        )
        config = midscene_computer_config_from_settings(parser)

        self.assertEqual(config.inter_keyword_pause_min, 180.0)
        self.assertEqual(config.inter_keyword_pause_max, 420.0)


if __name__ == "__main__":
    unittest.main()
