import configparser
import logging
import math
import os

import pandas as pd

from modules.utils import ensure_dir, get_project_root


def _safe_str(val):
    return str(val if val is not None else "").strip()


def _safe_int(val, default=0):
    s = str(val or "").replace(",", "").replace("'", "").strip()
    if not s:
        return default
    digits = []
    for ch in s:
        if ch.isdigit():
            digits.append(ch)
        elif digits:
            break
    if not digits:
        return default
    try:
        return int("".join(digits))
    except Exception:
        return default


def _safe_float(val, default=None):
    s = str(val or "").replace(",", "").replace("'", "").strip()
    if not s:
        return default
    out = []
    dot_used = False
    for ch in s:
        if ch.isdigit():
            out.append(ch)
        elif ch == "." and not dot_used:
            out.append(ch)
            dot_used = True
        elif out:
            break
    if not out:
        return default
    try:
        return float("".join(out))
    except Exception:
        return default


def _find_existing_col(df, candidates):
    for col_name in candidates:
        if col_name in df.columns:
            return col_name
    return None


def _extract_card_name_from_row(row):
    kw = str(row.get("搜索关键词", "") or row.get("关键词", "")).strip()
    if kw:
        return kw.replace("万智牌", "").strip()
    for col in ["中文卡牌名", "目标牌名", "card_name"]:
        value = str(row.get(col, "")).strip()
        if value:
            return value
    return "__UNKNOWN__"


def _weighted_quantile(values, weights, q):
    if not values:
        return None
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    threshold = q * total
    csum = 0.0
    for value, weight in pairs:
        csum += weight
        if csum >= threshold:
            return value
    return pairs[-1][0]


def _raw_quantile(sorted_values, q):
    if not sorted_values:
        return None
    idx = int(round((len(sorted_values) - 1) * q))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def _load_eval_config(config):
    return {
        "target_quantile": config.getfloat(
            "STATISTICAL_EVAL", "target_quantile", fallback=0.25
        ),
        "min_cluster_size": config.getint(
            "STATISTICAL_EVAL", "min_cluster_size",
            fallback=config.getint(
                "STATISTICAL_EVAL", "cluster_min_listing_count", fallback=4
            ),
        ),
        # 老牌（发售时间早于阈值）可降低成簇门槛
        "old_release_cutoff_date": config.get(
            "STATISTICAL_EVAL", "old_release_cutoff_date", fallback="2009-10-01"
        ),
        "old_release_min_cluster_size": config.getint(
            "STATISTICAL_EVAL", "old_release_min_cluster_size", fallback=3
        ),
        "abs_tolerance": config.getfloat(
            "STATISTICAL_EVAL", "abs_tolerance", fallback=10.0
        ),
        "max_span_ratio": config.getfloat(
            "STATISTICAL_EVAL", "max_span_ratio", fallback=1.6
        ),
        "enable_weighted_cluster_stats": config.getboolean(
            "STATISTICAL_EVAL", "enable_weighted_cluster_stats", fallback=True
        ),
        "enable_prefix_pool_selection": config.getboolean(
            "STATISTICAL_EVAL",
            "enable_prefix_pool_selection",
            fallback=config.getboolean(
                "STATISTICAL_EVAL", "enable_leading_merge_rescue", fallback=True
            ),
        ),
        "prefix_pool_gap_abs": config.getfloat(
            "STATISTICAL_EVAL",
            "prefix_pool_gap_abs",
            fallback=config.getfloat(
                "STATISTICAL_EVAL", "leading_rescue_plateau_gap_abs", fallback=6.0
            ),
        ),
        "prefix_pool_gap_ratio": config.getfloat(
            "STATISTICAL_EVAL",
            "prefix_pool_gap_ratio",
            fallback=config.getfloat(
                "STATISTICAL_EVAL", "leading_rescue_plateau_gap_ratio", fallback=1.30
            ),
        ),
        "block_if_prefix_mass_without_gap": config.getboolean(
            "STATISTICAL_EVAL",
            "block_if_prefix_mass_without_gap",
            fallback=config.getboolean(
                "STATISTICAL_EVAL", "block_if_incoherent_leading_mass", fallback=False
            ),
        ),
    }


