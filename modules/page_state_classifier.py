"""JSON page-state classifier backed by an OpenAI-compatible vision endpoint.

The classifier reads only an already-saved screenshot file. It does not inspect
browser state, DOM, network, cookies, or storage.
"""
import base64
import json
import mimetypes
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


CLASSIFIER_STATES = {
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


class PageStateClassifierUnavailable(RuntimeError):
    pass


def classify_screenshot_json(
    image_path: str,
    *,
    contract: Optional[Dict[str, Any]] = None,
    keyword: str = "",
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    config = _classifier_config(contract or {})
    api_key = _resolve_api_key(config["api_key_env"])
    if not api_key:
        raise PageStateClassifierUnavailable("classifier_api_key_missing")
    if not config["model_name"] or not config["base_url"]:
        raise PageStateClassifierUnavailable("classifier_model_config_missing")

    image = Path(image_path)
    if not image.is_file():
        raise PageStateClassifierUnavailable("classifier_image_missing")

    payload = _request_payload(
        model=config["model_name"],
        image_path=image,
        keyword=keyword,
        temperature=config["temperature"],
    )
    response = _post_chat_completion(
        base_url=config["base_url"],
        api_key=api_key,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    content = _extract_message_content(response)
    parsed = _parse_json_object(content)
    return _normalize_classifier_payload(parsed, raw_text=content)


def _classifier_config(contract: Dict[str, Any]) -> Dict[str, Any]:
    boundary = contract.get("model_boundary") or {}
    config = contract.get("config") or {}
    return {
        "model_name": (
            boundary.get("midscene_model_name")
            or config.get("model_name")
            or config.get("midscene_model_name")
            or os.environ.get("MIDSCENE_MODEL_NAME")
            or "glm-4.6v-flashx"
        ),
        "base_url": (
            boundary.get("midscene_model_base_url")
            or config.get("model_base_url")
            or config.get("midscene_model_base_url")
            or os.environ.get("MIDSCENE_MODEL_BASE_URL")
            or "https://open.bigmodel.cn/api/paas/v4"
        ),
        "api_key_env": (
            boundary.get("midscene_api_key_env")
            or config.get("model_api_key_env")
            or config.get("midscene_api_key_env")
            or os.environ.get("MIDSCENE_MODEL_API_KEY_ENV")
            or "MIDSCENE_MODEL_API_KEY"
        ),
        "temperature": _float_value(
            boundary.get("midscene_model_temperature", config.get("model_temperature", 0)),
            default=0.0,
        ),
    }


def _resolve_api_key(env_name: str) -> str:
    env_name = str(env_name or "").strip() or "MIDSCENE_MODEL_API_KEY"
    value = os.environ.get(env_name)
    if value:
        return value.strip()
    env_file = Path(__file__).resolve().parents[1] / "local" / "midscene-computer.env"
    values = _read_env_file(env_file)
    return str(values.get(env_name) or "").strip()


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    values: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            value = raw_value.strip().strip('"').strip("'")
            values[key] = value
    except OSError:
        return {}
    return values


def _request_payload(model: str, image_path: Path, keyword: str, temperature: float) -> Dict[str, Any]:
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "Using only this saved screenshot image, classify the coarse operational state of the visible page. "
        "Return only a valid JSON object with exactly these fields: state, confidence, reason, "
        "visible_search_keyword, keyword_match, search_box_text_kind, search_submitted, "
        "is_home_feed, result_page_evidence, url_or_page_evidence. "
        "state must be one of: chrome_not_foreground, captcha_required, login_required, risk_suspected, "
        "popup_blocked, closeable_popup_overlay, white_skeleton, empty_result, results_end, "
        "visible_results, search_results, results_page, visible_ready, unknown. "
        "Use chrome_not_foreground when Codex, Terminal, Cursor, VS Code, WPS, or another non-Chrome app "
        "is the visible foreground window. Use closeable_popup_overlay only for a normal Taobao in-page "
        "modal or marketing overlay where the page behind it is visibly dimmed by a translucent layer and "
        "the modal or nearby overlay area has a clear gray X close control, usually near the modal's own "
        "upper-right corner. Do not use closeable_popup_overlay for login, captcha, security/risk, account, "
        "permission, checkout, cart, favorite, reward-claim, or other account-state-changing dialogs; use "
        "the relevant hard-stop state or popup_blocked instead. Treat login, captcha, security/risk warnings, "
        "blocking popups, and white skeleton/loading pages as higher priority than visible listings. "
        "Use results_end when a readable Taobao results page clearly shows pagination, previous/next buttons, "
        "jump input, footer links, copyright/ICP/filing text, friend links, or a bottom scrollbar; a literal "
        "no-more-results label is not required. "
        f"The expected keyword is {keyword!r}. On a normal homepage/search-entry surface, recommendation, "
        "hot-search, suggestion, or placeholder text inside or near the search box is acceptable and should "
        "not prevent visible_ready. The keyword content mainly matters on results/search_results/results_end "
        "product-listing pages. If a submitted search keyword is clearly visible on a product-listing page, "
        "put it into visible_search_keyword and set keyword_match true when it equals the expected keyword, "
        "false when it clearly differs, or null when it is not visible or unreadable. Keep the compatible "
        "search_box_text_kind field as actual_input, placeholder, suggestion, hot_search, unreadable, none, "
        "or an empty string if the distinction is not useful. "
        "The first post-search screenshot must not be accepted just because the search box contains the "
        "expected keyword or because product cards are visible. Taobao homepage recommendation feeds can "
        "show product cards under a correctly typed keyword before the search button is actually submitted. "
        "Set search_submitted true only when visible evidence shows the page has changed into a Taobao "
        "search results structure, such as s.taobao.com/search evidence, sort/filter controls like 综合/销量/"
        "价格/区间/筛选, pagination/previous/next/jump controls, or a clear search-results layout rather "
        "than homepage channels, campaigns, hot recommendations, or 猜你喜欢. Put short visible cues in "
        "result_page_evidence and address/page evidence in url_or_page_evidence when available. Set "
        "is_home_feed true for a homepage recommendation feed; product cards alone do not prove submitted search. "
        "Do not output product rows, prices, shop names, item titles, business filtering, or price decisions."
    )
    return {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{data}"},
                    },
                ],
            }
        ],
    }


