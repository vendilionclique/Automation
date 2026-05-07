#!/usr/bin/env python3
"""
Unified diagnostics entry point.

The main workflow is moving to login-state visual collection. Legacy AdsPower,
proxy-pool, and shop-insight plugin diagnostics remain available only for
historical troubleshooting.
"""
import argparse
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
        import configparser

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
            "modules/visual_driver.py",
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
            "BROWSER_USE": ["allowed_domains", "max_scrolls_per_keyword", "min_rows_per_keyword"],
            "VISUAL_CAPTURE": ["chrome_path", "chrome_user_data_dir", "window_width", "window_height"],
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
        try:
            import browser_use  # noqa: F401
            print("[OK] browser-use Python package")
        except ImportError:
            print("[FAIL] browser-use 未安装；请运行: pip install -r requirements.txt")
            return False

        executable = cfg.get("BROWSER_USE", "chrome_executable_path", fallback="").strip()
        if executable:
            executable = os.path.expanduser(os.path.expandvars(executable))
            if os.path.exists(executable):
                print(f"[OK] browser-use Chrome executable: {executable}")
            else:
                print(f"[WARN] browser-use Chrome executable 不存在: {executable}")
                print("       请安装 Google Chrome，或把 [BROWSER_USE] chrome_executable_path 改为本机 Chrome/Chromium 路径。")

        profile_dir = cfg.get("BROWSER_USE", "chrome_user_data_dir", fallback="").strip()
        if not profile_dir:
            profile_dir = cfg.get("VISUAL_CAPTURE", "chrome_user_data_dir", fallback="").strip()
        if not profile_dir:
            print(f"[WARN] {args.config} 未配置 [BROWSER_USE] chrome_user_data_dir")
            print("       browser-use 会启动本机 Chrome；如需复用淘宝登录态，请配置 Chrome user data dir/profile。")
            return True
        profile_dir = os.path.expanduser(profile_dir)
        if not os.path.exists(profile_dir):
            print(f"[WARN] Chrome profile 目录不存在: {profile_dir}")
            print("       可先用 browser-use/Chrome 创建专用 profile 并人工登录淘宝。")
            return True
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


def cmd_db(args):
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


def cmd_ip_pool(args):
    print("[LEGACY] 代理池匿名采集路线已废弃；此命令仅用于历史诊断。")
    from modules.proxy_pool import ProxyPoolClient
    from modules.task_state import EvidenceRecorder
    from modules.utils import ConfigManager

    config = ConfigManager(args.config)
    client = ProxyPoolClient(
        provider_url=config.get("IP_POOL", "provider_url", fallback=""),
        healthcheck_url=config.get("IP_POOL", "healthcheck_url", fallback="https://api.ipify.org?format=json"),
        timeout=config.getfloat("IP_POOL", "timeout", fallback=10.0),
    )
    recorder = EvidenceRecorder()
    evidence_dir = recorder.create_dir("harness_ip_pool")

    print("=" * 60)
    print("代理池自检 (harness ip-pool)")
    print("=" * 60)

    proxy = args.proxy
    fetched = []
    fetch_payload = {"proxies": [], "raw_response": "", "error": None}
    if not proxy:
        fetch_payload = client.fetch_with_raw()
        if fetch_payload["error"]:
            payload = {"ok": False, "stage": "fetch", "error": fetch_payload["error"]}
            recorder.write_json(evidence_dir, "ip_pool_result", payload)
            print(f"[FAIL] 拉取代理失败: {fetch_payload['error']}")
            print(f"证据目录: {evidence_dir}")
            sys.exit(1)
        fetched = fetch_payload["proxies"]
        print(f"供应商返回代理数: {len(fetched)}")

    candidates = [proxy] if proxy else fetched[: args.limit]
    if not candidates and args.require_proxy:
        payload = {
            "ok": False,
            "stage": "select_proxy",
            "error": "供应商没有返回可测试代理，且启用了 --require-proxy",
            "fetch": fetch_payload,
        }
        recorder.write_json(evidence_dir, "ip_pool_result", payload)
        print("[FAIL] 未获取到可测试代理")
        print(f"证据目录: {evidence_dir}")
        sys.exit(1)

    if not candidates:
        candidates = [None]

    results = []
    for candidate in candidates:
        result = client.probe(candidate)
        results.append(result)
        status = "[OK]" if result.ok else "[FAIL]"
        print(f"{status} proxy={candidate or '(direct)'} exit_ip={result.exit_ip or '-'}")
        if result.error:
            print(f"  {result.error}")

    payload = {
        "results": [result.to_dict() for result in results],
        "fetched_count": len(fetched),
        "tested_count": len(results),
        "fetch": {
            "raw_response": fetch_payload["raw_response"],
            "error": fetch_payload["error"],
        },
        "evidence_dir": evidence_dir,
    }
    recorder.write_json(evidence_dir, "ip_pool_result", payload)

    ok_count = sum(1 for result in results if result.ok)
    if ok_count:
        print(f"[OK] 成功 {ok_count}/{len(results)}")
        print(f"证据目录: {evidence_dir}")
        return

    print(f"[FAIL] 全部代理连通性失败: {len(results)}")
    print(f"证据目录: {evidence_dir}")
    sys.exit(1)


