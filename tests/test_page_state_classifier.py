import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from modules import page_state_classifier


class PageStateClassifierTests(unittest.TestCase):
    def test_read_env_file_accepts_export_prefixed_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "midscene-computer.env"
            env_path.write_text(
                'export MIDSCENE_MODEL_API_KEY="secret-value"\n'
                "MIDSCENE_MODEL_NAME=glm-4.6v-flashx\n",
                encoding="utf-8",
            )

            values = page_state_classifier._read_env_file(env_path)

            self.assertEqual(values["MIDSCENE_MODEL_API_KEY"], "secret-value")
            self.assertEqual(values["MIDSCENE_MODEL_NAME"], "glm-4.6v-flashx")

    def test_safe_url_error_reason_does_not_include_secret_details(self):
        exc = urllib.error.URLError(
            Exception("[SSL: CERTIFICATE_VERIFY_FAILED] bearer secret-token")
        )

        reason = page_state_classifier._safe_url_error_reason(exc)

        self.assertEqual(reason, "Exception:certificate_verify_failed")
        self.assertNotIn("secret-token", reason)

    def test_parse_json_object_accepts_wrapped_model_text(self):
        parsed = page_state_classifier._parse_json_object(
            '```json\n{"state":"visible_results","keyword_match":"true"}\n```'
        )

        self.assertEqual(parsed["state"], "visible_results")
        self.assertEqual(parsed["keyword_match"], "true")

    def test_normalize_classifier_payload_clamps_and_parses_optional_bool(self):
        payload = page_state_classifier._normalize_classifier_payload(
            {
                "state": "visible_results",
                "confidence": 1.5,
                "reason": "readable listings",
                "visible_search_keyword": "万智牌 中止",
                "keyword_match": "yes",
                "search_box_text_kind": "typed_value",
            },
            raw_text="{}",
        )

        self.assertEqual(payload["status"], "visible_results")
        self.assertEqual(payload["confidence"], 1.0)
        self.assertEqual(payload["visible_search_keyword"], "万智牌 中止")
        self.assertTrue(payload["keyword_match"])
        self.assertEqual(payload["search_box_text_kind"], "actual_input")

    def test_normalize_classifier_payload_accepts_closeable_popup_overlay(self):
        payload = page_state_classifier._normalize_classifier_payload(
            {
                "state": "closeable_popup_overlay",
                "confidence": 0.88,
                "reason": "dimmed Taobao page with a normal modal and gray X close control",
            },
            raw_text="{}",
        )

        self.assertEqual(payload["status"], "closeable_popup_overlay")
        self.assertEqual(payload["confidence"], 0.88)

    def test_request_payload_describes_closeable_popup_overlay_boundary(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            f.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
                b"\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            f.flush()

            payload = page_state_classifier._request_payload(
                model="glm-4.6v-flashx",
                image_path=Path(f.name),
                keyword="万智牌 中止",
                temperature=0,
            )

        prompt = payload["messages"][0]["content"][0]["text"]
        self.assertIn("closeable_popup_overlay", prompt)
        self.assertIn("gray X close control", prompt)
        self.assertIn("Do not use closeable_popup_overlay for login", prompt)
        self.assertIn("search_box_text_kind", prompt)
        self.assertIn("normal homepage/search-entry surface", prompt)
        self.assertIn("should not prevent visible_ready", prompt)
        self.assertIn("keyword content mainly matters on results/search_results/results_end", prompt)

    def test_extract_message_content_accepts_text_parts(self):
        content = page_state_classifier._extract_message_content(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"state":"'},
                                {"type": "text", "text": 'unknown"}'},
                            ]
                        }
                    }
                ]
            }
        )

        self.assertEqual(content, '{"state":"unknown"}')

    def test_http_429_surfaces_status_without_response_body_or_secret(self):
        request_url = "https://example.test/chat/completions"
        error = urllib.error.HTTPError(
            request_url,
            429,
            "Too Many Requests bearer secret-token",
            hdrs=None,
            fp=None,
        )

        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(page_state_classifier.PageStateClassifierUnavailable) as ctx:
                page_state_classifier._post_chat_completion(
                    base_url="https://example.test",
                    api_key="secret-token",
                    payload={"messages": []},
                    timeout_seconds=1,
                )

        self.assertEqual(str(ctx.exception), "classifier_http_429")
        self.assertNotIn("secret-token", str(ctx.exception))

    def test_chat_completions_url_does_not_duplicate_suffix(self):
        self.assertEqual(
            page_state_classifier._chat_completions_url("https://example.test/chat/completions"),
            "https://example.test/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
