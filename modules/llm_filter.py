"""
LLM 智能过滤模块。
"""
import os
import logging
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from modules.llm_client import LLMClient, build_filter_prompt, parse_llm_response
from modules.mtg_db import MTGDatabase
from modules.utils import get_project_root, ensure_dir, print_progress


def _find_short_name_conflict(title, target_name, conflict_names):
    title = str(title or "").strip()
    target_name = str(target_name or "").strip()
    if not title or not target_name or target_name not in title:
        return None
    for candidate in conflict_names or []:
        cand = str(candidate or "").strip()
        if cand and cand in title:
            return cand
    return None


def _parse_name_list(raw_text):
    if not raw_text:
        return []
    text = str(raw_text)
    for sep in [";", "\n", "\r", "\t"]:
        text = text.replace(sep, ",")
    return [x.strip() for x in text.split(",") if x.strip()]


def _is_own_shop(shop_name, own_shop_names):
    shop = str(shop_name or "").strip()
    if not shop:
        return False
    return any(name and name in shop for name in own_shop_names)


def _find_existing_col(df, candidates):
    for col_name in candidates:
        if col_name in df.columns:
            return col_name
    return None


def _extract_target_name(keyword_value, title_value):
    if pd.notna(keyword_value):
        return str(keyword_value).replace("万智牌", "").strip()
    title_parts = str(title_value or "").split()
    return title_parts[1] if len(title_parts) > 1 else str(title_value or "")


def _prepare_db_references(config_file, config, df, log):
    use_db_reference = config.getboolean("FILTER", "use_db_reference", fallback=False)
    short_name_hard_veto = config.getboolean("FILTER", "short_name_hard_veto", fallback=True)
    short_name_conflict_limit = config.getint("FILTER", "short_name_conflict_limit", fallback=200)

    db_references = {}
    longer_name_conflicts = {}
    db_client = None

    if not use_db_reference:
        return use_db_reference, short_name_hard_veto, db_references, longer_name_conflicts, db_client

    db_client = MTGDatabase(config_file=config_file, logger=log)
    ok, message = db_client.test_connection()
    if not ok:
        log.warning(f"数据库参考未启用（{message}），将仅依赖 LLM 文本判断")
        return use_db_reference, short_name_hard_veto, db_references, longer_name_conflicts, None

    target_names = sorted({str(name).strip() for name in df["目标牌名"].tolist() if str(name).strip()})
    db_references = db_client.lookup_card_references(target_names)
    log.info(f"数据库参考已加载: {len(db_references)} 个目标牌名")

    if short_name_hard_veto:
        longer_name_conflicts = db_client.lookup_longer_name_conflicts(
            target_names, limit_count=short_name_conflict_limit
        )
        hit_keys = sum(1 for value in longer_name_conflicts.values() if value)
        log.info(f"短名冲突词已加载: {hit_keys}/{len(target_names)} 个目标牌名存在更长官方名")

    return use_db_reference, short_name_hard_veto, db_references, longer_name_conflicts, db_client


def _write_filtered_outputs(df, keep_col, result_col, output_file, pure_drop_cols, logger):
    kept_mask = df[keep_col] == True
    removed_mask = df[keep_col] == False
    uncertain_mask = df[keep_col].isna()

    kept_count = kept_mask.sum()
    removed_count = removed_mask.sum()
    uncertain_count = uncertain_mask.sum()

    full_df = df.copy()
    full_df[result_col] = "处理失败"
    full_df.loc[kept_mask, result_col] = "保留"
    full_df.loc[removed_mask, result_col] = "删除"

    cols = [x for x in full_df.columns if x != result_col]
    insert_at = cols.index(keep_col) + 1
    cols = cols[:insert_at] + [result_col] + cols[insert_at:]
    full_df = full_df[cols]

    kept_df = full_df[kept_mask].copy()
    removed_df = full_df[removed_mask].copy()
    uncertain_df = full_df[uncertain_mask].copy()

    ensure_dir(os.path.dirname(output_file))

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        full_df.to_excel(writer, sheet_name="全部", index=False)
        removed_df.to_excel(writer, sheet_name="已删除", index=False)
        if len(uncertain_df) > 0:
            uncertain_df.to_excel(writer, sheet_name="处理失败", index=False)

    pure_output = output_file.replace(".xlsx", "_pure.xlsx")
    kept_df.drop(columns=pure_drop_cols, errors="ignore").to_excel(
        pure_output, index=False, engine="openpyxl"
    )

    logger.info(f"过滤结果已保存: {output_file}")
    logger.info(f"纯净结果已保存: {pure_output}")

    return {
        "kept": int(kept_count),
        "removed": int(removed_count),
        "uncertain": int(uncertain_count),
        "output_file": output_file,
        "pure_output_file": pure_output,
    }