def cmd_adspower(args):
    print("[LEGACY] AdsPower 非登录采集路线已废弃；此命令仅用于历史诊断。")
    from modules.adspower import AdsPowerClient
    from modules.proxy_pool import ProxyPoolClient
    from modules.task_state import EvidenceRecorder
    from modules.utils import ConfigManager

    config = ConfigManager(args.config)
    client = AdsPowerClient(
        base_url=config.get("ADSPOWER", "base_url", fallback="http://local.adspower.net:50325"),
        api_key=config.get("ADSPOWER", "api_key", fallback=""),
        timeout=config.getfloat("ADSPOWER", "timeout", fallback=10.0),
    )
    profile_id = args.profile_id or config.get("ADSPOWER", "profile_id", fallback="")
    recorder = EvidenceRecorder()
    evidence_dir = recorder.create_dir("harness_adspower")

    print("=" * 60)
    print("AdsPower 自检 (harness adspower)")
    print("=" * 60)

    results = [client.health()]
    if args.set_proxy or args.set_proxy_from_pool:
        if not profile_id:
            print("[FAIL] 更新代理需要提供 --profile-id 或配置 [ADSPOWER] profile_id")
            sys.exit(1)
        proxy = args.set_proxy
        if args.set_proxy_from_pool:
            pool = ProxyPoolClient(
                provider_url=config.get("IP_POOL", "provider_url", fallback=""),
                healthcheck_url=config.get("IP_POOL", "healthcheck_url", fallback="http://httpbin.org/ip"),
                timeout=config.getfloat("IP_POOL", "timeout", fallback=10.0),
            )
            fetched = pool.fetch_with_raw()
            if fetched["error"] or not fetched["proxies"]:
                print(f"[FAIL] 无法从代理池获取代理: {fetched['error'] or 'empty response'}")
                sys.exit(1)
            proxy = fetched["proxies"][0]
        proxy_parts = parse_proxy(proxy)
        results.append(client.update_profile_proxy(profile_id, **proxy_parts))
    start_result = None
    if args.start or args.probe_url:
        if not profile_id:
            print("[FAIL] --start 需要提供 --profile-id 或配置 [ADSPOWER] profile_id")
            sys.exit(1)
        start_result = client.start(profile_id)
        results.append(start_result)
    if args.probe_url and start_result and start_result.ok:
        probe_result = probe_playwright(start_result, args.probe_url, evidence_dir)
        results.append(probe_result)
    if args.stop:
        if not profile_id:
            print("[FAIL] --stop 需要提供 --profile-id 或配置 [ADSPOWER] profile_id")
            sys.exit(1)
        results.append(client.stop(profile_id))

    recorder.write_json(evidence_dir, "adspower_result", {"results": [r.to_dict() for r in results]})

    all_ok = all(r.ok for r in results)
    for result in results:
        print(f"{result.action}: {'[OK]' if result.ok else '[FAIL]'}")
        if result.error:
            print(f"  {result.error}")
        if result.action == "start" and result.data:
            data = result.data.get("data") or {}
            print(f"  ws: {data.get('ws')}")
            print(f"  webdriver: {data.get('webdriver')}")
        if result.action == "playwright_probe" and result.data:
            print(f"  title: {result.data.get('title')}")
            print(f"  url: {result.data.get('url')}")
            print(f"  screenshot: {result.data.get('screenshot')}")
    print(f"证据目录: {evidence_dir}")
    sys.exit(0 if all_ok else 1)


