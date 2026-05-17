"""Lightweight goal contract and VLM evidence-check gate.

The VLM remains responsible for judging the visible page. Python only keeps the
current goal, validates the VLM's structured answer, enforces retry budgets, and
decides whether to accept, repair once, or stop.
"""
import json
import re
from typing import Any, Dict, Iterable, List, Optional


GOAL_CONTRACT_SCHEMA = "taobao_keyword_goal_contract_v1"
EVIDENCE_CHECK_SCHEMA = "taobao_goal_evidence_check_v1"
CAPTURE_DECISION_SCHEMA = "taobao_capture_gate_decision_v1"
SCHEMA = GOAL_CONTRACT_SCHEMA

ACCEPT = "accept"
ACCEPT_END = "accept_end"
REPAIR = "repair"
STOP = "stop"
NEEDS_REVIEW = "needs_review"

REPAIR_HOME_ENTRY = "repair_home_entry"
REPAIR_FOREGROUND = "repair_foreground"
REPAIR_REFRESH_VISIBLE_PAGE = "repair_refresh_visible_page"
REPAIR_CLOSE_NON_ACCOUNT_POPUP = "repair_close_non_account_popup"

EVIDENCE_FIELDS = (
    "schema",
    "goal_met",
    "page_kind",
    "keyword_match",
    "visible_search_keyword",
    "blocking_reason",
    "recommended_next",
    "confidence",
    "reason",
)

USER_BLOCKING_REASONS = {
    "",
    "none",
    "login",
    "login_required",
    "captcha",
    "captcha_required",
    "risk",
    "risk_suspected",
    "permission",
    "permission_panel",
    "unknown",
    "json_invalid",
    "low_confidence",
    "chrome_not_foreground",
    "popup_blocked",
    "white_skeleton",
}

HARD_GATE_BLOCKERS = {
    "login",
    "login_required",
    "captcha",
    "captcha_required",
    "risk",
    "risk_suspected",
    "permission",
    "permission_panel",
}

REVIEW_GATE_BLOCKERS = {
    "unknown",
    "json_invalid",
    "low_confidence",
    "chrome_not_foreground",
    "popup_blocked",
    "white_skeleton",
}

BLOCKING_STOP_REASONS = {
    "login_required",
    "captcha_required",
    "captcha_or_risk",
    "risk_suspected",
    "automation_permission_blocked",
    "permission_panel",
    "rate_limited",
    "account_state_changed_or_unusual",
    "popup_blocked",
}
REFRESH_REPAIR_REASONS = {"white_skeleton", "page_not_loaded", "loading_failed"}
FOREGROUND_REPAIR_REASONS = {"chrome_not_foreground"}
POPUP_REPAIR_REASONS = {"closeable_popup_overlay", "non_account_popup"}
CAPTURABLE_PAGE_KINDS = {"results_page", "search_results", "visible_results", "empty_result", "results_end"}


