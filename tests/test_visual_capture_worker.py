import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

from modules import codex_extract
from modules import visual_control
from modules import visual_scheduler
from modules import visual_capture_worker as worker
from modules import visual_pipeline
from modules import page_state_classifier
from modules.page_sampling import PageSamplingConfig, estimate_tile_scroll_distance
from modules.session_capsule import RUNNABLE_STATUSES


class FakeClient:
    classifier_results = None

    def __init__(self, act_result, classifier_result=None, stderr_tail="", tool_results=None):
        self.act_result = act_result
        self.classifier_result = classifier_result
        self.stderr_tail = stderr_tail
        self.tool_results = tool_results or {}
        self.calls = []
        self.screenshot_count = 0
        self.synthetic_home_entry_ready = False
        if isinstance(classifier_result, list):
            self.classifier_results = list(classifier_result)
            FakeClient.classifier_results = list(classifier_result)
        else:
            self.classifier_results = None
            FakeClient.classifier_results = [classifier_result] if classifier_result is not None else None

    def call_tool(self, name, arguments, **kwargs):
        self.calls.append({"name": name, "arguments": arguments, "kwargs": kwargs})
        if name in self.tool_results:
            values = self.tool_results[name]
            if isinstance(values, list):
                if values:
                    return values.pop(0)
                return {"content": [{"type": "text", "text": "ok"}]}
            return values
        if name == "act":
            prompt = str((arguments or {}).get("prompt") or "")
            if (
                "Prepare the Taobao homepage/search-entry boundary" in prompt
                and isinstance(self.act_result, list)
                and self.act_result
            ):
                next_value = self.act_result[0]
                next_text = worker._tool_text(next_value) if isinstance(next_value, dict) else str(next_value or "")
                if "home_entry_prepared" not in next_text:
                    self.calls.pop()
                    self.synthetic_home_entry_ready = True
                    return {"content": [{"type": "text", "text": "home_entry_prepared=true home_entry_used=true recovered_from_old_results=false bookmark_home_entry_used=false"}]}
            if isinstance(self.act_result, list):
                if self.act_result:
                    value = self.act_result.pop(0)
                    if isinstance(value, BaseException):
                        raise value
                    return value
                return {"content": [{"type": "text", "text": "ok"}]}
            if isinstance(self.act_result, BaseException):
                raise self.act_result
            return self.act_result
        if name in {"Input", "KeyboardPress", "Tap", "Scroll"}:
            return {"content": [{"type": "text", "text": "ok"}]}
        raise AssertionError(f"unexpected tool: {name}")

    def capture_screenshot(self, path, **kwargs):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        from PIL import Image, ImageDraw

        self.screenshot_count += 1
        bg = (255, 255 - (30 * self.screenshot_count) % 180, 220)
        img = Image.new("RGB", (800, 600), bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 799, 160), fill=((70 * self.screenshot_count) % 255, 120, 200))
        for index in range(6):
            x = 40 + index * 120
            draw.rectangle((x, 180, x + 80, 240), fill=(30, 30, 30))
            draw.rectangle((x, 260, x + 80, 320), fill=(230, 90, 30))
        img.save(path)
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


def _parse_test_optional_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _normalize_test_page_state_value(value):
    text = str(value or "").strip().lower()
    allowed = {
        "chrome_not_foreground",
        "captcha_required",
        "login_required",
        "risk_suspected",
        "popup_blocked",
        "closeable_popup_overlay",
        "white_skeleton",
        "empty_result",
        "results_end",
        "visible_results",
        "search_results",
        "results_page",
        "visible_ready",
        "unknown",
    }
    return text if text in allowed else ""


def _parse_test_page_state_payload(text):
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    state = _normalize_test_page_state_value(parsed.get("state") or parsed.get("status"))
    payload = {"state": state} if state else {}
    try:
        payload["confidence"] = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        pass
    reason = str(parsed.get("reason") or "").strip()
    if reason:
        payload["reason"] = reason
    visible_keyword = str(
        parsed.get("visible_search_keyword")
        or parsed.get("observed_keyword")
        or parsed.get("search_keyword")
        or ""
    ).strip()
    if visible_keyword:
        payload["visible_search_keyword"] = visible_keyword
    if "keyword_match" in parsed:
        parsed_keyword_match = _parse_test_optional_bool(parsed.get("keyword_match"))
        if parsed_keyword_match is not None:
            payload["keyword_match"] = parsed_keyword_match
    search_box_text_kind = str(parsed.get("search_box_text_kind") or "").strip()
    if search_box_text_kind:
        payload["search_box_text_kind"] = search_box_text_kind
    if "search_submitted" in parsed:
        parsed_search_submitted = _parse_test_optional_bool(parsed.get("search_submitted"))
        if parsed_search_submitted is not None:
            payload["search_submitted"] = parsed_search_submitted
    if "is_home_feed" in parsed or "home_feed" in parsed:
        parsed_home_feed = _parse_test_optional_bool(parsed.get("is_home_feed", parsed.get("home_feed")))
        if parsed_home_feed is not None:
            payload["is_home_feed"] = parsed_home_feed
    if "result_page_evidence" in parsed:
        payload["result_page_evidence"] = parsed.get("result_page_evidence")
    if "url_or_page_evidence" in parsed:
        payload["url_or_page_evidence"] = parsed.get("url_or_page_evidence")
    return payload


def _parse_test_page_state_text(text):
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    return _normalize_test_page_state_value(parsed.get("state") or parsed.get("status"))