def _build_release_date_map_from_raw_input(config, log, cutoff_dt):
    """
    从“原始输入表（同时也是最终回填表）”提取发售时间，按牌名聚合出 max(release_date)。
    严格模式：任一行缺失/不可解析 -> 该牌名不视为老牌。
    """
    raw_input_file = config.get("PRODUCT_ROUTING", "raw_input_file", fallback="").strip()
    if not raw_input_file or not os.path.exists(raw_input_file):
        return {}

    try:
        raw_df = pd.read_excel(raw_input_file, engine="openpyxl", dtype=str)
    except Exception as exc:  # pylint: disable=broad-except
        log.warning(f"读取原始输入表失败，老牌门槛将仅依赖统计输入：{exc}")
        return {}

    card_name_col = config.get("INPUT", "card_name_column", fallback="中文卡牌名").strip()
    card_col = _find_existing_col(raw_df, [card_name_col, "中文卡牌名", "card_name", "目标牌名"])
    release_col = _find_existing_col(raw_df, ["发售时间", "release_date", "release_time"])
    if card_col is None or release_col is None:
        return {}

    mapping = {}
    grouped = raw_df.groupby(raw_df[card_col].astype(str).str.strip(), dropna=False)
    for name, sub in grouped:
        card_name = str(name or "").strip()
        if not card_name:
            continue
        values = [str(v or "").strip() for v in sub[release_col].tolist()]
        if not values or any(not v for v in values):
            mapping[card_name] = {
                "parse_ok": False,
                "max_date_str": "",
                "old_rule_hit": False,
            }
            continue
        # pandas 2.x 已移除 infer_datetime_format 参数；这里依赖其内置推断即可
        parsed = pd.to_datetime(values, errors="coerce")
        if parsed.isna().any():
            mapping[card_name] = {
                "parse_ok": False,
                "max_date_str": "",
                "old_rule_hit": False,
            }
            continue
        max_dt = parsed.max().normalize()
        mapping[card_name] = {
            "parse_ok": True,
            "max_date_str": str(max_dt.date()),
            "old_rule_hit": bool(max_dt < cutoff_dt),
        }
    return mapping


# ---------------------------------------------------------------------------
#  自底向上贪心生长分簇
# ---------------------------------------------------------------------------


def _grow_clusters(sorted_samples, abs_tolerance, max_span_ratio):
    """从最低价开始，贪心地将价格纳入当前簇直到超出容忍范围。

    判定条件采用 OR 逻辑：
    - 绝对差 <= abs_tolerance（兜住低价区间的小绝对差、大倍率情况）
    - 倍率 <= max_span_ratio（兜住高价区间的大绝对差、小倍率情况）
    两者满足其一即可纳入。
    """
    if not sorted_samples:
        return []
    clusters = []
    current = [sorted_samples[0]]
    for sample in sorted_samples[1:]:
        cluster_min = current[0]["price"]
        p = sample["price"]
        abs_ok = (p - cluster_min) <= abs_tolerance
        ratio_ok = cluster_min > 0 and (p / cluster_min) <= max_span_ratio
        if abs_ok or ratio_ok:
            current.append(sample)
        else:
            clusters.append(current)
            current = [sample]
    clusters.append(current)
    return clusters


def _select_lowest_credible(cluster_lists, min_size):
    """在簇列表中取第一个（价格最低的）满足最小条数的簇。"""
    for idx, samples in enumerate(cluster_lists):
        if len(samples) >= min_size:
            return idx, samples
    return None, None


def _plateau_gap_ok(merged_tail_max, first_big_min, gap_abs, gap_ratio):
    """前缀池上沿与首个大簇底价之间须形成明显台阶（二选一即可）。

    gap_abs 可比生长用的 abs_tolerance 更小：生长是相对簇内最低价逐点收紧，
    断层是两段之间的相邻台阶，未必达到「相对全局起点」的 10 元量级。
    """
    if merged_tail_max is None or first_big_min is None:
        return False
    if merged_tail_max <= 0:
        return False
    if (first_big_min - merged_tail_max) >= gap_abs:
        return True
    return first_big_min / merged_tail_max >= gap_ratio


