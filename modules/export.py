"""
导出模块
优先通过插件的"复制表格"按钮从剪贴板读取数据（完整数据），
剪贴板失败时降级到DOM读取（仅可见行，可能不完整）
支持分页加载以获取多页结果
"""
import os
import io
import json
import time
import logging
import re
import pandas as pd
from datetime import datetime

# 店透视分析结果的列结构（剪贴板和DOM列名不同）
# 剪贴板: 商品名称, 商品ID, 商品链接, 原价, 现价, ...
# DOM:    #, 商品名称, 商品链接, 原价, 现价, ...
COLUMNS = ['#', '商品名称', '商品链接', '原价', '现价', '付款人数', '同款数', '类目', '掌柜名']


class PluginExporter:
    """插件导出类 — 剪贴板优先，DOM降级"""

    def __init__(self, page, download_dir, selectors_file=None, logger=None):
        self.page = page
        self.download_dir = download_dir
        self.logger = logger or logging.getLogger(__name__)
        self.selectors = self._load_selectors(selectors_file)

    def _load_selectors(self, selectors_file):
        if not selectors_file or not os.path.exists(selectors_file):
            return {}

        with open(selectors_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('plugin', {})

    def _click_copy_button(self):
        """点击'复制表格'按钮，返回是否成功"""
        for sel in ['text:复制表格', 'text:复制']:
            try:
                btn = self.page.ele(sel, timeout=2)
                if btn:
                    btn.click()
                    self.logger.info("已点击复制表格按钮")
                    return True
            except Exception:
                continue
        return False

    def _read_from_clipboard(self):
        """
        从剪贴板读取表格数据

        Returns:
            list: 行数据字典列表，失败返回None
        """
        import pyperclip

        try:
            clipboard_data = pyperclip.paste()
        except Exception as e:
            self.logger.warning(f"剪贴板读取失败: {e}")
            return None

        if not clipboard_data:
            self.logger.warning("剪贴板为空")
            return None

        # 调试：输出剪贴板前200字符和长度
        preview = clipboard_data[:200].replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        self.logger.info(f"剪贴板读取到 {len(clipboard_data)} 字符，前200字符: {preview}")

        if len(clipboard_data) < 10:
            self.logger.warning("剪贴板数据过短")
            return None

        # 尝试用pandas解析剪贴板内容（tab分隔的表格数据）
        try:
            df = pd.read_csv(io.StringIO(clipboard_data), sep='\t', header=None)
        except Exception as e:
            self.logger.warning(f"剪贴板内容无法解析为表格: {e}")
            return None

        if len(df) < 2:
            self.logger.warning(f"剪贴板解析行数不足: {len(df)}")
            return None

        # 用第一行作为表头，确定列名映射
        header = [str(v).strip() for v in df.iloc[0].tolist()]
        data_rows = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            if len(row) < 3:
                continue
            row_dict = {}
            for j in range(len(row)):
                col_name = header[j] if j < len(header) else f'col_{j}'
                row_dict[col_name] = str(row[j]).strip().replace('\n', ' ')
            # 数据行必须有商品名称
            if row_dict.get('商品名称', ''):
                data_rows.append(row_dict)

        if data_rows:
            self.logger.info(f"从剪贴板读取到 {len(data_rows)} 行数据")
            return data_rows

        return None

    def _read_table_from_dom(self):
        """
        从DOM中读取当前页的表格数据（降级方案，可能不完整）

        Returns:
            list: 行数据字典列表，失败返回None
        """
        try:
            tables = self.page.eles('tag:table')
            if not tables:
                return None

            best_table = None
            best_rows = 0
            for table in tables:
                rows = table.eles('tag:tr')
                if len(rows) > best_rows:
                    best_rows = len(rows)
                    best_table = table

            if not best_table or best_rows < 1:
                return None

            rows = best_table.eles('tag:tr')
            data_rows = []
            seen_nums = set()

            for row in rows:
                cells = row.eles('tag:td')
                if len(cells) < 3:
                    continue
                row_dict = {}
                for i, cell in enumerate(cells):
                    if i < len(COLUMNS):
                        row_dict[COLUMNS[i]] = cell.text.strip().replace('\n', ' ')
                num = row_dict.get('#', '')
                if num.isdigit() and num not in seen_nums:
                    seen_nums.add(num)
                    data_rows.append(row_dict)

            self.logger.info(f"从DOM读取到 {len(data_rows)} 行数据（降级）")
            return data_rows

        except Exception as e:
            self.logger.error(f"读取DOM表格失败: {e}")
            return None

    def _read_current_page(self, copy=False):
        """
        读取当前页数据

        Args:
            copy: 是否点击复制按钮从剪贴板读取。False时仅加载下一页不复制。

        Returns:
            list: 行数据字典列表，失败返回None
        """
        if copy:
            # 尝试剪贴板方案
            import pyperclip
            try:
                pyperclip.copy('')
            except Exception:
                pass

            if self._click_copy_button():
                time.sleep(1)
                rows = self._read_from_clipboard()
                # 小结果集可能只有 1 条，属于有效数据
                if rows and len(rows) >= 1:
                    return rows
                self.logger.info("剪贴板方案未获取有效数据，降级到DOM")

            return self._read_table_from_dom()
        return None

    def _click_next_page(self):
        """点击'加载下一页'，返回是否成功"""
        try:
            for sel in ['text:加载下一页', 'text:下一页']:
                btn = self.page.ele(sel, timeout=2)
                if btn:
                    btn.click()
                    self.logger.info("已点击加载下一页")
                    return True
        except Exception:
            pass
        return False

    def _estimate_loaded_rows(self):
        """估算当前已加载行数（用于判断翻页是否真正完成）。"""
        try:
            n = self.page.run_js('''
                var maxRows = 0;
                var tables = document.querySelectorAll('table');
                for (var i = 0; i < tables.length; i++) {
                    var rows = tables[i].querySelectorAll('tr').length;
                    if (rows > maxRows) maxRows = rows;
                }
                return maxRows;
            ''')
            return int(n or 0)
        except Exception:
            return 0

    def _get_loaded_progress(self):
        """
        读取插件“已成功加载：x/y”进度。

        Returns:
            tuple[int|None, int|None]: (x, y)，读取失败返回 (None, None)
        """
        patterns = [r'已成功加载[：:]\s*(\d+)\s*/\s*(\d+)']

        # 先按配置选择器查
        for sel in self.selectors.get('results_summary', ['text:已成功加载']):
            try:
                el = self.page.ele(sel, timeout=1.5)
                if not el:
                    continue
                text = (el.text or '').strip()
                for p in patterns:
                    m = re.search(p, text)
                    if m:
                        return int(m.group(1)), int(m.group(2))
            except Exception:
                continue

        # 回退：全页面抓文本（避免 selector 轻微漂移）
        try:
            text = self.page.run_js('return document.body ? document.body.innerText : "";') or ''
            for p in patterns:
                m = re.search(p, text)
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            pass

        return None, None

    def _wait_next_page_loaded(self, before_loaded, before_total, before_rows, timeout_seconds=4):
        """
        等待翻页完成。
        优先检测“已成功加载 x/y”中的 x 是否增长；若拿不到该指标，再回退行数估算。
        """
        start = time.time()
        last_progress_log = 0.0
        while time.time() - start < timeout_seconds:
            loaded, total = self._get_loaded_progress()

            if loaded is not None:
                # x 增长则认为翻页已生效
                if before_loaded is None or loaded > before_loaded:
                    self.logger.info(
                        f"翻页加载完成：已成功加载 {before_loaded if before_loaded is not None else '?'}"
                        f"/{before_total if before_total is not None else '?'} -> {loaded}/{total}"
                    )
                    return True
                # 适度打印进度，方便排查“卡住不涨”
                now = time.time()
                if now - last_progress_log >= 2.0:
                    self.logger.debug(f"翻页等待中：已成功加载 {loaded}/{total}")
                    last_progress_log = now

            current = self._estimate_loaded_rows()
            if current > before_rows:
                self.logger.info(f"翻页加载完成：行数 {before_rows} -> {current}")
                return True
            time.sleep(0.6)

        loaded, total = self._get_loaded_progress()
        if loaded is not None:
            self.logger.warning(
                f"翻页等待超时（{timeout_seconds}s），已成功加载仍为 {loaded}/{total}"
            )
        else:
            self.logger.warning(
                f"翻页等待超时（{timeout_seconds}s），行数仍为 {self._estimate_loaded_rows()}"
            )
        return False

    def export_results(self, keyword, max_pages=3, page_interval=2, next_page_timeout=4, copy_wait=1.6):
        """
        读取分析结果并保存为Excel
        先加载所有页，最后一次性复制获取全部数据

        Args:
            keyword: 当前搜索关键词
            max_pages: 最多加载多少页
            page_interval: 翻页等待间隔（秒）

        Returns:
            dict: {success, total_rows, pages, export_file}
        """
        self.logger.info(f"导出结果: {keyword}")

        page_num = 0

        while page_num < max_pages:
            page_num += 1
            if page_num < max_pages:
                self.logger.info(f"加载第 {page_num} 页...")
                before_loaded, before_total = self._get_loaded_progress()
                # 店透视特性：x/50 通常就是小结果单页，继续翻页大概率无意义
                if (
                    before_total is not None
                    and before_loaded is not None
                    and before_total <= 50
                    and before_loaded <= before_total
                ):
                    self.logger.info(
                        f"检测到小结果集（已成功加载 {before_loaded}/{before_total}），"
                        "跳过后续翻页，直接复制当前结果"
                    )
                    page_num -= 1
                    break
                before_rows = self._estimate_loaded_rows()
                if not self._click_next_page():
                    self.logger.info(f"第 {page_num} 页后没有更多页面")
                    break
                wait_seconds = max(next_page_timeout, page_interval)
                loaded_ok = self._wait_next_page_loaded(
                    before_loaded=before_loaded,
                    before_total=before_total,
                    before_rows=before_rows,
                    timeout_seconds=wait_seconds,
                )
                # 一次翻页未成功，说明暂无更多页或插件状态异常，直接停止后续翻页尝试
                if not loaded_ok:
                    self.logger.warning(f"第 {page_num} 页翻页未确认成功，停止后续翻页")
                    break
                # 再补一个短暂停顿，降低“刚加载就复制”的抖动
                time.sleep(max(0.8, page_interval))
            else:
                self.logger.info(f"最后一页（第 {page_num} 页）加载完毕")

        # 所有页加载完后，一次性复制
        self.logger.info("一次性复制全部已加载数据...")
        time.sleep(max(1.0, copy_wait))
        rows = self._read_current_page(copy=True)
        if not rows:
            self.logger.error("未能获取数据")
            return {'success': False, 'error': '复制失败'}

        seen_ids = set()
        all_rows = []
        for row in rows:
            item_id = row.get('商品ID', '').strip("'").strip()
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                all_rows.append(row)

        self.logger.info(f"共 {len(all_rows)} 行（去重后）")

        if not all_rows:
            return {'success': False, 'error': '未读取到任何数据'}

        os.makedirs(self.download_dir, exist_ok=True)
        safe_name = keyword.replace(' ', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(self.download_dir, f"{safe_name}_{timestamp}.xlsx")

        df = pd.DataFrame(all_rows)
        df.to_excel(output_file, index=False, engine='openpyxl')

        self.logger.info(f"已保存 {len(all_rows)} 行到 {output_file}")
        return {
            'success': True,
            'total_rows': len(all_rows),
            'pages': page_num,
            'export_file': output_file
        }