class VisualCaptureWorkerTests(unittest.TestCase):
    def setUp(self):
        FakeClient.classifier_results = None
        self.classifier_patch = mock.patch.object(
            worker,
            "classify_screenshot_json",
            side_effect=self._default_classifier,
        )
        self.mock_classifier = self.classifier_patch.start()

    def tearDown(self):
        self.classifier_patch.stop()
        FakeClient.classifier_results = None

    def _default_classifier(self, path, *, contract=None, keyword="", timeout_seconds=30.0):
        basename = os.path.basename(str(path or ""))
        if basename.startswith("home_entry_prepared") and getattr(self, "synthetic_home_entry_ready", False):
            self.synthetic_home_entry_ready = False
            return {
                "status": "visible_ready",
                "confidence": 0.9,
                "reason": "test_synthetic_home_entry_ready",
                "metrics": {},
                "source": "json_classifier",
                "raw_text": '{"state":"visible_ready"}',
                "visible_search_keyword": "",
                "keyword_match": None,
                "search_box_text_kind": "",
            }
        queued = FakeClient.classifier_results
        if queued is not None:
            if queued:
                item = queued.pop(0)
            else:
                item = {"content": [{"type": "text", "text": '{"state":"visible_results"}'}]}
            text = worker._tool_text(item) if isinstance(item, dict) else str(item or "")
            if "rate limit" in text.lower() or "rate_limited" in text.lower():
                raise page_state_classifier.PageStateClassifierUnavailable("classifier_rate_limited")
            payload = _parse_test_page_state_payload(text)
            state = payload.get("state")
            if state:
                if state in {"visible_results", "search_results", "results_page", "results_end"} and payload.get("keyword_match") is True:
                    payload.setdefault("search_box_text_kind", "actual_input")
                    payload.setdefault("search_submitted", True)
                    payload.setdefault("is_home_feed", False)
                    payload.setdefault("result_page_evidence", ["test_results_layout"])
                return {
                    "status": state,
                    "confidence": float(payload.get("confidence") or (0.35 if state == "unknown" else 0.9)),
                    "reason": payload.get("reason") or "test_json_classifier",
                    "metrics": {},
                    "source": "json_classifier",
                    "raw_text": text,
                    "visible_search_keyword": payload.get("visible_search_keyword") or "",
                    "keyword_match": payload.get("keyword_match"),
                    "search_box_text_kind": page_state_classifier._normalize_search_box_text_kind(
                        payload.get("search_box_text_kind")
                    ),
                    "search_submitted": payload.get("search_submitted"),
                    "is_home_feed": payload.get("is_home_feed"),
                    "result_page_evidence": page_state_classifier._normalize_text_list(
                        payload.get("result_page_evidence")
                    ),
                    "url_or_page_evidence": page_state_classifier._normalize_text_list(
                        payload.get("url_or_page_evidence")
                    ),
                }
            if text.strip().lower() not in {"true", "ok"}:
                raise page_state_classifier.PageStateClassifierUnavailable("classifier_json_unparseable")
        return {
            "status": "visible_results",
            "confidence": 0.9,
            "reason": "test_json_classifier_visible_results",
            "metrics": {},
            "source": "json_classifier",
            "raw_text": '{"state":"visible_results"}',
            "visible_search_keyword": keyword,
            "keyword_match": True if keyword else None,
            "search_box_text_kind": "actual_input" if keyword else "",
            "search_submitted": True if keyword else None,
            "is_home_feed": False if keyword else None,
            "result_page_evidence": ["test_results_layout"] if keyword else [],
        }

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

    def test_search_and_scroll_prompts_keep_search_submission_and_foreground_rules(self):
        search_prompt = worker._keyword_search_prompt("万智牌 中止", 560)
        bookmark_prompt = worker._keyword_search_home_entry_prompt(
            "万智牌 中止",
            {"config": {"allow_bookmark_home_entry_repair": True}},
        )
        scroll_prompt = worker._next_tile_prompt("万智牌 中止", 1, 560)
        reset_prompt = worker._keyword_search_reset_prompt("万智牌 中止")

        self.assertIn("search exactly this keyword", search_prompt)
        self.assertIn("'万智牌 中止'", search_prompt)
        self.assertIn("ordinary Taobao home/search-entry UI", search_prompt)
        self.assertIn("Taobao logo", search_prompt)
        self.assertIn("return-home button", search_prompt)
        self.assertIn("Do not replace text inside an old results-page search box", search_prompt)
        self.assertIn("mouse-clicking the visible search button", search_prompt)
        self.assertIn("Use Enter only as a fallback", search_prompt)
        self.assertIn("submission_method=search_button", search_prompt)
        self.assertIn("submission_method=enter_fallback", search_prompt)
        self.assertIn("Taobao search results structure", search_prompt)
        self.assertIn("Do not scroll the homepage recommendation feed", search_prompt)
        self.assertIn("Do not report success merely because the search box contains the keyword", search_prompt)
        self.assertIn("search_submit_failed", search_prompt)
        self.assertNotIn("pressing Enter or clicking", search_prompt)
        self.assertNotIn("submit once more with Enter", search_prompt)
        self.assertIn("Wait until visible search results settle", search_prompt)
        self.assertIn("chrome_not_foreground", search_prompt)
        self.assertIn("do not type, scroll, search, or navigate in that app", search_prompt)
        self.assertIn("chrome_not_foreground", scroll_prompt)
        self.assertIn("do not type, scroll, search, or navigate in that app", scroll_prompt)
        self.assertIn("login, captcha, security/risk", scroll_prompt)
        self.assertIn("closeable_popup_overlay", scroll_prompt)
        self.assertIn("popup's own upper-right corner", search_prompt)
        self.assertIn("popup/overlay gray X", reset_prompt)
        self.assertIn("next visible results viewport", scroll_prompt)
        self.assertIn("results end is visible", scroll_prompt)
        self.assertIn("pagination row", scroll_prompt)
        self.assertIn("copyright/ICP", scroll_prompt)
        self.assertIn("page count with current/total pages", scroll_prompt)
        self.assertIn("ordinary non-bottom scrolling", scroll_prompt)
        self.assertIn("keyword-boundary handling", scroll_prompt)
        self.assertNotIn("1/100", scroll_prompt)
        self.assertIn("bounded Taobao capture worker", reset_prompt)
        self.assertIn("chrome_not_foreground", reset_prompt)
        self.assertIn("do not type a URL", reset_prompt)
        self.assertIn("do not open a new browser tab", reset_prompt)
        self.assertIn("ordinary Taobao home/search-entry UI", reset_prompt)
        self.assertIn("return-home button", reset_prompt)
        self.assertIn("ordinary homepage/search-entry search box", reset_prompt)
        self.assertIn("'万智牌 中止'", reset_prompt)
        self.assertIn("mouse-clicking the visible search button", reset_prompt)
        self.assertIn("Use Enter only as a fallback", reset_prompt)
        self.assertIn("submission_method=search_button", reset_prompt)
        self.assertIn("submission_method=enter_fallback", reset_prompt)
        self.assertIn("Taobao search results structure", reset_prompt)
        self.assertIn("Do not scroll the homepage recommendation feed", reset_prompt)
        self.assertIn("search_submit_failed", reset_prompt)
        self.assertNotIn("submit with Enter or the visible search button", reset_prompt)
        self.assertIn("Do not read DOM, HTML, network", reset_prompt)
        self.assertIn("or clipboard contents", reset_prompt)
        self.assertIn("Do not use short action APIs", reset_prompt)
        self.assertIn("Tap, Input, KeyboardPress, Scroll, or ClearInput", reset_prompt)
        self.assertNotIn("Bring the existing Chrome window", search_prompt)
        self.assertNotIn("Bring the existing Chrome window", scroll_prompt)
        self.assertIn("Chrome is already foreground on a visible new tab", bookmark_prompt)
        self.assertIn("click that Taobao bookmark directly", bookmark_prompt)
        self.assertIn("do not open another new tab first", bookmark_prompt)
        self.assertNotIn("switch to Chrome first", search_prompt)
        self.assertIn("existing visible Taobao home page", search_prompt)
        self.assertNotIn("open a new browser tab", search_prompt.lower().replace("do not open a new browser tab", ""))
        self.assertNotIn("normal browser tab", reset_prompt)

        recovery_prompt = worker._foreground_recovery_prompt(
            keyword="万智牌 中止",
            stage="keyword_search",
            attempt_index=1,
        )
        self.assertIn("bounded Taobao visual capture", recovery_prompt)
        self.assertIn("OS-level app-switching shortcut", recovery_prompt)
        self.assertIn("do not search, re-search", recovery_prompt)
        self.assertIn("do not use the browser address bar", recovery_prompt)
        self.assertIn("do not type a URL", recovery_prompt)
        self.assertIn("do not open a new browser tab", recovery_prompt)
        self.assertIn("do not navigate to Taobao home", recovery_prompt)
        self.assertIn("foreground_recovery=blocked", recovery_prompt)

    def test_parse_reported_search_submission_method_requires_explicit_token(self):
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "search submitted submission_method=search_button"
            ),
            "search_button",
        )
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "search submitted submission_method: enter_fallback"
            ),
            "enter_fallback",
        )
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "search submitted submission method enter fallback"
            ),
            "enter_fallback",
        )
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "search submitted submission-method-search-button"
            ),
            "search_button",
        )
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "I did not use search_button and did not click the visible search button."
            ),
            "",
        )
        self.assertEqual(
            worker._parse_reported_search_submission_method(
                "clicked the visible search button after seeing the keyword"
            ),
            "",
        )

    def test_search_reset_retry_predicate_is_boundary_only_and_excludes_hard_blocks(self):
        self.assertTrue(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "visible_keyword_mismatch",
                    "rough_state": "keyword_mismatch",
                    "page_state": {"status": "visible_results"},
                }
            )
        )
        self.assertTrue(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "visible_keyword_unverified",
                    "rough_state": "keyword_unverified",
                    "page_state": {"status": "results_end"},
                }
            )
        )
        self.assertTrue(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "search_submit_unconfirmed",
                    "rough_state": "search_submit_unconfirmed",
                    "page_state": {"status": "visible_results"},
                }
            )
        )
        self.assertTrue(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "search_results_structure_unverified",
                    "rough_state": "search_results_structure_unverified",
                    "page_state": {"status": "results_page"},
                }
            )
        )
        self.assertFalse(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "login_required",
                    "rough_state": "login_required",
                    "page_state": {"status": "login_required"},
                }
            )
        )
        self.assertFalse(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "manual_review_needed",
                    "rough_state": "login_required",
                    "page_state": {"status": "login_required"},
                }
            )
        )
        self.assertFalse(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "manual_review_needed",
                    "rough_state": "rate_limited",
                    "page_state": {"status": "rate_limited"},
                }
            )
        )

    def test_json_classifier_prompt_describes_taobao_bottom_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, "tile_03.png")
            FakeClient({"content": [{"type": "text", "text": "unused"}]}).capture_screenshot(image_path)

            payload = page_state_classifier._request_payload(
                model="glm-4.6v-flashx",
                image_path=page_state_classifier.Path(image_path),
                keyword="万智牌 中止",
                temperature=0,
            )

        prompt = payload["messages"][0]["content"][0]["text"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("pagination", prompt)
        self.assertIn("previous/next buttons", prompt)
        self.assertIn("copyright/ICP", prompt)
        self.assertIn("literal no-more-results label is not required", prompt)
        self.assertIn("visible_search_keyword", prompt)
        self.assertIn("keyword_match", prompt)
        self.assertNotIn("1/100", prompt)

    def test_json_classifier_keyword_match_string_false_parses_false(self):
        payload = _parse_test_page_state_payload(
            '{"state":"results_end","visible_search_keyword":"万智牌 闪电击","keyword_match":"false"}'
        )

        self.assertIs(payload["keyword_match"], False)

    def test_search_and_scroll_use_bounded_act(self):
        client = FakeClient(
            [
                {"content": [{"type": "text", "text": "search submitted submission_method=search_button"}]},
                {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
            ]
        )

        search_result = worker._perform_keyword_search(
            client=client,
            contract={},
            keyword="万智牌 中止",
            scroll_distance=560,
            capture_plan={},
            tools=[],
            diagnostics={},
            foreground_recovery={"events_used": 0},
            evidence_dir=tempfile.gettempdir(),
            interrupt_check=None,
            keyword_deadline=time.monotonic() + 30,
            timeout_seconds=5,
        )
        scroll_result = worker._perform_page_scroll(
            client=client,
            contract={},
            keyword="万智牌 中止",
            tile_index=1,
            scroll_distance=560,
            capture_plan={},
            tools=[],
            diagnostics={},
            foreground_recovery={"events_used": 0},
            evidence_dir=tempfile.gettempdir(),
            interrupt_check=None,
            keyword_deadline=time.monotonic() + 30,
            timeout_seconds=5,
        )

        self.assertEqual(search_result["mode"], "bounded_act_search")
        self.assertEqual(scroll_result["mode"], "bounded_act_scroll")
        self.assertEqual([call["name"] for call in client.calls], ["act", "act"])
        self.assertIn("search exactly this keyword", client.calls[0]["arguments"]["prompt"])
        self.assertIn("'万智牌 中止'", client.calls[0]["arguments"]["prompt"])
        self.assertIn("mouse-clicking the visible search button", client.calls[0]["arguments"]["prompt"])
        self.assertIn("Use Enter only as a fallback", client.calls[0]["arguments"]["prompt"])
        self.assertIn("Wait until visible search results settle", client.calls[0]["arguments"]["prompt"])
        self.assertEqual(
            search_result["steps"]["act"]["submission_policy"]["preferred"],
            "visible_search_button_click",
        )
        self.assertEqual(search_result["steps"]["act"]["reported_submission_method"], "search_button")
        self.assertIn("next visible results viewport", client.calls[1]["arguments"]["prompt"])
        self.assertIn("about 560 px", client.calls[1]["arguments"]["prompt"])
        self.assertIn("exactly one normal page-level", client.calls[1]["arguments"]["prompt"])
        self.assertIn("Do not chain multiple wheel ticks", client.calls[1]["arguments"]["prompt"])
        self.assertIn("save the next screenshot at this intermediate position", client.calls[1]["arguments"]["prompt"])

    def test_tile_scroll_distance_is_capped_to_avoid_skipping_intermediate_viewports(self):
        calibration = estimate_tile_scroll_distance(
            screen_height=900,
            config=PageSamplingConfig(
                tile_scroll_viewport_ratio=0.80,
                calibration_top_reserved_ratio=0.20,
                calibration_bottom_reserved_ratio=0.05,
                max_tile_scroll_distance_px=320,
            ),
        )

        self.assertEqual(calibration["estimated_tile_scroll_distance_px"], 540)
        self.assertEqual(calibration["tile_scroll_distance_px"], 320)
        self.assertEqual(calibration["max_tile_scroll_distance_px"], 320)

    def test_keyword_search_act_exception_old_results_retries_home_entry_once(self):
        client = FakeClient(
            [
                RuntimeError(
                    'Failed to execute act: Task failed: 当前页面显示的是淘宝搜索结果页面，'
                    '但搜索框中显示的是"万智牌 无上猎者贾路"，这与任务要求的"万智牌 唤兽师贾路"不符。'
                    "页面已经显示搜索结果，但搜索关键词不正确，需要返回淘宝首页重新搜索正确的关键词。"
                ),
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "home_entry_used=true recovered_from_old_results=true "
                                "submission_method=search_button"
                            ),
                        }
                    ]
                },
            ]
        )
        diagnostics = {}

        result = worker._perform_keyword_search(
            client=client,
            contract={},
            keyword="万智牌 唤兽师贾路",
            scroll_distance=560,
            capture_plan={},
            tools=[],
            diagnostics=diagnostics,
            foreground_recovery={"events_used": 0},
            evidence_dir=tempfile.gettempdir(),
            interrupt_check=None,
            keyword_deadline=time.monotonic() + 30,
            timeout_seconds=5,
        )

        self.assertTrue(result["retry_from_act_exception"])
        self.assertEqual(result["mode"], "bounded_act_search")
        self.assertEqual([call["name"] for call in client.calls], ["act", "act"])
        retry_prompt = client.calls[1]["arguments"]["prompt"]
        self.assertIn("recovered_from_old_results=true", retry_prompt)
        self.assertIn("visible Taobao logo", retry_prompt)
        self.assertIn("do not open a new browser tab", retry_prompt)
        self.assertEqual(diagnostics["home_entry_act_exception_retry"]["status"], "completed")
        self.assertEqual(
            diagnostics["home_entry_act_exception_retry"]["mode"],
            "home_entry_retry_after_act_exception",
        )

    def test_keyword_search_act_exception_chrome_not_foreground_attempts_recovery_not_home_retry(self):
        client = FakeClient(
            RuntimeError("Failed to execute act: Failed to continue: chrome_not_foreground")
        )

        with self.assertRaises(RuntimeError):
            worker._perform_keyword_search(
                client=client,
                contract={},
                keyword="万智牌 唤兽师贾路",
                scroll_distance=560,
                capture_plan={},
                tools=[],
                diagnostics={},
                foreground_recovery={"events_used": 0},
                evidence_dir=tempfile.gettempdir(),
                interrupt_check=None,
                keyword_deadline=time.monotonic() + 30,
                timeout_seconds=5,
            )

        self.assertEqual([call["name"] for call in client.calls], ["act", "act"])

    def test_keyword_search_act_exception_chrome_text_retries_when_screenshot_is_results(self):
        client = FakeClient(
            [
                RuntimeError("Failed to execute act: Failed to continue: chrome_not_foreground"),
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "home_entry_used=true recovered_from_old_results=true "
                                "submission_method=search_button"
                            ),
                        }
                    ]
                },
            ],
            classifier_result={
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"state":"visible_results",'
                            '"visible_search_keyword":"万智牌 无上猎者贾路",'
                            '"keyword_match":false,'
                            '"reason":"old Taobao results page is visible"}'
                        ),
                    }
                ]
            },
        )
        diagnostics = {}

        result = worker._perform_keyword_search(
            client=client,
            contract={"page_sampling": {"allow_page_state_json_classifier": True}},
            keyword="万智牌 唤兽师贾路",
            scroll_distance=560,
            capture_plan={"allow_page_state_json_classifier": True},
            tools=[],
            diagnostics=diagnostics,
            foreground_recovery={"events_used": 0},
            evidence_dir=tempfile.gettempdir(),
            interrupt_check=None,
            keyword_deadline=time.monotonic() + 30,
            timeout_seconds=5,
        )

        self.assertTrue(result["retry_from_act_exception"])
        self.assertEqual([call["name"] for call in client.calls], ["act", "act"])
        self.assertEqual(
            diagnostics["foreground_recovery_exception_checks"][0]["page_state"]["status"],
            "visible_results",
        )
        self.assertEqual(diagnostics["home_entry_act_exception_retry"]["status"], "completed")

    def test_foreground_loss_during_search_recovers_and_verifies_current_step(self):
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
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "foreground_recovery_attempts_per_event": 3,
                    "foreground_recovery_events_per_keyword": 2,
                },
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "chrome_not_foreground: WPS is visible"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                    {"content": [{"type": "text", "text": "search submitted submission_method=search_button"}]},
                ]
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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            self.assertEqual([call["name"] for call in client.calls], ["act", "act", "act"])
            self.assertIn("do not use the browser address bar", client.calls[1]["arguments"]["prompt"])
            self.assertIn("search exactly this keyword", client.calls[2]["arguments"]["prompt"])
            attempts = payload["diagnostics"]["foreground_recovery_attempts"]
            self.assertEqual(attempts[0]["status"], "recovered")
            self.assertEqual(attempts[0]["event_index"], 1)

    def test_act_exception_with_non_chrome_screenshot_recovers_and_retries(self):
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
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "foreground_recovery_attempts_per_event": 3,
                    "foreground_recovery_events_per_keyword": 2,
                },
            }
            client = FakeClient(
                [
                    RuntimeError("Failed to continue: Unable to find the required element on the page"),
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                    {"content": [{"type": "text", "text": "search submitted submission_method=search_button"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"chrome_not_foreground","confidence":0.9,"reason":"Codex is visible"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            self.assertEqual(
                [call["name"] for call in client.calls],
                ["act", "act", "act"],
            )
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "foreground_exception_keyword_search.png")))
            self.assertEqual(
                payload["diagnostics"]["foreground_recovery_exception_checks"][0]["page_state"]["status"],
                "chrome_not_foreground",
            )
            self.assertEqual(payload["diagnostics"]["foreground_recovery_attempts"][0]["status"], "recovered")

    def test_closeable_popup_overlay_repair_reclassifies_same_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(
                {"content": [{"type": "text", "text": "closeable_overlay_closed=true"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"closeable_popup_overlay","confidence":0.9,"reason":"dimmed Taobao page with gray X"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )
            diagnostics = {}
            screenshot, page_state = worker._capture_and_classify_with_foreground_recovery(
                client=client,
                contract={"page_sampling": {"allow_page_state_json_classifier": True}},
                capture_plan={"allow_page_state_json_classifier": True},
                tools=[],
                path=os.path.join(tmp, "tile_00.png"),
                tile_id="tile_00",
                keyword="万智牌 中止",
                evidence_dir=tmp,
                stage="post_act_verification",
                diagnostics=diagnostics,
                foreground_recovery={"events_used": 0},
                interrupt_check=None,
                keyword_deadline=time.monotonic() + 30,
                timeout_seconds=5,
            )

            self.assertEqual(page_state["status"], "visible_results")
            self.assertTrue(os.path.exists(screenshot["path"]))
            self.assertEqual([call["name"] for call in client.calls], ["act"])
            self.assertIn("popup's own upper-right corner", client.calls[0]["arguments"]["prompt"])
            self.assertEqual(diagnostics["closeable_popup_overlay_repairs"][0]["status"], "attempted")

    def test_closeable_popup_overlay_budget_exhaustion_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(
                {"content": [{"type": "text", "text": "closeable_overlay_closed=true"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"closeable_popup_overlay","confidence":0.9}'}]},
                    {"content": [{"type": "text", "text": '{"state":"closeable_popup_overlay","confidence":0.9}'}]},
                ],
            )

            with self.assertRaises(worker.MidsceneActionAbnormal) as ctx:
                worker._capture_and_classify_with_foreground_recovery(
                    client=client,
                    contract={"page_sampling": {"allow_page_state_json_classifier": True}},
                    capture_plan={"allow_page_state_json_classifier": True},
                    tools=[],
                    path=os.path.join(tmp, "tile_00.png"),
                    tile_id="tile_00",
                    keyword="万智牌 中止",
                    evidence_dir=tmp,
                    stage="post_act_verification",
                    diagnostics={},
                    foreground_recovery={"events_used": 0},
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 30,
                    timeout_seconds=5,
                )

            self.assertEqual(ctx.exception.reason, "closeable_popup_overlay")

    def test_act_exception_white_skeleton_page_state_blocks_foreground_recovery(self):
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
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "foreground_recovery_attempts_per_event": 3,
                    "foreground_recovery_events_per_keyword": 2,
                },
            }
            client = FakeClient(
                RuntimeError("Failed to execute act: Task failed: chrome_not_foreground"),
                classifier_result=[
                    {"content": [{"type": "text", "text": "Classifier positive."}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    side_effect=[
                        {
                            "status": "white_skeleton",
                            "confidence": 0.64,
                            "reason": "mostly_light_gray_content_with_no_price_signal",
                            "metrics": {},
                        },
                        {
                            "status": "visible_ready",
                            "confidence": 0.82,
                            "reason": "chrome_foreground",
                            "metrics": {},
                        },
                    ],
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
            self.assertEqual(result["stop_reason"], "midscene_mcp_action_failed")
            check = payload["diagnostics"]["foreground_recovery_exception_checks"][0]
            self.assertEqual(check["status"], "checked")
            self.assertEqual(check["page_state"]["status"], "white_skeleton")
            self.assertNotIn("foreground_recovery_attempts", payload["diagnostics"])

    def test_foreground_recovery_exhausted_before_capture_needs_review(self):
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
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "foreground_recovery_attempts_per_event": 2,
                    "foreground_recovery_events_per_keyword": 1,
                },
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "chrome_not_foreground: WPS is visible"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=blocked WPS still visible"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=blocked WPS still visible"}]},
                ]
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

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "foreground_recovery_exhausted")
            attempts = payload["diagnostics"]["foreground_recovery_attempts"]
            self.assertEqual(attempts[0]["status"], "exhausted")
            self.assertEqual(len(attempts[0]["attempts"]), 2)

    def test_foreground_recovery_claim_requires_after_screenshot_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostics = {}
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"chrome_not_foreground","confidence":0.9,"reason":"WPS visible"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )

            record = worker._maybe_recover_foreground(
                client=client,
                contract={
                    "page_sampling": {"allow_page_state_json_classifier": True},
                    "hard_stop_policy": {
                        "foreground_recovery_attempts_per_event": 2,
                        "foreground_recovery_events_per_keyword": 1,
                    },
                },
                capture_plan={},
                tools=[],
                stage="keyword_search",
                keyword="万智牌 中止",
                diagnostics=diagnostics,
                foreground_recovery={"events_used": 0},
                evidence_dir=tmp,
                interrupt_check=None,
                keyword_deadline=time.monotonic() + 30,
                timeout_seconds=5,
            )

            self.assertEqual(record["status"], "recovered")
            self.assertEqual(record["recovered_attempt"], 2)
            first_attempt = record["attempts"][0]
            self.assertEqual(first_attempt["after_page_state"]["status"], "chrome_not_foreground")
            self.assertEqual(first_attempt["after_verification"], "still_not_foreground")
            self.assertEqual(record["attempts"][1]["after_page_state"]["status"], "visible_results")

    def test_foreground_recovery_accepts_classifier_chrome_new_tab_unknown_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostics = {}
            client = FakeClient(
                {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
            )

            with mock.patch.object(
                worker,
                "classify_screenshot_json",
                return_value={
                    "status": "unknown",
                    "confidence": 0.82,
                    "reason": "Chrome browser is foreground on a new tab page",
                    "metrics": {},
                    "source": "json_classifier",
                    "raw_text": "Chrome browser is foreground on a new tab page",
                },
            ):
                record = worker._maybe_recover_foreground(
                    client=client,
                    contract={
                        "page_sampling": {"allow_page_state_json_classifier": True},
                        "hard_stop_policy": {
                            "foreground_recovery_attempts_per_event": 1,
                            "foreground_recovery_events_per_keyword": 1,
                        },
                    },
                    capture_plan={},
                    tools=[],
                    stage="keyword_search",
                    keyword="万智牌 中止",
                    diagnostics=diagnostics,
                    foreground_recovery={"events_used": 0},
                    evidence_dir=tmp,
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 30,
                    timeout_seconds=5,
                )

            self.assertEqual(record["status"], "recovered")
            self.assertEqual(record["attempts"][0]["after_page_state"]["status"], "unknown")
            self.assertEqual([call["name"] for call in client.calls], ["act"])

    def test_foreground_recovery_accepts_visible_ready_even_with_stale_probe_foreground_text(self):
        page_state = {
            "status": "visible_ready",
            "confidence": 0.72,
            "reason": "taobao_homepage_visible",
            "source": "heuristic",
            "raw_text": (
                '{"checks":[{"status":"unknown","raw_text":"chrome_not_foreground: '
                'Codex was visible before recovery"}]}'
            ),
            "fallback_reason": "probe_unparseable",
            "probe_diagnostics": {
                "raw_text": "chrome_not_foreground was reported before the foreground recovery act",
                "fallback_reason": "probe_unparseable",
            },
        }

        self.assertFalse(worker._foreground_recovery_after_state_ok(page_state))

    def test_foreground_recovery_blocks_chrome_new_tab_white_skeleton_after_state(self):
        page_state = {
            "status": "white_skeleton",
            "confidence": 0.64,
            "reason": "mostly_light_gray_content_with_no_price_signal",
            "raw_text": (
                "Failed to execute assert: Classifier negative. Reason: 当前显示的是Chrome的新标签页，"
                "可见Google搜索主页和淘宝快捷方式；不是淘宝结果页。"
            ),
        }

        self.assertFalse(worker._foreground_recovery_after_state_ok(page_state))

    def test_foreground_recovery_blocks_plain_white_skeleton_after_state(self):
        page_state = {
            "status": "white_skeleton",
            "confidence": 0.64,
            "reason": "mostly_light_gray_content_with_no_price_signal",
            "raw_text": "Taobao page is blank or still loading.",
        }

        self.assertFalse(worker._foreground_recovery_after_state_ok(page_state))

    def test_third_foreground_loss_event_exhausts_per_keyword_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 3,
                    "min_retained_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "foreground_recovery_attempts_per_event": 1,
                    "foreground_recovery_events_per_keyword": 2,
                },
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "chrome_not_foreground: Codex is visible"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                    {"content": [{"type": "text", "text": "search submitted submission_method=search_button"}]},
                    {"content": [{"type": "text", "text": "chrome_not_foreground: Terminal is visible"}]},
                    {"content": [{"type": "text", "text": "foreground_recovery=recovered Chrome foreground"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                    {"content": [{"type": "text", "text": "chrome_not_foreground: WPS is visible"}]},
                ]
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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            self.assertEqual(result["stop_reason"], "captured_partial_foreground_recovery_exhausted")
            attempts = payload["diagnostics"]["foreground_recovery_attempts"]
            self.assertEqual([item["status"] for item in attempts], ["recovered", "recovered", "exhausted"])
            self.assertEqual(payload["diagnostics"]["partial_capture_stop"]["reason"], "foreground_recovery_exhausted_after_capturable_tiles")

    def test_foreground_recovery_does_not_mask_login_captcha_or_permission_states(self):
        for text, expected in [
            ("Task finished, message: login required", "login_required"),
            ("Task finished, message: captcha visible", "captcha_required"),
            ("Task finished, message: risk warning visible", "risk_suspected"),
            ("Task finished, message: automation permission panel visible", "popup_blocked"),
        ]:
            classified = worker.classify_midscene_act_result(
                {"content": [{"type": "text", "text": text}]},
                default_context="foreground_recovery",
            )
            self.assertTrue(classified["abnormal"])
            self.assertEqual(classified["stop_reason"], expected)

    def test_reset_retry_search_does_not_fire_for_unknown_or_foreground_loss(self):
        self.assertFalse(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "manual_review_needed",
                    "rough_state": "unknown",
                    "page_state": {"status": "unknown"},
                }
            )
        )
        self.assertFalse(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "chrome_not_foreground",
                    "rough_state": "chrome_not_foreground",
                    "page_state": {"status": "chrome_not_foreground"},
                }
            )
        )
        self.assertTrue(
            worker._should_reset_retry_search(
                {
                    "stop_reason": "visible_keyword_mismatch",
                    "rough_state": "keyword_mismatch",
                    "page_state": {"status": "visible_results"},
                    "diagnostics": {"screenshot_keyword": {"status": "mismatch"}},
                }
            )
        )

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

    def test_keyword_capture_does_not_use_assert_for_keyword_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 撼地灵",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
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
                {"content": [{"type": "text", "text": "<complete success=\"true\">done</complete>"}]},
                classifier_result={"content": [{"type": "text", "text": '{"state":"visible_results"}'}]},
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
                        "visible_search_keyword": "万智牌 撼地灵",
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            self.assertEqual(result["stop_reason"], "captured")
            self.assertEqual(payload["rough_state"], "visible_results_unverified")
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "visible_ready")
            self.assertTrue(os.path.exists(task["capture_plan"]["primary_screenshot_path"]))
            self.assertFalse(os.path.exists(task["abnormal_screenshot_path"]))
            self.assertEqual(
                [call["name"] for call in client.calls],
                ["act"],
            )

    def test_keyword_capture_resets_once_when_visible_keyword_is_unverified_with_assert(self):
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "<complete success=\"true\">done</complete>"}]},
                    {"content": [{"type": "text", "text": "reset search completed"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 撼地灵","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(result["stop_reason"], "captured")
            self.assertEqual(payload["status"], "captured")
            self.assertEqual(
                payload["diagnostics"]["post_act_verification_initial"]["screenshot_keyword"]["status"],
                "unknown",
            )
            reset_retry = payload["diagnostics"]["post_act_reset_retry"]
            self.assertEqual(reset_retry["status"], "recovered")
            self.assertEqual(reset_retry["trigger"]["stop_reason"], "visible_keyword_unverified")
            preserved = reset_retry["trigger"]["failed_screenshot_preservation"]
            self.assertEqual(preserved["status"], "preserved")
            self.assertTrue(preserved["preserved_path"].endswith("tile_00_initial_failed.png"))
            self.assertTrue(os.path.exists(preserved["preserved_path"]))
            self.assertEqual(reset_retry["recovered"]["screenshot_path"], os.path.join(tmp, "evidence", "tile_00.png"))
            retry_prompt = client.calls[1]["arguments"]["prompt"]
            self.assertIn("chrome_not_foreground", retry_prompt)
            self.assertIn("ordinary Taobao home/search-entry UI", retry_prompt)
            self.assertIn("Do not replace text inside an old results-page search box", retry_prompt)
            self.assertIn("home_entry_used=true", retry_prompt)
            self.assertEqual([call["name"] for call in client.calls], ["act", "act"])

    def test_new_keyword_post_act_mismatch_resets_once_from_old_results_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-2",
                "keyword_index": 2,
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "home_entry_prepared=true home_entry_used=true recovered_from_old_results=true bookmark_home_entry_used=false"}]},
                    {"content": [{"type": "text", "text": "search completed but old results remain"}]},
                    {"content": [{"type": "text", "text": "reset search completed"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_ready","reason":"Taobao homepage search entry is visible"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 闪电击","keyword_match":"false"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 撼地灵","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=2,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "captured")
            self.assertEqual(payload["status"], "captured")
            self.assertEqual(payload["diagnostics"]["pre_keyword_home_entry"]["status"], "verified")
            self.assertTrue(
                payload["diagnostics"]["pre_keyword_home_entry"]["steps"]["act"]["reported_home_entry_prepared"]
            )
            self.assertEqual(
                payload["diagnostics"]["post_act_verification_initial"]["screenshot_keyword"]["status"],
                "mismatch",
            )
            self.assertFalse(
                payload["diagnostics"]["post_act_verification_initial"]["page_state"]["keyword_match"]
            )
            reset_retry = payload["diagnostics"]["post_act_reset_retry"]
            self.assertEqual(reset_retry["status"], "recovered")
            self.assertEqual(reset_retry["trigger"]["stop_reason"], "visible_keyword_mismatch")
            preserved = reset_retry["trigger"]["failed_screenshot_preservation"]
            self.assertEqual(preserved["status"], "preserved")
            self.assertTrue(preserved["preserved_path"].endswith("tile_00_initial_failed.png"))
            self.assertTrue(os.path.exists(preserved["preserved_path"]))
            self.assertEqual([call["name"] for call in client.calls], ["act", "act", "act"])

    def test_old_keyword_page_retry_must_return_home_before_it_can_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-2",
                "keyword_index": 2,
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "home_entry_prepared=false old results remain"}]},
                    {"content": [{"type": "text", "text": "home_entry_prepared=false old results still remain"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 闪电击","keyword_match":false}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 闪电击","keyword_match":false}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=2,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["stop_reason"], "home_entry_not_reached")
            self.assertEqual(payload["status"], "needs_review")
            home_prompt = client.calls[0]["arguments"]["prompt"]
            self.assertIn("Prepare the Taobao homepage/search-entry boundary", home_prompt)
            self.assertIn("Do not replace text inside the old results-page search box", home_prompt)
            self.assertNotEqual(payload["status"], "captured")

    def test_pre_keyword_visible_ready_old_keyword_allows_searching_next_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-2",
                "keyword_index": 2,
                "keyword": "万智牌 剧毒裂片妖",
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "home_entry_prepared=true home_entry_used=true recovered_from_old_results=false bookmark_home_entry_used=false"}]},
                    {"content": [{"type": "text", "text": "home_entry_used=true submission_method=search_button"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_ready","visible_search_keyword":"万智牌 不倦供给人","keyword_match":false}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 剧毒裂片妖","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=2,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "captured")
            self.assertEqual(payload["diagnostics"]["pre_keyword_home_entry"]["status"], "verified")
            self.assertNotIn("pre_keyword_home_entry_retry", payload["diagnostics"])
            self.assertEqual([call["name"] for call in client.calls], ["act", "act"])
            search_prompt = client.calls[1]["arguments"]["prompt"]
            self.assertIn("search exactly this keyword", search_prompt)

    def test_pre_keyword_old_results_page_allows_bookmark_home_entry_repair_then_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-2",
                "keyword_index": 2,
                "keyword": "万智牌 动荡",
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
                "hard_stop_policy": {
                    "timeout_per_keyword_seconds": 30,
                    "allow_bookmark_home_entry_repair": True,
                },
                "config": {"allow_bookmark_home_entry_repair": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "home_entry_prepared=false old results page remains"}]},
                    {"content": [{"type": "text", "text": "home_entry_prepared=true home_entry_used=true recovered_from_old_results=true bookmark_home_entry_used=true"}]},
                    {"content": [{"type": "text", "text": "home_entry_used=true submission_method=search_button"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"results_page","visible_search_keyword":"万智牌 不倦供给人","keyword_match":false}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_ready","reason":"Taobao homepage from bookmark"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 动荡","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=2,
                    tools=["act", "take_screenshot"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "captured")
            retry = payload["diagnostics"]["pre_keyword_home_entry_retry"]
            self.assertEqual(retry["status"], "verified")
            self.assertEqual(retry["trigger"]["stop_reason"], "home_entry_not_reached")
            retry_prompt = client.calls[1]["arguments"]["prompt"]
            self.assertIn("visible browser new tab plus button", retry_prompt)
            self.assertIn("visible Taobao bookmark button", retry_prompt)
            self.assertIn("Do not type anything into the address bar", retry_prompt)

    def test_pre_keyword_hard_or_unknown_states_do_not_retry_or_search(self):
        cases = [
            (
                "login",
                '{"state":"login_required","reason":"login page visible"}',
                "login_required",
            ),
            (
                "captcha",
                '{"state":"captcha_required","reason":"captcha visible"}',
                "captcha_required",
            ),
            (
                "risk",
                '{"state":"risk_suspected","reason":"risk warning visible"}',
                "risk_suspected",
            ),
            (
                "permission_panel",
                '{"state":"popup_blocked","reason":"automation permission panel visible"}',
                "popup_blocked",
            ),
            (
                "non_chrome",
                '{"state":"chrome_not_foreground","reason":"WPS is visible"}',
                "foreground_recovery_exhausted",
            ),
            (
                "unknown",
                '{"state":"unknown","reason":"unclear screen"}',
                "home_entry_unverified",
            ),
        ]

        for label, classifier_text, expected_stop_reason in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                task = {
                    "task_id": f"task-{label}",
                    "keyword_index": 2,
                    "keyword": "万智牌 动荡",
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
                    "page_sampling": {"allow_page_state_json_classifier": True},
                }
                client = FakeClient(
                    [
                        {"content": [{"type": "text", "text": "home_entry_prepared=false stop for review"}]},
                    ],
                    classifier_result=[
                        {"content": [{"type": "text", "text": classifier_text}]},
                    ],
                )

                with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                    mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                    mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                    result = worker._capture_keyword_with_mcp(
                        client=client,
                        task=task,
                        contract=contract,
                        run_id="run",
                        session_index=1,
                        task_dir=tmp,
                        fallback_index=2,
                        tools=["act", "take_screenshot"],
                    )

                payload = worker._read_json(task["result_path"])
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(payload["status"], "needs_review")
                self.assertEqual(result["stop_reason"], expected_stop_reason)
                prompts = [
                    str((call.get("arguments") or {}).get("prompt") or "")
                    for call in client.calls
                    if call.get("name") == "act"
                ]
                self.assertTrue(prompts)
                self.assertIn("Prepare the Taobao homepage/search-entry boundary", prompts[0])
                self.assertFalse(
                    any("previous pre-keyword boundary check" in prompt for prompt in prompts),
                    prompts,
                )
                self.assertFalse(
                    any("search exactly this keyword" in prompt for prompt in prompts),
                    prompts,
                )
                self.assertNotIn("pre_keyword_home_entry_retry", payload["diagnostics"])
                self.assertNotIn("keyword_search", payload["diagnostics"])

    def test_pre_keyword_home_entry_gate_allows_visible_ready_text_and_blocks_results(self):
        cases = [
            (
                "unknown",
                {"status": "unknown", "reason": "unclear screen"},
                "home_entry_unverified",
            ),
            (
                "old_keyword",
                {
                    "status": "visible_ready",
                    "visible_search_keyword": "万智牌 闪电击",
                    "keyword_match": False,
                },
                "",
            ),
            (
                "already_typed",
                {
                    "status": "visible_ready",
                    "visible_search_keyword": "万智牌 撼地灵",
                    "keyword_match": True,
                    "search_box_text_kind": "actual_input",
                },
                "",
            ),
            (
                "homepage_suggestion",
                {
                    "status": "visible_ready",
                    "visible_search_keyword": "一次性拖鞋",
                    "keyword_match": None,
                    "search_box_text_kind": "suggestion",
                },
                "",
            ),
            (
                "homepage_placeholder",
                {
                    "status": "visible_ready",
                    "visible_search_keyword": "搜索宝贝",
                    "keyword_match": None,
                    "search_box_text_kind": "placeholder",
                },
                "",
            ),
            (
                "results_page",
                {
                    "status": "results_page",
                    "visible_search_keyword": "万智牌 闪电击",
                    "keyword_match": False,
                },
                "home_entry_not_reached",
            ),
        ]

        for label, page_state, reason in cases:
            with self.subTest(label=label):
                self.assertEqual(worker._home_entry_review_reason(page_state), reason)

    def test_post_keyword_cleanup_closes_results_tab_and_verifies_home_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "capture_plan": {
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "home_entry_prepared=true home_entry_used=true current_results_tab_closed=true bookmark_home_entry_used=false"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_ready","reason":"Taobao homepage search entry visible","search_box_text_kind":"suggestion","visible_search_keyword":"一次性拖鞋","keyword_match":null}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                cleanup = worker._post_keyword_cleanup_after_success(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    tools=["act", "take_screenshot"],
                )

            self.assertEqual(cleanup["status"], "verified")
            self.assertEqual(cleanup["stop_reason"], "")
            self.assertTrue(cleanup["steps"]["act"]["reported_current_results_tab_closed"])
            self.assertTrue(cleanup["verification_screenshot"].endswith("post_keyword_cleanup.png"))
            prompt = client.calls[0]["arguments"]["prompt"]
            self.assertIn("Command+W", prompt)
            self.assertIn("Ctrl+W", prompt)
            self.assertIn("Do not type the next keyword", prompt)

    def test_post_keyword_cleanup_blocks_when_results_page_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "capture_plan": {
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
                "page_sampling": {"allow_page_state_json_classifier": True},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "current_results_tab_closed=false"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"results_page","visible_search_keyword":"万智牌 中止","keyword_match":true,"search_box_text_kind":"actual_input"}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
                cleanup = worker._post_keyword_cleanup_after_success(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    tools=["act", "take_screenshot"],
                )

            self.assertEqual(cleanup["status"], "blocked")
            self.assertEqual(cleanup["stop_reason"], "home_entry_not_reached")

    def test_home_search_prompt_does_not_allow_url_or_short_action_fallbacks(self):
        prompt = worker._keyword_search_home_entry_prompt("万智牌 中止")
        pre_keyword_prompt = worker._pre_keyword_home_entry_prompt("万智牌 中止")

        self.assertIn("existing visible Taobao home page", prompt)
        self.assertIn("ordinary Taobao home/search-entry UI", prompt)
        self.assertIn("Taobao logo", prompt)
        self.assertIn("Home/首页 entry", prompt)
        self.assertIn("home_entry_used=true", prompt)
        self.assertIn("Do not replace text inside an old results-page search box", prompt)
        self.assertIn("do not type a URL", prompt)
        self.assertIn("do not open a new browser tab", prompt)
        self.assertIn("do not run scripts", prompt)
        self.assertIn("Do not use short action APIs", prompt)
        self.assertIn("Tap, Input, KeyboardPress, Scroll, or ClearInput", prompt)
        self.assertIn("Do not type the next keyword yet", pre_keyword_prompt)
        self.assertIn("not a results page", pre_keyword_prompt)
        self.assertIn("not a results page and not a results-page search box", pre_keyword_prompt)

    def test_home_search_prompt_allows_configured_visible_bookmark_repair_only(self):
        contract = {
            "config": {"allow_bookmark_home_entry_repair": True},
            "hard_stop_policy": {"allow_bookmark_home_entry_repair": True},
        }

        prompt = worker._keyword_search_home_entry_prompt("万智牌 中止", contract=contract)
        retry_prompt = worker._keyword_search_home_entry_retry_after_exception_prompt(
            "万智牌 中止",
            contract=contract,
        )

        self.assertIn("visible browser new tab plus button", prompt)
        self.assertIn("visible Taobao bookmark button", prompt)
        self.assertIn("Do not type anything into the address bar", prompt)
        self.assertIn("bookmark_home_entry_unavailable", prompt)
        self.assertIn("more than one Chrome tab will remain", prompt)
        self.assertIn("Never close the final remaining Chrome tab", prompt)
        self.assertIn("if the tab count is unclear, leave the old tab open", prompt)
        self.assertIn("bookmark_home_entry_used=true or false", prompt)
        self.assertIn("visible new tab plus button", retry_prompt)
        self.assertIn("visible Taobao bookmark button", retry_prompt)
        self.assertNotIn("do not open a new browser tab", prompt)
        self.assertIn("do not type a URL", prompt)
        self.assertIn("do not run scripts", prompt)

    def test_keyword_capture_resets_once_when_screenshot_keyword_hint_mismatches_without_assert(self):
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
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "search completed"}]},
                    {"content": [{"type": "text", "text": "reset search completed"}]},
                ]
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    side_effect=[
                        {
                            "status": "visible_ready",
                            "confidence": 0.72,
                            "reason": "test_visible_results",
                            "visible_search_keyword": "万智牌 闪电击",
                            "keyword_match": False,
                            "search_box_text_kind": "actual_input",
                            "search_submitted": True,
                            "is_home_feed": False,
                            "result_page_evidence": ["test_results_layout"],
                            "metrics": {},
                        },
                        {
                            "status": "visible_ready",
                            "confidence": 0.72,
                            "reason": "reset_visible_results",
                            "visible_search_keyword": "万智牌 撼地灵",
                            "keyword_match": True,
                            "search_box_text_kind": "actual_input",
                            "search_submitted": True,
                            "is_home_feed": False,
                            "result_page_evidence": ["test_results_layout"],
                            "metrics": {},
                        },
                    ],
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
            self.assertEqual(result["stop_reason"], "captured")
            self.assertEqual(payload["status"], "captured")
            self.assertEqual(
                payload["diagnostics"]["post_act_verification_initial"]["screenshot_keyword"]["observed_keyword"],
                "万智牌 闪电击",
            )
            self.assertEqual(payload["diagnostics"]["post_act_reset_retry"]["trigger"]["stop_reason"], "visible_keyword_mismatch")
            preserved = payload["diagnostics"]["post_act_reset_retry"]["trigger"]["failed_screenshot_preservation"]
            self.assertEqual(preserved["status"], "preserved")
            self.assertTrue(preserved["preserved_path"].endswith("tile_00_initial_failed.png"))
            self.assertTrue(os.path.exists(preserved["preserved_path"]))
            self.assertEqual([call["name"] for call in client.calls], ["act", "act"])

    def test_reset_retry_recovered_keeps_attempted_act_diagnostics(self):
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
                [
                    {"content": [{"type": "text", "text": "search completed"}]},
                    {"content": [{"type": "text", "text": "reset search completed"}]},
                ]
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(
                    worker,
                    "_classify_screenshot",
                    side_effect=[
                        {
                            "status": "visible_results",
                            "confidence": 0.82,
                            "reason": "visible_results_keyword_unclear",
                            "metrics": {},
                        },
                        {
                            "status": "visible_results",
                            "confidence": 0.82,
                            "reason": "retry_visible_results",
                            "visible_search_keyword": "万智牌 中止",
                            "keyword_match": True,
                            "search_box_text_kind": "actual_input",
                            "search_submitted": True,
                            "is_home_feed": False,
                            "result_page_evidence": ["test_results_layout"],
                            "metrics": {},
                        },
                    ],
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
            reset_retry = payload["diagnostics"]["post_act_reset_retry"]
            self.assertEqual(result["status"], "captured")
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "visible_results")
            self.assertEqual(reset_retry["status"], "recovered")
            self.assertEqual(reset_retry["attempted"]["status"], "attempted")
            self.assertEqual(reset_retry["recovered"]["status"], "recovered")
            self.assertIn("act", reset_retry["attempted"]["steps"])
            self.assertIn("act", reset_retry["steps"])
            self.assertEqual(reset_retry["attempted"]["steps"]["act"], reset_retry["steps"]["act"])
            self.assertEqual(
                [call["name"] for call in client.calls],
                ["act", "act"],
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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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

    def test_json_classifier_visible_listings_allows_capture(self):
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient({"content": [{"type": "text", "text": "search completed"}]})

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(worker, "_classify_screenshot") as heuristic, \
                mock.patch.object(
                    worker,
                    "classify_screenshot_json",
                    return_value={
                        "status": "visible_results",
                        "confidence": 0.9,
                        "reason": "readable listings visible",
                        "metrics": {},
                        "source": "json_classifier",
                        "raw_text": '{"state":"visible_results"}',
                        "visible_search_keyword": "万智牌 中止",
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["sort/filter bar"],
                    },
                ) as classifier:
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
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "visible_results")
            self.assertEqual(payload["screenshots"][0]["page_state"]["source"], "json_classifier")
            self.assertEqual(payload["screenshots"][0]["page_state"]["visible_search_keyword"], "万智牌 中止")
            self.assertEqual([call["name"] for call in client.calls], ["act"])
            classifier.assert_called()
            heuristic.assert_not_called()

    def test_tile_00_home_feed_without_search_submission_does_not_capture(self):
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "home_entry_used=true submission_method=search_button"}]},
                    {"content": [{"type": "text", "text": "home_entry_used=true submission_method=search_button"}]},
                ],
                classifier_result=[
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    '{"state":"visible_results","visible_search_keyword":"万智牌 中止",'
                                    '"keyword_match":true,"search_box_text_kind":"actual_input",'
                                    '"search_submitted":false,"is_home_feed":true,'
                                    '"reason":"homepage recommendation feed product cards are visible"}'
                                ),
                            }
                        ]
                    },
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    '{"state":"visible_results","visible_search_keyword":"万智牌 中止",'
                                    '"keyword_match":true,"search_box_text_kind":"actual_input",'
                                    '"search_submitted":false,"is_home_feed":true,'
                                    '"reason":"homepage recommendation feed still visible"}'
                                ),
                            }
                        ]
                    },
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(result["stop_reason"], "search_submit_unconfirmed")
            self.assertNotEqual(payload["status"], "captured")
            self.assertEqual(payload["screenshots"][0]["page_state"]["search_submitted"], False)
            self.assertEqual(payload["screenshots"][0]["page_state"]["is_home_feed"], True)
            self.assertEqual(
                payload["diagnostics"]["post_act_verification_initial"]["failed_screenshot_preservation"]["status"],
                "preserved",
            )

    def test_post_act_success_uses_one_probe_then_continues_to_scroll_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "search completed submission_method=search_button"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","confidence":0.86,"reason":"normal middle results tile"}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(len(payload["screenshots"]), 2)
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "visible_results")
            self.assertEqual(payload["screenshots"][1]["page_state"]["status"], "visible_results")
            action_trace_path = os.path.join(tmp, "evidence", "action_trace.jsonl")
            page_state_path = os.path.join(tmp, "evidence", "page_state_v2.jsonl")
            evidence_check_path = os.path.join(tmp, "evidence", "evidence_check.jsonl")
            decision_path = os.path.join(tmp, "evidence", "capture_decision.jsonl")
            boundary_path = os.path.join(tmp, "evidence", "keyword_boundary.json")
            goal_contract_path = os.path.join(tmp, "evidence", "goal_contract.json")
            self.assertTrue(os.path.exists(action_trace_path))
            self.assertTrue(os.path.exists(goal_contract_path))
            self.assertTrue(os.path.exists(page_state_path))
            self.assertTrue(os.path.exists(evidence_check_path))
            self.assertTrue(os.path.exists(decision_path))
            self.assertTrue(os.path.exists(boundary_path))
            with open(page_state_path, "r", encoding="utf-8") as f:
                observations = [json.loads(line) for line in f if line.strip()]
            with open(evidence_check_path, "r", encoding="utf-8") as f:
                evidence_checks = [json.loads(line) for line in f if line.strip()]
            with open(decision_path, "r", encoding="utf-8") as f:
                decisions = [json.loads(line) for line in f if line.strip()]
            self.assertEqual([item["tile_id"] for item in observations], ["tile_00", "tile_01"])
            self.assertEqual([item["tile_id"] for item in evidence_checks], ["tile_00", "tile_01"])
            self.assertEqual(observations[0]["page_state"]["visible_search_keyword"], "万智牌 中止")
            self.assertEqual([item["goal_state"] for item in decisions], ["BOUNDARY_VERIFY", "CAPTURING"])
            self.assertEqual([item["gate_decision"] for item in decisions], ["accept", "accept"])
            self.assertEqual(worker._read_json(boundary_path)["tile_id"], "tile_00")
            self.assertEqual(worker._read_json(goal_contract_path)["keyword"], "万智牌 中止")
            self.assertEqual(payload["diagnostics"]["artifacts"]["page_state_v2"], page_state_path)
            self.assertEqual(payload["diagnostics"]["artifacts"]["evidence_check"], evidence_check_path)
            self.assertEqual(payload["diagnostics"]["artifacts"]["goal_contract"], goal_contract_path)
            self.assertEqual([call["name"] for call in client.calls], ["act", "act"])
            self.assertEqual(self.mock_classifier.call_count, 2)

    def test_non_bottom_scroll_tile_without_readable_search_keyword_keeps_capturing(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 3,
                    "min_retained_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                [
                    {"content": [{"type": "text", "text": "search completed"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                    {"content": [{"type": "text", "text": "scrolled to results end"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","confidence":0.86,"reason":"normal middle results tile"}'}]},
                    {"content": [{"type": "text", "text": '{"state":"results_end","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(len(payload["screenshots"]), 3)
            self.assertEqual(payload["screenshots"][1]["page_state"]["status"], "visible_results")
            self.assertEqual(payload["screenshots"][1]["page_state"]["visible_search_keyword"], "")
            self.assertEqual(payload["diagnostics"]["capture_stop"]["reason"], "results_end")
            self.assertEqual([call["name"] for call in client.calls], ["act", "act", "act"])

    def test_results_end_keyword_mismatch_or_unreadable_stops_without_reset(self):
        cases = [
            (
                "mismatch",
                '{"state":"results_end","visible_search_keyword":"万智牌 闪电击","keyword_match":"false"}',
                "visible_keyword_mismatch",
                False,
            ),
            (
                "unreadable",
                '{"state":"results_end","confidence":0.9}',
                "visible_keyword_unverified",
                None,
            ),
        ]
        for label, results_end_probe, stop_reason, keyword_match in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                task = {
                    "task_id": "task-1",
                    "keyword_index": 1,
                    "keyword": "万智牌 中止",
                    "evidence_dir": os.path.join(tmp, "evidence"),
                    "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                    "page_sampling": {"allow_page_state_json_classifier": True},
                    "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
                }
                client = FakeClient(
                    [
                        {"content": [{"type": "text", "text": "search completed"}]},
                        {"content": [{"type": "text", "text": "scrolled to results end"}]},
                    ],
                    classifier_result=[
                        {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                        {"content": [{"type": "text", "text": results_end_probe}]},
                    ],
                )

                with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                    mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                    mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
                boundary = payload["diagnostics"]["tile_01_results_end_boundary"]
                self.assertEqual(result["status"], "captured")
                self.assertEqual(payload["status"], "captured")
                self.assertEqual(len(payload["screenshots"]), 2)
                self.assertEqual(payload["screenshots"][1]["tile_id"], "tile_01")
                self.assertEqual(payload["diagnostics"]["capture_stop"]["reason"], "results_end")
                self.assertFalse(payload["diagnostics"]["capture_stop"]["keyword_boundary_ok"])
                self.assertFalse(boundary["ok"])
                self.assertEqual(boundary["stop_reason"], stop_reason)
                self.assertEqual(boundary["page_state"].get("keyword_match"), keyword_match)
                self.assertNotIn("post_act_reset_retry", payload["diagnostics"])
                self.assertFalse(os.path.exists(os.path.join(tmp, "evidence", "tile_01_results_end_failed.png")))
                self.assertEqual([call["name"] for call in client.calls], ["act", "act"])

    def test_post_act_unknown_keyword_verification_resets_once_then_needs_review(self):
        for page_state in ("visible_results", "results_end"):
            with self.subTest(page_state=page_state), tempfile.TemporaryDirectory() as tmp:
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
                    "page_sampling": {"allow_page_state_json_classifier": True},
                    "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
                }
                client = FakeClient(
                    {"content": [{"type": "text", "text": "search completed"}]},
                    classifier_result={
                        "content": [
                            {
                                "type": "text",
                                "text": f'{{"state":"{page_state}","confidence":0.9}}',
                            }
                        ]
                    },
                )
                unknown_keyword = mock.Mock()
                unknown_keyword.to_dict.return_value = {
                    "status": "unknown",
                    "expected_keyword": "万智牌 中止",
                    "observed_keyword": "",
                    "confidence": 0.0,
                    "reason": "ocr_unavailable",
                    "source": "test",
                }

                with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                    mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                    mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                    mock.patch.object(worker, "verify_visible_keyword", return_value=unknown_keyword):
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
                self.assertEqual(result["stop_reason"], "visible_keyword_unverified")
                self.assertNotEqual(payload["status"], "captured")
                self.assertEqual(
                    payload["diagnostics"]["post_act_verification"]["screenshot_keyword"]["status"],
                    "unknown",
                )
                self.assertEqual(
                    payload["diagnostics"]["post_act_verification_initial"]["screenshot_keyword"]["status"],
                    "unknown",
                )
                self.assertEqual(payload["diagnostics"]["post_act_reset_retry"]["status"], "attempted")
                self.assertEqual([call["name"] for call in client.calls], ["act", "act"])

    def test_json_classifier_captcha_stops_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"captcha_required"}'}]},
                    {"content": [{"type": "text", "text": "true"}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(result["stop_reason"], "captcha_required")
            self.assertEqual(payload["rough_state"], "captcha_required")
            self.assertIn('"state":"captcha_required"', payload["screenshots"][0]["page_state"]["raw_text"])

    def test_json_classifier_rate_limited_does_not_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"isError": True, "content": [{"type": "text", "text": "429 rate limit"}]},
                    {"content": [{"type": "text", "text": "true"}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "rate_limited")

    def test_classifier_http_429_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tile.png")
            FakeClient({"content": [{"type": "text", "text": "unused"}]}).capture_screenshot(path)

            with mock.patch.object(
                worker,
                "classify_screenshot_json",
                side_effect=page_state_classifier.PageStateClassifierUnavailable("classifier_http_429"),
            ):
                result = worker._classify_screenshot_page_state(
                    client=FakeClient({"content": [{"type": "text", "text": "unused"}]}),
                    path=path,
                    contract={"page_sampling": {"allow_page_state_json_classifier": True}},
                    capture_plan={},
                    tools=[],
                    tile_id="tile_00",
                    keyword="万智牌 中止",
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 30,
                    timeout_seconds=30,
                )

            self.assertEqual(result["status"], "rate_limited")
            self.assertEqual(result["fallback_reason"], "classifier_http_429")

    def test_classifier_uses_remaining_keyword_deadline_as_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tile.png")
            FakeClient({"content": [{"type": "text", "text": "unused"}]}).capture_screenshot(path)
            seen = {}

            def fake_classifier(_path, *, contract=None, keyword="", timeout_seconds=30):
                seen["timeout_seconds"] = timeout_seconds
                return {
                    "status": "visible_results",
                    "confidence": 0.9,
                    "reason": "ok",
                    "metrics": {},
                    "source": "json_classifier",
                    "raw_text": "{}",
                    "visible_search_keyword": keyword,
                    "keyword_match": True,
                    "search_box_text_kind": "actual_input",
                    "search_submitted": True,
                    "is_home_feed": False,
                    "result_page_evidence": ["test_results_layout"],
                }

            with mock.patch.object(worker, "classify_screenshot_json", side_effect=fake_classifier):
                worker._classify_screenshot_page_state(
                    client=FakeClient({"content": [{"type": "text", "text": "unused"}]}),
                    path=path,
                    contract={"page_sampling": {"allow_page_state_json_classifier": True}},
                    capture_plan={},
                    tools=[],
                    tile_id="tile_00",
                    keyword="万智牌 中止",
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 2,
                    timeout_seconds=30,
                )

            self.assertGreater(seen["timeout_seconds"], 0)
            self.assertLessEqual(seen["timeout_seconds"], 2)

    def test_old_page_state_probe_flag_still_enables_json_classifier_for_existing_contracts(self):
        self.assertTrue(
            worker._allow_json_page_state_classifier(
                {"page_sampling": {"allow_midscene_page_state_probe": True}},
                {},
            )
        )
        self.assertTrue(
            worker._allow_json_page_state_classifier(
                {},
                {"allow_midscene_page_state_probe": "true"},
            )
        )

    def test_post_act_classifier_positive_text_does_not_accept_unknown_keyword_on_visible_ready_page(self):
        page_state = {
            "status": "visible_ready",
            "confidence": 0.82,
            "reason": "heuristic_visible_results",
            "source": "heuristic",
            "raw_text": (
                '{"checks":[{"raw_text":"Classifier positive.","rate_limited":false,'
                '"parsed":{"state":"visible_results"}}]}'
            ),
            "visible_search_keyword": "",
            "keyword_match": None,
        }
        unknown_keyword = mock.Mock()
        unknown_keyword.to_dict.return_value = {
            "status": "unknown",
            "expected_keyword": "万智牌 中止",
            "observed_keyword": "",
            "confidence": 0.0,
            "reason": "ocr_unavailable",
            "source": "test",
        }

        with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(
                worker,
                "_capture_and_classify_with_foreground_recovery",
                return_value=({"mime_type": "image/png"}, page_state),
            ), \
            mock.patch.object(worker, "verify_visible_keyword", return_value=unknown_keyword):
            result = worker._verify_keyword_after_act(
                client=FakeClient({"content": [{"type": "text", "text": "ok"}]}),
                task={},
                capture_plan={"primary_screenshot_path": os.path.join(tmp, "tile_00.png")},
                evidence_dir=tmp,
                keyword="万智牌 中止",
                tools=[],
                interrupt_check=None,
                keyword_deadline=time.monotonic() + 30,
                mcp_timeout_seconds=30,
                contract={},
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stop_reason"], "visible_keyword_unverified")
        screenshot_keyword = result["diagnostics"]["screenshot_keyword"]
        self.assertEqual(screenshot_keyword["status"], "unknown")
        self.assertEqual(screenshot_keyword["source"], "test")

    def test_post_act_classifier_positive_text_does_not_accept_explicit_or_hinted_mismatch(self):
        cases = [
            (
                "keyword_match_false",
                {
                    "status": "visible_results",
                    "raw_text": "Classifier positive.",
                    "visible_search_keyword": "万智牌 闪电击",
                    "keyword_match": False,
                },
                {
                    "status": "unknown",
                    "expected_keyword": "万智牌 中止",
                    "observed_keyword": "",
                    "confidence": 0.0,
                    "reason": "ocr_unavailable",
                    "source": "test",
                },
                "visible_keyword_unverified",
            ),
            (
                "classifier_negative_json",
                {
                    "status": "visible_ready",
                    "source": "heuristic",
                    "raw_text": '{"checks":[{"raw_text":"Classifier negative.","rate_limited":false}]}',
                    "visible_search_keyword": "",
                    "keyword_match": None,
                },
                {
                    "status": "unknown",
                    "expected_keyword": "万智牌 中止",
                    "observed_keyword": "",
                    "confidence": 0.0,
                    "reason": "ocr_unavailable",
                    "source": "test",
                },
                "visible_keyword_unverified",
            ),
            (
                "empty_result_not_boundary",
                {
                    "status": "empty_result",
                    "source": "heuristic",
                    "raw_text": '{"checks":[{"raw_text":"Classifier positive.","rate_limited":false}]}',
                    "visible_search_keyword": "",
                    "keyword_match": None,
                },
                {
                    "status": "unknown",
                    "expected_keyword": "万智牌 中止",
                    "observed_keyword": "",
                    "confidence": 0.0,
                    "reason": "ocr_unavailable",
                    "source": "test",
                },
                "visible_keyword_unverified",
            ),
            (
                "hinted_mismatch",
                {
                    "status": "visible_results",
                    "raw_text": "Classifier positive.",
                    "visible_search_keyword": "万智牌 闪电击",
                    "keyword_match": None,
                },
                {
                    "status": "mismatch",
                    "expected_keyword": "万智牌 中止",
                    "observed_keyword": "万智牌 闪电击",
                    "confidence": 0.9,
                    "reason": "visible_keyword_hint_mismatch",
                    "source": "page_state_hint",
                },
                "visible_keyword_mismatch",
            ),
        ]
        for label, page_state, keyword_payload, stop_reason in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                keyword_result = mock.Mock()
                keyword_result.to_dict.return_value = keyword_payload
                with mock.patch.object(
                    worker,
                    "_capture_and_classify_with_foreground_recovery",
                    return_value=({"mime_type": "image/png"}, page_state),
                ), mock.patch.object(worker, "verify_visible_keyword", return_value=keyword_result):
                    result = worker._verify_keyword_after_act(
                        client=FakeClient({"content": [{"type": "text", "text": "ok"}]}),
                        task={},
                        capture_plan={"primary_screenshot_path": os.path.join(tmp, "tile_00.png")},
                        evidence_dir=tmp,
                        keyword="万智牌 中止",
                        tools=[],
                        interrupt_check=None,
                        keyword_deadline=time.monotonic() + 30,
                        mcp_timeout_seconds=30,
                        contract={},
                    )

                self.assertFalse(result["ok"])
                self.assertEqual(result["stop_reason"], stop_reason)

    def test_results_end_classifier_positive_text_does_not_accept_unknown_keyword_boundary(self):
        unknown_keyword = mock.Mock()
        unknown_keyword.to_dict.return_value = {
            "status": "unknown",
            "expected_keyword": "万智牌 中止",
            "observed_keyword": "",
            "confidence": 0.0,
            "reason": "ocr_unavailable",
            "source": "test",
        }
        page_state = {
            "status": "results_end",
            "raw_text": "Classifier positive.",
            "visible_search_keyword": "",
            "keyword_match": True,
        }

        with mock.patch.object(worker, "verify_visible_keyword", return_value=unknown_keyword):
            result = worker._verify_results_end_keyword_boundary(
                tile_path="/tmp/tile_01.png",
                tile_id="tile_01",
                page_state=page_state,
                screenshot_payload={"tile_id": "tile_01", "path": "/tmp/tile_01.png"},
                keyword="万智牌 中止",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stop_reason"], "visible_keyword_unverified")
        screenshot_keyword = result["diagnostics"]["screenshot_keyword"]
        self.assertEqual(screenshot_keyword["status"], "unknown")
        self.assertEqual(screenshot_keyword["source"], "test")

    def test_later_unknown_tile_after_visible_results_keeps_keyword_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 3,
                    "min_retained_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"search_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"unknown"}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(payload["status"], "captured")
            self.assertEqual(payload["screenshots"][-1]["page_state"]["status"], "unknown")
            self.assertEqual(
                payload["diagnostics"]["partial_capture_stop"]["reason"],
                "later_tile_unknown_after_capturable_tiles",
            )

    def test_scroll_tiles_do_not_require_visible_search_keyword_when_results_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","confidence":0.82}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(payload["screenshots"][1]["page_state"]["status"], "visible_results")
            self.assertEqual(payload["screenshots"][1]["page_state"]["visible_search_keyword"], "")
            self.assertNotIn("post_act_reset_retry", payload["diagnostics"])

    def test_highly_similar_adjacent_tile_stops_and_removes_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 3,
                    "min_retained_tiles_per_keyword": 1,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }

            class ImageClient(FakeClient):
                def capture_screenshot(self, path, **kwargs):
                    from PIL import Image

                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Image.new("RGB", (80, 60), (240, 240, 240)).save(path)
                    return {"path": path, "mime_type": "image/png"}

            client = ImageClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            duplicate_path = os.path.join(tmp, "evidence", "tile_01.png")
            self.assertEqual(result["status"], "captured")
            self.assertEqual(len(payload["screenshots"]), 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "tile_00.png")))
            self.assertFalse(os.path.exists(duplicate_path))
            self.assertEqual(payload["diagnostics"]["capture_stop"]["reason"], "similar_adjacent_tile")
            self.assertEqual(payload["diagnostics"]["capture_stop"]["previous_tile_id"], "tile_00")
            self.assertGreaterEqual(payload["diagnostics"]["capture_stop"]["similarity"], 0.985)

    def test_similar_adjacent_tiles_wait_until_min_retained_before_stopping(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 4,
                    "min_retained_tiles_per_keyword": 3,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }

            class SameImageClient(FakeClient):
                def capture_screenshot(self, path, **kwargs):
                    from PIL import Image

                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Image.new("RGB", (80, 60), (240, 240, 240)).save(path)
                    return {"path": path, "mime_type": "image/png"}

            client = SameImageClient(
                [
                    {"content": [{"type": "text", "text": "search completed"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                    {"content": [{"type": "text", "text": "scrolled to duplicate viewport"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual([shot["tile_id"] for shot in payload["screenshots"]], ["tile_00", "tile_01", "tile_02"])
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "tile_01.png")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "tile_02.png")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "evidence", "tile_03.png")))
            self.assertEqual(payload["diagnostics"]["capture_stop"]["reason"], "similar_adjacent_tile")
            self.assertEqual(payload["diagnostics"]["capture_stop"]["previous_tile_id"], "tile_02")
            self.assertEqual(payload["diagnostics"]["capture_stop"]["min_retained_tiles"], 3)

    def test_results_end_tile_is_retained_even_when_similar_to_previous_tile(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                "capture_plan": {
                    "max_tiles_per_keyword": 3,
                    "min_retained_tiles_per_keyword": 3,
                    "tile_scroll_distance_px": 500,
                    "primary_screenshot_path": os.path.join(tmp, "evidence", "tile_00.png"),
                },
            }
            contract = {
                "run_id": "run",
                "session_index": 1,
                "task_dir": tmp,
                "model_boundary": {"allow_midscene_act": True},
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }

            class SameImageClient(FakeClient):
                def capture_screenshot(self, path, **kwargs):
                    from PIL import Image

                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Image.new("RGB", (80, 60), (240, 240, 240)).save(path)
                    return {"path": path, "mime_type": "image/png"}

            client = SameImageClient(
                [
                    {"content": [{"type": "text", "text": "search completed"}]},
                    {"content": [{"type": "text", "text": "scrolled to next results viewport"}]},
                    {"content": [{"type": "text", "text": "scrolled to results end"}]},
                ],
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": '{"state":"results_end","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual([shot["tile_id"] for shot in payload["screenshots"]], ["tile_00", "tile_01", "tile_02"])
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "tile_01.png")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "evidence", "tile_02.png")))
            self.assertEqual(payload["screenshots"][2]["page_state"]["status"], "results_end")
            self.assertEqual(payload["diagnostics"]["capture_stop"]["reason"], "results_end")
            self.assertNotEqual(payload["diagnostics"]["capture_stop"]["reason"], "similar_adjacent_tile")

    def test_similar_tile_helper_keeps_non_capturable_current_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            previous_path = os.path.join(tmp, "tile_00.png")
            current_path = os.path.join(tmp, "tile_01.png")
            Image.new("RGB", (80, 60), (240, 240, 240)).save(previous_path)
            Image.new("RGB", (80, 60), (240, 240, 240)).save(current_path)
            diagnostics = {}

            result = worker._maybe_stop_for_similar_adjacent_tile(
                previous={
                    "tile_id": "tile_00",
                    "path": previous_path,
                    "page_state": {"status": "visible_results"},
                },
                current={
                    "tile_id": "tile_01",
                    "path": current_path,
                    "page_state": {"status": "unknown"},
                },
                capture_plan={},
                diagnostics=diagnostics,
            )

            self.assertFalse(result["stopped"])
            self.assertTrue(os.path.exists(current_path))
            self.assertNotIn("capture_stop", diagnostics)

    def test_keyword_timeout_after_visible_results_keeps_keyword_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": "true"}]},
                ],
            )
            checks = {"count": 0}

            def raise_on_second_check(started, timeout_seconds, keyword):
                checks["count"] += 1
                if checks["count"] >= 2:
                    raise worker.KeywordTimeout("Keyword capture timed out while waiting for MCP request: 万智牌 中止")

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(worker, "_raise_if_keyword_timeout", side_effect=raise_on_second_check):
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
            self.assertEqual(result["stop_reason"], "captured_partial_keyword_timeout")
            self.assertEqual(len(payload["screenshots"]), 1)
            self.assertEqual(
                payload["diagnostics"]["partial_capture_stop"]["reason"],
                "keyword_timeout_after_capturable_tiles",
            )

    def test_mcp_action_failure_after_visible_results_keeps_keyword_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "focused search input"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                ],
            )
            act_results = [
                {"content": [{"type": "text", "text": "search submitted"}]},
                RuntimeError("Replanned 20 times, exceeding the limit."),
            ]

            def call_act_or_raise(*args, **kwargs):
                value = act_results.pop(0)
                if isinstance(value, BaseException):
                    raise value
                return value

            with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None), \
                mock.patch.object(worker, "_call_act", side_effect=call_act_or_raise):
                result = worker._capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id="run",
                    session_index=1,
                    task_dir=tmp,
                    fallback_index=1,
                    tools=["act", "take_screenshot", "Input", "KeyboardPress"],
                )

            payload = worker._read_json(task["result_path"])
            self.assertEqual(result["status"], "captured")
            self.assertEqual(result["stop_reason"], "captured_partial_mcp_action_failed")
            self.assertEqual(len(payload["screenshots"]), 1)
            self.assertEqual(
                payload["diagnostics"]["partial_capture_stop"]["reason"],
                "mcp_action_failed_after_capturable_tiles",
            )

    def test_supervisor_interrupt_after_visible_results_keeps_keyword_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "task-1",
                "keyword_index": 1,
                "keyword": "万智牌 中止",
                "evidence_dir": os.path.join(tmp, "evidence"),
                "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": '{"state":"visible_results","visible_search_keyword":"万智牌 中止","keyword_match":true}'}]},
                    {"content": [{"type": "text", "text": "true"}]},
                ],
            )
            control_responses = [
                {"interrupted": False},
                {"interrupted": True, "status": "paused_needs_supervisor", "reason": "manual_pause"},
            ]

            def interrupt_once_after_tile(*args, **kwargs):
                if control_responses:
                    return control_responses.pop(0)
                return {"interrupted": True, "status": "paused_needs_supervisor", "reason": "manual_pause"}

            with mock.patch.object(worker, "control_interrupt_for_worker", side_effect=interrupt_once_after_tile), \
                mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
            self.assertEqual(payload["status"], "captured")
            self.assertEqual(result["stop_reason"], "captured_partial_supervisor_interrupt")
            self.assertEqual(payload["screenshots"][0]["page_state"]["status"], "visible_results")
            self.assertEqual(
                payload["diagnostics"]["partial_capture_stop"]["reason"],
                "supervisor_interrupt_after_capturable_tiles",
            )

    def test_json_classifier_unparseable_falls_back_to_heuristic(self):
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
                "page_sampling": {"allow_page_state_json_classifier": True},
                "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
            }
            client = FakeClient(
                {"content": [{"type": "text", "text": "search completed"}]},
                classifier_result=[
                    {"content": [{"type": "text", "text": "I can see a shopping page"}]},
                    {"content": [{"type": "text", "text": "true"}]},
                ],
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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            page_state = payload["screenshots"][0]["page_state"]
            self.assertEqual(result["status"], "captured")
            self.assertEqual(page_state["status"], "visible_ready")
            self.assertEqual(page_state["source"], "heuristic")
            self.assertEqual(page_state["fallback_reason"], "classifier_json_unparseable")
            self.assertEqual(page_state["raw_text"], "")

    def test_json_classifier_disabled_does_not_call_json_classifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {"capture_plan": {"max_tiles_per_keyword": 1}}
            client = FakeClient({"content": [{"type": "text", "text": "unused"}]})

            with mock.patch.object(
                worker,
                "_classify_screenshot",
                return_value={
                    "status": "visible_ready",
                    "confidence": 0.72,
                    "reason": "test_visible_results",
                    "metrics": {},
                },
            ):
                page_state = worker._classify_screenshot_page_state(
                    client=client,
                    path=os.path.join(tmp, "tile_00.png"),
                    contract={"page_sampling": {"allow_page_state_json_classifier": False}},
                    capture_plan=task["capture_plan"],
                    tools=[],
                    tile_id="tile_00",
                    keyword="万智牌 中止",
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 30,
                    timeout_seconds=1.0,
                )

            self.assertEqual(page_state["source"], "heuristic")
            self.assertEqual(page_state["fallback_reason"], "classifier_disabled")
            self.assertEqual([call["name"] for call in client.calls], [])
            self.mock_classifier.assert_not_called()

    def test_json_classifier_unavailable_falls_back_to_heuristic(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, "tile_00.png")
            FakeClient({"content": [{"type": "text", "text": "unused"}]}).capture_screenshot(image_path)
            self.mock_classifier.side_effect = page_state_classifier.PageStateClassifierUnavailable(
                "classifier_api_key_missing"
            )

            page_state = worker._classify_screenshot_page_state(
                client=FakeClient({"content": [{"type": "text", "text": "unused"}]}),
                path=image_path,
                contract={"page_sampling": {"allow_page_state_json_classifier": True}},
                capture_plan={},
                tools=[],
                tile_id="tile_00",
                keyword="万智牌 中止",
                interrupt_check=None,
                keyword_deadline=time.monotonic() + 30,
                timeout_seconds=1.0,
            )

            self.assertEqual(page_state["source"], "heuristic")
            self.assertEqual(page_state["fallback_reason"], "classifier_api_key_missing")
            self.assertEqual(page_state["classifier_diagnostics"]["tile_id"], "tile_00")

    def test_json_classifier_string_false_disables_classifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient({"content": [{"type": "text", "text": "unused"}]})

            with mock.patch.object(
                worker,
                "_classify_screenshot",
                return_value={
                    "status": "visible_ready",
                    "confidence": 0.72,
                    "reason": "test_visible_results",
                    "metrics": {},
                },
            ):
                page_state = worker._classify_screenshot_page_state(
                    client=client,
                    path=os.path.join(tmp, "tile_00.png"),
                    contract={"page_sampling": {"allow_page_state_json_classifier": "false"}},
                    capture_plan={},
                    tools=[],
                    tile_id="tile_00",
                    keyword="万智牌 中止",
                    interrupt_check=None,
                    keyword_deadline=time.monotonic() + 30,
                    timeout_seconds=1.0,
                )

            self.assertEqual(page_state["fallback_reason"], "classifier_disabled")
            self.assertEqual([call["name"] for call in client.calls], [])

    def test_json_classifier_abnormal_states_do_not_capture(self):
        for state in (
            "unknown",
            "login_required",
            "captcha_required",
            "risk_suspected",
            "popup_blocked",
            "white_skeleton",
        ):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                task = {
                    "task_id": "task-1",
                    "keyword_index": 1,
                    "keyword": "万智牌 中止",
                    "evidence_dir": os.path.join(tmp, "evidence"),
                    "result_path": os.path.join(tmp, "evidence", "keyword_result.json"),
                    "abnormal_screenshot_path": os.path.join(tmp, "evidence", "abnormal.png"),
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
                    "page_sampling": {"allow_page_state_json_classifier": True},
                    "hard_stop_policy": {"timeout_per_keyword_seconds": 30},
                }
                if state == "unknown":
                    probe_results = [
                        {"content": [{"type": "text", "text": '{"state":"unknown"}'}]},
                        {"content": [{"type": "text", "text": '{"state":"unknown"}'}]},
                    ]
                else:
                    probe_results = [
                        {"content": [{"type": "text", "text": f'{{"state":"{state}"}}'}]},
                        {"content": [{"type": "text", "text": f'{{"state":"{state}"}}'}]},
                    ]
                client = FakeClient(
                    {"content": [{"type": "text", "text": "search completed"}]},
                    classifier_result=probe_results,
                )

                with mock.patch.object(worker, "control_interrupt_for_worker", return_value={"interrupted": False}), \
                    mock.patch.object(worker, "_interruptible_sleep", return_value=None), \
                    mock.patch.object(worker, "_sleep_micro_pause", return_value=None):
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
                self.assertNotEqual(payload["status"], "captured")
                self.assertEqual(payload["screenshots"][0]["page_state"]["status"], state)
                if state == "unknown":
                    self.assertEqual(result["stop_reason"], "manual_review_needed")
                else:
                    self.assertEqual(result["stop_reason"], state)

    def test_json_classifier_natural_language_is_unparseable(self):
        self.assertEqual(
            _parse_test_page_state_text("The page is not login_required and no captcha is visible."),
            "",
        )

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
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["test_results_layout"],
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
            search_act = payload["diagnostics"]["keyword_search"]
            self.assertTrue(search_act["http_429_detected"])
            excerpt = search_act["rate_limit_diagnostics"][0]["excerpt"]
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

    def test_heartbeat_sync_runs_even_when_control_is_cooling_down(self):
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
            plan = {
                "plan_id": run_id,
                "selected_count": 1,
                "daily_keyword_budget": 1,
                "daily_session_count": 1,
                "task_dir": task_dir,
                "manifest_path": os.path.join(task_dir, "visual_tasks.json"),
            }
            control = {
                "schema": "taobao_visual_control_v1",
                "plan_id": run_id,
                "status": "cooling_down",
                "reason": "capture_worker:manual_review_needed",
                "stop_requested": False,
                "locked": False,
                "cooldown_until": (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds"),
                "sessions": {
                    "1": {
                        "status": "cooling_down",
                        "reason": "capture_worker:manual_review_needed",
                    }
                },
            }
            keyword_result = {
                "schema": "taobao_visual_capture_keyword_result_v1",
                "keyword": "万智牌 中止",
                "status": "needs_review",
                "rough_state": "unknown",
                "stop_reason": "manual_review_needed",
                "screenshots": [],
            }
            worker._write_json(os.path.join(task_dir, "visual_tasks.json"), manifest)
            worker._write_json(os.path.join(task_dir, "daily_plan.json"), plan)
            worker._write_json(os.path.join(task_dir, "control.json"), control)
            worker._write_json(os.path.join(evidence_dir, "keyword_result.json"), keyword_result)
            worker._write_json(
                os.path.join(session_dir, "session_worker_result.json"),
                {"status": "needs_review", "stop_reason": "manual_review_needed"},
            )

            with mock.patch.object(visual_scheduler, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_control, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_pipeline, "get_project_root", return_value=tmp), \
                mock.patch.object(visual_scheduler, "session_dir_for", return_value=session_dir), \
                mock.patch.object(visual_control, "session_dir_for", return_value=session_dir), \
                mock.patch("modules.visual_pipeline.session_dir_for", return_value=session_dir):
                result = visual_scheduler.heartbeat_daily_collection(
                    plan_id=run_id,
                    session_index=1,
                    mode="sync",
                )

            self.assertEqual(result["action"], "paused")
            self.assertEqual(result["reason"], "cooling_down")
            self.assertEqual(result["sync"][0]["updated"], 1)
            updated_manifest = worker._read_json(os.path.join(task_dir, "visual_tasks.json"))
            self.assertEqual(updated_manifest["records"][0]["status"], "needs_review")
            self.assertEqual(updated_manifest["records"][0]["failure_reason"], "manual_review_needed")

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