def _resolve_credible_selection(
    cluster_lists,
    first_big_idx,
    first_big_samples,
    min_cluster_size,
    valid_price_count,
    enable_prefix_pool_selection,
    prefix_pool_gap_abs,
    prefix_pool_gap_ratio,
    block_if_prefix_mass_without_gap,
):
    """前缀池存在判定：前缀条数达标 + 与首个大簇的断层（不再要求占全样本比例、不再要求全样本条数下限）。"""
    if first_big_idx is None or first_big_samples is None:
        return {
            "credible_samples": None,
            "selected_indices": [],
            "prefix_pool_selected": False,
            "blocked": False,
            "block_detail": "",
            "prefix_pool_count": 0,
            "prefix_pool_share": 0.0,
            "prefix_pool_gap_abs_observed": None,
            "prefix_pool_gap_ratio_observed": None,
            "prefix_reject_reason": "",
        }

    selected_indices = [first_big_idx]
    credible_samples = first_big_samples
    prefix_pool_selected = False
    blocked = False
    block_detail = ""
    prefix_pool_count = 0
    prefix_pool_share = 0.0
    prefix_pool_gap_abs_observed = None
    prefix_pool_gap_ratio_observed = None
    prefix_reject_reason = ""

    if not enable_prefix_pool_selection or first_big_idx == 0:
        return {
            "credible_samples": credible_samples,
            "selected_indices": selected_indices,
            "prefix_pool_selected": False,
            "blocked": False,
            "block_detail": "",
            "prefix_pool_count": 0,
            "prefix_pool_share": 0.0,
            "prefix_pool_gap_abs_observed": None,
            "prefix_pool_gap_ratio_observed": None,
            "prefix_reject_reason": "",
        }

    leading = []
    for j in range(first_big_idx):
        leading.extend(cluster_lists[j])
    prefix_pool_count = len(leading)
    prefix_pool_share = (
        prefix_pool_count / valid_price_count if valid_price_count > 0 else 0.0
    )
    mass_ok = prefix_pool_count >= min_cluster_size
    if not mass_ok:
        prefix_reject_reason = "mass"
        return {
            "credible_samples": credible_samples,
            "selected_indices": selected_indices,
            "prefix_pool_selected": False,
            "blocked": False,
            "block_detail": "",
            "prefix_pool_count": prefix_pool_count,
            "prefix_pool_share": prefix_pool_share,
            "prefix_pool_gap_abs_observed": None,
            "prefix_pool_gap_ratio_observed": None,
            "prefix_reject_reason": prefix_reject_reason,
        }

    leading_sorted = sorted(leading, key=lambda x: x["price"])
    merged_tail_max = leading_sorted[-1]["price"]
    first_big_min = first_big_samples[0]["price"]
    prefix_pool_gap_abs_observed = first_big_min - merged_tail_max
    prefix_pool_gap_ratio_observed = (
        first_big_min / merged_tail_max if merged_tail_max > 0 else None
    )
    gap_ok = _plateau_gap_ok(
        merged_tail_max, first_big_min, prefix_pool_gap_abs, prefix_pool_gap_ratio
    )
    if gap_ok:
        credible_samples = leading_sorted
        selected_indices = list(range(first_big_idx))
        prefix_pool_selected = True
    elif block_if_prefix_mass_without_gap:
        credible_samples = None
        selected_indices = []
        blocked = True
        prefix_reject_reason = "gap"
        lo = leading_sorted[0]["price"]
        block_detail = (
            f"prefix_pool_gap_fail_block(n={len(leading)},"
            f"tail_max={merged_tail_max:.1f},next_min={first_big_min:.1f},"
            f"tail_range={lo:.1f}~{merged_tail_max:.1f})"
        )
    else:
        prefix_reject_reason = "gap"

    return {
        "credible_samples": credible_samples,
        "selected_indices": selected_indices,
        "prefix_pool_selected": prefix_pool_selected,
        "blocked": blocked,
        "block_detail": block_detail,
        "prefix_pool_count": prefix_pool_count,
        "prefix_pool_share": prefix_pool_share,
        "prefix_pool_gap_abs_observed": prefix_pool_gap_abs_observed,
        "prefix_pool_gap_ratio_observed": prefix_pool_gap_ratio_observed,
        "prefix_reject_reason": prefix_reject_reason,
    }


