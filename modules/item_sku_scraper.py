"""
商品 SKU 采集模块
逐条打开淘宝商品页，通过店透视插件复制 SKU 表并解析。
输入：LLM 过滤后的 pure Excel（需含「商品链接」列）。
输出：listing_meta + sku_rows 双 sheet Excel。
"""
import io
import os
import json
import time
import random
import math
import logging
import configparser
import re
from datetime import datetime

import pandas as pd
import pyperclip

from modules.mtg_db import MTGDatabase
from modules.utils import get_project_root, ensure_dir
from modules.warmup import dismiss_overlays


STATUS_SUCCESS = "success"
STATUS_NEED_LOGIN = "need_login"
STATUS_CAPTCHA = "captcha"
STATUS_PLUGIN_MISSING = "plugin_missing"
STATUS_CLIPBOARD_EMPTY = "clipboard_empty"
STATUS_PARSE_ERROR = "parse_error"
STATUS_NAV_ERROR = "nav_error"
STATUS_UNKNOWN = "unknown_error"


class SkuCheckpoint:
    """按商品链接做断点续传（JSON 文件）"""

    def __init__(self, checkpoint_dir="data/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
        self.file = None
        self.data = None

    def create(self, source_file, urls, checkpoint_file=None):
        if checkpoint_file:
            self.file = os.path.join(self.checkpoint_dir, checkpoint_file)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.file = os.path.join(self.checkpoint_dir, f"sku_{ts}.json")
        self.data = {
            "source_file": source_file,
            "started_at": datetime.now().isoformat(),
            "total": len(urls),
            "urls": urls,
            "processed": [],
            "failed": {},
        }
        self._ensure_schema()
        self._save()

    def load(self, path):
        if not os.path.isabs(path):
            path = os.path.join(self.checkpoint_dir, path)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self._ensure_schema()
        self.file = path
        return self.data

    def find_latest(self):
        if not os.path.exists(self.checkpoint_dir):
            return None
        candidates = [
            f for f in os.listdir(self.checkpoint_dir)
            if f.startswith("sku_") and f.endswith(".json")
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda f: os.path.getmtime(os.path.join(self.checkpoint_dir, f)),
            reverse=True,
        )
        return os.path.join(self.checkpoint_dir, candidates[0])

    def remaining(self, retry_failed=False):
        if not self.data:
            return []
        done = set(self.data["processed"])
        if not retry_failed:
            return [u for u in self.data["urls"] if u not in done]
        failed = set(self.data.get("failed", {}).keys())
        return [u for u in self.data["urls"] if (u not in done) or (u in failed)]

    def mark_done(self, url):
        if not self.data:
            return
        self._ensure_schema()
        if url not in self.data["processed"]:
            self.data["processed"].append(url)
        self.data.pop("failed", {}).pop(url, None)
        self._save()

    def mark_failed(self, url, status, detail=""):
        if not self.data:
            return
        self._ensure_schema()
        self.data["failed"][url] = {"status": status, "detail": detail}
        if url not in self.data["processed"]:
            self.data["processed"].append(url)
        self._save()

    def _ensure_schema(self):
        """兼容旧 checkpoint：补齐缺失字段，避免 KeyError。"""
        if self.data is None:
            self.data = {}
        if not isinstance(self.data.get("processed"), list):
            self.data["processed"] = []
        if not isinstance(self.data.get("failed"), dict):
            self.data["failed"] = {}
        if not isinstance(self.data.get("urls"), list):
            self.data["urls"] = []
        if "total" not in self.data:
            self.data["total"] = len(self.data["urls"])

    def _save(self):
        if not self.file or not self.data:
            return
        import tempfile, shutil
        fd, tmp = tempfile.mkstemp(dir=self.checkpoint_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp, self.file)


def _load_selectors(selectors_file):
    if selectors_file and os.path.exists(selectors_file):
        with open(selectors_file, "r", encoding="utf-8") as f:
            return json.load(f).get("item_sku", {})
    return {}


def _detect_anomaly(page, selectors):
    """检测登录踢出 / 验证码 / 插件缺失"""
    try:
        current_url = (page.url or "").lower()
        if "login.taobao.com" in current_url or "havanaone/login" in current_url:
            return STATUS_NEED_LOGIN
    except Exception:
        pass

    for sel in selectors.get("login_indicator", []):
        try:
            if page.ele(sel, timeout=1):
                return STATUS_NEED_LOGIN
        except Exception:
            pass
    for sel in selectors.get("captcha_indicator", []):
        try:
            if page.ele(sel, timeout=1):
                return STATUS_CAPTCHA
        except Exception:
            pass
    return None


def _click_copy_sku(page, selectors, logger):
    """点击店透视 SKU 区的「复制表格/复制」按钮"""
    for sel in selectors.get("copy_sku_button", ["text:复制表格", "text:复制"]):
        try:
            btn = page.ele(sel, timeout=3)
            if btn:
                btn.click()
                logger.debug(f"已点击 SKU 复制按钮: {sel}")
                return True
        except Exception:
            continue
    return False


def _click_any(page, selector_list, logger, step_name, timeout=3):
    """按选择器列表逐个点击，命中即返回 True。"""
    for sel in selector_list:
        try:
            el = page.ele(sel, timeout=timeout)
            if el:
                el.click()
                logger.debug(f"[{step_name}] 点击成功: {sel}")
                return True
        except Exception:
            continue
    return False


def _collect_clickable_text_candidates(page, limit=80):
    """采集页面常见可点击节点文本，失败排障用。"""
    try:
        js = f"""
            const nodes = Array.from(document.querySelectorAll('button,a,span,div,li'));
            const out = [];
            for (const n of nodes) {{
              const t = (n.innerText || '').trim();
              if (!t || t.length > 24) continue;
              const style = window.getComputedStyle(n);
              if (style.display === 'none' || style.visibility === 'hidden') continue;
              const r = n.getBoundingClientRect();
              if (r.width < 6 || r.height < 6) continue;
              out.push(t.replace(/\\s+/g, ' '));
              if (out.length >= {limit}) break;
            }}
            return Array.from(new Set(out));
        """
        return page.run_js(js) or []
    except Exception:
        return []


def _open_sku_preview_export_and_copy(page, selectors, logger):
    """
    你要求的固定流程：
    1) SKU预览入口
    2) 导出表格标签页
    3) 复制表格按钮
    """
    preview_selectors = selectors.get(
        "sku_preview_entry",
        [
            "text:SKU预览",
            "text:sku预览",
            "text:规格预览",
            "text:SKU",
        ],
    )
    export_tab_selectors = selectors.get(
        "export_tab",
        [
            "text:导出表格",
            "text:导出",
            "text:表格导出",
        ],
    )
    copy_selectors = selectors.get(
        "copy_sku_button",
        [
            "text:复制表格",
            "text:复制",
        ],
    )

    # step 1: SKU预览
    tabs_before = 0
    try:
        tabs_before = page.tabs_count
    except Exception:
        tabs_before = 0
    if not _click_any(page, preview_selectors, logger, "SKU预览", timeout=4):
        return False, "未找到 SKU预览入口"
    time.sleep(1.2)

    # 如果触发了新 tab，切到最新 tab
    try:
        tabs_after = page.tabs_count
        if tabs_after > tabs_before:
            page = page.latest_tab
            time.sleep(0.8)
            logger.debug("检测到新标签页，已切换到 latest_tab")
    except Exception:
        pass

    # step 2: 导出表格标签页
    if not _click_any(page, export_tab_selectors, logger, "导出表格tab", timeout=4):
        return False, "未找到 导出表格 标签页"
    time.sleep(1.0)

    # step 3: 复制表格
    if not _click_any(page, copy_selectors, logger, "复制表格", timeout=4):
        return False, "未找到 复制表格 按钮"
    return True, ""


def _open_plugin_panel_if_needed(page, selectors, logger):
    """
    商品页上先尝试打开店透视面板，再查找复制按钮。
    部分页面需要先点插件入口，复制按钮才会渲染出来。
    """
    if _click_copy_sku(page, selectors, logger):
        return True

    trigger_selectors = selectors.get(
        "panel_trigger",
        [
            "text:店透视",
            "text:店透视插件",
            "text:数据看板",
            "text:插件",
        ],
    )
    for sel in trigger_selectors:
        try:
            btn = page.ele(sel, timeout=2)
            if not btn:
                continue
            btn.click()
            logger.debug(f"已点击插件面板入口: {sel}")
            time.sleep(1)
            if _click_copy_sku(page, selectors, logger):
                return True
        except Exception:
            continue

    # 兜底：用 JS 按文案点击可能的入口节点
    try:
        js = """
            const texts = ['店透视', '插件', '数据看板'];
            const nodes = Array.from(document.querySelectorAll('button,a,div,span'));
            for (const n of nodes) {
                const t = (n.innerText || '').trim();
                if (!t) continue;
                if (texts.some(k => t.includes(k))) {
                    n.click();
                    return t;
                }
            }
            return '';
        """
        clicked = page.run_js(js)
        if clicked:
            logger.debug(f"JS点击插件入口: {clicked}")
            time.sleep(1)
            if _click_copy_sku(page, selectors, logger):
                return True
    except Exception:
        pass

    return False


def _read_clipboard_sku(logger):
    """从剪贴板读取 TSV，返回 (header_list, rows_list[dict]) 或 (None, None)"""
    try:
        raw = pyperclip.paste()
    except Exception as e:
        logger.warning(f"剪贴板读取失败: {e}")
        return None, None, None

    if not raw or len(raw) < 5:
        return None, None, None

    preview = raw[:300].replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    try:
        df = pd.read_csv(io.StringIO(raw), sep="\t", header=None, dtype=str)
    except Exception as e:
        logger.warning(f"TSV 解析失败: {e}")
        return preview, None, None

    if len(df) < 2:
        return preview, None, None

    header = [str(v).strip() for v in df.iloc[0].tolist()]
    rows = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        rd = {}
        raw_parts = []
        for j in range(len(row)):
            col = header[j] if j < len(header) else f"col_{j}"
            val = str(row[j]).strip() if pd.notna(row[j]) else ""
            rd[col] = val
            raw_parts.append(val)
        rd["_raw_row"] = "\t".join(raw_parts)
        rows.append(rd)

    return preview, header, rows


def _extract_item_id(url):
    """从淘宝 URL 中提取商品 ID"""
    import re
    m = re.search(r"[?&]id=(\d+)", str(url))
    return m.group(1) if m else ""


def _normalize_item_url(url):
    """归一化商品链接，避免 // 被浏览器误判为本地文件路径。"""
    u = str(url).strip()
    if not u:
        return ""
    if u.startswith("//"):
        return f"https:{u}"
    if u.startswith("/"):
        return f"https://item.taobao.com{u}"
    if u.startswith("item.taobao.com/"):
        return f"https://{u}"
    return u


def _safe_int(val, default=0):
    s = str(val or "").replace(",", "").replace("'", "").strip()
    if not s:
        return default
    digits = []
    for ch in s:
        if ch.isdigit():
            digits.append(ch)
        elif digits:
            break
    if not digits:
        return default
    try:
        return int("".join(digits))
    except Exception:
        return default


def _safe_float(val, default=None):
    s = str(val or "").replace(",", "").replace("'", "").strip()
    if not s:
        return default
    out = []
    dot_used = False
    for ch in s:
        if ch.isdigit():
            out.append(ch)
        elif ch == "." and not dot_used:
            dot_used = True
            out.append(ch)
        elif out:
            break
    if not out:
        return default
    try:
        return float("".join(out))
    except Exception:
        return default


def _extract_card_name_from_row(row):
    kw = str(row.get("搜索关键词", "") or row.get("关键词", "")).strip()
    if kw:
        return kw.replace("万智牌", "").strip()
    for col in ["中文卡牌名", "目标牌名", "card_name"]:
        v = str(row.get(col, "")).strip()
        if v:
            return v
    return "__UNKNOWN__"


def _build_price_proxy_row(run_id, input_file, card_name, rows, strategy):
    values = []
    weights = []
    unique_shops = set()
    for _, _, meta in rows:
        shop_name = (meta.get("shop_name") or "").strip()
        if shop_name:
            unique_shops.add(shop_name)
        p = meta.get("spu_price")
        if p is None:
            continue
        values.append(float(p))
        weights.append(math.log(meta.get("pay_count", 0) + 1) + 1.0)

    if not values:
        return None

    return {
        "run_id": run_id,
        "source_file": os.path.basename(input_file),
        "card_name": card_name,
        "listing_count": len(rows),
        "unique_shops": len(unique_shops),
        "valid_price_count": len(values),
        "p25": _weighted_quantile(values, weights, 0.25),
        "p50": _weighted_quantile(values, weights, 0.50),
        "p75": _weighted_quantile(values, weights, 0.75),
        "strategy": strategy,
        "captured_at": datetime.now().isoformat(),
    }


def _load_big_sellers(big_sellers_file):
    if not big_sellers_file or not os.path.exists(big_sellers_file):
        return []
    names = []
    with open(big_sellers_file, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            names.append(t)
    return names


def _shop_match(shop_name, big_sellers, match_mode="contains"):
    shop = str(shop_name or "").strip()
    if not shop or not big_sellers:
        return False
    if match_mode == "exact":
        return shop in big_sellers
    return any(x in shop for x in big_sellers if x)


def _weighted_quantile(values, weights, q):
    if not values:
        return None
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    threshold = q * total
    csum = 0.0
    for v, w in pairs:
        csum += w
        if csum >= threshold:
            return v
    return pairs[-1][0]


def _find_existing_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_text(text):
    return str(text or "").strip().lower()


def _contains_term(title_text, term):
    title = _normalize_text(title_text)
    t = _normalize_text(term)
    if not title or not t:
        return False
    return t in title


def _contains_collect_number(title_text, collect_number):
    title = _normalize_text(title_text)
    collect = _normalize_text(collect_number)
    if not title or not collect:
        return False
    if collect in title:
        return True
    # 兼容编号前缀符号，如 "#123"、"no.123"
    digits = "".join(ch for ch in collect if ch.isdigit())
    if not digits:
        return False
    return bool(re.search(rf"(#|no\.?)?\s*0*{re.escape(digits)}([a-z]|$)", title))


def _load_open_url_targets(open_url_input_file, config, logger):
    if not open_url_input_file or not os.path.exists(open_url_input_file):
        return [], f"open_url 输入文件不存在: {open_url_input_file}"

    try:
        df = pd.read_excel(open_url_input_file, engine="openpyxl", dtype=str)
    except Exception as exc:  # pylint: disable=broad-except
        return [], f"读取 open_url 输入失败: {exc}"

    product_id_col_cfg = config.get("INPUT", "product_id_column", fallback="productId").strip()
    card_name_col_cfg = config.get("INPUT", "card_name_column", fallback="中文卡牌名").strip()

    product_col = _find_existing_col(df, [product_id_col_cfg, "productId", "source_product_id"])
    card_col = _find_existing_col(df, [card_name_col_cfg, "中文卡牌名", "statistical_card_name", "card_name"])
    mode_col = _find_existing_col(df, ["effective_mode", "preferred_mode", "pricing_mode"])
    status_col = _find_existing_col(df, ["assignment_status"])

    if product_col is None:
        return [], "open_url 输入缺少 productId 列"

    open_targets = {}
    for _, row in df.iterrows():
        pid = str(row.get(product_col, "") or "").strip()
        if not pid:
            continue
        mode = _normalize_text(row.get(mode_col, "")) if mode_col else ""
        status = _normalize_text(row.get(status_col, "")) if status_col else ""
        is_open_url = (
            ("open_url" in mode)
            or (status in {"open_url_pending", "statistical_blocked_pending_open_url"})
        )
        if not is_open_url:
            continue
        card_name = str(row.get(card_col, "") or "").strip() if card_col else ""
        if pid not in open_targets:
            open_targets[pid] = {
                "product_id": pid,
                "card_name": card_name,
                "effective_mode": mode,
                "assignment_status": status,
            }
        elif not open_targets[pid].get("card_name") and card_name:
            open_targets[pid]["card_name"] = card_name

    targets = list(open_targets.values())
    logger.info(
        f"open_url 目标 product 数: {len(targets)}（来源文件: {open_url_input_file}）"
    )
    if not targets:
        return [], "未找到需要 open_url 的 product（检查 effective_mode/assignment_status）"
    return targets, ""


def _build_product_feature_map(product_targets, db_client):
    ids = [x["product_id"] for x in product_targets]
    rows = db_client.lookup_products_by_ids(ids)
    feature_map = {}
    for pid, row in rows.items():
        set_terms = []
        for key in ("groupChineseAbbr", "groupChineseName", "groupName"):
            val = str(row.get(key, "") or "").strip()
            if val:
                set_terms.append(val)
        # 去重并保序
        seen = set()
        dedup_terms = []
        for t in set_terms:
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            dedup_terms.append(t)
        feature_map[str(pid)] = {
            "product_id": str(pid),
            "card_name_db": str(row.get("chineseName", "") or "").strip(),
            "english_name": str(row.get("englishName", "") or "").strip(),
            "product_name": str(row.get("productName", "") or "").strip(),
            "zc_product_name": str(row.get("zcProductName", "") or "").strip(),
            "collect_number": str(row.get("collectNumber", "") or "").strip(),
            "set_terms": dedup_terms,
            "group_id": row.get("groupId"),
        }
    return feature_map


def scrape_skus(
    input_file,
    output_file=None,
    page=None,
    config_file=None,
    logger=None,
    resume=False,
    open_url_input_file=None,
):
    """
    主入口：逐条打开商品页 → 插件复制 SKU → 解析 → 输出。

    Args:
        input_file: LLM 过滤后的 pure Excel（需含「商品链接」列）
        output_file: 输出 xlsx 路径（默认 input 同目录 _sku_detail.xlsx）
        page: 已初始化的 ChromiumPage 实例
        config_file: settings.ini 路径
        logger: 日志
        resume: 是否从上次断点恢复
        open_url_input_file: open_url 目标 product 列表文件（通常为 final_assignment 输出）

    Returns:
        dict: 结果摘要
    """
    log = logger or logging.getLogger(__name__)

    if config_file is None:
        config_file = os.path.join(get_project_root(), "config", "settings.ini")
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    delay_min = config.getfloat("SKU_SCRAPE", "delay_min", fallback=3.0)
    delay_max = config.getfloat("SKU_SCRAPE", "delay_max", fallback=12.0)
    pause_every = config.getint("SKU_SCRAPE", "pause_every", fallback=30)
    pause_duration = config.getfloat("SKU_SCRAPE", "pause_duration", fallback=60.0)
    save_every = config.getint("SKU_SCRAPE", "save_every", fallback=1)
    retry_failed_on_resume = config.getboolean(
        "SKU_SCRAPE", "retry_failed_on_resume", fallback=True
    )
    nav_error_restart_threshold = config.getint(
        "SKU_SCRAPE", "nav_error_restart_threshold", fallback=5
    )
    page_load_timeout = config.getfloat("SKU_SCRAPE", "page_load_timeout", fallback=15.0)
    copy_wait = config.getfloat("SKU_SCRAPE", "copy_wait", fallback=1.5)
    dismiss_on_item_page = config.getboolean(
        "SKU_SCRAPE", "dismiss_overlays_on_item_page", fallback=True
    )
    dismiss_rounds = config.getint("WARMUP", "dismiss_rounds", fallback=3)
    dismiss_interval = config.getfloat("WARMUP", "dismiss_interval", fallback=2.0)
    selectors_file = config.get("PLUGIN", "selectors_file", fallback="config/selectors.json")
    if not os.path.isabs(selectors_file):
        selectors_file = os.path.join(get_project_root(), selectors_file)
    selectors = _load_selectors(selectors_file)
    checkpoint_dir = config.get("CHECKPOINT", "checkpoint_dir", fallback="data/checkpoints")
    if not os.path.isabs(checkpoint_dir):
        checkpoint_dir = os.path.join(get_project_root(), checkpoint_dir)

    if not os.path.exists(input_file):
        log.error(f"输入文件不存在: {input_file}")
        return {"success": False, "error": "文件不存在"}

    if output_file is None:
        base, _ = os.path.splitext(input_file)
        output_file = f"{base}_sku_detail.xlsx"

    df_input = pd.read_excel(input_file, engine="openpyxl", dtype=str)
    per_product_k = config.getint("SKU_OPEN_URL", "per_product_k", fallback=3)
    require_set_match = config.getboolean("SKU_OPEN_URL", "require_set_match", fallback=True)
    score_collect_weight = config.getfloat("SKU_OPEN_URL", "score_collect_weight", fallback=100.0)
    score_pay_weight = config.getfloat("SKU_OPEN_URL", "score_pay_weight", fallback=3.0)
    score_big_seller_weight = config.getfloat("SKU_OPEN_URL", "score_big_seller_weight", fallback=2.0)
    score_multi_product_weight = config.getfloat("SKU_OPEN_URL", "score_multi_product_weight", fallback=10.0)
    big_seller_match_mode = config.get(
        "SKU_SAMPLING", "big_seller_match_mode", fallback="contains"
    ).strip().lower()
    big_sellers_file = config.get(
        "SKU_SAMPLING", "big_sellers_file", fallback="config/big_sellers.txt"
    )
    if not os.path.isabs(big_sellers_file):
        big_sellers_file = os.path.join(get_project_root(), big_sellers_file)
    big_sellers = _load_big_sellers(big_sellers_file)
    url_col = None
    for c in ["商品链接", "商品URL", "url", "link"]:
        if c in df_input.columns:
            url_col = c
            break
    if url_col is None:
        log.error(f"输入文件无商品链接列，现有列: {list(df_input.columns)}")
        return {"success": False, "error": "未找到商品链接列"}

    id_col = None
    for c in ["商品ID", "商品id", "item_id"]:
        if c in df_input.columns:
            id_col = c
            break

    all_urls = [_normalize_item_url(u) for u in df_input[url_col].tolist() if str(u).strip()]
    all_urls = list(dict.fromkeys(all_urls))
    log.info(f"输入文件 {len(df_input)} 行，去重后 {len(all_urls)} 个商品链接")

    # 预计算 URL 维度元信息，用于采样与海量策略
    shop_col = next((c for c in ["店铺名称", "掌柜名", "店铺", "shop_name"] if c in df_input.columns), None)
    pay_col = next((c for c in ["付款人数", "pay_count", "成交人数"] if c in df_input.columns), None)
    price_col = next((c for c in ["一口价", "现价", "价格", "price"] if c in df_input.columns), None)
    title_col = next((c for c in ["商品名称", "标题", "商品标题", "title"] if c in df_input.columns), None)

    row_meta_by_url = {}
    for _, row in df_input.iterrows():
        norm_url = _normalize_item_url(row.get(url_col, ""))
        if not norm_url or norm_url in row_meta_by_url:
            continue
        shop_name = str(row.get(shop_col, "")).strip() if shop_col else ""
        pay_count = _safe_int(row.get(pay_col, "")) if pay_col else 0
        spu_price = _safe_float(row.get(price_col, "")) if price_col else None
        row_meta_by_url[norm_url] = {
            "card_name": _extract_card_name_from_row(row),
            "shop_name": shop_name,
            "pay_count": pay_count,
            "spu_price": spu_price,
            "title": str(row.get(title_col, "")).strip() if title_col else "",
            "raw_price": str(row.get(price_col, "")).strip() if price_col else "",
        }

    listing_meta = []
    sku_rows_all = []
    card_price_proxy_rows = []
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    success_count = 0
    fail_count = 0
    skipped_sampling_count = 0  # 兼容历史摘要键，语义改为“候选但未进入 per_product_k”
    massive_shortcut_count = 0  # 历史路径已移除，固定保持 0
    consecutive_nav_errors = 0

    # 断点续跑时尽量承接已落盘结果，避免中断后“白干”
    if resume and os.path.exists(output_file):
        old_meta, old_rows, old_proxy = _load_existing_output(output_file, log)
        listing_meta.extend(old_meta)
        sku_rows_all.extend(old_rows)
        card_price_proxy_rows.extend(old_proxy)
        if old_meta or old_rows or old_proxy:
            log.info(
                f"已加载既有结果: listing_meta {len(old_meta)} 行, sku_rows {len(old_rows)} 行, card_price_proxy {len(old_proxy)} 行"
            )

    # ---------- open_url 第三层：product 驱动关联 + per_product_k ----------
    if not open_url_input_file:
        open_url_input_file = config.get("SKU_OPEN_URL", "open_url_input_file", fallback="").strip()
    targets, err = _load_open_url_targets(open_url_input_file, config, log)
    if err:
        return {"success": False, "error": err}

    db = MTGDatabase(config_file=config_file, logger=log)
    ok, msg = db.test_connection()
    if not ok:
        return {"success": False, "error": f"open_url 关联需要 DB 支持，但连接失败: {msg}"}
    product_feature_map = _build_product_feature_map(targets, db)

    urls_by_card = {}
    for url, meta in row_meta_by_url.items():
        card_name = str(meta.get("card_name", "") or "").strip() or "__UNKNOWN__"
        urls_by_card.setdefault(card_name, []).append((url, meta))

    candidate_by_product = {}
    candidate_products_by_url = {}
    product_total = len(targets)
    feature_miss = 0
    no_set_miss = 0

    for target in targets:
        pid = str(target.get("product_id", "")).strip()
        card_name = str(target.get("card_name", "")).strip()
        feature = product_feature_map.get(pid)
        if not feature:
            feature_miss += 1
            continue
        set_terms = feature.get("set_terms", [])
        if not set_terms:
            no_set_miss += 1
            continue

        rows = urls_by_card.get(card_name, [])
        cands = []
        for url, meta in rows:
            title = meta.get("title", "")
            hit_term = ""
            for term in set_terms:
                if _contains_term(title, term):
                    hit_term = term
                    break
            if require_set_match and not hit_term:
                continue

            collect_hit = _contains_collect_number(title, feature.get("collect_number", ""))
            pay = int(meta.get("pay_count", 0) or 0)
            shop_hit = _shop_match(
                meta.get("shop_name", ""), big_sellers, match_mode=big_seller_match_mode
            )
            score = (math.log(pay + 1.0) * score_pay_weight) + (
                score_big_seller_weight if shop_hit else 0.0
            ) + (score_collect_weight if collect_hit else 0.0)
            cand = {
                "url": url,
                "score": score,
                "collect_hit": collect_hit,
                "set_hit_term": hit_term,
                "pay_count": pay,
                "shop_hit": shop_hit,
            }
            cands.append(cand)
            candidate_products_by_url.setdefault(url, set()).add(pid)

        candidate_by_product[pid] = cands

    # 覆盖增益：一个 URL 可覆盖越多 product，越优先
    selected_urls_by_product = {}
    selected_products_by_url = {}
    products_with_candidates = 0
    total_candidates = 0
    for target in targets:
        pid = str(target.get("product_id", "")).strip()
        cands = candidate_by_product.get(pid, [])
        if not cands:
            continue
        products_with_candidates += 1
        for cand in cands:
            coverage = len(candidate_products_by_url.get(cand["url"], set()))
            cand["coverage_count"] = coverage
            cand["score_total"] = cand["score"] + (coverage * score_multi_product_weight)
        cands = sorted(
            cands,
            key=lambda x: (
                -x.get("score_total", 0),
                -x.get("collect_hit", False),
                -x.get("pay_count", 0),
            ),
        )
        total_candidates += len(cands)
        chosen = cands[: max(1, per_product_k)]
        selected_urls = [x["url"] for x in chosen]
        selected_urls_by_product[pid] = selected_urls
        for u in selected_urls:
            selected_products_by_url.setdefault(u, set()).add(pid)

    selected_urls_ordered = list(selected_products_by_url.keys())
    log.info(
        "open_url 候选构建完成: target_product=%s, feature_miss=%s, no_set_miss=%s, "
        "products_with_candidates=%s, unique_selected_urls=%s",
        product_total,
        feature_miss,
        no_set_miss,
        products_with_candidates,
        len(selected_urls_ordered),
    )

    # 记录候选但未入 per_product_k 的 URL（仅诊断，不会打开）
    skipped_urls = set(candidate_products_by_url.keys()) - set(selected_urls_ordered)
    for url in sorted(skipped_urls):
        related = sorted(selected_products_by_url.get(url, set()) | candidate_products_by_url.get(url, set()))
        meta0 = row_meta_by_url.get(url, {})
        listing_meta.append(
            {
                "source_file": os.path.basename(input_file),
                "run_id": run_id,
                "商品链接": url,
                "商品ID": _extract_item_id(url),
                "opened_at": datetime.now().isoformat(),
                "status": "skipped_sampling",
                "strategy": "open_url_per_product_k",
                "status_detail": f"per_product_k={per_product_k}",
                "page_title_snapshot": str(meta0.get("title", ""))[:120],
                "clipboard_preview": "",
                "related_product_ids": ",".join(related),
                "related_product_count": len(related),
            }
        )
        skipped_sampling_count += 1

    ckpt = SkuCheckpoint(checkpoint_dir)
    if resume:
        latest = ckpt.find_latest()
        if latest:
            ckpt.load(latest)
            log.info(
                f"从断点恢复: {latest}，已处理 {len(ckpt.data['processed'])}/{ckpt.data['total']}"
            )
        else:
            log.info("未找到断点，从头开始")
            ckpt.create(input_file, selected_urls_ordered)
    else:
        ckpt.create(input_file, selected_urls_ordered)

    urls_todo = ckpt.remaining(retry_failed=(resume and retry_failed_on_resume))
    log.info(f"待打开 URL: {len(urls_todo)}（目标 URL 总数: {len(selected_urls_ordered)}）")

    for seq, raw_url in enumerate(urls_todo, 1):
        url = _normalize_item_url(raw_url)
        item_id = _extract_item_id(url)
        opened_at = datetime.now().isoformat()
        related_pids = sorted(selected_products_by_url.get(url, set()))
        log.info(f"[{seq}/{len(urls_todo)}] 打开: {url}")

        meta = {
            "source_file": os.path.basename(input_file),
            "run_id": run_id,
            "商品链接": url,
            "商品ID": item_id,
            "opened_at": opened_at,
            "status": STATUS_UNKNOWN,
            "strategy": "",
            "status_detail": "",
            "page_title_snapshot": "",
            "clipboard_preview": "",
            "related_product_ids": ",".join(related_pids),
            "related_product_count": len(related_pids),
        }

        try:
            page.get(url)
            time.sleep(min(page_load_timeout, 5))
            if dismiss_on_item_page:
                closed = dismiss_overlays(
                    page,
                    log,
                    max_rounds=dismiss_rounds,
                    round_interval=dismiss_interval,
                )
                if closed:
                    log.info(f"商品页已尝试关闭弹窗/遮罩（累计点击 {closed} 次）")
        except Exception as e:
            meta["status"] = STATUS_NAV_ERROR
            meta["status_detail"] = str(e)[:200]
            listing_meta.append(meta)
            ckpt.mark_failed(url, STATUS_NAV_ERROR, str(e)[:200])
            fail_count += 1
            consecutive_nav_errors += 1
            log.warning(f"导航失败: {e}")
            if save_every > 0 and (success_count + fail_count) % save_every == 0:
                _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
            if consecutive_nav_errors >= nav_error_restart_threshold:
                _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
                return {
                    "success": False,
                    "error": "browser_disconnected",
                    "recoverable": True,
                    "total_urls": len(selected_urls_ordered),
                    "processed": success_count + fail_count,
                    "success_count": success_count,
                    "fail_count": fail_count,
                    "sku_rows": len(sku_rows_all),
                    "output_file": output_file,
                }
            _random_sleep(delay_min, delay_max)
            continue

        current_url = ""
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""
        if "login.taobao.com" in current_url.lower() or "havanaone/login" in current_url.lower():
            meta["status"] = STATUS_NEED_LOGIN
            meta["status_detail"] = f"跳转登录页: {current_url[:180]}"
            listing_meta.append(meta)
            ckpt.mark_failed(url, STATUS_NEED_LOGIN, meta["status_detail"])
            fail_count += 1
            consecutive_nav_errors = 0
            if save_every > 0 and (success_count + fail_count) % save_every == 0:
                _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
            log.warning(f"需要登录，已跳转登录页: {url}")
            log.warning("请在浏览器中登录后按回车继续...")
            input()
            continue

        try:
            meta["page_title_snapshot"] = (page.title or "")[:120]
        except Exception:
            pass

        anomaly = _detect_anomaly(page, selectors)
        if anomaly:
            meta["status"] = anomaly
            meta["status_detail"] = f"检测到 {anomaly}"
            listing_meta.append(meta)
            ckpt.mark_failed(url, anomaly)
            fail_count += 1
            consecutive_nav_errors = 0
            if save_every > 0 and (success_count + fail_count) % save_every == 0:
                _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
            log.warning(f"异常: {anomaly}，URL={url}")
            if anomaly in (STATUS_NEED_LOGIN, STATUS_CAPTCHA):
                log.warning("需要人工干预，暂停采集。处理完后按回车继续...")
                input()
            continue

        try:
            pyperclip.copy("")
        except Exception:
            pass

        ok, fail_reason = _open_sku_preview_export_and_copy(page, selectors, log)
        if not ok:
            # 回退尝试：历史面板逻辑（兼容旧版 UI）
            if _open_plugin_panel_if_needed(page, selectors, log):
                ok = True
            else:
                # corner case：无SKU时用SPU价格做兜底行
                row_meta = row_meta_by_url.get(url, {})
                fallback_price = row_meta.get("spu_price")
                if fallback_price is not None:
                    scraped_at = datetime.now().isoformat()
                    sku_rows_all.append({
                        "商品链接": url,
                        "商品ID": item_id,
                        "related_product_ids": ",".join(related_pids),
                        "sku_index": 1,
                        "sku_name": row_meta.get("title", "") or f"SPU-{item_id}",
                        "stock": 1,
                        "price": fallback_price,
                        "raw_row": "__fallback_no_sku__",
                        "scraped_at": scraped_at,
                    })
                    meta["status"] = "success_no_sku_fallback"
                    meta["strategy"] = "no_sku_fallback"
                    meta["status_detail"] = f"无SKU兜底: {fail_reason}"
                    listing_meta.append(meta)
                    ckpt.mark_done(url)
                    success_count += 1
                    consecutive_nav_errors = 0
                    if save_every > 0 and (success_count + fail_count) % save_every == 0:
                        _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
                    log.info(f"无SKU兜底成功: 商品ID={item_id}, price={fallback_price}")
                    _random_sleep(delay_min, delay_max)
                    continue

                cands = _collect_clickable_text_candidates(page)
                detail = fail_reason
                if cands:
                    detail += f"；可点击文案样本: {', '.join(cands[:12])}"
                meta["status"] = STATUS_PLUGIN_MISSING
                meta["status_detail"] = detail[:300]
                listing_meta.append(meta)
                ckpt.mark_failed(url, STATUS_PLUGIN_MISSING, meta["status_detail"])
                fail_count += 1
                consecutive_nav_errors = 0
                if save_every > 0 and (success_count + fail_count) % save_every == 0:
                    _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
                log.warning(f"未找到复制链路: {url} | {meta['status_detail']}")
                _random_sleep(delay_min, delay_max)
                continue

        time.sleep(copy_wait)

        preview, header, rows = _read_clipboard_sku(log)
        meta["clipboard_preview"] = (preview or "")[:200]

        if rows is None or len(rows) == 0:
            row_meta = row_meta_by_url.get(url, {})
            fallback_price = row_meta.get("spu_price")
            if fallback_price is not None:
                scraped_at = datetime.now().isoformat()
                sku_rows_all.append({
                    "商品链接": url,
                    "商品ID": item_id,
                    "related_product_ids": ",".join(related_pids),
                    "sku_index": 1,
                    "sku_name": row_meta.get("title", "") or f"SPU-{item_id}",
                    "stock": 1,
                    "price": fallback_price,
                    "raw_row": "__fallback_no_sku__",
                    "scraped_at": scraped_at,
                })
                meta["status"] = "success_no_sku_fallback"
                meta["strategy"] = "no_sku_fallback"
                meta["status_detail"] = "剪贴板空，按SPU兜底"
                listing_meta.append(meta)
                ckpt.mark_done(url)
                success_count += 1
                consecutive_nav_errors = 0
                if save_every > 0 and (success_count + fail_count) % save_every == 0:
                    _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
                log.info(f"剪贴板空但无SKU兜底成功: 商品ID={item_id}, price={fallback_price}")
                _random_sleep(delay_min, delay_max)
                continue

            meta["status"] = STATUS_CLIPBOARD_EMPTY
            meta["status_detail"] = "剪贴板无有效行"
            listing_meta.append(meta)
            ckpt.mark_failed(url, STATUS_CLIPBOARD_EMPTY)
            fail_count += 1
            consecutive_nav_errors = 0
            if save_every > 0 and (success_count + fail_count) % save_every == 0:
                _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
            log.warning(f"剪贴板空: {url}")
            _random_sleep(delay_min, delay_max)
            continue

        scraped_at = datetime.now().isoformat()
        name_col_candidates = ["SKU名称", "sku名称", "规格", "名称", "sku_name"]
        stock_col_candidates = ["库存", "stock", "数量"]
        price_col_candidates = ["价格", "现价", "price", "单价"]

        def _find_col(candidates, hdr):
            for c in candidates:
                if c in hdr:
                    return c
            return None

        sku_name_key = _find_col(name_col_candidates, header) if header else None
        stock_key = _find_col(stock_col_candidates, header) if header else None
        price_key = _find_col(price_col_candidates, header) if header else None

        for idx, row in enumerate(rows):
            sku_rows_all.append({
                "商品链接": url,
                "商品ID": item_id,
                "related_product_ids": ",".join(related_pids),
                "sku_index": idx + 1,
                "sku_name": row.get(sku_name_key, "") if sku_name_key else row.get(header[0] if header else "col_0", "") if header else "",
                "stock": row.get(stock_key, "") if stock_key else "",
                "price": row.get(price_key, "") if price_key else "",
                "raw_row": row.get("_raw_row", ""),
                "scraped_at": scraped_at,
            })

        meta["status"] = STATUS_SUCCESS
        meta["strategy"] = "open_url_sku"
        meta["status_detail"] = f"{len(rows)} SKU"
        listing_meta.append(meta)
        ckpt.mark_done(url)
        success_count += 1
        consecutive_nav_errors = 0
        if save_every > 0 and (success_count + fail_count) % save_every == 0:
            _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
        log.info(f"成功: {len(rows)} SKU，商品ID={item_id}")

        if seq % pause_every == 0 and seq < len(urls_todo):
            log.info(f"已处理 {seq} 条，暂停 {pause_duration}s")
            # 长休息前先做一次中间落盘，避免意外中断丢失内存结果
            _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, log)
            time.sleep(pause_duration)
        else:
            _random_sleep(delay_min, delay_max)

    ensure_dir(os.path.dirname(output_file))

    meta_df = pd.DataFrame(listing_meta)
    if not meta_df.empty and "商品链接" in meta_df.columns:
        meta_df = meta_df.drop_duplicates(subset=["商品链接"], keep="last")
    sku_df = pd.DataFrame(sku_rows_all)
    if not sku_df.empty:
        dedup_cols = [c for c in ["商品链接", "sku_index", "sku_name", "stock", "price", "raw_row"] if c in sku_df.columns]
        if dedup_cols:
            sku_df = sku_df.drop_duplicates(subset=dedup_cols, keep="last")
    proxy_df = pd.DataFrame(card_price_proxy_rows)
    if not proxy_df.empty:
        dedup_proxy = [c for c in ["card_name", "strategy"] if c in proxy_df.columns]
        if dedup_proxy:
            proxy_df = proxy_df.drop_duplicates(subset=dedup_proxy, keep="last")

    try:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            if not meta_df.empty:
                meta_df.to_excel(writer, sheet_name="listing_meta", index=False)
            if not sku_df.empty:
                sku_df.to_excel(writer, sheet_name="sku_rows", index=False)
            if not proxy_df.empty:
                proxy_df.to_excel(writer, sheet_name="card_price_proxy", index=False)
        log.info(f"结果已保存: {output_file}")
    except Exception as e:
        log.error(f"保存失败: {e}")
        return {"success": False, "error": str(e)}

    summary = {
        "success": True,
        "total_urls": len(selected_urls_ordered),
        "processed": success_count + fail_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "skipped_sampling_count": skipped_sampling_count,
        "massive_shortcut_count": massive_shortcut_count,
        "target_products": product_total,
        "products_with_candidates": products_with_candidates,
        "unique_opened_urls": len(selected_urls_ordered),
        "avg_candidates_per_product": (
            round(total_candidates / max(1, products_with_candidates), 3)
            if products_with_candidates > 0
            else 0.0
        ),
        "sku_rows": len(sku_rows_all),
        "card_price_proxy_rows": len(card_price_proxy_rows),
        "output_file": output_file,
    }
    log.info(
        f"采集完成: product目标 {product_total} / 有候选 {products_with_candidates} / "
        f"打开URL {len(selected_urls_ordered)} / 成功 {success_count} / 失败 {fail_count} / "
        f"候选跳过 {skipped_sampling_count} / SKU行 {len(sku_rows_all)}"
    )
    return summary


def _random_sleep(lo, hi):
    time.sleep(random.uniform(lo, hi))


def _write_interim_output(output_file, input_file, listing_meta, sku_rows_all, card_price_proxy_rows, logger):
    """中间落盘（最佳努力），不影响主流程。"""
    try:
        target = output_file
        if target is None:
            base, _ = os.path.splitext(input_file)
            target = f"{base}_sku_detail.xlsx"
        ensure_dir(os.path.dirname(target))
        meta_df = pd.DataFrame(listing_meta)
        if not meta_df.empty and "商品链接" in meta_df.columns:
            meta_df = meta_df.drop_duplicates(subset=["商品链接"], keep="last")
        sku_df = pd.DataFrame(sku_rows_all)
        if not sku_df.empty:
            dedup_cols = [c for c in ["商品链接", "sku_index", "sku_name", "stock", "price", "raw_row"] if c in sku_df.columns]
            if dedup_cols:
                sku_df = sku_df.drop_duplicates(subset=dedup_cols, keep="last")
        proxy_df = pd.DataFrame(card_price_proxy_rows)
        if not proxy_df.empty:
            dedup_proxy = [c for c in ["card_name", "strategy"] if c in proxy_df.columns]
            if dedup_proxy:
                proxy_df = proxy_df.drop_duplicates(subset=dedup_proxy, keep="last")
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            if not meta_df.empty:
                meta_df.to_excel(writer, sheet_name="listing_meta", index=False)
            if not sku_df.empty:
                sku_df.to_excel(writer, sheet_name="sku_rows", index=False)
            if not proxy_df.empty:
                proxy_df.to_excel(writer, sheet_name="card_price_proxy", index=False)
        logger.info(f"中间结果已更新: {target}")
    except Exception as e:
        logger.warning(f"中间落盘失败（忽略继续）: {e}")


def _load_existing_output(output_file, logger):
    """读取已存在的 sku_detail.xlsx（若有）并返回列表数据。"""
    metas = []
    rows = []
    proxies = []
    try:
        xls = pd.ExcelFile(output_file, engine="openpyxl")
        if "listing_meta" in xls.sheet_names:
            mdf = pd.read_excel(output_file, sheet_name="listing_meta", engine="openpyxl", dtype=str)
            if not mdf.empty:
                metas = mdf.fillna("").to_dict("records")
        if "sku_rows" in xls.sheet_names:
            rdf = pd.read_excel(output_file, sheet_name="sku_rows", engine="openpyxl", dtype=str)
            if not rdf.empty:
                rows = rdf.fillna("").to_dict("records")
        if "card_price_proxy" in xls.sheet_names:
            pdf = pd.read_excel(output_file, sheet_name="card_price_proxy", engine="openpyxl", dtype=str)
            if not pdf.empty:
                proxies = pdf.fillna("").to_dict("records")
    except Exception as e:
        logger.warning(f"读取既有输出失败（忽略继续）: {e}")
    return metas, rows, proxies
