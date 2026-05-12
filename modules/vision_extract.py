"""
Codex-assisted visual extraction storage.

Codex reads screenshots externally, then passes structured rows through this
module. This module validates and persists rows; it does not call browser APIs,
read DOM, or contact Taobao.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from modules.visual_capture import maybe_delete_screenshot
from modules.utils import ensure_dir


REQUIRED_COLUMNS = [
    "搜索关键词",
    "采集时间",
    "商品名称",
    "现价",
    "店铺名称",
    "付款人数",
    "地区",
    "截图文件",
    "截图坐标",
    "识别置信度",
    "识别备注",
]


@dataclass
class IngestResult:
    ok: bool
    status: str
    rows_written: int
    raw_jsonl: str
    raw_excel: str
    rows_received: int = 0
    duplicates_removed: int = 0
    rows_dropped_by_limit: int = 0
    screenshot_path: str = ""
    screenshot_deleted: bool = False
    error: Optional[str] = None

    def to_dict(self):
        return {
            "ok": self.ok,
            "status": self.status,
            "rows_written": self.rows_written,
            "raw_jsonl": self.raw_jsonl,
            "raw_excel": self.raw_excel,
            "rows_received": self.rows_received,
            "duplicates_removed": self.duplicates_removed,
            "rows_dropped_by_limit": self.rows_dropped_by_limit,
            "screenshot_path": self.screenshot_path,
            "screenshot_deleted": self.screenshot_deleted,
            "error": self.error,
        }


def load_rows(rows_json: Optional[str] = None, rows_file: Optional[str] = None) -> List[Dict[str, Any]]:
    if rows_file:
        with open(rows_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif rows_json:
        payload = json.loads(rows_json)
    else:
        payload = []

    if isinstance(payload, dict):
        payload = payload.get("rows", [])
    if not isinstance(payload, list):
        raise ValueError("识别结果必须是 list 或包含 rows 的 JSON object")
    return [dict(row) for row in payload]


def normalize_rows(
    rows: Iterable[Dict[str, Any]],
    keyword: str,
    screenshot_path: str = "",
    captured_at: str = "",
) -> List[Dict[str, Any]]:
    normalized = []
    captured_at = captured_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        item = {col: row.get(col, "") for col in REQUIRED_COLUMNS}
        item["搜索关键词"] = item["搜索关键词"] or keyword
        item["采集时间"] = _normalize_capture_time(item["采集时间"] or captured_at)
        item["截图文件"] = item["截图文件"] or screenshot_path
        item["商品名称"] = str(item["商品名称"] or "").strip()
        item["店铺名称"] = str(item["店铺名称"] or "").strip()
        item["地区"] = str(item["地区"] or "").strip()
        item["付款人数"] = str(item["付款人数"] or "").strip()
        item["识别备注"] = str(item["识别备注"] or "").strip()
        item["现价"] = _clean_price(item["现价"])
        try:
            item["识别置信度"] = float(item["识别置信度"] or 0)
        except Exception:
            item["识别置信度"] = 0.0
        normalized.append(item)
    return normalized


def ingest_rows(
    task_dir: str,
    keyword: str,
    rows: List[Dict[str, Any]],
    screenshot_path: str = "",
    confidence_threshold: float = 0.80,
    retain_screenshot: Optional[bool] = None,
    target_limit: int = 0,
    dedupe: bool = True,
) -> IngestResult:
    ensure_dir(task_dir)
    raw_jsonl = os.path.join(task_dir, "raw_rows.jsonl")
    raw_excel = os.path.join(task_dir, "raw_results.xlsx")

    normalized = normalize_rows(rows, keyword=keyword, screenshot_path=screenshot_path)
    rows_received = len(normalized)
    existing_rows = _load_existing_rows(raw_jsonl)
    existing_keys = {_dedupe_key(row) for row in existing_rows} if dedupe else set()
    existing_for_keyword = [
        row for row in existing_rows
        if str(row.get("搜索关键词", "") or "").strip() == str(keyword or "").strip()
    ]
    deduped = []
    duplicates_removed = 0
    for row in normalized:
        key = _dedupe_key(row)
        if dedupe and key in existing_keys:
            duplicates_removed += 1
            continue
        if dedupe:
            existing_keys.add(key)
        deduped.append(row)

    rows_dropped_by_limit = 0
    if target_limit and target_limit > 0:
        remaining = max(0, int(target_limit) - len(existing_for_keyword))
        if len(deduped) > remaining:
            rows_dropped_by_limit = len(deduped) - remaining
            deduped = deduped[:remaining]

    missing_required = [
        row for row in deduped
        if not row["商品名称"] or row["现价"] in ("", None)
    ]
    low_conf = [row for row in deduped if float(row.get("识别置信度") or 0) < confidence_threshold]

    status = "extracted"
    ok = True
    if not deduped:
        if rows_received > 0 and existing_for_keyword:
            status = "extracted"
            ok = True
        else:
            status = "needs_review"
            ok = False
    elif missing_required or low_conf:
        status = "needs_review"
        ok = False

    with open(raw_jsonl, "a", encoding="utf-8") as f:
        for row in deduped:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    export_jsonl_to_excel(raw_jsonl, raw_excel)

    if retain_screenshot is None:
        retain_screenshot = not ok
    screenshot_deleted = False
    if not retain_screenshot:
        screenshot_deleted = maybe_delete_screenshot(screenshot_path)

    return IngestResult(
        ok=ok,
        status=status,
        rows_written=len(deduped),
        raw_jsonl=raw_jsonl,
        raw_excel=raw_excel,
        rows_received=rows_received,
        duplicates_removed=duplicates_removed,
        rows_dropped_by_limit=rows_dropped_by_limit,
        screenshot_path=screenshot_path,
        screenshot_deleted=screenshot_deleted,
        error=None if ok else "empty_rows_or_low_confidence_or_missing_required_fields",
    )


def export_jsonl_to_excel(raw_jsonl: str, raw_excel: str) -> str:
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise RuntimeError("openpyxl 未安装，请运行 pip install -r requirements.txt") from e

    rows = []
    if os.path.exists(raw_jsonl):
        with open(raw_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    ensure_dir(os.path.dirname(raw_excel))
    wb = Workbook()
    ws = wb.active
    ws.title = "raw_results"
    ws.append(REQUIRED_COLUMNS)
    for row in rows:
        ws.append([row.get(col, "") for col in REQUIRED_COLUMNS])
    wb.save(raw_excel)
    return raw_excel


def _clean_price(value):
    text = str(value or "").strip().replace("¥", "").replace("￥", "").replace(",", "")
    # Keep the first numeric-looking token.
    import re

    m = re.search(r"\d+(?:\.\d+)?", text)
    return m.group(0) if m else text


def _normalize_capture_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        import pandas as pd

        parsed = pd.to_datetime(text, errors="coerce")
        if not pd.isna(parsed):
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return text


def _load_existing_rows(raw_jsonl: str) -> List[Dict[str, Any]]:
    rows = []
    if not os.path.exists(raw_jsonl):
        return rows
    with open(raw_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _dedupe_key(row: Dict[str, Any]) -> str:
    def clean(value):
        return " ".join(str(value or "").strip().lower().split())

    return "|".join(
        [
            clean(row.get("搜索关键词")),
            clean(row.get("商品名称")),
            clean(row.get("现价")),
            clean(row.get("店铺名称")),
        ]
    )
