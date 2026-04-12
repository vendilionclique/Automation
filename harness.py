#!/usr/bin/env python3
"""
统一自检与插件调试入口（替代 test_setup / test_db_connection / test_single_keyword）。

用法:
  python harness.py setup
  python harness.py db
  python harness.py plugin <牌名>
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def cmd_setup():
    def test_python_version():
        print("检查Python版本...")
        v = sys.version_info
        if v.major >= 3 and v.minor >= 10:
            print(f"[OK] Python: {sys.version}")
            return True
        print(f"[FAIL] Python 版本过低: {sys.version}（需要 3.10+）")
        return False

    def test_imports():
        print("\n检查依赖包...")
        required = [
            ("DrissionPage", "DrissionPage"),
            ("pandas", "pandas"),
            ("openpyxl", "openpyxl"),
            ("configparser", "configparser"),
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
            print(f"\n请运行: pip install -r requirements.txt")
            return False
        return True

    def test_project_structure():
        print("\n检查项目结构...")
        required_files = [
            "main.py",
            "config/settings.example.ini",
            "config/keywords.example.txt",
            "modules/__init__.py",
            "modules/browser.py",
            "modules/login.py",
            "modules/search.py",
            "modules/export.py",
            "modules/utils.py",
        ]
        for fp in required_files:
            if os.path.exists(fp):
                print(f"[OK] {fp}")
            else:
                print(f"[FAIL] 缺少 {fp}")
                return False
        for local_path, example_path in [
            ("config/settings.ini", "config/settings.example.ini"),
            ("config/keywords.txt", "config/keywords.example.txt"),
        ]:
            if not os.path.exists(local_path):
                print(f"[FAIL] {local_path} 不存在，请复制 {example_path} 并填写")
                return False
            print(f"[OK] {local_path}")
        return True

    def test_browser():
        print("\n检查浏览器环境...")
        try:
            from DrissionPage import ChromiumOptions

            ChromiumOptions()
            print("[OK] DrissionPage 配置正常")
            from DrissionPage import WebPage

            _ = WebPage
            print("[OK] 浏览器驱动可用")
            return True
        except ImportError as e:
            print(f"[FAIL] DrissionPage: {e}")
            return False
        except Exception as e:
            print(f"[FAIL] 浏览器检查: {e}")
            return False

    print("=" * 60)
    print("环境自检 (harness setup)")
    print("=" * 60)
    tests = [
        ("Python版本", test_python_version),
        ("依赖包", test_imports),
        ("项目结构", test_project_structure),
        ("浏览器环境", test_browser),
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
    all_ok = all(r for _, r in results)
    print("=" * 60)
    sys.exit(0 if all_ok else 1)


def cmd_db():
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


def cmd_plugin(card_name: str):
    from modules.harness_plugin import run_plugin_debug

    run_plugin_debug(card_name)


def main():
    p = argparse.ArgumentParser(description="Taobao automation harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Python/依赖/目录/浏览器自检")
    sub.add_parser("db", help="万智牌数据库（含 SSH 隧道）连通性")

    pp = sub.add_parser("plugin", help="店透视插件单关键词 DOM 调试")
    pp.add_argument("card", help="牌名（不含「万智牌」前缀），如 中止")

    args = p.parse_args()
    if args.cmd == "setup":
        cmd_setup()
    elif args.cmd == "db":
        cmd_db()
    elif args.cmd == "plugin":
        cmd_plugin(args.card)


if __name__ == "__main__":
    main()