def filter_with_db_only(input_file, output_file=None, logger=None):
    log = logger or logging.getLogger(__name__)

    config_file = os.path.join(get_project_root(), "config", "settings.ini")
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    if not os.path.exists(input_file):
        log.error(f"输入文件不存在: {input_file}")
        return {"success": False, "error": "文件不存在"}

    try:
        df = pd.read_excel(input_file, engine="openpyxl")
        log.info(f"读取文件: {input_file} ({len(df)} 行)")
    except Exception as e:
        log.error(f"读取 Excel 失败: {e}")
        return {"success": False, "error": str(e)}

    title_col = _find_existing_col(df, ["商品名称", "标题", "title", "商品标题"])
    keyword_col = _find_existing_col(df, ["搜索关键词", "关键词", "keyword"])
    shop_col = _find_existing_col(df, ["店铺名称", "掌柜名", "店铺", "shop_name", "seller_name"])

    if title_col is None:
        log.error(f"未找到标题列，现有列: {list(df.columns)}")
        return {"success": False, "error": "未找到标题列"}

    df["目标牌名"] = [
        _extract_target_name(row.get(keyword_col) if keyword_col else None, row[title_col])
        for _, row in df.iterrows()
    ]

    (
        use_db_reference,
        short_name_hard_veto,
        _db_references,
        longer_name_conflicts,
        _db_client,
    ) = _prepare_db_references(config_file, config, df, log)

    own_shop_names = _parse_name_list(config.get("FILTER", "exclude_shop_names", fallback="真橙卡牌"))

    df["DB_保留"] = True
    df["DB_规则来源"] = "db_pass_through"
    df["DB_原因"] = "未命中DB硬规则，直接保留"

    own_shop_veto_count = 0
    short_name_veto_count = 0

    if shop_col and own_shop_names:
        own_shop_mask = df[shop_col].astype(str).apply(lambda x: _is_own_shop(x, own_shop_names))
        df.loc[own_shop_mask, "DB_保留"] = False
        df.loc[own_shop_mask, "DB_规则来源"] = "hard_veto_own_shop"
        df.loc[own_shop_mask, "DB_原因"] = (
            "自有店铺前置剔除: 店铺<" + df.loc[own_shop_mask, shop_col].astype(str) + ">"
        )
        own_shop_veto_count = int(own_shop_mask.sum())

    if use_db_reference and short_name_hard_veto and longer_name_conflicts:
        for idx, row in df[df["DB_保留"] == True].iterrows():
            conflict_hit = _find_short_name_conflict(
                title=row[title_col],
                target_name=row["目标牌名"],
                conflict_names=longer_name_conflicts.get(str(row["目标牌名"]).strip(), []),
            )
            if conflict_hit:
                df.at[idx, "DB_保留"] = False
                df.at[idx, "DB_规则来源"] = "hard_veto_short_name"
                df.at[idx, "DB_原因"] = (
                    f"短名冲突硬拦截: 目标牌名<{row['目标牌名']}> 命中更长官方名<{conflict_hit}>"
                )
                short_name_veto_count += 1

    total_rows = len(df)
    kept_count = int((df["DB_保留"] == True).sum())
    removed_count = int((df["DB_保留"] == False).sum())
    log.info(f"DB前置过滤完成: 保留 {kept_count}, 删除 {removed_count}, 处理失败 0")
    if own_shop_veto_count > 0:
        log.info(f"自有店铺前置剔除命中 {own_shop_veto_count} 条")
    if short_name_veto_count > 0:
        log.info(f"短名冲突硬拦截命中 {short_name_veto_count} 条")

    if output_file is None:
        base, _ = os.path.splitext(input_file)
        output_file = f"{base}_db_filtered.xlsx"

    output_info = _write_filtered_outputs(
        df=df,
        keep_col="DB_保留",
        result_col="DB_结果",
        output_file=output_file,
        pure_drop_cols=["目标牌名"],
        logger=log,
    )

    return {
        "success": True,
        "total": int(total_rows),
        **output_info,
    }


