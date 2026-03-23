"""
过滤模块
对店透视导出的搜索结果进行基于规则的初筛
"""
import os
import logging
import pandas as pd


def filter_exported_results(export_file, keyword, card_name,
                            output_dir='data/filtered',
                            require_magic_prefix=True,
                            require_card_name=True,
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

    # 应用过滤规则
    mask = pd.Series([True] * len(df), index=df.index)

    if require_magic_prefix:
        magic_mask = df[title_col].astype(str).apply(
            lambda t: '万智牌' in t or 'MTG' in t or 'mtg' in t
        )
        mask = mask & magic_mask
        log.info(f"  \"万智牌\"/\"MTG\" 过滤后: {magic_mask.sum()}/{total_rows}")

    if require_card_name:
        name_mask = df[title_col].astype(str).apply(
            lambda t: card_name in t
        )
        mask = mask & name_mask
        log.info(f"  牌名\"{card_name}\" 过滤后: {name_mask.sum()}/{total_rows}")

    filtered_df = df[mask]
    filtered_rows = len(filtered_df)

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

    try:
        filtered_df.to_excel(output_file, index=False, engine='openpyxl')
        log.info(f"  过滤结果已保存: {output_file} ({filtered_rows} 行)")
    except Exception as e:
        log.error(f"  保存过滤结果失败: {e}")

    result = {
        'success': True,
        'total_rows': total_rows,
        'filtered_rows': filtered_rows,
        'min_price': float(min_price) if min_price is not None else None,
        'filtered_file': output_file
    }

    log.info(f"过滤完成: {total_rows} → {filtered_rows} 行")
    return result


def merge_filtered_results(task_dir, output_file=None):
    """
    合并一次任务中所有关键词的过滤结果为一张总表

    Args:
        task_dir: 包含多个过滤结果Excel的目录
        output_file: 合并后的输出文件路径

    Returns:
        str: 合并文件路径，失败返回None
    """
    if not os.path.exists(task_dir):
        return None

    excel_files = [f for f in os.listdir(task_dir) if f.endswith('_filtered.xlsx')]

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