def probe_playwright(start_result, url, evidence_dir):
    from modules.adspower import AdsPowerResult

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return AdsPowerResult(ok=False, action="playwright_probe", error=f"playwright 未安装: {e}")

    data = start_result.data.get("data") if start_result.data else {}
    ws = (data.get("ws") or {}).get("puppeteer")
    if not ws:
        return AdsPowerResult(ok=False, action="playwright_probe", error="AdsPower start 响应缺少 ws.puppeteer")

    screenshot = os.path.join(evidence_dir, "playwright_probe.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            final_url = page.url
            page.screenshot(path=screenshot, full_page=True)
            browser.close()
        return AdsPowerResult(
            ok=True,
            action="playwright_probe",
            data={"title": title, "url": final_url, "screenshot": screenshot},
        )
    except Exception as e:
        return AdsPowerResult(ok=False, action="playwright_probe", error=str(e))


def parse_proxy(proxy: str):
    if not proxy:
        raise ValueError("proxy is empty")
    proxy_type = "http"
    value = proxy.strip()
    if "://" in value:
        proxy_type, value = value.split("://", 1)
    proxy_user = ""
    proxy_password = ""
    if "@" in value:
        auth, value = value.rsplit("@", 1)
        if ":" in auth:
            proxy_user, proxy_password = auth.split(":", 1)
        else:
            proxy_user = auth
    host, port = value.rsplit(":", 1)
    return {
        "proxy_host": host,
        "proxy_port": port,
        "proxy_type": proxy_type,
        "proxy_user": proxy_user,
        "proxy_password": proxy_password,
    }


def cmd_plugin(args):
    print("[LEGACY] 店透视插件/DOM 采集路线已废弃；此命令仅用于历史诊断。")
    from modules.harness_plugin import run_plugin_debug

    run_plugin_debug(args.card)


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
        launch=not args.no_launch,
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
        launch=not args.no_launch,
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
    parser = argparse.ArgumentParser(description="Taobao automation harness")
    parser.add_argument("-c", "--config", default="config/settings.ini", help="配置文件路径")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Python/依赖/目录自检")
    sub.add_parser("db", help="万智牌数据库（含 SSH 隧道）连通性")

    ip = sub.add_parser("ip-pool", help="[legacy] 代理供应商接口和出口 IP 连通性自检")
    ip.add_argument("--proxy", help="跳过供应商接口，直接验证指定代理（host:port 或 URL）")
    ip.add_argument("--limit", type=int, default=1, help="最多测试多少个供应商返回的代理")
    ip.add_argument("--require-proxy", action="store_true", help="供应商未返回代理时视为失败，不走直连检查")

    adsp = sub.add_parser("adspower", help="[legacy] AdsPower Local API 自检")
    adsp.add_argument("--profile-id", help="AdsPower profile user_id，覆盖配置文件")
    adsp.add_argument("--start", action="store_true", help="启动指定 profile")
    adsp.add_argument("--stop", action="store_true", help="停止指定 profile")
    adsp.add_argument("--set-proxy", help="把指定代理写入 profile（host:port 或 URL）")
    adsp.add_argument("--set-proxy-from-pool", action="store_true", help="从 [IP_POOL] 提取 1 个代理并写入 profile")
    adsp.add_argument("--probe-url", help="启动 profile 后用 Playwright CDP 打开 URL 并截图")

    plugin = sub.add_parser("plugin", help="[legacy] 店透视插件单关键词 DOM 调试")
    plugin.add_argument("card", help="牌名（不含「万智牌」前缀），如 中止")

    visual_one = sub.add_parser("visual-one", help="准备单关键词 browser-use MCP 采集任务")
    visual_one.add_argument("card", help="牌名（不含「万智牌」前缀），如 中止")
    visual_one.add_argument("--state", help="手动覆盖页面状态，如 visible_ready / white_skeleton")
    visual_one.add_argument("--no-launch", action="store_true", help="不启动 Chrome，只操作当前前台窗口")
    visual_one.add_argument("--agent-execute", action="store_true", help="[fallback] 项目内直接运行 browser-use Agent；需要额外 LLM API key")

    visual_run = sub.add_parser("visual-run", help="为已准备 run_id 生成 browser-use MCP 采集任务")
    visual_run.add_argument("run_id", help="data/tasks/<run_id> 中的 run_id")
    visual_run.add_argument("--limit", type=int, help="最多处理多少个 pending 关键词")
    visual_run.add_argument("--state", help="手动覆盖页面状态，如 visible_ready / white_skeleton")
    visual_run.add_argument("--no-launch", action="store_true", help="不启动 Chrome，只操作当前前台窗口")
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
    elif args.cmd == "ip-pool":
        cmd_ip_pool(args)
    elif args.cmd == "adspower":
        cmd_adspower(args)
    elif args.cmd == "plugin":
        cmd_plugin(args)
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
