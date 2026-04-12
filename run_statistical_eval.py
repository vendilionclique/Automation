"""
牌名级货盘诊断 CLI。
默认读取 pure 文件，输出“价格货盘划分 + 最低稳定簇”诊断结果。
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.price_cluster_eval import evaluate_price_clusters
from modules.utils import setup_logging, get_project_root


def find_latest_pure_file():
    tasks_dir = os.path.join(get_project_root(), "data", "tasks")
    if not os.path.exists(tasks_dir):
        return None

    candidates = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if not os.path.isdir(item_path):
            continue
        for name in os.listdir(item_path):
            if name.endswith("_db_filtered_pure.xlsx") or name.endswith("_llm_filtered_pure.xlsx"):
                full = os.path.join(item_path, name)
                candidates.append((os.path.getmtime(full), full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def main():
    parser = argparse.ArgumentParser(description="对 pure 文件做牌名级货盘诊断")
    parser.add_argument("-i", "--input", help="输入 pure Excel")
    parser.add_argument("-o", "--output", help="输出统计评估 Excel")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    args = parser.parse_args()

    input_file = args.input or find_latest_pure_file()
    if not input_file:
        print("错误: 未找到 *_filtered_pure.xlsx，请使用 -i 参数指定")
        sys.exit(1)

    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 {input_file}")
        sys.exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger = setup_logging(level=log_level)

    print(f"\n{'='*60}")
    print("牌名级货盘诊断")
    print(f"{'='*60}")
    print(f"输入文件: {input_file}")
    if args.output:
        print(f"输出文件: {args.output}")
    print(f"{'='*60}\n")

    result = evaluate_price_clusters(
        input_file=input_file,
        output_file=args.output,
        logger=logger,
    )

    print(f"\n{'='*60}")
    print("货盘诊断结果")
    print(f"{'='*60}")
    if result.get("success"):
        print(f"总牌名数: {result['total_cards']}")
        print(f"statistical_candidate 牌名数: {result['eligible_cards']}")
        print(f"open_url_fallback 牌名数: {result.get('fallback_cards', 0)}")
        print(f"输出文件: {result['output_file']}")
    else:
        print(f"处理失败: {result.get('error', '未知错误')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
