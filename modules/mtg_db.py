"""
万智牌数据库参考模块
用于从现有OMG数据库中查询卡牌候选信息，辅助LLM过滤判断。
"""
import os
import select
import threading
import socketserver
import logging
import configparser
from contextlib import contextmanager
from typing import Dict, List

import paramiko
import pymysql
from pymysql.cursors import DictCursor

from modules.utils import get_project_root


class _ThreadingForwardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ForwardHandler(socketserver.BaseRequestHandler):
    ssh_transport = None
    chain_host = ""
    chain_port = 0

    def handle(self):
        try:
            chan = self.ssh_transport.open_channel(
                "direct-tcpip",
                (self.chain_host, self.chain_port),
                self.request.getpeername(),
            )
        except Exception:
            return

        if chan is None:
            return

        try:
            while True:
                read_ready, _, _ = select.select([self.request, chan], [], [])
                if self.request in read_ready:
                    data = self.request.recv(1024)
                    if len(data) == 0:
                        break
                    chan.sendall(data)
                if chan in read_ready:
                    data = chan.recv(1024)
                    if len(data) == 0:
                        break
                    self.request.sendall(data)
        finally:
            chan.close()
            self.request.close()


class MTGDatabase:
    """MySQL查询客户端（只读用途）"""

    def __init__(self, config_file=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.config = self._load_config(config_file)

        self.enabled = self._get_bool("DB", "enabled", False)
        self.use_ssh_tunnel = self._get_bool("DB", "use_ssh_tunnel", False)
        self.host = os.environ.get("MTG_DB_HOST") or self._get("DB", "host", "")
        self.port = int(os.environ.get("MTG_DB_PORT") or self._get("DB", "port", "3306"))
        self.database = os.environ.get("MTG_DB_NAME") or self._get("DB", "database", "")
        self.username = os.environ.get("MTG_DB_USER") or self._get("DB", "username", "")
        self.password = os.environ.get("MTG_DB_PASSWORD") or self._get("DB", "password", "")
        self.connect_timeout = int(self._get("DB", "connect_timeout", "8"))
        self.max_candidates_per_name = int(self._get("DB", "max_candidates_per_name", "5"))

        # SSH跳板机配置（用于透明连接RDS）
        self.ssh_host = os.environ.get("MTG_SSH_HOST") or self._get("SSH", "host", "")
        self.ssh_port = int(os.environ.get("MTG_SSH_PORT") or self._get("SSH", "port", "22"))
        self.ssh_username = os.environ.get("MTG_SSH_USER") or self._get("SSH", "username", "")
        self.ssh_password = os.environ.get("MTG_SSH_PASSWORD") or self._get("SSH", "password", "")
        self.local_bind_port = int(self._get("SSH", "local_bind_port", "0"))

    def _load_config(self, config_file):
        if config_file is None:
            config_file = os.path.join(get_project_root(), "config", "settings.ini")
        config = configparser.ConfigParser()
        config.read(config_file, encoding="utf-8")
        return config

    def _get(self, section, key, fallback):
        return self.config.get(section, key, fallback=fallback)

    def _get_bool(self, section, key, fallback):
        try:
            return self.config.getboolean(section, key, fallback=fallback)
        except ValueError:
            return fallback

    def is_ready(self):
        if not self.enabled:
            return False
        db_required = [self.host, self.database, self.username, self.password]
        if not all(bool(v) for v in db_required):
            return False
        if self.use_ssh_tunnel:
            ssh_required = [self.ssh_host, self.ssh_username, self.ssh_password]
            if not all(bool(v) for v in ssh_required):
                return False
        return True

    def _connect(self, host, port):
        return pymysql.connect(
            host=host,
            port=port,
            user=self.username,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=self.connect_timeout,
            read_timeout=15,
            write_timeout=15,
            autocommit=True,
        )

    def _start_local_forwarder(self, ssh_transport, remote_host, remote_port):
        class SubHandler(_ForwardHandler):
            pass

        SubHandler.ssh_transport = ssh_transport
        SubHandler.chain_host = remote_host
        SubHandler.chain_port = remote_port

        bind_port = self.local_bind_port
        server = _ThreadingForwardServer(("127.0.0.1", bind_port), SubHandler)
        host, port = server.server_address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, host, port

    @contextmanager
    def _connection_with_optional_tunnel(self):
        ssh_client = None
        forward_server = None
        db_host = self.host
        db_port = self.port

        if self.use_ssh_tunnel:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_username,
                password=self.ssh_password,
                timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
            )

            transport = ssh_client.get_transport()
            if transport is None or not transport.is_active():
                raise RuntimeError("SSH连接建立后未获得可用的transport")

            forward_server, _, db_host, db_port = self._start_local_forwarder(
                ssh_transport=transport,
                remote_host=self.host,
                remote_port=self.port,
            )
            self.logger.info(
                f"SSH隧道已建立: {self.ssh_host}:{self.ssh_port} -> "
                f"{self.host}:{self.port} (local {db_host}:{db_port})"
            )

        conn = None
        try:
            conn = self._connect(db_host, db_port)
            yield conn
        finally:
            if conn:
                conn.close()
            if forward_server:
                forward_server.shutdown()
                forward_server.server_close()
            if ssh_client:
                ssh_client.close()

    def test_connection(self):
        if not self.is_ready():
            return False, "DB配置不完整或未启用"

        try:
            with self._connection_with_optional_tunnel() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 AS ok")
                    row = cursor.fetchone()
            if row and row.get("ok") == 1:
                return True, "连接成功"
            return False, "连接异常：测试查询未返回预期结果"
        except Exception as exc:  # pylint: disable=broad-except
            return False, f"连接失败: {exc}"

    def lookup_card_references(self, card_names: List[str]) -> Dict[str, List[str]]:
        """
        批量查询牌名候选信息。
        返回示例：
        {
            "中止": [
                "中文名=中止 | 英文名=Counterspell | 系列中文=无主之地 | 系列缩写=..."
            ]
        }
        """
        result: Dict[str, List[str]] = {}
        if not self.is_ready():
            return result

        clean_names = [str(name).strip() for name in card_names if str(name).strip()]
        if not clean_names:
            return result

        try:
            with self._connection_with_optional_tunnel() as conn:
                with conn.cursor() as cursor:
                    for name in clean_names:
                        rows = self._query_candidates(cursor, name, self.max_candidates_per_name)
                        refs = [self._format_reference(r) for r in rows]
                        # 系列同名/缩写冲突提示：仅用于防误判，不作为保留依据。
                        group_rows = self._query_group_name_collisions(cursor, name, 3)
                        if group_rows:
                            refs.append(self._format_group_collision(group_rows))
                        result[name] = refs
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(f"数据库参考查询失败，已降级为不使用数据库参考: {exc}")
            return {}

        return result

    def lookup_title_hints(self, items: List[Dict]) -> Dict[int, List[str]]:
        """
        基于标题中的系列词与目标牌名关系，生成消歧提示。
        返回: { row_index: [hint1, hint2, ...] }
        """
        result: Dict[int, List[str]] = {}
        if not self.is_ready():
            return result

        try:
            with self._connection_with_optional_tunnel() as conn:
                with conn.cursor() as cursor:
                    for item in items:
                        idx = item.get("index")
                        title = str(item.get("商品名称", "")).strip()
                        target = str(item.get("目标牌名", "")).strip()
                        if idx is None or not title or not target:
                            continue

                        groups = self._query_groups_in_title(cursor, title, 8)
                        if not groups:
                            continue

                        labels = []
                        possible_groups = []
                        for g in groups:
                            label = (
                                g.get("groupChineseName")
                                or g.get("groupChineseAbbr")
                                or g.get("name")
                                or str(g.get("groupId"))
                            )
                            labels.append(label)
                            if self._group_contains_target_card(cursor, g.get("groupId"), target):
                                possible_groups.append(label)

                        hints = [f"标题命中系列词={', '.join(labels)}"]
                        if possible_groups:
                            hints.append(
                                f"系列-牌名关系提示=目标牌名<{target}>在系列<{', '.join(possible_groups)}>中存在"
                            )
                        elif len(labels) >= 2:
                            hints.append(
                                f"系列-牌名关系提示=命中系列词均未找到目标牌名<{target}>，请警惕系列词干扰"
                            )
                        else:
                            continue

                        result[idx] = hints
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(f"标题消歧提示查询失败，已忽略: {exc}")
            return {}

        return result

    def lookup_longer_name_conflicts(
        self, card_names: List[str], limit_count: int = 200
    ) -> Dict[str, List[str]]:
        """
        查询“更长官方中文名”冲突词：
        - key: 目标牌名（通常较短）
        - value: 数据库中包含该牌名、且不等于该牌名的 chineseName 列表（按长度升序，优先更短的扩展名，避免 LIMIT 只截到极长牌名而漏掉常见撞车名）
        """
        result: Dict[str, List[str]] = {}
        if not self.is_ready():
            return result

        clean_names = sorted({str(name).strip() for name in card_names if str(name).strip()})
        if not clean_names:
            return result

        try:
            with self._connection_with_optional_tunnel() as conn:
                with conn.cursor() as cursor:
                    for name in clean_names:
                        rows = self._query_longer_name_conflicts(cursor, name, limit_count)
                        result[name] = [str(r.get("chineseName", "")).strip() for r in rows if r.get("chineseName")]
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(f"短名冲突词查询失败，已忽略该策略: {exc}")
            return {}

        return result

    def lookup_products_by_ids(self, product_ids: List[str]) -> Dict[str, Dict]:
        """
        按 productId 批量查询产品与系列特征，供 open_url 阶段做 URL 关联。
        返回: { "123": {product fields...}, ... }
        """
        result: Dict[str, Dict] = {}
        if not self.is_ready():
            return result

        clean_ids = []
        for pid in product_ids:
            text = str(pid or "").strip()
            if not text:
                continue
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                clean_ids.append(digits)
        clean_ids = sorted(set(clean_ids))
        if not clean_ids:
            return result

        try:
            with self._connection_with_optional_tunnel() as conn:
                with conn.cursor() as cursor:
                    batch_size = 200
                    for i in range(0, len(clean_ids), batch_size):
                        batch = clean_ids[i : i + batch_size]
                        rows = self._query_products_by_ids(cursor, batch)
                        for row in rows:
                            pid = str(row.get("productId", "")).strip()
                            if pid:
                                result[pid] = row
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(f"按 productId 查询产品特征失败，已降级: {exc}")
            return {}

        return result

    def _query_candidates(self, cursor, card_name, limit_count):
        exact_sql = """
            SELECT
                p.productId,
                p.chineseName,
                p.englishName,
                p.productName,
                p.zcProductName,
                p.collectNumber,
                p.rarity,
                g.name AS groupName,
                g.groupChineseName,
                g.groupChineseAbbr
            FROM product p
            LEFT JOIN `group` g ON p.groupId = g.groupId
            WHERE p.chineseName = %s
            ORDER BY p.productId DESC
            LIMIT %s
        """
        cursor.execute(exact_sql, (card_name, limit_count))
        rows = cursor.fetchall()
        if rows:
            return rows

        # 回退：目标词也可能是英文名，保留少量英文精确候选供LLM参考。
        english_exact_sql = """
            SELECT
                p.productId,
                p.chineseName,
                p.englishName,
                p.productName,
                p.zcProductName,
                p.collectNumber,
                p.rarity,
                g.name AS groupName,
                g.groupChineseName,
                g.groupChineseAbbr
            FROM product p
            LEFT JOIN `group` g ON p.groupId = g.groupId
            WHERE p.englishName = %s
            ORDER BY p.productId DESC
            LIMIT %s
        """
        cursor.execute(english_exact_sql, (card_name, limit_count))
        rows = cursor.fetchall()
        if rows:
            return rows

        like_kw = f"%{card_name}%"
        fuzzy_sql = """
            SELECT
                p.productId,
                p.chineseName,
                p.englishName,
                p.productName,
                p.zcProductName,
                p.collectNumber,
                p.rarity,
                g.name AS groupName,
                g.groupChineseName,
                g.groupChineseAbbr
            FROM product p
            LEFT JOIN `group` g ON p.groupId = g.groupId
            WHERE p.chineseName LIKE %s
            ORDER BY p.productId DESC
            LIMIT %s
        """
        cursor.execute(fuzzy_sql, (like_kw, limit_count))
        return cursor.fetchall()

    def _query_group_name_collisions(self, cursor, card_name, limit_count):
        query = """
            SELECT
                groupId,
                name,
                groupChineseName,
                groupChineseAbbr
            FROM `group`
            WHERE groupChineseName = %s
               OR groupChineseAbbr = %s
               OR name = %s
            ORDER BY groupId DESC
            LIMIT %s
        """
        cursor.execute(query, (card_name, card_name, card_name, limit_count))
        return cursor.fetchall()

    def _query_products_by_ids(self, cursor, product_ids):
        placeholders = ",".join(["%s"] * len(product_ids))
        query = f"""
            SELECT
                p.productId,
                p.chineseName,
                p.englishName,
                p.productName,
                p.zcProductName,
                p.collectNumber,
                p.rarity,
                p.groupId,
                g.name AS groupName,
                g.groupChineseName,
                g.groupChineseAbbr
            FROM product p
            LEFT JOIN `group` g ON p.groupId = g.groupId
            WHERE p.productId IN ({placeholders})
        """
        cursor.execute(query, tuple(product_ids))
        return cursor.fetchall()

    def _query_longer_name_conflicts(self, cursor, card_name, limit_count):
        query = """
            SELECT DISTINCT chineseName
            FROM product
            WHERE chineseName LIKE %s
              AND chineseName <> %s
            ORDER BY CHAR_LENGTH(chineseName) ASC, chineseName ASC
            LIMIT %s
        """
        cursor.execute(query, (f"%{card_name}%", card_name, limit_count))
        return cursor.fetchall()

    def _query_groups_in_title(self, cursor, title, limit_count):
        query = """
            SELECT
                groupId,
                name,
                groupChineseName,
                groupChineseAbbr
            FROM `group`
            WHERE (groupChineseName <> '' AND %s LIKE CONCAT('%%', groupChineseName, '%%'))
               OR (groupChineseAbbr <> '' AND %s LIKE CONCAT('%%', groupChineseAbbr, '%%'))
               OR (name <> '' AND %s LIKE CONCAT('%%', name, '%%'))
            ORDER BY groupId DESC
            LIMIT %s
        """
        cursor.execute(query, (title, title, title, limit_count))
        return cursor.fetchall()

    def _group_contains_target_card(self, cursor, group_id, target):
        if not group_id:
            return False
        query = """
            SELECT 1
            FROM product
            WHERE groupId = %s
              AND (chineseName = %s OR englishName = %s)
            LIMIT 1
        """
        cursor.execute(query, (group_id, target, target))
        row = cursor.fetchone()
        return bool(row)

    @staticmethod
    def _format_reference(row):
        chinese_name = row.get("chineseName") or "-"
        english_name = row.get("englishName") or "-"
        group_cn = row.get("groupChineseName") or "-"
        group_abbr = row.get("groupChineseAbbr") or "-"
        collect_number = row.get("collectNumber") or "-"
        rarity = row.get("rarity") or "-"
        return (
            f"中文名={chinese_name} | 英文名={english_name} | "
            f"系列中文={group_cn} | 系列缩写={group_abbr} | "
            f"编号={collect_number} | 稀有度={rarity}"
        )

    @staticmethod
    def _format_group_collision(rows):
        parts = []
        for row in rows:
            parts.append(
                f"{row.get('groupChineseName') or '-'}"
                f"/{row.get('groupChineseAbbr') or '-'}"
                f"/{row.get('name') or '-'}"
            )
        return "同名系列提示=" + " ; ".join(parts)
