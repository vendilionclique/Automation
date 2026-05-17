#!/usr/bin/env python3
"""
Diagnostics and visual collection entry point.

The repository keeps a pure-vision local Chrome collection workflow and the
downstream DB/LLM/statistical assignment assets.
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
            ("requests", "requests"),
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
            "modules/page_sampling.py",
            "modules/midscene_computer_driver.py",
            "modules/page_state.py",
            "modules/visual_capture.py",
            "modules/visual_capture_worker.py",
            "modules/visual_control.py",
            "modules/codex_extract.py",
            "modules/vision_extract.py",
            "modules/visual_pipeline.py",
            "modules/visual_scheduler.py",
            "modules/session_capsule.py",
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
            "VISUAL_CAPTURE": ["provider", "confidence_threshold", "screenshot_retention"],
            "MIDSCENE_COMPUTER": [
                "max_scrolls_per_keyword",
                "min_rows_per_keyword",
                "page_load_wait",
                "session_keyword_limit",
                "keyword_timeout_seconds",
                "consecutive_abnormal_stop",
                "foreground_recovery_enabled",
                "foreground_recovery_attempts_per_event",
                "foreground_recovery_events_per_keyword",
                "allow_bookmark_home_entry_repair",
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

        optional_config = {
            "SCHEDULER": [
                "daily_keyword_budget",
                "daily_session_count",
                "capture_freshness_days",
                "session_due_times",
                "session_due_interval_minutes",
                "capture_worker_stale_after_minutes",
            ],
            "CAPTURE_WATCHDOG": [
                "poll_seconds",
                "idle_timeout_seconds",
                "max_restarts",
            ],
            "VISUAL_BEHAVIOR": ["micro_pause_short", "inter_keyword_pause_min", "inter_keyword_pause_max"],
            "PAGE_SAMPLING": ["target_listings_per_keyword", "max_tiles_per_keyword", "retain_screenshots"],
            "CODEX_EXTRACT": ["codex_bin", "profile", "model", "approval_policy"],
        }
        for section, keys in optional_config.items():
            if not cfg.has_section(section):
                print(f"[WARN] {args.config} 缺少 [{section}]，将使用代码默认值；建议从 settings.example.ini 同步")
                continue
            for key in keys:
                if not cfg.has_option(section, key):
                    print(f"[WARN] {args.config} 缺少 [{section}] {key}，将使用代码默认值")

        provider = cfg.get("VISUAL_CAPTURE", "provider", fallback="midscene_computer").strip()
        print(f"[OK] visual provider: {provider or 'midscene_computer'}")
        if (provider or "midscene_computer").replace("-", "_") == "midscene_computer":
            env_example = os.path.join(ROOT, "local", "midscene-computer.env.example")
            env_file = os.path.join(ROOT, "local", "midscene-computer.env")
            mcp_script = os.path.join(ROOT, "local", "start_midscene_computer_mcp.sh")
            print(f"[OK] Midscene MCP launcher: {mcp_script}" if os.path.exists(mcp_script) else f"[FAIL] 缺少 {mcp_script}")
            if not os.path.exists(mcp_script):
                return False
            print(f"[OK] Midscene env example: {env_example}" if os.path.exists(env_example) else f"[WARN] 缺少 {env_example}")
            if os.path.exists(env_file):
                print(f"[OK] Midscene local env: {env_file}")
            else:
                print(f"[WARN] Midscene local env 未创建: {env_file}")
                print("       拿到外部 VLM key 后，复制 local/midscene-computer.env.example 并填写本机 env。")
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


def cmd_visual_plan_day(args):
    from modules.visual_scheduler import plan_daily_collection

    result = plan_daily_collection(
        raw_input_file=args.raw_input,
        config_file=args.config,
        plan_id=args.plan_id,
        random_sample=args.random_sample,
        random_seed=args.random_seed,
        session_count=args.session_count,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_session_run(args):
    from modules.visual_pipeline import run_visual_collection

    result = run_visual_collection(
        args.plan_id,
        config_file=args.config,
        limit=args.limit,
        manual_state=args.state,
        session_index=args.session,
        force_lease=args.force_lease,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_sync_worker(args):
    from modules.visual_pipeline import sync_midscene_worker_results

    result = sync_midscene_worker_results(args.plan_id, args.session)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_session_capsule(args):
    from modules.session_capsule import build_session_capsule

    result = build_session_capsule(
        args.plan_id,
        args.session,
        config_file=args.config,
        limit=args.limit,
        manual_state=args.state,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_session_lease(args):
    from modules.session_capsule import (
        acquire_session_lease,
        complete_session_lease,
        heartbeat_session_lease,
        inspect_session_lease,
    )

    if args.action == "inspect":
        result = inspect_session_lease(args.plan_id, args.session)
    elif args.action == "acquire":
        result = acquire_session_lease(
            args.plan_id,
            args.session,
            owner=args.owner,
            ttl_minutes=args.ttl_minutes,
            force=args.force,
        )
    elif args.action == "heartbeat":
        result = heartbeat_session_lease(
            args.plan_id,
            args.session,
            ttl_minutes=args.ttl_minutes,
        )
    else:
        result = complete_session_lease(
            args.plan_id,
            args.session,
            status=args.status,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_scheduler_status(args):
    from modules.visual_scheduler import scheduler_status

    result = scheduler_status(args.plan_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_heartbeat(args):
    from modules.visual_scheduler import heartbeat_daily_collection

    result = heartbeat_daily_collection(
        raw_input_file=args.raw_input,
        config_file=args.config,
        plan_id=args.plan_id,
        session_index=args.session,
        limit=args.limit,
        mode=args.mode,
        random_sample=args.random_sample,
        random_seed=args.random_seed,
        session_count=args.session_count,
        force_lease=args.force_lease,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_capture_watchdog(args):
    try:
        from modules.visual_capture_watchdog import run_capture_watchdog
    except ImportError as exc:
        result = {
            "ok": False,
            "action": "capture_watchdog",
            "error": "visual_capture_watchdog_module_missing",
            "message": "modules.visual_capture_watchdog.run_capture_watchdog is not available yet",
            "import_error": str(exc),
        }
    else:
        result = run_capture_watchdog(
            args.plan_id,
            args.session,
            raw_input_file=args.raw_input,
            config_file=args.config,
            start=args.start,
            poll_seconds=args.poll_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            max_restarts=args.max_restarts,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_control(args):
    from modules.visual_control import apply_control_action, load_control_state, session_runtime_summary
    from modules.visual_scheduler import scheduler_status

    if args.action == "status":
        payload = {
            "ok": True,
            "plan_id": args.plan_id,
            "control": load_control_state(args.plan_id),
        }
        try:
            payload["status"] = scheduler_status(args.plan_id)
        except Exception as exc:
            payload["status_error"] = str(exc)
        if args.session is not None:
            payload["runtime"] = session_runtime_summary(args.plan_id, args.session)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    result = apply_control_action(
        args.plan_id,
        args.action,
        session_index=args.session,
        reason=args.reason or "",
        cooldown_minutes=args.cooldown_minutes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_capture_worker(args):
    from modules.visual_capture_worker import run_capture_worker

    result = run_capture_worker(args.contract)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_codex_extract_prepare(args):
    from modules.codex_extract import prepare_codex_extract_requests

    result = prepare_codex_extract_requests(
        args.plan_id,
        args.session,
        config_file=args.config,
        limit=args.limit,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_codex_extract_dispatch(args):
    from modules.codex_extract import dispatch_codex_extract_requests

    result = dispatch_codex_extract_requests(
        args.plan_id,
        args.session,
        config_file=args.config,
        limit=args.limit,
        start=args.start,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_codex_extract_drain(args):
    from modules.codex_extract import run_codex_extract_drain

    result = run_codex_extract_drain(
        args.plan_id,
        args.session,
        config_file=args.config,
        start=args.start,
        poll_seconds=args.poll_seconds,
        idle_timeout_seconds=args.idle_timeout_seconds,
        max_cycles=args.max_cycles,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_apply_extracted_rows(args):
    from modules.codex_extract import apply_codex_extracted_rows

    result = apply_codex_extracted_rows(
        args.request,
        rows_file=args.rows_file,
        config_file=args.config,
        retain_screenshots=args.retain_screenshots,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_visual_log_tile(args):
    from modules.page_sampling import write_tile_summary
    from modules.visual_pipeline import task_dir_for_run

    task_dir = os.path.abspath(args.task_dir) if args.task_dir else task_dir_for_run(args.run_id)
    path = write_tile_summary(
        task_dir=task_dir,
        run_id=args.run_id,
        keyword=args.keyword,
        tile_id=args.tile_id,
        scroll_distance_px=args.scroll_distance_px,
        rough_state=args.rough_state or "",
        image_path=os.path.abspath(args.image) if args.image else "",
        image_retained=args.image_retained,
        rows_extracted=args.rows_extracted,
        new_rows_after_dedupe=args.new_rows_after_dedupe,
        stop_reason=args.stop_reason or "",
        notes=args.notes or "",
    )
    print(json.dumps({"ok": True, "tile_summary": path}, ensure_ascii=False, indent=2))


def cmd_visual_log_event(args):
    from modules.page_sampling import write_task_event
    from modules.visual_pipeline import task_dir_for_run

    task_dir = os.path.abspath(args.task_dir) if args.task_dir else task_dir_for_run(args.run_id)
    path = write_task_event(
        task_dir=task_dir,
        event=args.event,
        level=args.level,
        run_id=args.run_id,
        session_index=args.session,
        keyword=args.keyword or "",
        notes=args.notes or "",
    )
    print(json.dumps({"ok": True, "task_events": path}, ensure_ascii=False, indent=2))


def cmd_visual_ingest(args):
    from modules.vision_extract import ingest_rows, load_rows
    from modules.visual_pipeline import update_manifest_after_ingest
    from modules.page_sampling import page_sampling_config_from_settings, should_retain_screenshot
    from modules.utils import ConfigManager

    rows = load_rows(rows_json=args.rows_json, rows_file=args.rows_file)
    sampling_config = page_sampling_config_from_settings(ConfigManager(args.config))
    retain = True if args.retain_screenshot else None
    if retain is None:
        retain = should_retain_screenshot(
            sampling_config.retain_screenshots,
            failure_reason=args.failure_reason or "",
        )
    result = ingest_rows(
        task_dir=os.path.abspath(args.task_dir),
        keyword=args.keyword,
        rows=rows,
        screenshot_path=os.path.abspath(args.screenshot) if args.screenshot else "",
        captured_at=args.captured_at or "",
        confidence_threshold=args.confidence_threshold,
        retain_screenshot=retain,
        target_limit=sampling_config.target_listings_per_keyword,
        dedupe=True,
    )
    payload = result.to_dict()
    payload["screenshot_retained"] = bool(
        retain and result.screenshot_path and os.path.exists(result.screenshot_path)
    )
    payload["screenshot_retention_policy"] = sampling_config.retain_screenshots
    payload["failure_reason"] = args.failure_reason or ""
    run_id = args.run_id
    if not run_id:
        task_dir = os.path.abspath(args.task_dir)
        run_id = os.path.basename(task_dir.rstrip(os.sep))
    try:
        update_manifest_after_ingest(run_id, args.keyword, payload)
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_visual_export(args):
    from modules.visual_pipeline import export_raw_rows, task_dir_for_run

    result = export_raw_rows(args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.filter:
        from modules.filter import filter_exported_results, filter_exported_results_by_keyword
        from modules.utils import ConfigManager, setup_logging

        config = ConfigManager(args.config)
        logger = setup_logging(level=20)
        task_dir = task_dir_for_run(args.run_id)
        filtered_dir = os.path.join(task_dir, "filtered")
        keyword = args.keyword or ""
        card_name = args.card or keyword.replace(config.get("INPUT", "keyword_prefix", fallback="万智牌"), "").strip()
        if keyword or args.card:
            filter_result = filter_exported_results(
                result["raw_excel"],
                keyword=keyword or card_name or "all_keywords",
                card_name=card_name,
                output_dir=filtered_dir,
                require_magic_prefix=config.getboolean("FILTER", "require_magic_prefix", fallback=True),
                require_card_name=bool(card_name) and config.getboolean("FILTER", "require_card_name", fallback=True),
                exclude_shop_names=config.get("FILTER", "exclude_shop_names", fallback=""),
                exclude_title_keywords=config.get("FILTER", "exclude_title_keywords", fallback=""),
                logger=logger,
            )
        else:
            filter_result = filter_exported_results_by_keyword(
                result["raw_excel"],
                output_dir=filtered_dir,
                keyword_prefix=config.get("INPUT", "keyword_prefix", fallback="万智牌"),
                require_magic_prefix=config.getboolean("FILTER", "require_magic_prefix", fallback=True),
                require_card_name=config.getboolean("FILTER", "require_card_name", fallback=True),
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

    plan_day = sub.add_parser("visual-plan-day", help="从全量输入台账生成当天分段采集计划")
    plan_day.add_argument("--raw-input", required=True, help="原始输入台账 Excel")
    plan_day.add_argument("--plan-id", help="可选：指定 data/tasks/<plan_id>，默认使用时间戳")
    plan_day.add_argument("--random-sample", type=int, help="从候选牌名中随机抽样 N 个关键词")
    plan_day.add_argument("--random-seed", type=int, help="随机抽样 seed，便于复现")
    plan_day.add_argument("--session-count", type=int, help="覆盖配置中的 daily_session_count")

    session_run = sub.add_parser("visual-session-run", help="为 daily plan 的某个 session 生成视觉采集请求")
    session_run.add_argument("plan_id", help="visual-plan-day 生成的 plan_id")
    session_run.add_argument("--session", type=int, required=True, help="要运行的 session 编号（从 1 开始）")
    session_run.add_argument("--limit", type=int, help="最多处理多少个 pending 关键词")
    session_run.add_argument("--state", help="手动覆盖页面状态，如 visible_ready / white_skeleton")
    session_run.add_argument("--force-lease", action="store_true", help="覆盖已有 active lease（仅确认旧进程已死时使用）")

    sync_worker = sub.add_parser("visual-sync-worker", help="Sync Midscene small-session worker output into visual_tasks.json")
    sync_worker.add_argument("plan_id", help="visual-plan-day 生成的 plan_id")
    sync_worker.add_argument("--session", type=int, required=True, help="session 编号（从 1 开始）")

    session_capsule = sub.add_parser("visual-session-capsule", help="为 daily plan 的某个 session 生成短线程上下文 capsule")
    session_capsule.add_argument("plan_id", help="visual-plan-day 生成的 plan_id")
    session_capsule.add_argument("--session", type=int, required=True, help="要准备的 session 编号（从 1 开始）")
    session_capsule.add_argument("--limit", type=int, help="最多纳入多少个 runnable 关键词")
    session_capsule.add_argument("--state", help="手动覆盖页面状态提示")

    session_lease = sub.add_parser("visual-session-lease", help="检查或维护 session lease/watchdog 状态")
    session_lease.add_argument("plan_id", help="visual-plan-day 生成的 plan_id")
    session_lease.add_argument("--session", type=int, required=True, help="session 编号（从 1 开始）")
    session_lease.add_argument(
        "--action",
        default="inspect",
        choices=["inspect", "acquire", "heartbeat", "complete"],
        help="lease 操作",
    )
    session_lease.add_argument("--owner", default="codex", help="acquire 时写入的 owner")
    session_lease.add_argument("--ttl-minutes", type=int, default=240, help="active lease 过期分钟数")
    session_lease.add_argument("--status", default="completed", help="complete 时写入的状态")
    session_lease.add_argument("--force", action="store_true", help="acquire 时覆盖未过期 active lease")

    scheduler_status = sub.add_parser("visual-scheduler-status", help="查看 daily plan 的 session/状态摘要")
    scheduler_status.add_argument("plan_id", help="visual-plan-day 生成的 plan_id")

    heartbeat = sub.add_parser("visual-heartbeat", help="短命心跳：同步状态、准备 session worker contract、返回 worker 命令")
    heartbeat.add_argument("--raw-input", help="整本原始输入台账；缺省读 config [PRODUCT_ROUTING] raw_input_file")
    heartbeat.add_argument("--plan-id", help="可选：覆盖自动 daily_YYYYMMDD plan_id")
    heartbeat.add_argument("--session", type=int, help="可选：强制指定 session；缺省按当前时间和状态选择")
    heartbeat.add_argument("--limit", type=int, help="最多纳入多少个 runnable 关键词")
    heartbeat.add_argument("--mode", default="all", choices=["sync", "prepare", "dispatch", "all"], help="心跳执行阶段")
    heartbeat.add_argument("--random-sample", type=int, help="首次创建 plan 时从候选牌名中随机抽样 N 个关键词")
    heartbeat.add_argument("--random-seed", type=int, help="随机抽样 seed，便于复现")
    heartbeat.add_argument("--session-count", type=int, help="首次创建 plan 时覆盖 session 数")
    heartbeat.add_argument("--force-lease", action="store_true", help="准备请求时覆盖已有 active lease")

    capture_watchdog = sub.add_parser(
        "visual-capture-watchdog",
        help="Session 级 bounded capture watchdog：监督并按规则恢复一个 capture worker",
    )
    capture_watchdog.add_argument("--raw-input", help="整本原始输入台账；heartbeat prepare 需要时使用")
    capture_watchdog.add_argument("--plan-id", required=True, help="daily plan id / run_id")
    capture_watchdog.add_argument("--session", type=int, required=True, help="session 编号")
    capture_watchdog.add_argument("--start", action="store_true", help="真正启动/恢复 capture worker；默认只做建议循环")
    capture_watchdog.add_argument("--poll-seconds", type=float, help="worker 存活或无新动作时的轮询间隔")
    capture_watchdog.add_argument("--idle-timeout-seconds", type=float, help="无进展多久后退出")
    capture_watchdog.add_argument("--max-restarts", type=int, help="本 watchdog 生命周期内最多恢复启动次数")

    control = sub.add_parser("visual-control", help="Codex/人工 supervisor 控制面")
    control.add_argument("action", choices=["status", "pause", "resume", "stop", "cooldown", "lock", "unlock"])
    control.add_argument("--plan-id", required=True, help="daily plan id / run_id")
    control.add_argument("--session", type=int, help="可选：只作用于指定 session")
    control.add_argument("--reason", help="控制动作原因")
    control.add_argument("--cooldown-minutes", type=int, default=60, help="cooldown 持续分钟数")

    capture_worker = sub.add_parser("visual-capture-worker", help="采集 worker：读取 session contract，通过 Midscene computer MCP 真实采集")
    capture_worker.add_argument("--contract", required=True, help="midscene_session_worker_request.json 路径")

    codex_extract_prepare = sub.add_parser(
        "visual-codex-extract-prepare",
        help="为 captured keyword 生成短命 Codex 抽取 contract",
    )
    codex_extract_prepare.add_argument("--plan-id", required=True, help="daily plan id / run_id")
    codex_extract_prepare.add_argument("--session", type=int, required=True, help="session 编号")
    codex_extract_prepare.add_argument("--limit", type=int, help="最多生成多少个 keyword contract")
    codex_extract_prepare.add_argument("--force", action="store_true", help="覆盖已有抽取 contract / apply 结果")

    codex_extract_dispatch = sub.add_parser(
        "visual-codex-extract-dispatch",
        help="返回或启动短命 Codex extract worker 命令",
    )
    codex_extract_dispatch.add_argument("--plan-id", required=True, help="daily plan id / run_id")
    codex_extract_dispatch.add_argument("--session", type=int, required=True, help="session 编号")
    codex_extract_dispatch.add_argument("--limit", type=int, help="最多派发多少个 pending contract")
    codex_extract_dispatch.add_argument("--start", action="store_true", help="真正启动 codex exec；默认只返回启动建议")

    codex_extract_drain = sub.add_parser(
        "visual-codex-extract-drain",
        help="常驻消费 capture 产物：增量 sync、prepare、dispatch，直到 capture 结束且队列清空",
    )
    codex_extract_drain.add_argument("--plan-id", required=True, help="daily plan id / run_id")
    codex_extract_drain.add_argument("--session", type=int, required=True, help="session 编号")
    codex_extract_drain.add_argument("--start", action="store_true", help="真正启动 codex exec worker；默认只做建议循环")
    codex_extract_drain.add_argument("--poll-seconds", type=float, help="没有新输入时的轮询间隔")
    codex_extract_drain.add_argument("--idle-timeout-seconds", type=float, help="无活动多久后退出为 needs_review")
    codex_extract_drain.add_argument("--max-cycles", type=int, help="测试/诊断用：最多循环次数")

    apply_extracted = sub.add_parser(
        "visual-apply-extracted-rows",
        help="确定性应用 Codex extract worker 产出的 rows；不是抽取 worker",
    )
    apply_extracted.add_argument("--request", required=True, help="extract_request.json 路径")
    apply_extracted.add_argument("--rows-file", help="可选：覆盖 request 中的 rows_output")
    apply_extracted.add_argument("--retain-screenshots", action="store_true", help="即使应用成功也保留截图")

    log_tile = sub.add_parser("visual-log-tile", help="追加 viewport tile 轻量摘要")
    log_tile.add_argument("run_id", help="data/tasks/<run_id> 中的 run_id")
    log_tile.add_argument("--task-dir", help="可选：显式任务目录")
    log_tile.add_argument("--keyword", required=True, help="tile 对应搜索关键词")
    log_tile.add_argument("--tile-id", required=True, help="tile_00 / tile_01 ...")
    log_tile.add_argument("--scroll-distance-px", type=int, default=0, help="本 tile 前的滚动距离")
    log_tile.add_argument("--rough-state", help="粗页面状态，如 visible_ready/captcha_required")
    log_tile.add_argument("--image", help="tile 截图路径；成功后可能被删除")
    log_tile.add_argument("--image-retained", action="store_true", help="该 tile 截图是否长期保留")
    log_tile.add_argument("--rows-extracted", type=int, default=0, help="该 tile 或批次识别出的行数")
    log_tile.add_argument("--new-rows-after-dedupe", type=int, default=0, help="去重后新增行数")
    log_tile.add_argument("--stop-reason", help="早停或停止原因")
    log_tile.add_argument("--notes", help="备注")

    log_event = sub.add_parser("visual-log-event", help="追加 task 级结构化事件")
    log_event.add_argument("run_id", help="data/tasks/<run_id> 中的 run_id")
    log_event.add_argument("--task-dir", help="可选：显式任务目录")
    log_event.add_argument("--event", required=True, help="事件名")
    log_event.add_argument("--level", default="info", choices=["debug", "info", "warning", "error"])
    log_event.add_argument("--session", type=int, help="session 编号")
    log_event.add_argument("--keyword", help="相关关键词")
    log_event.add_argument("--notes", help="备注")

    ingest = sub.add_parser("visual-ingest", help="底层 rows 写入能力；主线请用 visual-apply-extracted-rows")
    ingest.add_argument("task_dir", help="任务目录，如 data/tasks/xxx")
    ingest.add_argument("--keyword", required=True, help="截图对应搜索关键词")
    ingest.add_argument("--screenshot", help="截图路径；正常高置信识别后可删除")
    ingest.add_argument("--rows-json", help="JSON 数组，或包含 rows 的 JSON object")
    ingest.add_argument("--rows-file", help="识别结果 JSON 文件")
    ingest.add_argument("--run-id", help="可选：显式指定 run_id；默认取 task_dir 末级目录")
    ingest.add_argument("--confidence-threshold", type=float, default=0.80, help="低于该置信度标记 needs_review")
    ingest.add_argument("--failure-reason", help="异常原因；只有人工介入级别会按策略保留截图")
    ingest.add_argument("--retain-screenshot", action="store_true", default=False, help="即使识别成功也保留原始截图")
    ingest.add_argument("--captured-at", help="截图证据时间；缺失时会 fallback 到当前时间并在结果中提示")

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
    elif args.cmd == "visual-plan-day":
        cmd_visual_plan_day(args)
    elif args.cmd == "visual-session-run":
        cmd_visual_session_run(args)
    elif args.cmd == "visual-sync-worker":
        cmd_visual_sync_worker(args)
    elif args.cmd == "visual-session-capsule":
        cmd_visual_session_capsule(args)
    elif args.cmd == "visual-session-lease":
        cmd_visual_session_lease(args)
    elif args.cmd == "visual-scheduler-status":
        cmd_visual_scheduler_status(args)
    elif args.cmd == "visual-heartbeat":
        cmd_visual_heartbeat(args)
    elif args.cmd == "visual-capture-watchdog":
        cmd_visual_capture_watchdog(args)
    elif args.cmd == "visual-control":
        cmd_visual_control(args)
    elif args.cmd == "visual-capture-worker":
        cmd_visual_capture_worker(args)
    elif args.cmd == "visual-codex-extract-prepare":
        cmd_visual_codex_extract_prepare(args)
    elif args.cmd == "visual-codex-extract-dispatch":
        cmd_visual_codex_extract_dispatch(args)
    elif args.cmd == "visual-codex-extract-drain":
        cmd_visual_codex_extract_drain(args)
    elif args.cmd == "visual-apply-extracted-rows":
        cmd_visual_apply_extracted_rows(args)
    elif args.cmd == "visual-log-tile":
        cmd_visual_log_tile(args)
    elif args.cmd == "visual-log-event":
        cmd_visual_log_event(args)
    elif args.cmd == "visual-ingest":
        cmd_visual_ingest(args)
    elif args.cmd == "visual-export":
        cmd_visual_export(args)


if __name__ == "__main__":
    main()
