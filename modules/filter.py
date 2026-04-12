"""
过滤模块
对店透视导出的搜索结果进行基于规则的初筛
"""
import os
import logging
import pandas as pd


def _parse_name_list(raw_text):
    """支持逗号/分号/换行分隔的店铺名单配置。"""
    if not raw_text:
        return []
    text = str(raw_text)
    for sep in [';', '\n', '\r', '\t']:
        text = text.replace(sep, ',')
    return [x.strip() for x in text.split(',') if x.strip()]


def _is_own_shop(shop_name, own_shop_names):
    shop = str(shop_name or '').strip()
    if not shop:
        return False
    return any(name and name in shop for name in own_shop_names)


def _contains_excluded_keyword(title, excluded_keywords):
    text = str(title or '').strip().lower()
    if not text:
        return False
    for keyword in excluded_keywords:
        kw = str(keyword or '').strip().lower()
        if kw and kw in text:
            return True
    return False


def filter_exported_results(export_file, keyword, card_name,
                            output_dir='data/filtered',
                            require_magic_prefix=True,
                            require_card_name=True,
                            exclude_shop_names='',
                            exclude_title_keywords='',
                            logger=None):
    """
    过滤导出的搜索结果

    初筛规则：
    - 标题必须包含"万智牌"或"MTG"
    - 标题必须包含牌名字符串（子串匹配，不判断边界）

    注意：中文无空格分隔，子串匹配可能产生误匹配（如"风化侵蚀"匹配到"风化侵蚀术"），
    精确匹配留给未来LLM阶段处理。

    Args:
        export_file: 导出的Excel文件路径
        keyword: 搜索关键词（如"万智牌 中止"）
        card_name: 牌名（如"中止"）
        output_dir: 过滤结果输出目录
        require_magic_prefix: 是否要求标题含"万智牌"或"MTG"
        require_card_name: 是否要求标题含牌名
        exclude_shop_names: 自有店铺名单，逗号/分号/换行分隔
        exclude_title_keywords: 标题禁词，逗号/分号/换行分隔
        logger: 日志记录器

    Returns:
        dict: 过滤结果摘要
    """
    log = logger or logging.getLogger(__name__)

    if not os.path.exists(export_file):
        log.error(f"导出文件不存在: {export_file}")
        return {'success': False, 'error': '文件不存在'}

    # 读取导出的Excel文件
    try:
        df = pd.read_excel(export_file, engine='openpyxl')
        log.info(f"读取导出文件: {export_file} ({len(df)} 行)")
    except Exception as e:
        log.error(f"读取导出文件失败: {e}")
        return {'success': False, 'error': str(e)}

    # 确定标题列
    title_col = None
    for col_name in ['商品名称', '标题', 'title', '商品标题']:
        if col_name in df.columns:
            title_col = col_name
            break

    if title_col is None:
        log.error(f"未找到标题列，现有列: {list(df.columns)}")
        return {'success': False, 'error': '未找到标题列'}

    # 确定价格列
    price_col = None
    for col_name in ['现价', '价格', 'price']:
        if col_name in df.columns:
            price_col = col_name
            break

    total_rows = len(df)
    own_shop_names = _parse_name_list(exclude_shop_names)
    excluded_title_keywords = _parse_name_list(exclude_title_keywords)

    # 应用过滤规则
    mask = pd.Series([True] * len(df), index=df.index)
    reason_mask = pd.Series([""] * len(df), index=df.index, dtype='object')

    if require_magic_prefix:
        magic_mask = df[title_col].astype(str).apply(
            lambda t: '万智牌' in t or 'MTG' in t or 'mtg' in t
        )
        mask = mask & magic_mask
        reason_mask = reason_mask.mask(~magic_mask, reason_mask.astype(str) + '缺少万智牌/MTG前缀;')
        log.info(f"  \"万智牌\"/\"MTG\" 过滤后: {magic_mask.sum()}/{total_rows}")

    if require_card_name:
        name_mask = df[title_col].astype(str).apply(
            lambda t: card_name in t
        )
        mask = mask & name_mask
        reason_mask = reason_mask.mask(~name_mask, reason_mask.astype(str) + f'标题不含牌名<{card_name}>;')
        log.info(f"  牌名\"{card_name}\" 过滤后: {name_mask.sum()}/{total_rows}")

    if excluded_title_keywords:
        excluded_title_mask = df[title_col].astype(str).apply(
            lambda t: _contains_excluded_keyword(t, excluded_title_keywords)
        )
        mask = mask & ~excluded_title_mask
        reason_mask = reason_mask.mask(
            excluded_title_mask,
            reason_mask.astype(str) + '命中标题禁词;'
        )
        log.info(
            f"  标题禁词前置剔除后: {(~excluded_title_mask).sum()}/{total_rows}（命中 {excluded_title_mask.sum()}）"
        )

    shop_col = None
    for col_name in ['店铺名称', '掌柜名', '店铺', 'shop_name', 'seller_name']:
        if col_name in df.columns:
            shop_col = col_name
            break

    if own_shop_names and shop_col:
        own_shop_mask = df[shop_col].astype(str).apply(
            lambda shop: _is_own_shop(shop, own_shop_names)
        )
        mask = mask & ~own_shop_mask
        reason_mask = reason_mask.mask(
            own_shop_mask,
            reason_mask.astype(str) + '自有店铺前置剔除;'
        )
        log.info(f"  自有店铺前置剔除后: {(~own_shop_mask).sum()}/{total_rows}（命中 {own_shop_mask.sum()}）")

    full_df = df.copy()
    full_df['规则过滤_保留'] = mask
    full_df['规则过滤_规则来源'] = None
    full_df['规则过滤_原因'] = reason_mask.astype(str).str.rstrip(';')

    full_df.loc[full_df['规则过滤_保留'], '规则过滤_规则来源'] = 'base_filter_keep'
    full_df.loc[
        full_df['规则过滤_原因'].str.contains('自有店铺前置剔除', na=False),
        '规则过滤_规则来源'
    ] = 'hard_veto_own_shop'
    full_df.loc[
        full_df['规则过滤_原因'].str.contains('命中标题禁词', na=False),
        '规则过滤_规则来源'
    ] = 'hard_veto_title_keyword'
    full_df.loc[
        full_df['规则过滤_规则来源'].isna() & (~full_df['规则过滤_保留']),
        '规则过滤_规则来源'
    ] = 'base_filter_rule'

    filtered_df = full_df[mask].copy()
    filtered_rows = len(filtered_df)
    removed_df = full_df[~mask].copy()

    # 提取价格信息
    min_price = None
    if price_col and filtered_rows > 0:
        try:
            prices = pd.to_numeric(filtered_df[price_col], errors='coerce')
            prices = prices.dropna()
            if len(prices) > 0:
                min_price = prices.min()
                log.info(f"  过滤后最低价: {min_price}")
        except Exception:
            pass

    # 保存过滤结果
    os.makedirs(output_dir, exist_ok=True)
    safe_name = keyword.replace(' ', '_').replace('/', '_')
    output_file = os.path.join(output_dir, f"{safe_name}_filtered.xlsx")
    audit_file = os.path.join(output_dir, f"{safe_name}_filter_audit.xlsx")

    try:
        filtered_df.to_excel(output_file, index=False, engine='openpyxl')
        log.info(f"  过滤结果已保存: {output_file} ({filtered_rows} 行)")
    except Exception as e:
        log.error(f"  保存过滤结果失败: {e}")

    try:
        with pd.ExcelWriter(audit_file, engine='openpyxl') as writer:
            full_df.to_excel(writer, sheet_name='全部', index=False)
            if len(removed_df) > 0:
                removed_df.to_excel(writer, sheet_name='已删除', index=False)
        log.info(f"  规则过滤审计已保存: {audit_file}")
    except Exception as e:
        log.error(f"  保存规则过滤审计失败: {e}")

    result = {
        'success': True,
        'total_rows': total_rows,
        'filtered_rows': filtered_rows,
        'min_price': float(min_price) if min_price is not None else None,
        'filtered_file': output_file,
        'audit_file': audit_file,
        'removed_rows': int((~mask).sum())
    }

    log.info(f"过滤完成: {total_rows} → {filtered_rows} 行")
    return result


