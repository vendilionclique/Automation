"""
淘宝店透视插件自动化工具 - 模块包
"""

from .input_reader import (
    read_excel_input,
    extract_unique_card_names,
    build_search_keywords,
    save_card_name_mapping,
    process_excel
)

from .checkpoint import CheckpointManager

from .filter import filter_exported_results, merge_filtered_results

__version__ = '2.0.0'