def build_goal_contract(
    request: Optional[Dict[str, Any]] = None,
    keyword: str = "",
    budgets: Optional[Dict[str, int]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    if isinstance(request, dict):
        keyword = str(request.get("keyword") or keyword or "")
        task = request.get("task") or {}
        contract = request.get("contract") or {}
        capture_plan = request.get("capture_plan") or {}
        keyword_index = request.get("keyword_index")
    else:
        task = kwargs.get("task") or {}
        contract = kwargs.get("contract") or {}
        capture_plan = kwargs.get("capture_plan") or {}
        keyword_index = kwargs.get("keyword_index")
        if isinstance(keyword, dict) and budgets is None:
            budgets = keyword
            keyword = str(request or "")
        if not keyword and request is not None:
            keyword = str(request)
    budgets = budgets or {}
    repair_budget = {
        "foreground": 2,
        "home_entry": 1,
        "refresh": 1,
        "popup": 1,
    }
    for key, value in budgets.items():
        if key in repair_budget:
            try:
                repair_budget[key] = max(0, int(value))
            except (TypeError, ValueError):
                pass
    return {
        "schema": GOAL_CONTRACT_SCHEMA,
        "keyword": str(keyword or ""),
        "keyword_index": keyword_index,
        "task_id": task.get("task_id") or "",
        "run_id": contract.get("run_id") or "",
        "session_index": contract.get("session_index") or 0,
        "goal": "reach_current_keyword_taobao_results_from_visible_home_search_entry",
        "success_evidence": [
            "chrome_or_taobao_related_foreground",
            "taobao_results_or_empty_results_page",
            "visible evidence belongs to current keyword",
            "no login captcha risk white skeleton permission panel or account-state-changing popup",
        ],
        "forbidden": [
            "do not accept an old-keyword results page as current keyword evidence",
            "do not automate login captcha security verification permissions cart favorite checkout rewards",
            "do not read DOM HTML network cookies storage or hidden page data",
        ],
        "evidence_check_schema": list(EVIDENCE_FIELDS),
        "budgets": {
            "min_confidence": _float_or_default(budgets.get("min_confidence"), 0.7),
            "max_repairs": max(0, int(_float_or_default(budgets.get("max_repairs"), 1.0))),
        },
        "repair_budget": repair_budget,
        "capture_plan": {
            "max_tiles_per_keyword": capture_plan.get("max_tiles_per_keyword"),
            "tile_scroll_distance_px": capture_plan.get("tile_scroll_distance_px"),
        },
    }


def build_evidence_check(request: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
    data = request if isinstance(request, dict) else kwargs
    keyword = str(data.get("keyword") or "")
    goal_state = str(data.get("goal_state") or "")
    observation = data.get("observation") or {}
    page_state = observation.get("page_state") or {}
    verification = observation.get("verification") or {}
    screenshot_keyword = verification.get("screenshot_keyword") or {}
    keyword_status = str(screenshot_keyword.get("status") or "")
    page_kind = _page_kind_from_state(str(page_state.get("status") or verification.get("rough_state") or "unknown"))
    keyword_match = _keyword_match_from_page_state(page_state, keyword_status)
    blocking_reason = _blocking_reason_from_page_kind(page_kind)
    goal_met = (
        goal_state == "BOUNDARY_VERIFY"
        and page_kind in CAPTURABLE_PAGE_KINDS
        and keyword_match == "matched"
        and not blocking_reason
    ) or (
        goal_state == "CAPTURING"
        and page_kind in CAPTURABLE_PAGE_KINDS
        and keyword_match != "mismatched"
        and not blocking_reason
    )
    if page_kind == "results_end" and goal_state == "CAPTURING":
        recommended_next = ACCEPT_END
    elif goal_met:
        recommended_next = ACCEPT
    elif blocking_reason in BLOCKING_STOP_REASONS or page_kind == "unknown":
        recommended_next = STOP
    else:
        recommended_next = REPAIR
    check = normalize_evidence_check(
        {
            "schema": EVIDENCE_CHECK_SCHEMA,
            "goal_met": goal_met,
            "page_kind": page_kind,
            "keyword_match": keyword_match,
            "visible_search_keyword": page_state.get("visible_search_keyword") or "",
            "blocking_reason": blocking_reason,
            "recommended_next": recommended_next,
            "confidence": page_state.get("confidence", 0.8 if page_kind != "unknown" else 0.0),
            "reason": _evidence_reason(keyword, page_kind, keyword_match, blocking_reason),
        }
    )
    check["keyword"] = keyword
    check["goal_state"] = goal_state
    check["tile_id"] = observation.get("tile_id") or ""
    check["stage"] = observation.get("stage") or ""
    check["screenshot_path"] = observation.get("screenshot_path") or ""
    return check


def decide_capture_gate(request: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
    data = request if isinstance(request, dict) else kwargs
    goal_state = str(data.get("goal_state") or "")
    evidence_check = data.get("evidence_check") or {}
    goal_contract = data.get("goal_contract") or {}
    history: List[Dict[str, Any]] = []
    if data.get("repair_attempted"):
        history.append({"repair_action": REPAIR_HOME_ENTRY})
    gate = gate_evidence_check(
        evidence_check,
        goal_contract,
        history=history,
        stage=goal_state,
        min_confidence=0.0,
    )
    action = gate["action"]
    if action == ACCEPT_END:
        decision = "keyword_end"
        gate_decision = "accept"
    elif action == ACCEPT:
        decision = "continue_capture"
        gate_decision = "accept"
    elif action == REPAIR:
        decision = "repair_once"
        gate_decision = "repair_once"
    else:
        decision = "blocked"
        gate_decision = "stop"
    return {
        "decision": decision,
        "gate_decision": gate_decision,
        "reason": gate.get("reason") or "",
        "repair_action": gate.get("repair_action") or "",
        "terminal_status": gate.get("terminal_status") or "",
        "evidence_check_status": evidence_check.get("recommended_next") or "",
        "observed_state": evidence_check.get("page_kind") or "",
        "tile_id": (data.get("observation") or {}).get("tile_id") or "",
    }


def build_evidence_check_prompt(
    goal_contract: Dict[str, Any],
    stage: str,
    tile_id: str = "",
    tile: str = "",
) -> str:
    keyword = str(goal_contract.get("keyword") or "")
    contract_json = json.dumps(goal_contract, ensure_ascii=False, sort_keys=True)
    tile_value = tile_id or tile
    return (
        "Using only the current visible screenshot, judge whether this screenshot satisfies the "
        "Taobao visual capture goal. You are the visual evidence checker, not a product extractor. "
        f"Goal contract JSON: {contract_json}. "
        f"Current stage: {stage}. Current tile: {tile_value}. stage: {stage}. tile: {tile_value}. "
        f"Current keyword: {keyword!r}. "
        "Return only compact JSON with this exact schema: "
        '{"schema":"taobao_goal_evidence_check_v1","goal_met":false,'
        '"page_kind":"unknown","keyword_match":false,"visible_search_keyword":"",'
        '"blocking_reason":"unknown","recommended_next":"needs_review","confidence":0.0,"reason":""}. '
        "page_kind must be one of chrome_not_foreground, results_page, results_end, empty_result, "
        "login_required, captcha_required, risk_suspected, popup_blocked, closeable_popup_overlay, white_skeleton, "
        "permission_panel, unknown. keyword_match may be true or false. "
        "recommended_next must be accept, repair, stop, needs_review, or accept_end. "
        "Set goal_met true only when the visible page clearly satisfies the current keyword goal. "
        "For capture-stage bottom/footer/pagination views use recommended_next accept_end. "
        "If login, captcha, security/risk warning, account popup, permission panel, non-Chrome "
        "foreground, white skeleton, or unknown page appears, set goal_met false and explain the "
        "blocking_reason. Do not output item titles, prices, shop names, or product rows."
    )


def parse_evidence_check_text(text: str) -> Dict[str, Any]:
    raw_text = str(text or "")
    parsed: Dict[str, Any] = {}
    try:
        parsed_value = json.loads(raw_text)
        if isinstance(parsed_value, dict):
            parsed = parsed_value
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if match:
            try:
                parsed_value = json.loads(match.group(0))
                if isinstance(parsed_value, dict):
                    parsed = parsed_value
            except (TypeError, ValueError):
                parsed = {}
    if not parsed:
        return {
            "schema": EVIDENCE_CHECK_SCHEMA,
            "valid": False,
            "goal_met": False,
            "page_kind": "unknown",
            "keyword_match": "unreadable",
            "visible_search_keyword": "",
            "blocking_reason": "evidence_check_unparseable",
            "recommended_next": STOP,
            "confidence": 0.0,
            "reason": "VLM evidence check did not return parseable JSON.",
            "raw_text": raw_text,
        }
    return normalize_evidence_check(parsed, raw_text=raw_text)


def normalize_evidence_check(payload: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    page_kind = _normalize_choice(
        payload.get("page_kind") or payload.get("state") or payload.get("status"),
        {
            "chrome_not_foreground",
            "results_page",
            "results_end",
            "empty_result",
            "login_required",
            "captcha_required",
            "risk_suspected",
            "popup_blocked",
            "closeable_popup_overlay",
            "white_skeleton",
            "permission_panel",
            "rate_limited",
            "unknown",
            "visible_results",
            "search_results",
        },
        "unknown",
    )
    keyword_match = _normalize_choice(
        payload.get("keyword_match"),
        {"matched", "mismatched", "unreadable", "not_visible"},
        _keyword_match_from_bool(payload.get("keyword_match")),
    )
    blocking_reason = str(payload.get("blocking_reason") or "").strip()
    if blocking_reason.lower() in {"none", "no", "null"}:
        blocking_reason = ""
    if blocking_reason == "none":
        blocking_reason = ""
    if not blocking_reason:
        blocking_reason = _blocking_reason_from_page_kind(page_kind)
    recommended_next = _normalize_choice(
        payload.get("recommended_next"),
        {ACCEPT, REPAIR, STOP, ACCEPT_END},
        _recommended_next_from_payload(payload, page_kind, keyword_match, blocking_reason),
    )
    confidence = _float_or_zero(payload.get("confidence"))
    goal_met = _bool_value(payload.get("goal_met"))
    if page_kind in CAPTURABLE_PAGE_KINDS and keyword_match == "matched" and not blocking_reason:
        goal_met = bool(goal_met)
    elif page_kind == "results_end" and not blocking_reason:
        goal_met = bool(goal_met)
    else:
        goal_met = False
    return {
        "schema": EVIDENCE_CHECK_SCHEMA,
        "valid": str(payload.get("schema") or EVIDENCE_CHECK_SCHEMA) == EVIDENCE_CHECK_SCHEMA,
        "goal_met": goal_met,
        "page_kind": page_kind,
        "keyword_match": keyword_match,
        "visible_search_keyword": str(payload.get("visible_search_keyword") or ""),
        "blocking_reason": blocking_reason,
        "recommended_next": recommended_next,
        "confidence": confidence,
        "reason": str(payload.get("reason") or ""),
        "raw_text": raw_text,
    }


def gate_evidence_check(
    check: Dict[str, Any],
    goal_contract: Dict[str, Any],
    history: Optional[Iterable[Dict[str, Any]]] = None,
    stage: str = "boundary",
    min_confidence: float = 0.5,
) -> Dict[str, Any]:
    counts = _repair_counts(history or [])
    budget = goal_contract.get("repair_budget") or {}
    page_kind = str(check.get("page_kind") or "unknown")
    blocking_reason = str(check.get("blocking_reason") or "")
    recommended_next = str(check.get("recommended_next") or STOP)
    confidence = _float_or_zero(check.get("confidence"))
    valid = bool(check.get("valid", True))

    if not valid:
            return _decision(STOP, "invalid_evidence_check_json", stage, terminal_status=NEEDS_REVIEW)
    if confidence < min_confidence:
        return _decision(STOP, "low_confidence_evidence_check", stage, terminal_status=NEEDS_REVIEW)
    if blocking_reason in BLOCKING_STOP_REASONS or page_kind in BLOCKING_STOP_REASONS:
        return _decision(STOP, blocking_reason or page_kind, stage, terminal_status=NEEDS_REVIEW)
    if stage == "BOUNDARY_VERIFY" and page_kind == "results_end" and not check.get("goal_met"):
        repair_action = REPAIR_HOME_ENTRY
        key = _budget_key(repair_action)
        if counts.get(key, 0) < int(budget.get(key, 0)):
            return _decision(REPAIR, f"repair_allowed:{repair_action}", stage, repair_action=repair_action)
        return _decision(STOP, f"repair_budget_exhausted:{repair_action}", stage, terminal_status=NEEDS_REVIEW)
    if stage == "CAPTURING" and (recommended_next == ACCEPT_END or page_kind == "results_end"):
        return _decision(ACCEPT_END, "results_end", "keyword_end", terminal_status="captured")
    if (
        stage == "CAPTURING"
        and page_kind in CAPTURABLE_PAGE_KINDS
        and str(check.get("keyword_match") or "") != "mismatched"
        and not blocking_reason
    ):
        return _decision(ACCEPT, "capture_tile_still_capturable", "capture")
    if check.get("goal_met") and recommended_next == ACCEPT and not blocking_reason:
        return _decision(ACCEPT, "goal_met", "capture")
    repair_action = _repair_action_for(check)
    if recommended_next == REPAIR or repair_action:
        repair_action = repair_action or REPAIR_HOME_ENTRY
        key = _budget_key(repair_action)
        if counts.get(key, 0) < int(budget.get(key, 0)):
            return _decision(REPAIR, f"repair_allowed:{repair_action}", stage, repair_action=repair_action)
        return _decision(STOP, f"repair_budget_exhausted:{repair_action}", stage, terminal_status=NEEDS_REVIEW)
    return _decision(STOP, blocking_reason or "goal_not_met", stage, terminal_status=NEEDS_REVIEW)


def _decision(
    action: str,
    reason: str,
    stage_after: str,
    repair_action: str = "",
    terminal_status: str = "",
) -> Dict[str, Any]:
    return {
        "schema": CAPTURE_DECISION_SCHEMA,
        "action": action,
        "reason": reason,
        "stage_after": stage_after,
        "repair_action": repair_action,
        "terminal_status": terminal_status,
    }


def _repair_action_for(check: Dict[str, Any]) -> str:
    page_kind = str(check.get("page_kind") or "")
    reason = str(check.get("blocking_reason") or "")
    if page_kind in FOREGROUND_REPAIR_REASONS or reason in FOREGROUND_REPAIR_REASONS:
        return REPAIR_FOREGROUND
    if page_kind in REFRESH_REPAIR_REASONS or reason in REFRESH_REPAIR_REASONS:
        return REPAIR_REFRESH_VISIBLE_PAGE
    if page_kind in POPUP_REPAIR_REASONS or reason in POPUP_REPAIR_REASONS:
        raw = " ".join([str(check.get("raw_text") or ""), str(check.get("reason") or "")]).lower()
        if any(token in raw for token in ["login", "captcha", "risk", "security"]):
            return ""
        return REPAIR_CLOSE_NON_ACCOUNT_POPUP
    if check.get("keyword_match") in {"mismatched", "unreadable", "not_visible"}:
        return REPAIR_HOME_ENTRY
    return ""


def _repair_counts(history: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"foreground": 0, "home_entry": 0, "refresh": 0, "popup": 0}
    for item in history:
        action = str(item.get("repair_action") or "")
        key = _budget_key(action)
        if key in counts:
            counts[key] += 1
    return counts


def _budget_key(repair_action: str) -> str:
    return {
        REPAIR_FOREGROUND: "foreground",
        REPAIR_HOME_ENTRY: "home_entry",
        REPAIR_REFRESH_VISIBLE_PAGE: "refresh",
        REPAIR_CLOSE_NON_ACCOUNT_POPUP: "popup",
    }.get(repair_action, "")


def _keyword_match_from_bool(value: Any) -> str:
    if value is True:
        return "matched"
    if value is False:
        return "mismatched"
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "matched", "match"}:
        return "matched"
    if text in {"false", "no", "mismatch", "mismatched"}:
        return "mismatched"
    return "unreadable"


def _recommended_next_from_payload(
    payload: Dict[str, Any],
    page_kind: str,
    keyword_match: str,
    blocking_reason: str,
) -> str:
    if page_kind == "results_end":
        return ACCEPT_END
    if blocking_reason in BLOCKING_STOP_REASONS or page_kind in BLOCKING_STOP_REASONS:
        return STOP
    if payload.get("goal_met") is True and keyword_match == "matched":
        return ACCEPT
    if page_kind in REFRESH_REPAIR_REASONS | FOREGROUND_REPAIR_REASONS | POPUP_REPAIR_REASONS:
        return REPAIR
    if keyword_match in {"mismatched", "unreadable", "not_visible"}:
        return REPAIR
    return STOP


def _page_kind_from_state(state: str) -> str:
    mapping = {
        "visible_results": "results_page",
        "search_results": "results_page",
        "results_page": "results_page",
        "results_end": "results_end",
        "empty_result": "empty_result",
        "chrome_not_foreground": "chrome_not_foreground",
        "login_required": "login_required",
        "captcha_required": "captcha_required",
        "risk_suspected": "risk_suspected",
        "popup_blocked": "popup_blocked",
        "closeable_popup_overlay": "closeable_popup_overlay",
        "white_skeleton": "white_skeleton",
        "automation_permission_blocked": "permission_panel",
        "rate_limited": "rate_limited",
        "visible_ready": "unknown",
    }
    return mapping.get(state, "unknown")


def _keyword_match_from_page_state(page_state: Dict[str, Any], keyword_status: str) -> str:
    value = page_state.get("keyword_match")
    if value is True:
        return "matched"
    if value is False:
        return "mismatched"
    if keyword_status == "matched":
        return "matched"
    if keyword_status == "mismatch":
        return "mismatched"
    if keyword_status == "unknown":
        return "unreadable"
    visible_keyword = str(page_state.get("visible_search_keyword") or "")
    return "not_visible" if not visible_keyword else "unreadable"


def _evidence_reason(keyword: str, page_kind: str, keyword_match: str, blocking_reason: str) -> str:
    if blocking_reason:
        return blocking_reason
    if page_kind in CAPTURABLE_PAGE_KINDS and keyword_match == "matched":
        return f"visible evidence matches current keyword {keyword}"
    if page_kind == "results_end":
        return "results_end"
    return f"goal_not_met:{page_kind}:{keyword_match}"


def _blocking_reason_from_page_kind(page_kind: str) -> str:
    if page_kind in BLOCKING_STOP_REASONS | REFRESH_REPAIR_REASONS | FOREGROUND_REPAIR_REASONS | POPUP_REPAIR_REASONS:
        return page_kind
    if page_kind == "unknown":
        return "unknown"
    return ""


def _normalize_choice(value: Any, allowed: set, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "matched"}


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_evidence_check_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        payload = dict(raw)
    else:
        payload = parse_evidence_check_text(str(raw or ""))
        if payload.get("valid") is False:
            return {
                "schema": EVIDENCE_CHECK_SCHEMA,
                "goal_met": False,
                "page_kind": "unknown",
                "keyword_match": False,
                "visible_search_keyword": "",
                "blocking_reason": "json_invalid",
                "recommended_next": NEEDS_REVIEW,
                "confidence": 0.0,
                "reason": payload.get("reason") or "invalid evidence check JSON",
            }
    normalized = normalize_evidence_check(payload)
    blocking_reason = _normalize_gate_token(normalized.get("blocking_reason") or "none")
    if blocking_reason == "":
        blocking_reason = "none"
    recommended_next = _normalize_gate_token(normalized.get("recommended_next") or NEEDS_REVIEW)
    if recommended_next == ACCEPT_END:
        recommended_next = "end"
    return {
        "schema": EVIDENCE_CHECK_SCHEMA,
        "goal_met": bool(normalized.get("goal_met")),
        "page_kind": _normalize_gate_token(normalized.get("page_kind") or "unknown"),
        "keyword_match": normalized.get("keyword_match") == "matched" or normalized.get("keyword_match") is True,
        "visible_search_keyword": str(normalized.get("visible_search_keyword") or ""),
        "blocking_reason": blocking_reason,
        "recommended_next": recommended_next,
        "confidence": _float_or_zero(normalized.get("confidence")),
        "reason": str(normalized.get("reason") or ""),
    }


def validate_evidence_check(check: Dict[str, Any]) -> tuple:
    errors = []
    for field in EVIDENCE_FIELDS:
        if field not in check:
            errors.append(f"missing_{field}")
    if errors:
        return False, errors
    if check.get("schema") not in {SCHEMA, EVIDENCE_CHECK_SCHEMA}:
        errors.append("schema_mismatch")
    if not isinstance(check.get("goal_met"), bool):
        errors.append("goal_met_not_bool")
    if not isinstance(check.get("keyword_match"), bool):
        errors.append("keyword_match_not_bool")
    if check.get("blocking_reason") not in USER_BLOCKING_REASONS:
        errors.append("blocking_reason_invalid")
    if check.get("recommended_next") not in {ACCEPT, REPAIR, STOP, NEEDS_REVIEW, "continue", "end", ACCEPT_END}:
        errors.append("recommended_next_invalid")
    confidence = check.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        errors.append("confidence_invalid")
    if not str(check.get("reason") or ""):
        errors.append("reason_empty")
    return not errors, errors


def python_gate_decision(
    check: Any,
    budgets: Optional[Dict[str, Any]] = None,
    history: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    budgets = budgets or {}
    history = history or {}
    normalized = normalize_evidence_check_json(check)
    valid, errors = validate_evidence_check(normalized)
    if not valid:
        return _gate_decision(NEEDS_REVIEW, "invalid_evidence_check:" + ",".join(errors), normalized)

    confidence = _float_or_zero(normalized.get("confidence"))
    min_confidence = _float_or_default(budgets.get("min_confidence"), 0.7)
    blocker = str(normalized.get("blocking_reason") or "none")
    recommended_next = str(normalized.get("recommended_next") or "")

    if blocker in HARD_GATE_BLOCKERS:
        return _gate_decision(STOP, blocker, normalized)
    if blocker in REVIEW_GATE_BLOCKERS:
        return _gate_decision(NEEDS_REVIEW, blocker, normalized)
    if confidence < min_confidence:
        normalized = dict(normalized)
        normalized["blocking_reason"] = "low_confidence"
        return _gate_decision(NEEDS_REVIEW, "low_confidence", normalized)
    if recommended_next == REPAIR:
        repairs_used = int(_float_or_default(history.get("repairs_used", history.get("repair_attempts")), 0.0))
        max_repairs = int(_float_or_default(budgets.get("max_repairs"), 1.0))
        if repairs_used < max_repairs:
            return _gate_decision(REPAIR, "recommended_repair", normalized)
        return _gate_decision(STOP, "repair_budget_exhausted", normalized)
    if normalized.get("goal_met") and blocker in {"", "none"}:
        if history.get("stage") == "capture" and normalized.get("page_kind") == "results_end":
            return _gate_decision(ACCEPT_END, "results_end", normalized)
        return _gate_decision(ACCEPT, "goal_met", normalized)
    if recommended_next in {STOP, NEEDS_REVIEW}:
        return _gate_decision(recommended_next, f"recommended_{recommended_next}", normalized)
    return _gate_decision(NEEDS_REVIEW, "goal_not_met", normalized)


def _gate_decision(action: str, reason: str, check: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "decision": action,
        "reason": reason,
        "confidence": _float_or_zero(check.get("confidence")),
        "blocking_reason": str(check.get("blocking_reason") or ""),
        "recommended_next": str(check.get("recommended_next") or ""),
    }


def _normalize_gate_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