def merge_filtered_results(task_dir, output_file=None, keyword_order=None):
    """
    合并一次任务中所有关键词的过滤结果为一张总表

    Args:
        task_dir: 包含多个过滤结果Excel的目录
        output_file: 合并后的输出文件路径
        keyword_order: 搜索关键词顺序列表（用于按原始处理顺序合并）

    Returns:
        str: 合并文件路径，失败返回None
    """
    if not os.path.exists(task_dir):
        return None

    excel_files = [f for f in os.listdir(task_dir) if f.endswith('_filtered.xlsx')]

    if keyword_order:
        # 以保存过滤文件时的 safe_name 规则建立顺序索引
        def _safe_name(keyword):
            return str(keyword).replace(' ', '_').replace('/', '_')

        order_index = {
            _safe_name(kw): idx for idx, kw in enumerate(keyword_order)
        }

        def _sort_key(filename):
            stem = filename[:-len('_filtered.xlsx')]
            return (order_index.get(stem, 10**9), filename)

        excel_files = sorted(excel_files, key=_sort_key)

    if not excel_files:
        return None

    all_dfs = []
    for filename in excel_files:
        filepath = os.path.join(task_dir, filename)
        try:
            df = pd.read_excel(filepath, engine='openpyxl')
            # 添加来源关键词列
            keyword = filename.replace('_filtered.xlsx', '').replace('_', ' ')
            df['搜索关键词'] = keyword
            all_dfs.append(df)
        except Exception:
            continue

    if not all_dfs:
        return None

    merged = pd.concat(all_dfs, ignore_index=True)

    if output_file is None:
        output_file = os.path.join(task_dir, '合并结果.xlsx')

    merged.to_excel(output_file, index=False, engine='openpyxl')
    return output_file
