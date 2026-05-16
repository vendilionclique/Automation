import os
import tempfile
import unittest
from unittest.mock import patch

from modules.visual_pipeline import load_visual_manifest, save_visual_manifest


class VisualPipelineManifestTests(unittest.TestCase):
    def test_save_visual_manifest_atomic_roundtrips_without_tmp_leftover(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = {
                "run_id": "atomic_manifest_test",
                "records": [{"keyword": "万智牌 测试", "status": "pending"}],
            }
            with patch("modules.visual_pipeline.get_project_root", return_value=root):
                path = save_visual_manifest("atomic_manifest_test", manifest)
                loaded = load_visual_manifest("atomic_manifest_test")

            self.assertEqual(loaded, manifest)
            self.assertTrue(os.path.exists(path))
            task_dir = os.path.dirname(path)
            leftovers = [name for name in os.listdir(task_dir) if name.endswith(".tmp")]
            self.assertEqual(leftovers, [])

    def test_load_visual_manifest_reports_path_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as root:
            task_dir = os.path.join(root, "data", "tasks", "broken_manifest_test")
            os.makedirs(task_dir)
            path = os.path.join(task_dir, "visual_tasks.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"records": [')

            with patch("modules.visual_pipeline.get_project_root", return_value=root):
                with self.assertRaises(ValueError) as raised:
                    load_visual_manifest("broken_manifest_test")

            self.assertIn(path, str(raised.exception))
            self.assertIn("读取视觉任务清单 JSON 失败", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
