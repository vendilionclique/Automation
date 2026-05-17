import unittest

from modules.visual_goal_contract import (
    ACCEPT,
    ACCEPT_END,
    REPAIR,
    REPAIR_CLOSE_NON_ACCOUNT_POPUP,
    REPAIR_HOME_ENTRY,
    SCHEMA,
    STOP,
    build_evidence_check,
    build_goal_contract,
    gate_evidence_check,
    normalize_evidence_check,
    normalize_evidence_check_json,
    python_gate_decision,
    parse_evidence_check_text,
    validate_evidence_check,
)


class VisualGoalContractTests(unittest.TestCase):
    def test_goal_met_accepts_current_keyword_results(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        check = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": True,
                "page_kind": "results_page",
                "keyword_match": "matched",
                "visible_search_keyword": "MTG Counterspell",
                "search_box_text_kind": "actual_input",
                "search_submitted": True,
                "is_home_feed": False,
                "result_page_evidence": ["sort/filter bar"],
                "recommended_next": "accept",
                "confidence": 0.9,
            }
        )

        decision = gate_evidence_check(check, contract, stage="BOUNDARY_VERIFY")

        self.assertEqual(decision["action"], ACCEPT)

    def test_boundary_verify_requires_submitted_search_not_home_feed(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        check = build_evidence_check(
            {
                "keyword": "MTG Counterspell",
                "goal_state": "BOUNDARY_VERIFY",
                "observation": {
                    "page_state": {
                        "status": "visible_results",
                        "visible_search_keyword": "MTG Counterspell",
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": False,
                        "is_home_feed": True,
                        "result_page_evidence": [],
                    },
                    "verification": {"screenshot_keyword": {"status": "matched"}},
                },
            }
        )

        decision = gate_evidence_check(check, contract, stage="BOUNDARY_VERIFY")

        self.assertFalse(check["goal_met"])
        self.assertEqual(check["recommended_next"], REPAIR)
        self.assertEqual(check["reason"], "search_submit_unconfirmed")
        self.assertNotEqual(decision["action"], ACCEPT)

    def test_old_keyword_repairs_once_then_stops(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        check = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": False,
                "page_kind": "results_page",
                "keyword_match": "mismatched",
                "visible_search_keyword": "MTG Lightning Bolt",
                "recommended_next": "repair",
                "confidence": 0.9,
            }
        )

        first = gate_evidence_check(check, contract, stage="BOUNDARY_VERIFY")
        second = gate_evidence_check(
            check,
            contract,
            history=[{"repair_action": REPAIR_HOME_ENTRY}],
            stage="BOUNDARY_VERIFY",
        )

        self.assertEqual(first["action"], REPAIR)
        self.assertEqual(first["repair_action"], REPAIR_HOME_ENTRY)
        self.assertEqual(second["action"], STOP)
        self.assertIn("repair_budget_exhausted", second["reason"])

    def test_results_end_accepts_end_in_capture(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        check = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": False,
                "page_kind": "results_end",
                "keyword_match": "unreadable",
                "recommended_next": "accept_end",
                "confidence": 0.8,
            }
        )

        decision = gate_evidence_check(check, contract, stage="CAPTURING")

        self.assertEqual(decision["action"], ACCEPT_END)

    def test_hard_abnormal_stops(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        check = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": False,
                "page_kind": "captcha_required",
                "blocking_reason": "captcha_required",
                "recommended_next": "stop",
                "confidence": 0.9,
            }
        )

        decision = gate_evidence_check(check, contract, stage="BOUNDARY_VERIFY")

        self.assertEqual(decision["action"], STOP)
        self.assertEqual(decision["terminal_status"], "needs_review")

    def test_closeable_popup_overlay_repairs_once_but_popup_blocked_stops(self):
        contract = build_goal_contract(keyword="MTG Counterspell")
        closeable = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": False,
                "page_kind": "closeable_popup_overlay",
                "blocking_reason": "closeable_popup_overlay",
                "recommended_next": "repair",
                "confidence": 0.9,
            }
        )
        blocked = normalize_evidence_check(
            {
                "schema": "taobao_goal_evidence_check_v1",
                "goal_met": False,
                "page_kind": "popup_blocked",
                "blocking_reason": "popup_blocked",
                "recommended_next": "stop",
                "confidence": 0.9,
            }
        )

        first = gate_evidence_check(closeable, contract, stage="BOUNDARY_VERIFY")
        second = gate_evidence_check(
            closeable,
            contract,
            history=[{"repair_action": REPAIR_CLOSE_NON_ACCOUNT_POPUP}],
            stage="BOUNDARY_VERIFY",
        )
        hard_stop = gate_evidence_check(blocked, contract, stage="BOUNDARY_VERIFY")

        self.assertEqual(first["action"], REPAIR)
        self.assertEqual(first["repair_action"], REPAIR_CLOSE_NON_ACCOUNT_POPUP)
        self.assertEqual(second["action"], STOP)
        self.assertEqual(hard_stop["action"], STOP)

    def test_parse_unstructured_text_stops(self):
        check = parse_evidence_check_text("I see a normal shopping page.")

        self.assertFalse(check["valid"])
        self.assertEqual(check["recommended_next"], STOP)

    def test_build_evidence_check_from_existing_observation(self):
        check = build_evidence_check(
            {
                "keyword": "MTG Counterspell",
                "goal_state": "BOUNDARY_VERIFY",
                "observation": {
                    "page_state": {
                        "status": "visible_results",
                        "visible_search_keyword": "MTG Counterspell",
                        "keyword_match": True,
                        "search_box_text_kind": "actual_input",
                        "search_submitted": True,
                        "is_home_feed": False,
                        "result_page_evidence": ["sort/filter bar"],
                    },
                    "verification": {"screenshot_keyword": {"status": "matched"}},
                },
            }
        )

        self.assertTrue(check["goal_met"])
        self.assertEqual(check["recommended_next"], ACCEPT)

    def test_user_schema_normalize_validate_and_accept(self):
        check = normalize_evidence_check_json(
            {
                "schema": SCHEMA,
                "goal_met": True,
                "page_kind": "search_results",
                "keyword_match": True,
                "visible_search_keyword": "MTG Black Lotus",
                "search_box_text_kind": "actual_input",
                "blocking_reason": "none",
                "recommended_next": "accept",
                "confidence": "0.91",
                "reason": "visible result page matches",
            }
        )

        valid, errors = validate_evidence_check(check)
        decision = python_gate_decision(check, {"min_confidence": 0.7})

        self.assertTrue(valid, errors)
        self.assertEqual(decision["decision"], ACCEPT)

    def test_user_schema_invalid_json_and_low_confidence_need_review(self):
        invalid = normalize_evidence_check_json("not json")
        invalid_decision = python_gate_decision("not json")
        low_confidence = python_gate_decision(
            {
                "schema": SCHEMA,
                "goal_met": True,
                "page_kind": "search_results",
                "keyword_match": True,
                "visible_search_keyword": "MTG Black Lotus",
                "search_box_text_kind": "actual_input",
                "blocking_reason": "none",
                "recommended_next": "accept",
                "confidence": 0.2,
                "reason": "too blurry",
            },
            {"min_confidence": 0.7},
        )

        self.assertEqual(invalid["blocking_reason"], "json_invalid")
        self.assertEqual(invalid_decision["decision"], "needs_review")
        self.assertEqual(invalid_decision["blocking_reason"], "json_invalid")
        self.assertEqual(low_confidence["decision"], "needs_review")
        self.assertEqual(low_confidence["blocking_reason"], "low_confidence")

    def test_user_schema_repair_budget_and_capture_results_end(self):
        repair_check = {
            "schema": SCHEMA,
            "goal_met": False,
            "page_kind": "search_results",
            "keyword_match": False,
            "visible_search_keyword": "MTG Lightning Bolt",
            "blocking_reason": "none",
            "recommended_next": "repair",
            "confidence": 0.88,
            "reason": "old keyword is visible",
        }
        results_end_check = {
            "schema": SCHEMA,
            "goal_met": True,
            "page_kind": "results_end",
            "keyword_match": False,
            "visible_search_keyword": "",
            "blocking_reason": "none",
            "recommended_next": "end",
            "confidence": 0.83,
            "reason": "bottom pagination and footer are visible",
        }

        repair = python_gate_decision(repair_check, {"max_repairs": 1}, {"repairs_used": 0})
        exhausted = python_gate_decision(repair_check, {"max_repairs": 1}, {"repairs_used": 1})
        accept_end = python_gate_decision(results_end_check, {}, {"stage": "capture"})

        self.assertEqual(repair["decision"], REPAIR)
        self.assertEqual(exhausted["decision"], STOP)
        self.assertEqual(accept_end["decision"], ACCEPT_END)


if __name__ == "__main__":
    unittest.main()
