"""
淘宝店透视插件自动化工具 - 模块包
"""

# 这里使用惰性兼容导出，避免在轻量脚本（如数据库连接测试）中
# 因缺少可选依赖而导致整个modules包无法导入。
try:
    from .input_reader import (
        read_excel_input,
        extract_unique_card_names,
        build_search_keywords,
        save_card_name_mapping,
        process_excel
    )
except Exception:  # pylint: disable=broad-except
    pass

try:
    from .checkpoint import CheckpointManager
except Exception:  # pylint: disable=broad-except
    pass

try:
    from .filter import filter_exported_results, merge_filtered_results
except Exception:  # pylint: disable=broad-except
    pass

__version__ = '2.0.0'
