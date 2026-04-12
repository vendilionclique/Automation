"""
从 *_statistical_eval.xlsx 生成可视化 HTML 报告（与 run_statistical_eval.py 配套）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.stat_eval_report import write_report


def main():
    parser = argparse.ArgumentParser(description="统计评估结果 → HTML 可视化报告")
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="*_statistical_eval.xlsx 路径",
    )
    parser.add_argument("-o", "--output", help="输出 HTML 路径（默认同名 _report.html）")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在 {args.input}")
        sys.exit(1)

    out = write_report(args.input, args.output)
    print(f"已生成: {out}")


if __name__ == "__main__":
    main()
