"""
导出模块
从店透视插件的分析结果DOM中直接读取表格数据（替代文件下载）
支持分页加载以获取超过一页的结果
"""
import os
import json
import time
import logging
import pandas as pd
from datetime import datetime

# 店透视分析结果的固定列结构（表格没有独立表头行）
COLUMNS = [
    '#', '商品名称', '商品链接', '原价', '现价',
    '付款人数', '同款数', '类目', '掌柜名',
    '占位类型', '店铺名称', '店铺类型', '平台', '地址'
]


class PluginExporter:
    """插件导出类 — 从DOM读取表格数据"""

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

    def _read_table_from_dom(self):
        """
        从DOM中读取当前页的表格数据

        Returns:
            list: 行数据列表，每行是一个字典。失败返回None。
        """
        try:
            tables = self.page.eles('tag:table')
            if not tables:
                self.logger.warning("页面上未找到table元素")
                return None

            # 找到包含分析数据的表格（行数最多的那个）
            best_table = None
            best_rows = 0
            for table in tables:
                rows = table.eles('tag:tr')
                if len(rows) > best_rows:
                    best_rows = len(rows)
                    best_table = table

            if not best_table or best_rows < 1:
                self.logger.warning(f"未找到有效数据表格（最大行数: {best_rows}）")
                return None

            rows = best_table.eles('tag:tr')
            data_rows = []

            for row in rows:
                cells = row.eles('tag:td')
                if len(cells) < 3:
                    continue  # 跳过非数据行
                row_dict = {}
                for i, cell in enumerate(cells):
                    if i < len(COLUMNS):
                        row_dict[COLUMNS[i]] = cell.text.strip().replace('\n', ' ')
                # 只取有序号（#列是纯数字）的数据行
                if row_dict.get('#', '').isdigit():
                    data_rows.append(row_dict)

            self.logger.info(f"从DOM读取到 {len(data_rows)} 行数据")
            return data_rows

        except Exception as e:
            self.logger.error(f"读取DOM表格失败: {e}")
            return None

    def _click_next_page(self):
        """点击'加载下一页'，返回是否成功"""
        try:
            for sel in ['text:加载下一页', 'text:下一页']:
                btn = self.page.ele(sel, timeout=2)
                if btn:
                    btn.click()
                    self.logger.debug("已点击下一页")
                    time.sleep(2)
                    return True
        except Exception:
            pass
        return False

    def export_results(self, keyword, max_pages=2, page_interval=2):
        """
        从DOM读取分析结果并保存为Excel

        Args:
            keyword: 当前搜索关键词
            max_pages: 最多加载多少页
            page_interval: 翻页等待间隔（秒）

        Returns:
            dict: {success, total_rows, pages, export_file}
        """
        self.logger.info(f"从DOM导出结果: {keyword}")

        all_rows = []
        page_num = 0

        while page_num < max_pages:
            page_num += 1
            self.logger.info(f"读取第 {page_num} 页...")

            rows = self._read_table_from_dom()
            if not rows:
                if page_num == 1:
                    self.logger.error("第一页就没读到数据")
                    return {'success': False, 'error': '第一页无数据'}
                break

            all_rows.extend(rows)

            if page_num >= max_pages:
                self.logger.info(f"已达到最大页数 {max_pages}，停止")
                break

            if not self._click_next_page():
                self.logger.info("没有更多页面")
                break

            time.sleep(page_interval)

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
