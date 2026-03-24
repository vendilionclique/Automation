"""
LLM过滤独立运行脚本

用法:
    python run_llm_filter.py                                     # 使用data/tasks下最新的合并结果
    python run_llm_filter.py -i data/tasks/xxx/合并结果.xlsx     # 指定输入文件
    python run_llm_filter.py -i 合并结果.xlsx -o 结果.xlsx       # 指定输出文件
"""
import os
import sys
import argparse
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.llm_filter import filter_with_llm
from modules.utils import setup_logging, get_project_root


def find_latest_merged_file():
    """查找data/tasks下最新的合并结果文件"""
    tasks_dir = os.path.join(get_project_root(), 'data', 'tasks')

    if not os.path.exists(tasks_dir):
        return None

    # 查找所有合并结果文件
    merged_files = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if os.path.isdir(item_path):
            merged_path = os.path.join(item_path, '合并结果.xlsx')
            if os.path.exists(merged_path):
                merged_files.append((os.path.getmtime(merged_path), merged_path))

    if not merged_files:
        return None

    # 返回最新的
    merged_files.sort(reverse=True)
    return merged_files[0][1]


def main():
    parser = argparse.ArgumentParser(description='使用LLM对淘宝万智牌搜索结果进行智能过滤')
    parser.add_argument('-i', '--input', help='输入的合并结果Excel文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认添加_llm_filtered后缀）')
    parser.add_argument('-b', '--batch-size', type=int, default=5, help='每批处理的商品数量（默认5）')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='日志级别（默认INFO）')

    args = parser.parse_args()

    # 确定输入文件
    input_file = args.input
    if not input_file:
        input_file = find_latest_merged_file()
        if not input_file:
            print("错误: 未找到合并结果文件，请使用 -i 参数指定")
            print("    或确保 data/tasks/<timestamp>/合并结果.xlsx 存在")
            sys.exit(1)
        print(f"使用最新合并结果: {input_file}")

    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在: {input_file}")
        sys.exit(1)

    # 设置日志
    log_level = getattr(logging, args.log_level.upper())
    logger = setup_logging(level=log_level)

    # 执行过滤
    print(f"\n{'='*60}")
    print(f"LLM智能过滤")
    print(f"{'='*60}")
    print(f"输入文件: {input_file}")
    if args.output:
        print(f"输出文件: {args.output}")
    print(f"批次大小: {args.batch_size}")
    print(f"{'='*60}\n")

    result = filter_with_llm(
        input_file=input_file,
        output_file=args.output,
        batch_size=args.batch_size,
        logger=logger
    )

    # 输出结果摘要
    print(f"\n{'='*60}")
    print(f"过滤结果摘要")
    print(f"{'='*60}")
    if result['success']:
        print(f"总记录数: {result['total']}")
        print(f"保留: {result['kept']}")
        print(f"删除: {result['removed']}")
        print(f"处理失败: {result['uncertain']}")
        print(f"输出文件: {result['output_file']}")
        print(f"纯净结果: {result['pure_output_file']}")
    else:
        print(f"处理失败: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