def _build_failure_reason(cluster_lists, min_size):
    """当没有合格簇时，生成诊断信息。"""
    if not cluster_lists:
        return "no_valid_prices"
    reasons = []
    for idx, samples in enumerate(cluster_lists):
        n = len(samples)
        if n == 0:
            continue
        if n < min_size:
            p_min = samples[0]["price"]
            p_max = samples[-1]["price"]
            reasons.append(
                f"cluster_{idx + 1}(count={n}<{min_size},range={p_min:.1f}~{p_max:.1f})"
            )
    return "; ".join(reasons) if reasons else "all_clusters_too_small"


# ---------------------------------------------------------------------------
#  簇级统计
# ---------------------------------------------------------------------------

def _cluster_stats(card_name, cluster_id, cluster_rows, enable_weighted_cluster_stats):
    prices = [row["price"] for row in cluster_rows]
    prices_sorted = sorted(prices)
    cluster_listing_count = len(cluster_rows)
    unique_shop_count = len(
        {
            str(row.get("shop_name", "")).strip()
            for row in cluster_rows
            if str(row.get("shop_name", "")).strip()
        }
    )

    result = {
        "card_name": card_name,
        "cluster_id": cluster_id,
        "cluster_listing_count": cluster_listing_count,
        "cluster_unique_shop_count": unique_shop_count,
        "cluster_min_price": prices_sorted[0] if prices_sorted else None,
        "cluster_max_price": prices_sorted[-1] if prices_sorted else None,
        "cluster_median_price": _raw_quantile(prices_sorted, 0.50),
        "cluster_raw_p25": _raw_quantile(prices_sorted, 0.25),
        "cluster_raw_p50": _raw_quantile(prices_sorted, 0.50),
        "cluster_raw_p75": _raw_quantile(prices_sorted, 0.75),
        "cluster_price_values_head": ", ".join(str(v) for v in prices_sorted[:8]),
        "cluster_price_values_tail": ", ".join(str(v) for v in prices_sorted[-8:]),
    }

    if enable_weighted_cluster_stats:
        weights = [row["weight"] for row in cluster_rows]
        result.update(
            {
                "cluster_weighted_p25": _weighted_quantile(prices, weights, 0.25),
                "cluster_weighted_p50": _weighted_quantile(prices, weights, 0.50),
                "cluster_weighted_p75": _weighted_quantile(prices, weights, 0.75),
            }
        )
    else:
        result.update(
            {
                "cluster_weighted_p25": None,
                "cluster_weighted_p50": None,
                "cluster_weighted_p75": None,
            }
        )
    return result


# ---------------------------------------------------------------------------
#  主入口
# ---------------------------------------------------------------------------

