"""
LLM智能过滤模块
使用大模型对合并结果进行双重验证过滤
"""
import os
import logging
import configparser
import pandas as pd
from datetime import datetime

from modules.llm_client import LLMClient, build_filter_prompt, parse_llm_response
from modules.mtg_db import MTGDatabase
from modules.utils import get_project_root, ensure_dir, print_progress


def filter_with_llm(input_file, output_file=None, batch_size=5, logger=None):
    """
    使用LLM对合并结果进行智能过滤

    双重验证：
    1. 是否是MTG产品？（排除周边、书籍、桌游等）
    2. 是否是目标牌名？（使用搜索关键词列匹配）

    Args:
        input_file: 合并结果Excel文件路径
        output_file: 过滤结果输出路径，默认在同目录添加_llm_filtered后缀
        batch_size: 每批处理的商品数量
        logger: 日志记录器

    Returns:
        dict: 过滤结果摘要
    """
    log = logger or logging.getLogger(__name__)

    config_file = os.path.join(get_project_root(), 'config', 'settings.ini')
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')

    if not os.path.exists(input_file):
        log.error(f"输入文件不存在: {input_file}")
        return {'success': False, 'error': '文件不存在'}

    # 读取Excel
    try:
        df = pd.read_excel(input_file, engine='openpyxl')
        log.info(f"读取文件: {input_file} ({len(df)} 行)")
    except Exception as e:
        log.error(f"读取Excel失败: {e}")
        return {'success': False, 'error': str(e)}

    # 确定列名
    title_col = None
    for col_name in ['商品名称', '标题', 'title', '商品标题']:
        if col_name in df.columns:
            title_col = col_name
            break

    keyword_col = None
    for col_name in ['搜索关键词', '关键词', 'keyword']:
        if col_name in df.columns:
            keyword_col = col_name
            break

    if title_col is None:
        log.error(f"未找到标题列，现有列: {list(df.columns)}")
        return {'success': False, 'error': '未找到标题列'}

    if keyword_col is None:
        log.warning(f"未找到关键词列，使用默认值，假设关键词已去前缀")
        df['目标牌名'] = df[title_col].apply(lambda x: str(x).split()[1] if len(str(x).split()) > 1 else str(x))
    else:
        # 从搜索关键词提取牌名（去掉"万智牌 "前缀）
        df['目标牌名'] = df[keyword_col].apply(
            lambda x: str(x).replace('万智牌', '').strip() if pd.notna(x) else ''
        )

    # 初始化LLM客户端
    try:
        llm = LLMClient(logger=log)
        log.info("LLM客户端初始化成功")
    except Exception as e:
        log.error(f"LLM客户端初始化失败: {e}")
        return {'success': False, 'error': f'LLM初始化失败: {e}'}

    # 初始化数据库参考客户端（可选）
    use_db_reference = config.getboolean('FILTER', 'use_db_reference', fallback=False)
    db_references = {}
    db_client = None
    if use_db_reference:
        db_client = MTGDatabase(config_file=config_file, logger=log)
        ok, message = db_client.test_connection()
        if ok:
            target_names = sorted({
                str(name).strip()
                for name in df['目标牌名'].tolist()
                if str(name).strip()
            })
            db_references = db_client.lookup_card_references(target_names)
            log.info(f"数据库参考已加载: {len(db_references)} 个目标牌名")
        else:
            log.warning(f"数据库参考未启用（{message}），将仅依赖LLM文本判断")

    # 准备处理数据
    raw_items = []
    for idx, row in df.iterrows():
        target_name = str(row['目标牌名']).strip()
        raw_items.append({
            'index': idx,
            '商品名称': str(row[title_col]),
            '目标牌名': target_name
        })

    title_hints_by_index = {}
    if use_db_reference and db_client is not None:
        title_hints_by_index = db_client.lookup_title_hints(raw_items)

    items = []
    for item in raw_items:
        refs = list(db_references.get(item['目标牌名'], []))
        refs.extend(title_hints_by_index.get(item['index'], []))
        item['数据库候选'] = refs
        items.append(item)

    total = len(items)
    log.info(f"共 {total} 条记录待处理")

    # 添加结果列
    df['LLM_是MTG卡牌'] = None
    df['LLM_牌名匹配'] = None
    df['LLM_保留'] = None
    df['LLM_原因'] = None

    # 分批处理
    processed = 0
    success_count = 0
    error_count = 0

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_items = items[batch_start:batch_end]

        log.info(f"处理批次 {batch_start + 1}-{batch_end}/{total}")

        # 构建prompt（从配置文件加载）
        system_prompt, user_prompt = build_filter_prompt(batch_items)

        try:
            # 调用LLM
            response = llm.chat(user_prompt, system_prompt=system_prompt, temperature=0.3)

            # 解析结果
            results = parse_llm_response(response)

            # 填充结果
            for result in results:
                original_idx = result.get('index', 0) - 1  # prompt中index从1开始
                if original_idx < len(batch_items):
                    actual_idx = batch_items[original_idx]['index']
                    df.at[actual_idx, 'LLM_是MTG卡牌'] = result.get('是MTG卡牌')
                    df.at[actual_idx, 'LLM_牌名匹配'] = result.get('牌名匹配')
                    df.at[actual_idx, 'LLM_保留'] = result.get('保留')
                    df.at[actual_idx, 'LLM_原因'] = result.get('原因', '')
                    success_count += 1

        except Exception as e:
            log.error(f"批次处理失败: {e}")
            error_count += len(batch_items)
            # 批次失败，标记为不确定
            for item in batch_items:
                df.at[item['index'], 'LLM_是MTG卡牌'] = None
                df.at[item['index'], 'LLM_牌名匹配'] = None
                df.at[item['index'], 'LLM_保留'] = None
                df.at[item['index'], 'LLM_原因'] = f'处理失败: {e}'

        processed += len(batch_items)
        print_progress(processed, total, prefix='LLM过滤进度', suffix='')

    print()  # 换行

    # 统计结果
    kept_mask = df['LLM_保留'] == True
    removed_mask = df['LLM_保留'] == False
    uncertain_mask = df['LLM_保留'].isna()

    kept_count = kept_mask.sum()
    removed_count = removed_mask.sum()
    uncertain_count = uncertain_mask.sum()

    log.info(f"过滤完成: 保留 {kept_count}, 删除 {removed_count}, 处理失败 {uncertain_count}")

    # 分离保留和删除的数据
    kept_df = df[kept_mask].copy()
    removed_df = df[removed_mask].copy()
    uncertain_df = df[uncertain_mask].copy()

    # 生成输出路径
    if output_file is None:
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_llm_filtered.xlsx"

    ensure_dir(os.path.dirname(output_file))

    # 保存结果
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            kept_df.to_excel(writer, sheet_name='保留', index=False)
            removed_df.to_excel(writer, sheet_name='删除', index=False)
            if len(uncertain_df) > 0:
                uncertain_df.to_excel(writer, sheet_name='处理失败', index=False)

        log.info(f"过滤结果已保存: {output_file}")

        # 同时保存一份只包含保留行的版本
        pure_output = output_file.replace('.xlsx', '_pure.xlsx')
        kept_df.drop(columns=['目标牌名'], errors='ignore').to_excel(pure_output, index=False, engine='openpyxl')
        log.info(f"纯净结果已保存: {pure_output}")

    except Exception as e:
        log.error(f"保存结果失败: {e}")
        return {'success': False, 'error': str(e)}

    return {
        'success': True,
        'total': total,
        'kept': int(kept_count),
        'removed': int(removed_count),
        'uncertain': int(uncertain_count),
        'output_file': output_file,
        'pure_output_file': pure_output
    }
