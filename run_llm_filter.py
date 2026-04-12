"""
LLM 过滤独立运行脚本。
"""
import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.llm_filter import filter_with_llm, filter_with_db_only
from modules.utils import setup_logging, get_project_root


def find_latest_merged_file():
    """查找 data/tasks 下最新的 合并结果.xlsx。"""
    tasks_dir = os.path.join(get_project_root(), 'data', 'tasks')
    if not os.path.exists(tasks_dir):
        return None

    merged_files = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if os.path.isdir(item_path):
            merged_path = os.path.join(item_path, '合并结果.xlsx')
            if os.path.exists(merged_path):
                merged_files.append((os.path.getmtime(merged_path), merged_path))

    if not merged_files:
        return None

    merged_files.sort(reverse=True)
    return merged_files[0][1]


def main():
    parser = argparse.ArgumentParser(description='对淘宝万智牌搜索结果进行 DB/LLM 过滤')
    parser.add_argument('-i', '--input', help='输入的合并结果 Excel 文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径，默认自动追加 _llm_filtered 后缀')
    parser.add_argument('-b', '--batch-size', type=int, default=5, help='每批处理的商品数量，默认 5')
    parser.add_argument(
        '--mode',
        default='db',
        choices=['db', 'llm'],
        help='过滤模式：db=仅用DB/硬规则快速产出，llm=再走LLM精筛',
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别，默认 INFO',
    )

    args = parser.parse_args()

    input_file = args.input
    if not input_file:
        input_file = find_latest_merged_file()
        if not input_file:
            print('错误: 未找到合并结果文件，请使用 -i 参数指定')
            print('    或确认 data/tasks/<timestamp>/合并结果.xlsx 存在')
            sys.exit(1)
        print(f'使用最新合并结果: {input_file}')

    if not os.path.exists(input_file):
        print(f'错误: 输入文件不存在: {input_file}')
        sys.exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger = setup_logging(level=log_level)

    print(f"\n{'=' * 60}")
    print('结果过滤')
    print(f"{'=' * 60}")
    print(f'输入文件: {input_file}')
    if args.output:
        print(f'输出文件: {args.output}')
    print(f'过滤模式: {args.mode}')
    if args.mode == 'llm':
        print(f'批次大小: {args.batch_size}')
    print(f"{'=' * 60}\n")

    if args.mode == 'db':
        result = filter_with_db_only(
            input_file=input_file,
            output_file=args.output,
            logger=logger,
        )
    else:
        result = filter_with_llm(
            input_file=input_file,
            output_file=args.output,
            batch_size=args.batch_size,
            logger=logger,
        )

    print(f"\n{'=' * 60}")
    print('过滤结果摘要')
    print(f"{'=' * 60}")
    if result['success']:
        print(f"总记录数: {result['total']}")
        print(f"保留: {result['kept']}")
        print(f"删除: {result['removed']}")
        print(f"处理失败: {result['uncertain']}")
        print(f"输出文件: {result['output_file']}")
        print('  -> 打开后看「全部」= 原表每一行+LLM 列；「已删除」= 仅筛掉行')
        print(f"纯净结果: {result['pure_output_file']}")
        print('  -> 仅含判定为保留的行，给后续步骤用')
    else:
        print(f"处理失败: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