def evaluate_price_clusters(input_file, output_file=None, logger=None):
    log = logger or logging.getLogger(__name__)

    config_file = os.path.join(get_project_root(), "config", "settings.ini")
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")
    eval_cfg = _load_eval_config(config)

    if not os.path.exists(input_file):
        log.error(f"输入文件不存在: {input_file}")
        return {"success": False, "error": "文件不存在"}

    try:
        df = pd.read_excel(input_file, engine="openpyxl", dtype=str)
        log.info(f"读取文件: {input_file} ({len(df)} 行)")
    except Exception as exc:
        log.error(f"读取 Excel 失败: {exc}")
        return {"success": False, "error": str(exc)}

    price_col = _find_existing_col(df, ["一口价", "现价", "价格", "price"])
    shop_col = _find_existing_col(df, ["店铺名称", "掌柜名", "店铺", "shop_name"])
    pay_col = _find_existing_col(df, ["付款人数", "pay_count", "成交人数"])
    url_col = _find_existing_col(df, ["商品链接", "商品URL", "url", "link"])
    item_id_col = _find_existing_col(df, ["商品ID", "商品id", "item_id"])

    if price_col is None:
        log.error(f"未找到价格列，现有列: {list(df.columns)}")
        return {"success": False, "error": "未找到价格列"}

    # 发售时间阈值（严格模式：任一行缺失/不可解析则不降门槛）
    cutoff_dt = pd.to_datetime(
        eval_cfg.get("old_release_cutoff_date", "2009-10-01"), errors="coerce"
    )
    if pd.isna(cutoff_dt):
        cutoff_dt = pd.to_datetime("2009-10-01")
        log.warning(
            f"old_release_cutoff_date 配置无法解析，已回退为 {cutoff_dt.date()}"
        )
    cutoff_dt = cutoff_dt.normalize()

    # 发售时间仅来自原始输入表（最终回填表）；pure 不要求携带该列
    raw_release_map = _build_release_date_map_from_raw_input(config, log, cutoff_dt)

    grouped = {}
    for _, row in df.iterrows():
        card_name = _extract_card_name_from_row(row)
        grouped.setdefault(card_name, []).append(row)

    card_rows = []
    cluster_rows = []

    for card_name, rows in grouped.items():
        # ---- 动态成簇门槛：老牌（所有发售时间 < 2009-10-01）可降到 3 ----
        old_release_rule_hit = False
        release_parse_ok = False
        release_max_date_str = ""
        effective_min_cluster_size = int(eval_cfg["min_cluster_size"])

        if raw_release_map:
            raw_info = raw_release_map.get(card_name)
            if raw_info:
                release_parse_ok = bool(raw_info.get("parse_ok"))
                release_max_date_str = str(raw_info.get("max_date_str") or "")
                if raw_info.get("old_rule_hit"):
                    old_release_rule_hit = True
                    effective_min_cluster_size = int(
                        eval_cfg.get("old_release_min_cluster_size", 3)
                    )

        samples = []
        unique_shops = set()
        for row in rows:
            shop_name = str(row.get(shop_col, "")).strip() if shop_col else ""
            if shop_name:
                unique_shops.add(shop_name)
            price = _safe_float(row.get(price_col, ""))
            if price is None or price <= 0:
                continue
            pay_count = _safe_int(row.get(pay_col, "")) if pay_col else 0
            samples.append(
                {
                    "price": float(price),
                    "log_price": math.log(float(price)),
                    "shop_name": shop_name,
                    "pay_count": pay_count,
                    "weight": math.log(pay_count + 1) + 1.0,
                    "item_id": (
                        str(row.get(item_id_col, "")).strip() if item_id_col else ""
                    ),
                    "url": (
                        str(row.get(url_col, "")).strip() if url_col else ""
                    ),
                }
            )

        prices = [s["price"] for s in samples]
        prices_sorted = sorted(prices)
        valid_price_count = len(samples)
        listing_count = len(rows)
        unique_shop_count = len(unique_shops)

        overall_raw_p25 = _raw_quantile(prices_sorted, 0.25) if prices_sorted else None
        overall_raw_p50 = _raw_quantile(prices_sorted, 0.50) if prices_sorted else None
        overall_raw_p75 = _raw_quantile(prices_sorted, 0.75) if prices_sorted else None

        overall_weighted_p25 = None
        overall_weighted_p50 = None
        overall_weighted_p75 = None
        if samples and eval_cfg["enable_weighted_cluster_stats"]:
            weights = [s["weight"] for s in samples]
            overall_weighted_p25 = _weighted_quantile(prices, weights, 0.25)
            overall_weighted_p50 = _weighted_quantile(prices, weights, 0.50)
            overall_weighted_p75 = _weighted_quantile(prices, weights, 0.75)

        # ---- 贪心生长分簇 ----
        if samples:
            sorted_samples = sorted(samples, key=lambda x: x["price"])
            cluster_lists = _grow_clusters(
                sorted_samples, eval_cfg["abs_tolerance"], eval_cfg["max_span_ratio"]
            )
        else:
            sorted_samples = []
            cluster_lists = []

        # ---- 构建每个簇的统计 ----
        clusters = []
        for idx, c_samples in enumerate(cluster_lists, start=1):
            stat = _cluster_stats(
                card_name=card_name,
                cluster_id=idx,
                cluster_rows=c_samples,
                enable_weighted_cluster_stats=eval_cfg["enable_weighted_cluster_stats"],
            )
            stat["is_credible"] = len(c_samples) >= effective_min_cluster_size
            clusters.append(stat)

        # ---- 找到最低可信货盘（前缀池存在判定：先看量，再看断层） ----
        first_big_idx, first_big_samples = _select_lowest_credible(
            cluster_lists, effective_min_cluster_size
        )
        resolved = _resolve_credible_selection(
            cluster_lists,
            first_big_idx,
            first_big_samples,
            effective_min_cluster_size,
            valid_price_count,
            eval_cfg["enable_prefix_pool_selection"],
            eval_cfg["prefix_pool_gap_abs"],
            eval_cfg["prefix_pool_gap_ratio"],
            eval_cfg["block_if_prefix_mass_without_gap"],
        )
        credible_samples = resolved["credible_samples"]
        selected_indices = set(resolved["selected_indices"])
        prefix_pool_selected = resolved["prefix_pool_selected"]
        selection_blocked = resolved["blocked"]
        block_detail = resolved["block_detail"]
        prefix_pool_count = resolved["prefix_pool_count"]
        prefix_pool_share = resolved["prefix_pool_share"]
        prefix_pool_gap_abs_observed = resolved["prefix_pool_gap_abs_observed"]
        prefix_pool_gap_ratio_observed = resolved["prefix_pool_gap_ratio_observed"]
        prefix_reject_reason = resolved["prefix_reject_reason"]

        has_credible = (
            credible_samples is not None
            and len(credible_samples) > 0
            and not selection_blocked
        )

        if has_credible and prefix_pool_selected:
            merge_start = min(selected_indices)
            credible_cluster = _cluster_stats(
                card_name=card_name,
                cluster_id=merge_start + 1,
                cluster_rows=credible_samples,
                enable_weighted_cluster_stats=eval_cfg[
                    "enable_weighted_cluster_stats"
                ],
            )
            credible_cluster["is_credible"] = True
        elif has_credible and first_big_idx is not None:
            credible_cluster = clusters[first_big_idx]
        else:
            credible_cluster = None

        # 标记哪个簇被选中（救援合并时多段同时标记）
        for idx, cluster in enumerate(clusters):
            cluster["is_selected_lowest"] = idx in selected_indices
            cluster_rows.append(cluster)

        # ---- 计算回填价格（原始 P25，不加权） ----
        target_value = None
        if has_credible and credible_samples:
            credible_prices = sorted([s["price"] for s in credible_samples])
            target_value = _raw_quantile(credible_prices, eval_cfg["target_quantile"])

        routing_suggestion = (
            "statistical_candidate" if has_credible else "open_url_fallback"
        )
        if selection_blocked:
            routing_reason = "prefix_pool_rejected_gap"
        elif has_credible:
            if prefix_pool_selected:
                routing_reason = "prefix_pool_selected"
            elif prefix_reject_reason == "mass":
                routing_reason = "prefix_pool_rejected_mass"
            elif prefix_reject_reason == "gap":
                routing_reason = "prefix_pool_rejected_gap"
            elif len(clusters) <= 1:
                routing_reason = "single_cluster_credible"
            else:
                routing_reason = "multi_cluster_lowest_credible"
        else:
            routing_reason = "no_credible_cluster"

        secondary_reason = ""
        if selection_blocked:
            secondary_reason = block_detail
        elif not has_credible:
            secondary_reason = _build_failure_reason(
                cluster_lists, effective_min_cluster_size
            )

        # ---- 构建牌名级汇总行 ----
        card_rows.append(
            {
                "card_name": card_name,
                "effective_min_cluster_size": effective_min_cluster_size,
                "old_release_rule_hit": old_release_rule_hit,
                "release_date_parse_ok": release_parse_ok if raw_release_map else "",
                "release_date_max": release_max_date_str if raw_release_map else "",
                "listing_count": listing_count,
                "unique_shop_count": unique_shop_count,
                "valid_price_count": valid_price_count,
                "overall_min_price": prices_sorted[0] if prices_sorted else None,
                "overall_max_price": prices_sorted[-1] if prices_sorted else None,
                "overall_raw_p25": overall_raw_p25,
                "overall_raw_p50": overall_raw_p50,
                "overall_raw_p75": overall_raw_p75,
                "overall_weighted_p25": overall_weighted_p25,
                "overall_weighted_p50": overall_weighted_p50,
                "overall_weighted_p75": overall_weighted_p75,
                "cluster_count": len(clusters),
                "has_lowest_trustworthy_cluster": has_credible,
                "lowest_trustworthy_cluster_id": (
                    credible_cluster["cluster_id"] if credible_cluster else None
                ),
                "lowest_trustworthy_cluster_listing_count": (
                    credible_cluster["cluster_listing_count"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_min_price": (
                    credible_cluster["cluster_min_price"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_max_price": (
                    credible_cluster["cluster_max_price"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_median_price": (
                    credible_cluster["cluster_median_price"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_raw_p25": (
                    credible_cluster["cluster_raw_p25"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_raw_p50": (
                    credible_cluster["cluster_raw_p50"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_raw_p75": (
                    credible_cluster["cluster_raw_p75"]
                    if credible_cluster
                    else None
                ),
                "lowest_trustworthy_cluster_span_ratio": (
                    credible_cluster["cluster_max_price"]
                    / max(0.01, credible_cluster["cluster_min_price"])
                    if credible_cluster
                    else None
                ),
                "routing_suggestion": routing_suggestion,
                "routing_reason": routing_reason,
                "target_quantile": eval_cfg["target_quantile"],
                "target_value": target_value,
                "eligible_final": has_credible,
                "risk_status": "pass" if has_credible else "blocked",
                "secondary_reason": secondary_reason,
                "prefix_pool_selected": prefix_pool_selected,
                "prefix_pool_count": prefix_pool_count,
                "prefix_pool_share": prefix_pool_share,
                "prefix_pool_gap_abs_observed": prefix_pool_gap_abs_observed,
                "prefix_pool_gap_ratio_observed": prefix_pool_gap_ratio_observed,
                "prefix_pool_reject_reason": prefix_reject_reason,
                "prefix_pool_blocked": selection_blocked,
                "evaluation_source": "greedy_growth_v3",
            }
        )

    result_df = pd.DataFrame(card_rows).sort_values(
        by=["has_lowest_trustworthy_cluster", "valid_price_count", "listing_count"],
        ascending=[False, False, False],
    )
    cluster_df = pd.DataFrame(cluster_rows).sort_values(
        by=["card_name", "cluster_id"], ascending=[True, True]
    )

    if output_file is None:
        base, _ = os.path.splitext(input_file)
        output_file = f"{base}_statistical_eval.xlsx"

    ensure_dir(os.path.dirname(output_file))
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        result_df.to_excel(writer, sheet_name="all_cards", index=False)
        cluster_df.to_excel(writer, sheet_name="clusters", index=False)
        result_df[
            result_df["routing_suggestion"] == "statistical_candidate"
        ].to_excel(writer, sheet_name="statistical_candidates", index=False)

    candidate_count = (
        int((result_df["routing_suggestion"] == "statistical_candidate").sum())
        if not result_df.empty
        else 0
    )
    fallback_count = (
        int((result_df["routing_suggestion"] == "open_url_fallback").sum())
        if not result_df.empty
        else 0
    )

    log.info(
        "货盘诊断完成: 共 %s 个牌名，statistical_candidate %s，open_url_fallback %s，输出 %s",
        len(result_df),
        candidate_count,
        fallback_count,
        output_file,
    )
    return {
        "success": True,
        "total_cards": int(len(result_df)),
        "eligible_cards": candidate_count,
        "warning_cards": 0,
        "fallback_cards": fallback_count,
        "output_file": output_file,
    }
