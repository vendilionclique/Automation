"""
SKU 采集独立运行脚本

用法:
    python run_sku_scrape.py -i data/tasks/xxx/合并结果_llm_filtered_pure.xlsx -r data/tasks/xxx/采数输入表_final_assignment_v1.xlsx
    python run_sku_scrape.py -i filtered_pure.xlsx -r final_assignment_v1.xlsx -o sku_output.xlsx
    python run_sku_scrape.py -i filtered_pure.xlsx -r final_assignment_v1.xlsx --resume   # 从断点恢复
"""
import os
import sys
import argparse
import logging
import configparser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.item_sku_scraper import scrape_skus, STATUS_SUCCESS
from modules.browser import BrowserManager
from modules.login import TaobaoLogin
from modules.utils import setup_logging, get_project_root


def find_latest_pure_file():
    """查找 data/tasks 下最新的 pure 过滤结果文件。"""
    tasks_dir = os.path.join(get_project_root(), "data", "tasks")
    if not os.path.exists(tasks_dir):
        return None

    candidates = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if os.path.isdir(item_path):
            for f in os.listdir(item_path):
                if f.endswith("_llm_filtered_pure.xlsx") or f.endswith("_db_filtered_pure.xlsx"):
                    full = os.path.join(item_path, f)
                    candidates.append((os.path.getmtime(full), full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def find_latest_final_assignment_file():
    """查找 data/tasks 下最新 *_final_assignment_v1.xlsx。"""
    tasks_dir = os.path.join(get_project_root(), "data", "tasks")
    if not os.path.exists(tasks_dir):
        return None
    candidates = []
    for item in os.listdir(tasks_dir):
        item_path = os.path.join(tasks_dir, item)
        if not os.path.isdir(item_path):
            continue
        for f in os.listdir(item_path):
            if f.endswith("_final_assignment_v1.xlsx"):
                full = os.path.join(item_path, f)
                candidates.append((os.path.getmtime(full), full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def main():
    parser = argparse.ArgumentParser(
        description="逐条打开淘宝商品页，通过店透视插件采集 SKU 数据"
    )
    parser.add_argument("-i", "--input", help="输入 Excel（需含「商品链接」列）")
    parser.add_argument(
        "-r",
        "--routing-input",
        help="open_url 路由输入（推荐 *_final_assignment_v1.xlsx，需含 effective_mode/productId）",
    )
    parser.add_argument("-o", "--output", help="输出文件路径（默认 _sku_detail.xlsx）")
    parser.add_argument("--resume", action="store_true", help="从上次断点恢复")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    args = parser.parse_args()

    input_file = args.input
    if not input_file:
        input_file = find_latest_pure_file()
        if not input_file:
            print("错误: 未找到 *_filtered_pure.xlsx（支持 _db_filtered_pure.xlsx / _llm_filtered_pure.xlsx），请使用 -i 参数指定")
            sys.exit(1)
        print(f"使用最新 pure 文件: {input_file}")

    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在: {input_file}")
        sys.exit(1)

    routing_input = args.routing_input
    if not routing_input:
        routing_input = find_latest_final_assignment_file()
        if routing_input:
            print(f"使用最新 open_url 路由文件: {routing_input}")
    if not routing_input or not os.path.exists(routing_input):
        print("错误: 未找到 open_url 路由文件（需要包含 effective_mode/assignment_status/productId）。")
        print("请使用 -r 指定 *_final_assignment_v1.xlsx")
        sys.exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger = setup_logging(level=log_level)

    print(f"\n{'='*60}")
    print("SKU 采集")
    print(f"{'='*60}")
    print(f"输入文件: {input_file}")
    print(f"open_url 路由: {routing_input}")
    if args.output:
        print(f"输出文件: {args.output}")
    print(f"断点恢复: {'是' if args.resume else '否'}")
    print(f"{'='*60}")
    print("即将启动浏览器，请确保:")
    print("  1. chrome_profile/ 已安装店透视插件")
    print("  2. 淘宝已登录")
    print(f"{'='*60}\n")

    cfg_path = os.path.join(get_project_root(), "config", "settings.ini")
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")
    dl = cfg.get("BROWSER", "download_dir", fallback="data/downloads")
    ud = cfg.get("BROWSER", "user_data_dir", fallback="").strip() or None
    max_browser_restarts = cfg.getint("SKU_SCRAPE", "max_browser_restarts", fallback=2)
    if ud:
        print(f"使用自定义 Chrome 用户数据目录:\n  {ud}\n")

    restart_count = 0
    result = None
    while True:
        with BrowserManager(download_dir=dl, user_data_dir=ud) as bm:
            page = bm.page

            login_mgr = TaobaoLogin(bm)
            if not login_mgr.auto_login():
                print("登录失败，退出")
                sys.exit(1)

            result = scrape_skus(
                input_file=input_file,
                output_file=args.output,
                page=page,
                config_file=os.path.join(get_project_root(), "config", "settings.ini"),
                logger=logger,
                resume=args.resume,
                open_url_input_file=routing_input,
            )

        if result.get("success"):
            break
        if result.get("recoverable") and result.get("error") == "browser_disconnected":
            restart_count += 1
            if restart_count <= max_browser_restarts:
                print(f"\n检测到浏览器连接中断，准备自动重启浏览器并续跑 ({restart_count}/{max_browser_restarts})...\n")
                continue
        break

    print(f"\n{'='*60}")
    print("采集结果摘要")
    print(f"{'='*60}")
    if result.get("success"):
        print(f"总链接数: {result['total_urls']}")
        print(f"已处理:   {result['processed']}")
        print(f"成功:     {result['success_count']}")
        print(f"失败:     {result['fail_count']}")
        print(f"SKU 行:   {result['sku_rows']}")
        print(f"输出文件: {result['output_file']}")
        print(f"  → listing_meta sheet: 每个 URL 一行，含状态与诊断")
        print(f"  → sku_rows sheet:     每个 SKU 一行，核心分析表")
    else:
        print(f"处理失败: {result.get('error', '未知错误')}")
        sys.exit(1)

    print()
    if result.get("fail_count", 0) > 0:
        print("提示: 存在采集失败的商品，可查看 listing_meta 中 status 列进行排查。")
        print("  - need_login:     需重新登录淘宝")
        print("  - captcha:        遇到验证码，需手动处理")
        print("  - plugin_missing: 未找到店透视复制按钮，确认插件已安装")
        print("  - clipboard_empty: 插件未返回数据")
        print("  - parse_error:    剪贴板数据无法解析")
        print("  - nav_error:      页面加载失败")
        print("使用 --resume 可跳过已处理的链接，仅重采失败项。")


if __name__ == "__main__":
    main()
