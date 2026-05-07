"""
输入模块
负责读取Excel文件，提取去重后的牌名，生成搜索关键词
"""
import os
import json
import pandas as pd
from datetime import datetime


def read_excel_input(filepath):
    """
    读取Excel输入文件

    Args:
        filepath: Excel文件路径

    Returns:
        pd.DataFrame: 完整的数据表
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Excel文件不存在: {filepath}")

    df = pd.read_excel(filepath, engine='openpyxl')
    print(f"成功读取Excel文件: {filepath}")
    print(f"  总行数: {len(df)}, 总列数: {len(df.columns)}")
    print(f"  列名: {list(df.columns)}")
    return df


def extract_unique_card_names(df, card_name_column='中文卡牌名', product_id_column='productId'):
    """
    从数据表中提取唯一牌名，并建立牌名到productId的映射

    Args:
        df: 数据表DataFrame
        card_name_column: 牌名列名（D列）
        product_id_column: productId列名（H列）

    Returns:
        tuple: (唯一牌名列表, 牌名到productId列表的映射字典)
    """
    if card_name_column not in df.columns:
        raise ValueError(f"数据表中找不到列 '{card_name_column}'，现有列: {list(df.columns)}")

    # 去除空值和空白
    mask = df[card_name_column].notna() & (df[card_name_column].astype(str).str.strip() != '')
    df_valid = df[mask].copy()
    df_valid[card_name_column] = df_valid[card_name_column].astype(str).str.strip()

    # 按首次出现顺序去重
    unique_names = df_valid[card_name_column].unique().tolist()
    print(f"  有效行数: {len(df_valid)}")
    print(f"  唯一牌名数: {len(unique_names)}")

    # 建立牌名到productId的映射
    name_to_product_ids = {}
    for name in unique_names:
        rows = df_valid[df_valid[card_name_column] == name]
        if product_id_column in rows.columns:
            ids = rows[product_id_column].dropna().astype(int).tolist()
        else:
            ids = []
        name_to_product_ids[name] = ids

    return unique_names, name_to_product_ids


def build_search_keywords(unique_names, prefix='万智牌'):
    """
    为每个唯一牌名构建搜索关键词

    Args:
        unique_names: 唯一牌名列表
        prefix: 搜索前缀

    Returns:
        list: 搜索关键词列表
    """
    def normalize_name_for_search(name):
        """
        规范化搜索牌名。

        双面牌常见写法是“正面 // 背面”，淘宝 listing 通常只写正面。
        因此仅在“空格//空格”格式下，取 `//` 前半段作为搜索词。
        """
        text = str(name).strip()
        if ' // ' in text:
            front = text.split(' // ', 1)[0].strip()
            return front or text
        return text

    keywords = [f"{prefix} {normalize_name_for_search(name)}" for name in unique_names]
    print(f"  已生成 {len(keywords)} 个搜索关键词（前缀: '{prefix}'）")
    return keywords


def save_card_name_mapping(name_to_product_ids, output_dir):
    """
    保存牌名到productId的映射到JSON文件

    Args:
        name_to_product_ids: 映射字典
        output_dir: 输出目录

    Returns:
        str: 保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, 'card_name_mapping.json')

    # 转换为可序列化的格式
    serializable = {str(k): [int(i) for i in v] for k, v in name_to_product_ids.items()}

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    print(f"  牌名映射已保存: {filepath} ({len(serializable)} 个牌名)")
    return filepath


def process_excel(filepath, prefix='万智牌', card_name_column='中文卡牌名',
                  product_id_column='productId', checkpoint_dir=None):
    """
    完整处理流程：读取Excel → 提取去重牌名 → 生成关键词 → 保存映射

    Args:
        filepath: Excel文件路径
        prefix: 搜索关键词前缀
        card_name_column: 牌名列名
        product_id_column: productId列名
        checkpoint_dir: 映射文件保存目录

    Returns:
        tuple: (DataFrame, 唯一牌名列表, 搜索关键词列表, 映射字典)
    """
    print("=" * 60)
    print("读取输入Excel文件")
    print("=" * 60)

    df = read_excel_input(filepath)
    unique_names, name_to_ids = extract_unique_card_names(df, card_name_column, product_id_column)
    keywords = build_search_keywords(unique_names, prefix)

    # 显示一些统计信息
    from collections import Counter
    id_counts = [len(ids) for ids in name_to_ids.values()]
    print(f"  每个牌名对应product数: 最多 {max(id_counts)}, 平均 {sum(id_counts)/len(id_counts):.1f}")

    # 显示前10个关键词作为示例
    print(f"\n  前10个搜索关键词示例:")
    for kw in keywords[:10]:
        print(f"    - {kw}")
    if len(keywords) > 10:
        print(f"    ... 共 {len(keywords)} 个")

    # 保存映射
    if checkpoint_dir:
        save_card_name_mapping(name_to_ids, checkpoint_dir)

    return df, unique_names, keywords, name_to_ids
