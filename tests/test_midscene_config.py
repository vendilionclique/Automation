import configparser
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from modules.midscene_computer_driver import (
    build_midscene_session_worker_instructions,
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

    def test_glm_5v_turbo_env_example_points_to_local_secret_env(self):
        text = (ROOT / "local" / "midscene-computer.env.example").read_text(encoding="utf-8")

        self.assertIn('MIDSCENE_MODEL_NAME="glm-5v-turbo"', text)
        self.assertIn('MIDSCENE_MODEL_BASE_URL="https://api.z.ai/api/paas/v4"', text)
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
        self.assertIn('"allow_bookmark_home_entry_repair"', text)

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
model_name = glm-5v-turbo
model_family = glm-v
base_url = https://api.z.ai/api/paas/v4
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
        self.assertEqual(payload["config"]["model_name"], "glm-5v-turbo")
        self.assertFalse(payload["config"]["reasoning_enabled"])
        self.assertEqual(payload["config"]["temperature"], 0.0)
        self.assertTrue(payload["model_boundary"]["midscene_vlm_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_name"], "glm-5v-turbo")
        self.assertEqual(payload["model_boundary"]["midscene_model_family"], "glm-v")
        self.assertEqual(
            payload["model_boundary"]["midscene_model_base_url"],
            "https://api.z.ai/api/paas/v4",
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

    def test_session_worker_contract_uses_glm_5v_turbo_mainline(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer

[MIDSCENE_COMPUTER]
page_load_wait = 2

[MIDSCENE_MODEL]
enabled = true
model_name = glm-5v-turbo
model_family = glm-v
base_url = https://api.z.ai/api/paas/v4
api_key_env = MIDSCENE_MODEL_API_KEY
reasoning_enabled = false
temperature = 0
allow_midscene_act = true
allow_midscene_query = false
final_extraction_owner = codex
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

        self.assertEqual(config.model_name, "glm-5v-turbo")
        self.assertEqual(payload["config"]["model_name"], "glm-5v-turbo")
        self.assertEqual(payload["config"]["model_family"], "glm-v")
        self.assertEqual(payload["config"]["model_base_url"], "https://api.z.ai/api/paas/v4")
        self.assertEqual(payload["config"]["model_api_key_env"], "MIDSCENE_MODEL_API_KEY")
        self.assertFalse(payload["config"]["reasoning_enabled"])
        self.assertEqual(payload["config"]["temperature"], 0.0)
        self.assertTrue(payload["model_boundary"]["midscene_vlm_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_name"], "glm-5v-turbo")
        self.assertEqual(payload["model_boundary"]["midscene_model_family"], "glm-v")
        self.assertEqual(
            payload["model_boundary"]["midscene_model_base_url"],
            "https://api.z.ai/api/paas/v4",
        )
        self.assertEqual(payload["model_boundary"]["midscene_api_key_env"], "MIDSCENE_MODEL_API_KEY")
        self.assertFalse(payload["model_boundary"]["midscene_model_reasoning_enabled"])
        self.assertEqual(payload["model_boundary"]["midscene_model_temperature"], 0.0)
        self.assertTrue(payload["model_boundary"]["allow_midscene_act"])
        self.assertFalse(payload["model_boundary"]["allow_midscene_query"])
        self.assertEqual(payload["model_boundary"]["final_extraction_owner"], "codex")
        self.assertIn("visual_behavior", payload)
        self.assertEqual(payload["entry_context"], "taobao_homepage_visible_search_entry_required")
        self.assertEqual(
            payload["navigation_instruction"],
            "visual_homepage_entry_only_no_address_bar_url_or_script",
        )
        self.assertNotIn("new browser tab", payload["action_boundary"]["forbidden_navigation"])
        self.assertEqual(
            payload["action_boundary"]["new_tab_policy"],
            "bookmark_home_entry_repair_only",
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

    def test_session_worker_instructions_allow_only_bounded_foreground_recovery(self):
        payload = {
            "run_id": "run",
            "session_index": 1,
            "task_dir": "/tmp/task",
            "session_result_path": "/tmp/task/session_worker_result.json",
            "operational_states": ["visible_results", "unknown"],
            "hard_stop_states": ["unknown"],
            "hard_stop_policy": {
                "stop_after_consecutive_abnormal": 1,
                "timeout_per_keyword_seconds": 30,
                "foreground_recovery_attempts_per_event": 3,
                "foreground_recovery_events_per_keyword": 2,
            },
            "page_sampling": {
                "max_tiles_per_keyword": 2,
                "calibration": {"tile_scroll_distance_px": 500},
                "tile_summary_command": "python harness.py visual-log-tile ...",
            },
            "keyword_tasks": [
                {"index": 1, "keyword": "万智牌 中止", "evidence_dir": "/tmp/evidence"}
            ],
        }

        text = build_midscene_session_worker_instructions(payload)

        self.assertIn("chrome_not_foreground", text)
        self.assertIn("bounded visual", text)
        self.assertIn("foreground recovery", text)
        self.assertIn("OS-level app-switching shortcuts", text)
        self.assertIn("must not type", text)
        self.assertIn("3", text)
        self.assertIn("2", text)
        self.assertIn("force-activate", text)
        self.assertIn("type a URL", text)
        self.assertIn("navigate to\n  Taobao home", text)
        self.assertIn("search/research the keyword", text)
        self.assertIn("Per-keyword homepage entry rule", text)
        self.assertIn("visible Taobao homepage", text)
        self.assertIn("homepage search\n  box", text)
        self.assertIn("bounded visual `act`", text)
        self.assertIn("browser address bar", text)
        self.assertIn("new tab", text)
        self.assertIn("scripted force-activation", text)
        self.assertIn("short-action tools", text)
        for tool in ("`Tap`", "`Input`", "`KeyboardPress`", "`Scroll`", "`ClearInput`"):
            self.assertIn(tool, text)
        self.assertIn("`tile_00` as the hard\n  acceptance boundary", text)
        self.assertIn("before any scrolling", text)
        self.assertIn("current keyword", text)
        self.assertIn("Never treat a reset homepage first viewport as a captured\n  keyword result", text)
        self.assertNotIn("existing visible Taobao search box", text)
        self.assertNotIn("Cmd-Tab", text)
        self.assertNotIn("Alt-Tab", text)
        self.assertNotIn("start_taobao_visual_chrome", text)
        self.assertNotIn("platform launcher", text)

    def test_session_worker_instructions_preserve_bookmark_home_entry_tab_safety(self):
        payload = {
            "run_id": "run",
            "session_index": 1,
            "task_dir": "/tmp/task",
            "session_result_path": "/tmp/task/session_worker_result.json",
            "operational_states": ["visible_results", "unknown"],
            "hard_stop_states": ["unknown"],
            "hard_stop_policy": {
                "stop_after_consecutive_abnormal": 1,
                "timeout_per_keyword_seconds": 30,
                "foreground_recovery_attempts_per_event": 3,
                "foreground_recovery_events_per_keyword": 2,
                "allow_bookmark_home_entry_repair": True,
            },
            "action_boundary": {
                "limited_navigation_repair": (
                    "visible new tab plus visible Taobao bookmark only; close obsolete tabs "
                    "only when more than one Chrome tab remains"
                ),
                "tab_safety": "never close the final remaining Chrome tab",
            },
            "page_sampling": {
                "max_tiles_per_keyword": 2,
                "calibration": {"tile_scroll_distance_px": 500},
                "tile_summary_command": "python harness.py visual-log-tile ...",
            },
            "keyword_tasks": [
                {"index": 1, "keyword": "万智牌 中止", "evidence_dir": "/tmp/evidence"}
            ],
        }

        text = build_midscene_session_worker_instructions(payload)

        self.assertIn("allow_bookmark_home_entry_repair", text)
        self.assertIn("old results page or bottom-of-results page", text)
        self.assertIn("visible browser new tab plus button", text)
        self.assertIn("visible Taobao\n  bookmark button", text)
        self.assertIn("only\n  allowed new-tab repair path", text)
        self.assertIn("Taobao bookmark is not visibly available", text)
        self.assertIn("obsolete old-results tabs may be closed only\n  if", text)
        self.assertIn("more than one Chrome tab remains", text)
        self.assertIn("Never close\n  the final remaining Chrome tab", text)
        self.assertIn("if tab count is unclear, leave the tab open", text)
        self.assertIn("Do not use the browser address bar", text)
        self.assertIn("do not type or paste a URL", text)
        self.assertIn("short-action tools", text)

    def test_session_worker_contract_carries_foreground_recovery_defaults(self):
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

        self.assertTrue(payload["config"]["foreground_recovery_enabled"])
        self.assertEqual(payload["config"]["foreground_recovery_attempts_per_event"], 3)
        self.assertEqual(payload["config"]["foreground_recovery_events_per_keyword"], 2)
        self.assertTrue(payload["config"]["allow_bookmark_home_entry_repair"])
        self.assertTrue(payload["hard_stop_policy"]["foreground_recovery_enabled"])
        self.assertEqual(payload["hard_stop_policy"]["foreground_recovery_attempts_per_event"], 3)
        self.assertEqual(payload["hard_stop_policy"]["foreground_recovery_events_per_keyword"], 2)
        self.assertTrue(payload["hard_stop_policy"]["allow_bookmark_home_entry_repair"])
        self.assertNotIn("start_url", payload)
        self.assertEqual(payload["entry_context"], "taobao_homepage_visible_search_entry_required")
        self.assertEqual(
            payload["navigation_instruction"],
            "visual_homepage_entry_only_no_address_bar_url_or_script",
        )
        self.assertNotIn("existing_visible_taobao_search_box", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("taobao_home_visible_search_box", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("metadata_only_not_authorized_for_recovery", json.dumps(payload, ensure_ascii=False))
        task_plan = payload["keyword_tasks"][0]["capture_plan"]
        self.assertNotIn("start_url", task_plan)
        self.assertNotIn("entry_mode", task_plan)
        self.assertEqual(task_plan["entry_context"], "taobao_homepage_visible_search_entry_required")
        self.assertEqual(
            task_plan["navigation_instruction"],
            "visual_homepage_entry_only_no_address_bar_url_or_script",
        )

    def test_session_worker_contract_can_enable_bookmark_home_entry_repair(self):
        parser = configparser.ConfigParser()
        parser.read_string(
            """
[VISUAL_CAPTURE]
provider = midscene_computer

[MIDSCENE_COMPUTER]
allow_bookmark_home_entry_repair = true
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

        self.assertTrue(payload["config"]["allow_bookmark_home_entry_repair"])
        self.assertTrue(payload["hard_stop_policy"]["allow_bookmark_home_entry_repair"])
        self.assertEqual(
            payload["navigation_instruction"],
            "visual_homepage_entry_only_no_address_bar_url_or_script",
        )
        self.assertEqual(
            payload["keyword_tasks"][0]["capture_plan"]["navigation_instruction"],
            "visual_homepage_entry_only_no_address_bar_url_or_script",
        )
        self.assertNotIn("new browser tab", payload["action_boundary"]["forbidden_navigation"])
        self.assertEqual(
            payload["action_boundary"]["limited_navigation_repair"],
            "visible new tab plus visible Taobao bookmark only; close obsolete tabs only when more than one Chrome tab remains",
        )
        self.assertEqual(
            payload["action_boundary"]["new_tab_policy"],
            "bookmark_home_entry_repair_only",
        )
        self.assertEqual(
            payload["action_boundary"]["tab_safety"],
            "never close the final remaining Chrome tab",
        )

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
