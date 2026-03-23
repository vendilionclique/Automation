"""
搜索模块
负责店透视插件的搜索操作：打开对话框 → 输入关键词 → 开始分析 → 等待结果
"""
import os
import json
import re
import time
import logging
from urllib.parse import quote


class PluginOperator:
    """店透视插件操作类"""

    def __init__(self, page, selectors_file=None, logger=None):
        """
        初始化插件操作器

        Args:
            page: DrissionPage的ChromiumPage实例
            selectors_file: 选择器配置文件路径
            logger: 日志记录器
        """
        self.page = page
        self.logger = logger or logging.getLogger(__name__)
        self.selectors = self._load_selectors(selectors_file)
        self.taobao_search_url = 'https://s.taobao.com/search'

    def _load_selectors(self, selectors_file):
        """加载选择器配置"""
        if not selectors_file or not os.path.exists(selectors_file):
            self.logger.warning(f"选择器配置文件不存在: {selectors_file}，使用默认选择器")
            return {
                'trigger_button': ['text:市场分析'],
                'search_input': ['text:搜索内容'],
                'start_analysis': ['text:开始分析'],
                'results_summary': ['text:已成功加载'],
                'export_button': ['text:导出表格'],
                'close_dialog': ['text:取消']
            }

        with open(selectors_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('plugin', {})

    def _find_element(self, selector_key, timeout=10):
        """
        尝试多个选择器查找元素

        Args:
            selector_key: 选择器键名
            timeout: 每个选择器的超时时间（秒）

        Returns:
            找到的元素，或None
        """
        selector_list = self.selectors.get(selector_key, [])
        for selector in selector_list:
            try:
                el = self.page.ele(selector, timeout=timeout)
                if el:
                    self.logger.debug(f"找到元素 [{selector_key}]: {selector}")
                    return el
            except Exception:
                continue

        self.logger.warning(f"未找到元素 [{selector_key}]，已尝试选择器: {selector_list}")
        return None

    def navigate_to_search(self, keyword):
        """
        导航到淘宝搜索页

        Args:
            keyword: 搜索关键词

        Returns:
            bool: 是否成功
        """
        encoded = quote(keyword)
        url = f'{self.taobao_search_url}?q={encoded}'
        self.logger.info(f"导航到淘宝搜索: {keyword}")

        try:
            self.page.get(url)
            time.sleep(3)
            return True
        except Exception as e:
            self.logger.error(f"导航失败: {e}")
            return False

    def open_plugin_dialog(self):
        """
        打开店透视插件的"市场分析"对话框

        Returns:
            bool: 是否成功打开
        """
        self.logger.info("尝试打开店透视插件对话框...")

        trigger = self._find_element('trigger_button', timeout=5)
        if trigger:
            try:
                trigger.click()
                time.sleep(2)
                self.logger.info("插件对话框已打开")
                return True
            except Exception as e:
                self.logger.warning(f"点击触发按钮失败: {e}")

        self.logger.error("无法打开插件对话框，请确认插件已安装并激活")
        return False

    def input_keyword(self, keyword):
        """
        在插件的搜索框中输入关键词

        Args:
            keyword: 搜索关键词

        Returns:
            bool: 是否成功输入
        """
        self.logger.info(f"输入关键词: {keyword}")

        search_input = self._find_element('search_input', timeout=10)
        if not search_input:
            self.logger.error("未找到搜索输入框")
            return False

        try:
            search_input.clear()
            time.sleep(0.5)
            search_input.input(keyword)
            time.sleep(1)
            self.logger.info(f"关键词输入成功: {keyword}")
            return True
        except Exception as e:
            self.logger.error(f"输入关键词失败: {e}")
            return False

    def start_analysis(self):
        """
        点击"开始分析"按钮

        Returns:
            bool: 是否成功点击
        """
        self.logger.info("点击\"开始分析\"按钮...")

        btn = self._find_element('start_analysis', timeout=10)
        if not btn:
            self.logger.error("未找到\"开始分析\"按钮")
            return False

        try:
            btn.click()
            self.logger.info("\"开始分析\"已点击")
            return True
        except Exception as e:
            self.logger.error(f"点击\"开始分析\"失败: {e}")
            return False

    def wait_for_results(self, timeout=120):
        """
        等待分析结果加载

        点击"开始分析"后，旧的"已成功加载"文本可能仍可见。
        本方法等待直到出现有效的非零结果。

        Args:
            timeout: 最长等待时间（秒）

        Returns:
            bool: 是否成功加载结果
        """
        self.logger.info(f"等待分析结果加载（最长 {timeout} 秒）...")

        # 先等一下，让旧结果被清除
        time.sleep(2)

        start = time.time()
        while time.time() - start < timeout:
            try:
                summary = self._find_element('results_summary', timeout=2)
                if summary:
                    text = summary.text
                    # 检查是否有实际数据（匹配 "已成功加载：数字/数字条数据"）
                    match = re.search(r'已成功加载[：:]\s*(\d+)/\d+', text)
                    if match and int(match.group(1)) > 0:
                        self.logger.info(f"检测结果摘要: {text}")
                        return True
                    else:
                        # 0/0 或格式不匹配，说明是旧结果，继续等待
                        self.logger.debug(f"检测到旧结果或空结果: {text}，继续等待...")
            except Exception:
                pass

            time.sleep(3)

        self.logger.warning(f"等待结果超时（{timeout}秒）")
        return False

    def run_keyword_analysis(self, keyword, analysis_timeout=120):
        """
        对单个关键词执行完整的插件分析流程

        Args:
            keyword: 搜索关键词（如"万智牌 中止"）
            analysis_timeout: 分析结果等待超时（秒）

        Returns:
            bool: 是否成功完成分析
        """
        self.logger.info(f"========== 开始分析: {keyword} ==========")

        # 先关闭可能残留的对话框
        self.close_dialog()
        time.sleep(1)

        # Step 1: 导航到淘宝搜索页
        if not self.navigate_to_search(keyword):
            return False

        # Step 2: 打开插件对话框
        if not self.open_plugin_dialog():
            return False

        # Step 3: 输入关键词
        if not self.input_keyword(keyword):
            return False

        # Step 4: 点击开始分析
        if not self.start_analysis():
            return False

        # Step 5: 等待结果
        if not self.wait_for_results(timeout=analysis_timeout):
            return False

        self.logger.info(f"========== 分析完成: {keyword} ==========")
        return True

    def close_dialog(self):
        """
        关闭插件对话框，为下一个关键词做准备

        Returns:
            bool: 是否成功关闭
        """
        close_btn = self._find_element('close_dialog', timeout=3)
        if close_btn:
            try:
                close_btn.click()
                time.sleep(1)
                return True
            except Exception:
                pass

        # 备选：按Escape键
        try:
            self.page.actions.key_down('Escape')
            time.sleep(1)
            return True
        except Exception:
            return False
