"""
数据库连通性测试脚本

用法:
    python test_db_connection.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.mtg_db import MTGDatabase
from modules.utils import setup_logging


def main():
    logger = setup_logging(level=20)
    db = MTGDatabase(logger=logger)
    ok, message = db.test_connection()

    print("=" * 60)
    print("MTG数据库连接测试")
    print("=" * 60)
    print(f"SSH隧道模式: {'开启' if db.use_ssh_tunnel else '关闭'}")
    print(f"结果: {'成功' if ok else '失败'}")
    print(f"详情: {message}")

    if not ok:
        print("\n请检查 config/settings.ini 的 [DB]/[SSH] 配置，或环境变量：")
        print("  MTG_DB_HOST, MTG_DB_PORT, MTG_DB_NAME, MTG_DB_USER, MTG_DB_PASSWORD")
        print("  MTG_SSH_HOST, MTG_SSH_PORT, MTG_SSH_USER, MTG_SSH_PASSWORD")
        sys.exit(1)


if __name__ == "__main__":
    main()
