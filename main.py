#!/usr/bin/env python3
"""Local Chrome visual collection task preparation entry point."""
import argparse
import json
import os
import sys
from datetime import datetime


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from modules.checkpoint import CheckpointManager
from modules.task_state import TaskRecord
from modules.utils import ConfigManager, ensure_dir


def _keyword_from_card(config, card_name):
    prefix = config.get("INPUT", "keyword_prefix", fallback="万智牌")
    return f"{prefix} {card_name}".strip()


def _load_keywords_from_args(args, config, checkpoint_dir):
    if args.keyword:
        return [_keyword_from_card(config, args.keyword)]

    if args.excel:
        from modules.input_reader import process_excel

        prefix = config.get("INPUT", "keyword_prefix", fallback="万智牌")
        _df, _unique_names, keywords, _name_to_ids = process_excel(
            args.excel,
            prefix=prefix,
            checkpoint_dir=checkpoint_dir,
        )
        return keywords

    return []


def prepare_visual_task(args):
    config = ConfigManager(args.config)
    checkpoint_dir = os.path.abspath(
        config.get("CHECKPOINT", "checkpoint_dir", fallback="data/checkpoints")
    )
    ensure_dir(checkpoint_dir)

    keywords = _load_keywords_from_args(args, config, checkpoint_dir)
    if not keywords:
        raise SystemExit("没有有效关键词。请使用 -e cards.xlsx 或 -k 牌名。")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = os.path.join(ROOT, "data", "tasks", run_id)
    evidence_root = os.path.join(task_dir, "evidence")
    ensure_dir(task_dir)
    ensure_dir(evidence_root)

    records = []
    for keyword in keywords:
        evidence_dir = os.path.join(evidence_root, _safe_name(keyword))
        ensure_dir(evidence_dir)
        record = TaskRecord(
            keyword=keyword,
            status="pending",
            evidence_dir=evidence_dir,
            last_action="visual_task_prepared",
            agent_notes=(
                "Prepared for local Chrome pure-vision collection. "
                "Collect only visible page evidence and structured visual rows."
            ),
        )
        records.append(record.to_dict())

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "excel": os.path.abspath(args.excel) if args.excel else None,
            "keyword": args.keyword,
            "config": os.path.abspath(args.config),
        },
        "workflow": "local_chrome_visual_capture",
        "keywords": keywords,
        "records": records,
        "next_steps": [
            "Use the configured visual provider with logged-in local Chrome and low-frequency scheduling.",
            "Capture retained visible screenshots into each evidence_dir.",
            "Extract visible product rows into raw rows without network/cookie/storage access.",
            "Feed raw rows into existing filter/DB/LLM/statistical assignment pipeline.",
        ],
    }

    manifest_path = os.path.join(task_dir, "visual_tasks.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    keywords_path = os.path.join(task_dir, "keywords.txt")
    with open(keywords_path, "w", encoding="utf-8") as f:
        f.write("\n".join(keywords))
        f.write("\n")

    checkpoint = CheckpointManager(checkpoint_dir)
    checkpoint.create(args.excel or f"keyword:{args.keyword}", keywords)
    checkpoint_copy = os.path.join(task_dir, os.path.basename(checkpoint.checkpoint_file))
    try:
        import shutil

        shutil.copy2(checkpoint.checkpoint_file, checkpoint_copy)
    except Exception:
        checkpoint_copy = None

    print("=" * 60)
    print("视觉采集任务已准备")
    print("=" * 60)
    print(f"run_id: {run_id}")
    print(f"关键词数: {len(keywords)}")
    print(f"任务目录: {task_dir}")
    print(f"任务清单: {manifest_path}")
    print(f"关键词文件: {keywords_path}")
    if checkpoint_copy:
        print(f"checkpoint: {checkpoint_copy}")
    print("\n下一步: 使用 harness.py visual-run 生成视觉采集请求。")


def _safe_name(value):
    keep = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    name = "".join(keep).strip("_")
    return name[:80] or "keyword"


def main():
    parser = argparse.ArgumentParser(
        description="淘宝万智牌价格视觉采集任务准备入口"
    )
    parser.add_argument("-e", "--excel", help="Excel 输入文件路径")
    parser.add_argument("-k", "--keyword", help="单关键词任务（输入牌名，不含前缀）")
    parser.add_argument("-c", "--config", default="config/settings.ini", help="配置文件路径")
    parser.add_argument("--run-id", help="指定任务目录 run_id，默认使用时间戳")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="保留参数占位：视觉采集恢复将在 visual checkpoint 中实现",
    )
    args = parser.parse_args()

    if not args.excel and not args.keyword:
        parser.print_help()
        print("\n示例:")
        print("  python3 main.py -e cards.xlsx")
        print("  python3 main.py -k 中止")
        return

    if args.resume:
        print("提示: --resume 暂未接入视觉采集恢复逻辑，本次仍会准备新的任务清单。")

    prepare_visual_task(args)


if __name__ == "__main__":
    main()
