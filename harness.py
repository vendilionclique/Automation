#!/usr/bin/env python3
"""
Diagnostics and visual collection entry point.

The repository now keeps only the browser-use + local Chrome visual workflow
and the downstream DB/LLM/statistical assignment assets.
"""
import argparse
import configparser
import json
import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def cmd_setup(args):
    def test_python_version():
        print("检查 Python 版本...")
        v = sys.version_info
        if v.major >= 3 and v.minor >= 10:
            print(f"[OK] Python: {sys.version}")
            return True
        print(f"[FAIL] Python 版本过低: {sys.version}（需要 3.10+）")
        return False

    def test_imports():
        print("\n检查依赖包...")
        required = [
            ("pandas", "pandas"),
            ("openpyxl", "openpyxl"),
            ("configparser", "configparser"),
            ("Pillow", "PIL"),
            ("pyperclip", "pyperclip"),
            ("browser-use", "browser_use"),
        ]
        missing = []
        for name, mod in required:
            try:
                __import__(mod)
                print(f"[OK] {name}")
            except ImportError:
                print(f"[FAIL] {name} 未安装")
                missing.append(name)
        if missing:
            print("\n请运行: pip install -r requirements.txt")
            return False
        return True

    def test_project_structure():
        print("\n检查项目结构...")
        required_files = [
            "main.py",
            "harness.py",
            "config/settings.example.ini",
            "modules/__init__.py",
            "modules/task_state.py",
            "modules/input_reader.py",
            "modules/filter.py",
            "modules/checkpoint.py",
            "modules/utils.py",
            "modules/browser_use_driver.py",
            "modules/page_state.py",
            "modules/visual_capture.py",
            "modules/vision_extract.py",
            "modules/visual_pipeline.py",
        ]
        for fp in required_files:
            if os.path.exists(fp):
                print(f"[OK] {fp}")
            else:
                print(f"[FAIL] 缺少 {fp}")
                return False

        if not os.path.exists(args.config):
            print(f"[FAIL] {args.config} 不存在，请复制 config/settings.example.ini 并填写本机配置")
            return False
        print(f"[OK] {args.config}")

        cfg = configparser.ConfigParser()
        cfg.read(args.config, encoding="utf-8")
        required_config = {
            "BROWSER_USE": [
                "allowed_domains",
                "chrome_executable_path",
                "chrome_user_data_dir",
                "max_scrolls_per_keyword",
                "min_rows_per_keyword",
            ],
            "SESSION": ["daily_keyword_budget", "hourly_keyword_budget", "max_consecutive_abnormal"],
        }
        for section, keys in required_config.items():
            if not cfg.has_section(section):
                print(f"[FAIL] {args.config} 缺少 [{section}]，请从 config/settings.example.ini 同步新配置")
                return False
            for key in keys:
                if not cfg.has_option(section, key):
                    print(f"[FAIL] {args.config} 缺少 [{section}] {key}")
                    return False

        executable = cfg.get("BROWSER_USE", "chrome_executable_path", fallback="").strip()
        if executable:
            executable = os.path.expanduser(os.path.expandvars(executable))
            if os.path.exists(executable):
                print(f"[OK] browser-use Chrome executable: {executable}")
            else:
                print(f"[WARN] browser-use Chrome executable 不存在: {executable}")

        profile_dir = cfg.get("BROWSER_USE", "chrome_user_data_dir", fallback="").strip()
        if not profile_dir:
            print(f"[WARN] {args.config} 未配置 [BROWSER_USE] chrome_user_data_dir")
            print("       如需复用淘宝登录态，请配置 Chrome user data dir/profile。")
            return True
        profile_dir = os.path.expanduser(profile_dir)
        if not os.path.exists(profile_dir):
            print(f"[WARN] Chrome profile 目录不存在: {profile_dir}")
            print("       请先创建/选择 Chrome profile 并人工登录淘宝。")
        else:
            print(f"[OK] Chrome profile dir: {profile_dir}")
        return True

    print("=" * 60)
    print("环境自检 (harness setup)")
    print("=" * 60)
    tests = [
        ("Python版本", test_python_version),
        ("依赖包", test_imports),
        ("项目结构", test_project_structure),
    ]
    results = []
    for name, fn in tests:
        try:
            results.append((name, fn()))
        except Exception as e:
            print(f"\n[FAIL] {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    for name, ok in results:
        print(f"{name}: {'通过' if ok else '失败'}")
    print("=" * 60)
    sys.exit(0 if all(ok for _, ok in results) else 1)


def cmd_db(_args):
    from modules.mtg_db import MTGDatabase
    from modules.utils import setup_logging

    logger = setup_logging(level=20)
    db = MTGDatabase(logger=logger)
    ok, message = db.test_connection()
    print("=" * 60)
    print("MTG 数据库连接 (harness db)")
    print("=" * 60)
    print(f"SSH隧道: {'开启' if db.use_ssh_tunnel else '关闭'}")
    print(f"结果: {'成功' if ok else '失败'}")
    print(f"详情: {message}")
    if not ok:
        print("\n请检查 config/settings.ini 的 [DB]/[SSH] 或环境变量 MTG_DB_* / MTG_SSH_*")
        sys.exit(1)


def _keyword_with_prefix(config_file, card_name):
    from modules.utils import ConfigManager

    config = ConfigManager(config_file)
    prefix = config.get("INPUT", "keyword_prefix", fallback="万智牌")
    return f"{prefix} {card_name}".strip()


def cmd_visual_one(args):
    from modules.visual_pipeline import prepare_single_keyword_run, run_visual_collection

    keyword = _keyword_with_prefix(args.config, args.card)
    manifest = prepare_single_keyword_run(keyword, config_file=args.config)
    run_id = manifest["run_id"]
    result = run_visual_collection(
        run_id,
        config_file=args.config,
        limit=1,
        manual_state=args.state,
        execute_browser_use=args.agent_execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_run(args):
    from modules.visual_pipeline import run_visual_collection

    result = run_visual_collection(
        args.run_id,
        config_file=args.config,
        limit=args.limit,
        manual_state=args.state,
        execute_browser_use=args.agent_execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_ingest(args):
    from modules.vision_extract import ingest_rows, load_rows
    from modules.visual_pipeline import update_manifest_after_ingest

    rows = load_rows(rows_json=args.rows_json, rows_file=args.rows_file)
    retain = True if args.retain_screenshot else None
    result = ingest_rows(
        task_dir=os.path.abspath(args.task_dir),
        keyword=args.keyword,
        rows=rows,
        screenshot_path=os.path.abspath(args.screenshot) if args.screenshot else "",
        confidence_threshold=args.confidence_threshold,
        retain_screenshot=retain,
    )
    run_id = args.run_id
    if not run_id:
        task_dir = os.path.abspath(args.task_dir)
        run_id = os.path.basename(task_dir.rstrip(os.sep))
    try:
        update_manifest_after_ingest(run_id, args.keyword, result.to_dict())
    except Exception:
        pass
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def cmd_visual_export(args):
    from modules.visual_pipeline import export_raw_rows, task_dir_for_run

    result = export_raw_rows(args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.filter:
        from modules.filter import filter_exported_results
        from modules.utils import ConfigManager, setup_logging

        config = ConfigManager(args.config)
        logger = setup_logging(level=20)
        task_dir = task_dir_for_run(args.run_id)
        filtered_dir = os.path.join(task_dir, "filtered")
        keyword = args.keyword or ""
        card_name = args.card or keyword.replace(config.get("INPUT", "keyword_prefix", fallback="万智牌"), "").strip()
        filter_result = filter_exported_results(
            result["raw_excel"],
            keyword=keyword or args.run_id,
            card_name=card_name,
            output_dir=filtered_dir,
            require_magic_prefix=config.getboolean("FILTER", "require_magic_prefix", fallback=True),
            require_card_name=bool(card_name) and config.getboolean("FILTER", "require_card_name", fallback=True),
            exclude_shop_names=config.get("FILTER", "exclude_shop_names", fallback=""),
            exclude_title_keywords=config.get("FILTER", "exclude_title_keywords", fallback=""),
            logger=logger,
        )
        print(json.dumps(filter_result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Taobao visual collection harness")
    parser.add_argument("-c", "--config", default="config/settings.ini", help="配置文件路径")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Python/依赖/目录自检")
    sub.add_parser("db", help="万智牌数据库（含 SSH 隧道）连通性")

    visual_one = sub.add_parser("visual-one", help="准备单关键词 browser-use MCP 采集任务")
    visual_one.add_argument("card", help="牌名（不含「万智牌」前缀），如 中止")
    visual_one.add_argument("--state", help="手动覆盖页面状态，如 visible_ready / white_skeleton")
    visual_one.add_argument("--agent-execute", action="store_true", help="[fallback] 项目内直接运行 browser-use Agent；需要额外 LLM API key")

    visual_run = sub.add_parser("visual-run", help="为已准备 run_id 生成 browser-use MCP 采集任务")
    visual_run.add_argument("run_id", help="data/tasks/<run_id> 中的 run_id")
    visual_run.add_argument("--limit", type=int, help="最多处理多少个 pending 关键词")
    visual_run.add_argument("--state", help="手动覆盖页面状态，如 visible_ready / white_skeleton")
    visual_run.add_argument("--agent-execute", action="store_true", help="[fallback] 项目内直接运行 browser-use Agent；需要额外 LLM API key")

    ingest = sub.add_parser("visual-ingest", help="Codex 识别后写入结构化视觉结果")
    ingest.add_argument("task_dir", help="任务目录，如 data/tasks/xxx")
    ingest.add_argument("--keyword", required=True, help="截图对应搜索关键词")
    ingest.add_argument("--screenshot", help="截图路径；正常高置信识别后可删除")
    ingest.add_argument("--rows-json", help="JSON 数组，或包含 rows 的 JSON object")
    ingest.add_argument("--rows-file", help="识别结果 JSON 文件")
    ingest.add_argument("--run-id", help="可选：显式指定 run_id；默认取 task_dir 末级目录")
    ingest.add_argument("--confidence-threshold", type=float, default=0.80, help="低于该置信度标记 needs_review")
    ingest.add_argument("--retain-screenshot", action="store_true", default=False, help="即使识别成功也保留原始截图")

    export = sub.add_parser("visual-export", help="将 raw_rows.jsonl 导出为 raw_results.xlsx")
    export.add_argument("run_id", help="data/tasks/<run_id> 中的 run_id")
    export.add_argument("--filter", action="store_true", help="导出后运行现有规则过滤")
    export.add_argument("--keyword", help="过滤时使用的搜索关键词")
    export.add_argument("--card", help="过滤时使用的目标牌名")

    args = parser.parse_args()
    if args.cmd == "setup":
        cmd_setup(args)
    elif args.cmd == "db":
        cmd_db(args)
    elif args.cmd == "visual-one":
        cmd_visual_one(args)
    elif args.cmd == "visual-run":
        cmd_visual_run(args)
    elif args.cmd == "visual-ingest":
        cmd_visual_ingest(args)
    elif args.cmd == "visual-export":
        cmd_visual_export(args)


if __name__ == "__main__":
    main()
