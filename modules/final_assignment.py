import configparser
import logging
import os

import pandas as pd

from modules.utils import ensure_dir, get_project_root


def _load_config():
    config_file = os.path.join(get_project_root(), "config", "settings.ini")
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")
    return config


def _find_existing_col(df, candidates):
    for col in candidates:
        if col and col in df.columns:
            return col
    return None


def _normalize_mode(value):
    mode = str(value or "").strip().lower()
    if mode in {"statistical", "open_url", "skip"}:
        return mode
    return ""


def _safe_float(value):
    if pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _build_default_output(raw_input_file, statistical_eval_file=None):
    raw_base_name = os.path.splitext(os.path.basename(raw_input_file))[0]
    ext = os.path.splitext(raw_input_file)[1] or ".xlsx"
    if statistical_eval_file:
        return os.path.join(
            os.path.dirname(statistical_eval_file),
            f"{raw_base_name}_final_assignment_v1{ext}",
        )
    base, _ = os.path.splitext(raw_input_file)
    return f"{base}_final_assignment_v1{ext}"


def _find_latest_stat_eval_file():
    tasks_dir = os.path.join(get_project_root(), "data", "tasks")
    if not os.path.exists(tasks_dir):
        return None

    candidates = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if not os.path.isdir(item_path):
            continue
        for name in os.listdir(item_path):
            if name.endswith("_statistical_eval.xlsx"):
                full = os.path.join(item_path, name)
                candidates.append((os.path.getmtime(full), full))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def assign_final_values(raw_input_file=None, statistical_eval_file=None, output_file=None, logger=None):
    log = logger or logging.getLogger(__name__)
    config = _load_config()

    raw_input_file = raw_input_file or config.get(
        "PRODUCT_ROUTING", "raw_input_file", fallback=""
    ).strip()
    statistical_eval_file = statistical_eval_file or _find_latest_stat_eval_file()

    if not raw_input_file:
        return {"success": False, "error": "未提供原始输入表路径"}
    if not os.path.exists(raw_input_file):
        return {"success": False, "error": f"原始输入表不存在: {raw_input_file}"}
    if not statistical_eval_file:
        return {"success": False, "error": "未找到 statistical_eval 文件"}
    if not os.path.exists(statistical_eval_file):
        return {"success": False, "error": f"统计评估文件不存在: {statistical_eval_file}"}

    preferred_mode_col = config.get(
        "PRODUCT_ROUTING", "preferred_mode_column", fallback="preferred_mode"
    ).strip()
    legacy_mode_col = config.get(
        "PRODUCT_ROUTING", "pricing_mode_column", fallback="pricing_mode"
    ).strip()
    card_name_col = config.get("INPUT", "card_name_column", fallback="中文卡牌名").strip()
    product_id_col = config.get("INPUT", "product_id_column", fallback="productId").strip()
    output_price_col = config.get(
        "PRODUCT_ROUTING", "output_price_column", fallback="准确淘宝价"
    ).strip()

    raw_df = pd.read_excel(raw_input_file, engine="openpyxl")
    eval_df = pd.read_excel(statistical_eval_file, engine="openpyxl", sheet_name="all_cards")

    mode_col = _find_existing_col(raw_df, [preferred_mode_col, legacy_mode_col])
    source_card_name_col = _find_existing_col(raw_df, [card_name_col, "中文卡牌名", "card_name", "目标牌名"])
    source_product_id_col = _find_existing_col(raw_df, [product_id_col, "productId"])

    if mode_col is None:
        return {"success": False, "error": "原始输入表缺少 preferred_mode/pricing_mode 列"}
    if source_card_name_col is None:
        return {"success": False, "error": "原始输入表缺少牌名列"}
    if output_price_col not in raw_df.columns:
        return {"success": False, "error": f"原始输入表缺少回填列: {output_price_col}"}
    if "card_name" not in eval_df.columns:
        return {"success": False, "error": "统计评估文件缺少 card_name 列"}

    eval_map = {}
    for _, row in eval_df.iterrows():
        card_name = str(row.get("card_name", "")).strip()
        if card_name:
            eval_map[card_name] = row

    assigned_df = raw_df.copy()
    assigned_df[output_price_col] = assigned_df[output_price_col].where(
        assigned_df[output_price_col].notna(), ""
    )

    audit_cols = {
        "preferred_mode_normalized": [],
        "effective_mode": [],
        "assignment_status": [],
        "assignment_reason": [],
        "statistical_card_name": [],
        "statistical_target_value": [],
        "statistical_risk_status": [],
        "statistical_secondary_reason": [],
        "final_price_source": [],
    }
    if source_product_id_col:
        audit_cols["source_product_id"] = []

    summary = {
        "skip": 0,
        "statistical_assigned": 0,
        "statistical_blocked_pending": 0,
        "open_url_pending": 0,
        "mode_missing_or_unknown": 0,
    }

    pending_rows = []
    assigned_rows = []

    for _, row in assigned_df.iterrows():
        mode = _normalize_mode(row.get(mode_col, ""))
        card_name = str(row.get(source_card_name_col, "") or "").strip()
        eval_row = eval_map.get(card_name)
        assigned_price = ""
        effective_mode = ""
        status = ""
        reason = ""
        source = ""
        target_value = None
        risk_status = ""
        secondary_reason = ""

        if mode == "skip":
            effective_mode = "skip"
            status = "skipped"
            reason = "preferred_mode=skip"
            source = "skip"
            summary["skip"] += 1
        elif mode == "statistical":
            if eval_row is None:
                effective_mode = "open_url_fallback_pending"
                status = "statistical_eval_missing_pending_open_url"
                reason = "未找到该牌名的统计评估结果"
                source = "pending_open_url"
                summary["statistical_blocked_pending"] += 1
            else:
                target_value = _safe_float(eval_row.get("target_value"))
                risk_status = str(eval_row.get("risk_status", "") or "").strip()
                secondary_reason = str(eval_row.get("secondary_reason", "") or "").strip()
                if bool(eval_row.get("eligible_final")) and target_value is not None:
                    assigned_price = target_value
                    effective_mode = "statistical"
                    status = "statistical_assigned"
                    reason = "统计评估通过，按 target_value 回填"
                    source = "statistical_target_value"
                    summary["statistical_assigned"] += 1
                else:
                    effective_mode = "open_url_fallback_pending"
                    status = "statistical_blocked_pending_open_url"
                    reason = "统计评估未通过，需升级为 open_url"
                    source = "pending_open_url"
                    summary["statistical_blocked_pending"] += 1
        elif mode == "open_url":
            effective_mode = "open_url"
            status = "open_url_pending"
            reason = "preferred_mode=open_url，等待后续 URL/SKU 赋值模块"
            source = "pending_open_url"
            summary["open_url_pending"] += 1
        else:
            effective_mode = ""
            status = "mode_missing_or_unknown"
            reason = "preferred_mode 缺失或取值无效"
            source = "unresolved"
            summary["mode_missing_or_unknown"] += 1

        audit_cols["preferred_mode_normalized"].append(mode)
        audit_cols["effective_mode"].append(effective_mode)
        audit_cols["assignment_status"].append(status)
        audit_cols["assignment_reason"].append(reason)
        audit_cols["statistical_card_name"].append(card_name)
        audit_cols["statistical_target_value"].append(target_value)
        audit_cols["statistical_risk_status"].append(risk_status)
        audit_cols["statistical_secondary_reason"].append(secondary_reason)
        audit_cols["final_price_source"].append(source)
        if source_product_id_col:
            audit_cols["source_product_id"].append(row.get(source_product_id_col, ""))

        assigned_df.at[row.name, output_price_col] = assigned_price

        exported = row.to_dict()
        exported.update({
            output_price_col: assigned_price,
            "preferred_mode_normalized": mode,
            "effective_mode": effective_mode,
            "assignment_status": status,
            "assignment_reason": reason,
            "statistical_card_name": card_name,
            "statistical_target_value": target_value,
            "statistical_risk_status": risk_status,
            "statistical_secondary_reason": secondary_reason,
            "final_price_source": source,
        })
        if source_product_id_col:
            exported["source_product_id"] = row.get(source_product_id_col, "")

        if status in {
            "open_url_pending",
            "statistical_blocked_pending_open_url",
            "statistical_eval_missing_pending_open_url",
            "mode_missing_or_unknown",
        }:
            pending_rows.append(exported)
        if status == "statistical_assigned":
            assigned_rows.append(exported)

    for col_name, values in audit_cols.items():
        assigned_df[col_name] = values

    output_file = output_file or _build_default_output(raw_input_file, statistical_eval_file)
    ensure_dir(os.path.dirname(output_file))

    pending_df = pd.DataFrame(pending_rows)
    assigned_only_df = pd.DataFrame(assigned_rows)
    summary_df = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in summary.items()]
    )

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        assigned_df.to_excel(writer, sheet_name="原始输入_已回填", index=False)
        pending_df.to_excel(writer, sheet_name="待后续处理", index=False)
        assigned_only_df.to_excel(writer, sheet_name="统计已回填", index=False)
        summary_df.to_excel(writer, sheet_name="摘要", index=False)

    log.info(
        "最终赋值 v1 完成: skip=%s, statistical_assigned=%s, blocked_pending=%s, open_url_pending=%s, unknown=%s, 输出=%s",
        summary["skip"],
        summary["statistical_assigned"],
        summary["statistical_blocked_pending"],
        summary["open_url_pending"],
        summary["mode_missing_or_unknown"],
        output_file,
    )

    return {
        "success": True,
        "output_file": output_file,
        "raw_input_file": raw_input_file,
        "statistical_eval_file": statistical_eval_file,
        **summary,
    }