def _post_chat_completion(
    *,
    base_url: str,
    api_key: str,
    payload: Dict[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    url = _chat_completions_url(base_url)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(1.0, float(timeout_seconds)),
            context=_ssl_context(),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PageStateClassifierUnavailable(f"classifier_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PageStateClassifierUnavailable(f"classifier_url_error:{_safe_url_error_reason(exc)}") from exc
    except Exception as exc:
        raise PageStateClassifierUnavailable(f"classifier_request_failed:{type(exc).__name__}") from exc


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _safe_url_error_reason(exc: urllib.error.URLError) -> str:
    reason = getattr(exc, "reason", None)
    if reason is None:
        return type(exc).__name__
    name = type(reason).__name__
    text = str(reason).lower()
    if "certificate" in text or "cert" in text:
        return f"{name}:certificate_verify_failed"
    if "timed out" in text or "timeout" in text:
        return f"{name}:timeout"
    if "name or service" in text or "nodename" in text or "dns" in text:
        return f"{name}:dns"
    if "connection refused" in text:
        return f"{name}:connection_refused"
    return name


def _chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or "").rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_message_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise PageStateClassifierUnavailable("classifier_response_missing_choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise PageStateClassifierUnavailable("classifier_response_missing_content")
    return content.strip()


def _parse_json_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise PageStateClassifierUnavailable("classifier_json_unparseable")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise PageStateClassifierUnavailable("classifier_json_not_object")
    return value


def _normalize_classifier_payload(payload: Dict[str, Any], *, raw_text: str) -> Dict[str, Any]:
    state = str(payload.get("state") or "unknown").strip()
    if state not in CLASSIFIER_STATES:
        state = "unknown"
    confidence = _float_value(payload.get("confidence"), default=0.35 if state == "unknown" else 0.82)
    confidence = max(0.0, min(1.0, confidence))
    keyword_match = payload.get("keyword_match")
    if isinstance(keyword_match, str):
        lowered = keyword_match.strip().lower()
        if lowered in {"true", "yes", "1"}:
            keyword_match = True
        elif lowered in {"false", "no", "0"}:
            keyword_match = False
        elif lowered in {"null", "none", "unknown", ""}:
            keyword_match = None
    if not isinstance(keyword_match, bool):
        keyword_match = None
    search_submitted = _optional_bool(payload.get("search_submitted"))
    is_home_feed = _optional_bool(payload.get("is_home_feed"))
    if is_home_feed is None:
        is_home_feed = _optional_bool(payload.get("home_feed"))
    return {
        "status": state,
        "confidence": confidence,
        "reason": str(payload.get("reason") or "page_state_json_classifier").strip(),
        "metrics": {},
        "source": "json_classifier",
        "raw_text": raw_text,
        "visible_search_keyword": str(payload.get("visible_search_keyword") or "").strip(),
        "keyword_match": keyword_match,
        "search_box_text_kind": _normalize_search_box_text_kind(payload.get("search_box_text_kind")),
        "search_submitted": search_submitted,
        "is_home_feed": is_home_feed,
        "result_page_evidence": _normalize_text_list(payload.get("result_page_evidence")),
        "url_or_page_evidence": _normalize_text_list(payload.get("url_or_page_evidence")),
    }


def _optional_bool(value: Any) -> Optional[bool]:
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
    if text in {"true", "yes", "1", "y", "on", "submitted"}:
        return True
    if text in {"false", "no", "0", "n", "off", "unsubmitted"}:
        return False
    if text in {"", "null", "none", "unknown", "unreadable"}:
        return None
    return None


def _normalize_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]
    items: List[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _normalize_search_box_text_kind(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "actual": "actual_input",
        "typed": "actual_input",
        "typed_value": "actual_input",
        "input": "actual_input",
        "query": "actual_input",
        "submitted_query": "actual_input",
        "recommendation": "suggestion",
        "recommended": "suggestion",
        "recommendation_text": "suggestion",
        "placeholder_text": "placeholder",
        "hot": "hot_search",
        "hotsearch": "hot_search",
        "hot_search_text": "hot_search",
        "not_visible": "none",
        "empty": "none",
        "missing": "none",
        "unknown": "unreadable",
    }
    text = aliases.get(text, text)
    if text in {"actual_input", "placeholder", "suggestion", "hot_search", "unreadable", "none"}:
        return text
    return ""


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
