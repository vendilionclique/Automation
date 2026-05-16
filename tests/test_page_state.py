import os
import tempfile
import unittest

from PIL import Image, ImageDraw

from modules.page_state import UNKNOWN, VISIBLE_READY, WHITE_SKELETON, detect_page_state


REAL_RESULT_SCREENSHOT = (
    os.path.expanduser(
        "~/workspace/automation/data/tasks/supervisor_20260516_10kw_session/"
        "evidence/万智牌_卓尼斯的寇卓将军/20260516_193707_万智牌 卓尼斯的寇卓将军.png"
    )
)


class PageStateTests(unittest.TestCase):
    def test_real_taobao_result_page_with_footer_is_visible_ready(self):
        if not os.path.exists(REAL_RESULT_SCREENSHOT):
            self.skipTest("real Taobao screenshot fixture is not available on this machine")

        state = detect_page_state(REAL_RESULT_SCREENSHOT)

        self.assertEqual(state.status, VISIBLE_READY)
        self.assertEqual(state.reason, "detected_distributed_price_text_in_listing_region")
        self.assertGreater(state.metrics["listing_orange_bucket_count"], 4)

    def test_distributed_listing_band_survives_large_white_footer(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            img = Image.new("RGB", (1200, 900), "white")
            draw = ImageDraw.Draw(img)
            for index in range(6):
                x = 60 + index * 180
                draw.rectangle((x, 220, x + 140, 330), fill=(120, 90, 70))
                draw.rectangle((x, 350, x + 150, 366), fill=(35, 35, 35))
                draw.rectangle((x, 375, x + 70, 392), fill=(245, 75, 20))
                draw.rectangle((x, 404, x + 120, 418), fill=(80, 80, 80))
            draw.rectangle((0, 520, 1200, 900), fill="white")
            img.save(f.name)

            state = detect_page_state(f.name)

        self.assertEqual(state.status, VISIBLE_READY)
        self.assertEqual(state.reason, "detected_distributed_price_text_in_listing_region")

    def test_single_center_button_does_not_count_as_result_grid(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            img = Image.new("RGB", (1200, 900), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle((460, 260, 740, 340), fill=(245, 75, 20))
            draw.rectangle((500, 380, 700, 408), fill=(35, 35, 35))
            img.save(f.name)

            state = detect_page_state(f.name)

        self.assertEqual(state.status, UNKNOWN)

    def test_white_skeleton_stays_conservative(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            img = Image.new("RGB", (1200, 900), "white")
            draw = ImageDraw.Draw(img)
            for index in range(4):
                x = 80 + index * 260
                draw.rectangle((x, 250, x + 180, 360), fill=(218, 218, 218))
                draw.rectangle((x, 385, x + 160, 405), fill=(205, 205, 205))
                draw.rectangle((x, 425, x + 120, 445), fill=(225, 225, 225))
            img.save(f.name)

            state = detect_page_state(f.name)

        self.assertEqual(state.status, WHITE_SKELETON)


if __name__ == "__main__":
    unittest.main()