def filter_with_llm(input_file, output_file=None, batch_size=10, logger=None):
    log = logger or logging.getLogger(__name__)

    config_file = os.path.join(get_project_root(), "config", "settings.ini")
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    if not os.path.exists(input_file):
        log.error(f"输入文件不存在: {input_file}")
        return {"success": False, "error": "文件不存在"}

    try:
        df = pd.read_excel(input_file, engine="openpyxl")
        log.info(f"读取文件: {input_file} ({len(df)} 行)")
    except Exception as e:
        log.error(f"读取 Excel 失败: {e}")
        return {"success": False, "error": str(e)}

    title_col = _find_existing_col(df, ["商品名称", "标题", "title", "商品标题"])
    keyword_col = _find_existing_col(df, ["搜索关键词", "关键词", "keyword"])
    shop_col = _find_existing_col(df, ["店铺名称", "掌柜名", "店铺", "shop_name", "seller_name"])

    if title_col is None:
        log.error(f"未找到标题列，现有列: {list(df.columns)}")
        return {"success": False, "error": "未找到标题列"}

    df["目标牌名"] = [
        _extract_target_name(row.get(keyword_col) if keyword_col else None, row[title_col])
        for _, row in df.iterrows()
    ]

    try:
        llm = LLMClient(logger=log)
        log.info("LLM 客户端初始化成功")
    except Exception as e:
        log.error(f"LLM 客户端初始化失败: {e}")
        return {"success": False, "error": f"LLM 初始化失败: {e}"}

    (
        use_db_reference,
        short_name_hard_veto,
        db_references,
        longer_name_conflicts,
        db_client,
    ) = _prepare_db_references(config_file, config, df, log)

    own_shop_names = _parse_name_list(config.get("FILTER", "exclude_shop_names", fallback="真橙卡牌"))

    df["LLM_是MTG卡牌"] = None
    df["LLM_牌名匹配"] = None
    df["LLM_保留"] = None
    df["LLM_规则来源"] = None
    df["LLM_原因"] = None

    raw_items = []
    for idx, row in df.iterrows():
        raw_items.append({
            "index": idx,
            "商品名称": str(row[title_col]),
            "目标牌名": str(row["目标牌名"]).strip(),
            "店铺名称": str(row[shop_col]) if shop_col else "",
        })

    title_hints_by_index = {}
    if use_db_reference and db_client is not None:
        title_hints_by_index = db_client.lookup_title_hints(raw_items)

    items = []
    pre_veto_count = 0
    pre_veto_by_target = {}
    own_shop_veto_count = 0

    for item in raw_items:
        refs = list(db_references.get(item["目标牌名"], []))
        refs.extend(title_hints_by_index.get(item["index"], []))
        item["数据库候选"] = refs

        if own_shop_names and _is_own_shop(item.get("店铺名称"), own_shop_names):
            actual_idx = item["index"]
            df.at[actual_idx, "LLM_保留"] = False
            df.at[actual_idx, "LLM_规则来源"] = "hard_veto_own_shop"
            df.at[actual_idx, "LLM_原因"] = f"自有店铺前置剔除: 店铺<{item.get('店铺名称', '')}>"
            own_shop_veto_count += 1
            continue

        if short_name_hard_veto and longer_name_conflicts:
            conflict_hit = _find_short_name_conflict(
                title=item["商品名称"],
                target_name=item["目标牌名"],
                conflict_names=longer_name_conflicts.get(item["目标牌名"], []),
            )
            if conflict_hit:
                actual_idx = item["index"]
                df.at[actual_idx, "LLM_牌名匹配"] = False
                df.at[actual_idx, "LLM_保留"] = False
                df.at[actual_idx, "LLM_规则来源"] = "hard_veto_short_name"
                df.at[actual_idx, "LLM_原因"] = (
                    f"短名冲突硬拦截: 目标牌名<{item['目标牌名']}> 命中更长官方名<{conflict_hit}>"
                )
                pre_veto_count += 1
                pre_veto_by_target[item["目标牌名"]] = pre_veto_by_target.get(item["目标牌名"], 0) + 1
                continue

        items.append(item)

    llm_total = len(items)
    total_rows = len(raw_items)

    if pre_veto_count > 0:
        top_targets = sorted(pre_veto_by_target.items(), key=lambda x: x[1], reverse=True)[:5]
        top_text = ", ".join([f"{k}:{v}" for k, v in top_targets])
        log.info(f"短名冲突硬拦截命中 {pre_veto_count} 条；Top目标牌名: {top_text}")
    if own_shop_veto_count > 0:
        log.info(f"自有店铺前置剔除命中 {own_shop_veto_count} 条")
    log.info(f"需进入 LLM 处理 {llm_total} 条（总计 {total_rows} 条）")

    use_web_search_fallback = config.getboolean("LLM", "use_web_search_fallback", fallback=False)
    if use_web_search_fallback and llm.current_provider != "zhipu":
        log.warning("use_web_search_fallback 已开启，但当前 provider 非 zhipu，联网第二判将跳过")

    max_workers = max(1, config.getint("LLM", "max_workers", fallback=2))
    ws_model = config.get("LLM", "web_search_model", fallback=llm.zhipu_model)

    batches = []
    for batch_start in range(0, llm_total, batch_size):
        batch_end = min(batch_start + batch_size, llm_total)
        batches.append((batch_start, batch_end, items[batch_start:batch_end]))

    def process_batch(batch_start, batch_end, batch_items):
        payload = {
            "batch_items": batch_items,
            "results": [],
            "results2": None,
            "error": None,
            "web_error": None,
        }
        log.info(f"处理批次 {batch_start + 1}-{batch_end}/{llm_total}")
        try:
            system_prompt, user_prompt = build_filter_prompt(batch_items)
            response = llm.chat(user_prompt, system_prompt=system_prompt, temperature=0.3)
            results = parse_llm_response(response)
            payload["results"] = results

            if use_web_search_fallback and llm.current_provider == "zhipu" and results:
                need_web = []
                for result in results:
                    oi = result.get("index", 0) - 1
                    if oi < len(batch_items) and result.get("需要联网") is True:
                        need_web.append(batch_items[oi])
                if need_web:
                    log.info(f"联网第二判: {len(need_web)} 条 (model={ws_model})")
                    sys2, user2 = build_filter_prompt(need_web, second_round_web=True)
                    try:
                        resp2 = llm.chat(
                            user2,
                            system_prompt=sys2,
                            temperature=0.3,
                            zhipu_model=ws_model,
                            zhipu_web_search=True,
                        )
                        payload["results2"] = {
                            "items": need_web,
                            "results": parse_llm_response(resp2),
                        }
                    except Exception as e2:
                        payload["web_error"] = str(e2)
        except Exception as e:
            payload["error"] = str(e)
        return payload

    processed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_batch, batch_start, batch_end, batch_items)
            for batch_start, batch_end, batch_items in batches
        ]

        for future in as_completed(futures):
            payload = future.result()
            batch_items = payload["batch_items"]
            results = payload["results"] or []

            if payload["error"]:
                e = payload["error"]
                log.error(f"批次处理失败: {e}")
                for item in batch_items:
                    df.at[item["index"], "LLM_是MTG卡牌"] = None
                    df.at[item["index"], "LLM_牌名匹配"] = None
                    df.at[item["index"], "LLM_保留"] = None
                    df.at[item["index"], "LLM_规则来源"] = "llm_batch_error"
                    df.at[item["index"], "LLM_原因"] = f"处理失败: {e}"
            else:
                for result in results:
                    original_idx = result.get("index", 0) - 1
                    if original_idx < len(batch_items):
                        actual_idx = batch_items[original_idx]["index"]
                        df.at[actual_idx, "LLM_是MTG卡牌"] = result.get("是MTG卡牌")
                        df.at[actual_idx, "LLM_牌名匹配"] = result.get("牌名匹配")
                        df.at[actual_idx, "LLM_保留"] = result.get("保留")
                        df.at[actual_idx, "LLM_规则来源"] = "llm_round1"
                        df.at[actual_idx, "LLM_原因"] = result.get("原因", "")

                if payload["results2"]:
                    for result in payload["results2"]["results"]:
                        oi = result.get("index", 0) - 1
                        if oi < len(payload["results2"]["items"]):
                            actual_idx = payload["results2"]["items"][oi]["index"]
                            df.at[actual_idx, "LLM_是MTG卡牌"] = result.get("是MTG卡牌")
                            df.at[actual_idx, "LLM_牌名匹配"] = result.get("牌名匹配")
                            df.at[actual_idx, "LLM_保留"] = result.get("保留")
                            df.at[actual_idx, "LLM_规则来源"] = "llm_web_round2"
                            reason = result.get("原因", "") or ""
                            prefix = "[联网复核] "
                            df.at[actual_idx, "LLM_原因"] = f"{prefix}{reason}" if reason else prefix.strip()
                elif payload["web_error"]:
                    log.warning(f"联网第二判失败，保留首轮结果: {payload['web_error']}")

            processed += len(batch_items)
            print_progress(processed, llm_total, prefix="LLM过滤进度", suffix="")

    print()

    kept_mask = df["LLM_保留"] == True
    removed_mask = df["LLM_保留"] == False
    uncertain_mask = df["LLM_保留"].isna()

    kept_count = kept_mask.sum()
    removed_count = removed_mask.sum()
    uncertain_count = uncertain_mask.sum()

    log.info(f"过滤完成: 保留 {kept_count}, 删除 {removed_count}, 处理失败 {uncertain_count}")

    full_df = df.copy()
    full_df["LLM_结果"] = "处理失败"
    full_df.loc[kept_mask, "LLM_结果"] = "保留"
    full_df.loc[removed_mask, "LLM_结果"] = "删除"

    cols = [x for x in full_df.columns if x != "LLM_结果"]
    insert_at = cols.index("LLM_保留") + 1
    cols = cols[:insert_at] + ["LLM_结果"] + cols[insert_at:]
    full_df = full_df[cols]

    kept_df = full_df[kept_mask].copy()
    removed_df = full_df[removed_mask].copy()
    uncertain_df = full_df[uncertain_mask].copy()

    if output_file is None:
        base, _ = os.path.splitext(input_file)
        output_file = f"{base}_llm_filtered.xlsx"

    ensure_dir(os.path.dirname(output_file))

    try:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            full_df.to_excel(writer, sheet_name="全部", index=False)
            removed_df.to_excel(writer, sheet_name="已删除", index=False)
            if len(uncertain_df) > 0:
                uncertain_df.to_excel(writer, sheet_name="处理失败", index=False)

        log.info(
            f"过滤结果已保存: {output_file} "
            f"（工作表「全部」= 原表全部行+LLM 列；「已删除」= 仅被筛掉的行；有失败批次时另有「处理失败」）"
        )

        pure_output = output_file.replace(".xlsx", "_pure.xlsx")
        kept_df.drop(columns=["目标牌名"], errors="ignore").to_excel(
            pure_output, index=False, engine="openpyxl"
        )
        log.info(f"纯净结果已保存: {pure_output}（仅保留 LLM 判定为保留的行）")

    except Exception as e:
        log.error(f"保存结果失败: {e}")
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "total": int(total_rows),
        "kept": int(kept_count),
        "removed": int(removed_count),
        "uncertain": int(uncertain_count),
        "output_file": output_file,
        "pure_output_file": pure_output,
    }
