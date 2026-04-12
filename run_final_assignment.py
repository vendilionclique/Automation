"""
最终赋值模块 v1 CLI。

当前只落实：
1. skip -> 原始输入表目标价格列留空
2. statistical -> 仅消费 statistical_eval 中 eligible_final=true 的牌名级 target_value
3. blocked / open_url -> 暂不回填，只输出待后续处理清单
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.final_assignment import assign_final_values
from modules.utils import setup_logging


def main():
    parser = argparse.ArgumentParser(description="将统计评估结果回填到原始输入表（最终赋值模块 v1）")
    parser.add_argument("-r", "--raw-input", help="原始输入表路径")
    parser.add_argument("-e", "--eval-file", help="统计评估文件路径（*_statistical_eval.xlsx）")
    parser.add_argument("-o", "--output", help="输出 Excel 路径")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logger = setup_logging(level=log_level)

    print(f"\n{'=' * 60}")
    print("最终赋值模块 v1")
    print(f"{'=' * 60}")
    if args.raw_input:
        print(f"原始输入表: {args.raw_input}")
    if args.eval_file:
        print(f"统计评估文件: {args.eval_file}")
    if args.output:
        print(f"输出文件: {args.output}")
    print(f"{'=' * 60}\n")

    result = assign_final_values(
        raw_input_file=args.raw_input,
        statistical_eval_file=args.eval_file,
        output_file=args.output,
        logger=logger,
    )

    print(f"\n{'=' * 60}")
    print("赋值结果摘要")
    print(f"{'=' * 60}")
    if not result.get("success"):
        print(f"处理失败: {result.get('error', '未知错误')}")
        sys.exit(1)

    print(f"原始输入表: {result['raw_input_file']}")
    print(f"统计评估文件: {result['statistical_eval_file']}")
    print(f"skip 留空: {result['skip']}")
    print(f"statistical 已回填: {result['statistical_assigned']}")
    print(f"statistical 升级 open_url 待处理: {result['statistical_blocked_pending']}")
    print(f"open_url 待处理: {result['open_url_pending']}")
    print(f"mode 缺失/未知: {result['mode_missing_or_unknown']}")
    print(f"输出文件: {result['output_file']}")


if __name__ == "__main__":
    main()
