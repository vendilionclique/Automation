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

        # 等待textarea可见 + 用JS原生setter写入值（兼容Vue响应式）
        for attempt in range(30):
            result = self.page.run_js('''
                var tas = document.querySelectorAll('textarea.el-textarea__inner');
                var ta = null;
                for (var i = 0; i < tas.length; i++) {
                    var rect = tas[i].getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        ta = tas[i];
                        break;
                    }
                }
                if (!ta) return 'not_visible';

                var nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(ta, arguments[0]);
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
                ta.dispatchEvent(new Event('compositionend', {bubbles: true}));
                return ta.value;
            ''', keyword)

            if result == keyword:
                self.logger.info(f"关键词输入成功: {keyword}")
                return True
            elif result in ('not_found', 'not_visible'):
                time.sleep(0.5)
                continue
            else:
                self.logger.warning(f"textarea值不匹配: '{result}'，重试...")
                time.sleep(0.5)

        # 最后一次尝试用DrissionPage键盘输入作为降级
        try:
            ta = self.page.ele('css:textarea.el-textarea__inner', timeout=2)
            if ta:
                ta.click()
                time.sleep(0.2)
                ta.input(keyword)
                time.sleep(0.5)
                actual = self.page.run_js(
                    'return document.querySelector("textarea.el-textarea__inner").value;')
                if actual == keyword:
                    self.logger.info(f"关键词输入成功(降级): {keyword}")
                    return True
        except Exception:
            pass

        self.logger.error("关键词输入失败")
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

        点击"开始分析"后，需要等待旧结果消失后新结果出现。

        Args:
            timeout: 最长等待时间（秒）

        Returns:
            bool: 是否成功加载结果
        """
        self.logger.info(f"等待分析结果加载（最长 {timeout} 秒）...")

        start = time.time()
        result_found = False
        last_text = ''

        while time.time() - start < timeout:
            try:
                summary = self._find_element('results_summary', timeout=2)
                if summary:
                    text = summary.text.strip()
                    match = re.search(r'已成功加载[：:]\s*(\d+)/\d+', text)
                    if match and int(match.group(1)) > 0:
                        # 检测到结果，记录文本
                        if not result_found:
                            # 首次检测到结果，等一下确认不是旧结果残留
                            time.sleep(3)
                            new_summary = self._find_element('results_summary', timeout=1)
                            if new_summary:
                                new_text = new_summary.text.strip()
                                if new_text != last_text or not result_found:
                                    self.logger.info(f"检测结果摘要: {new_text}")
                                    result_found = True
                                    last_text = new_text
                                    return True
                        else:
                            self.logger.info(f"检测结果摘要: {text}")
                            return True
                    else:
                        # 结果文本变化或显示0条，说明正在分析中
                        if text != last_text:
                            self.logger.debug(f"结果变化: {text}")
                            last_text = text
                            result_found = False
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

    def close_result_and_back(self):
        """
        关闭分析结果页，回到插件的关键词输入页
        点击对话框外的遮罩层关闭结果页

        Returns:
            bool: 是否成功回到输入页
        """
        try:
            result = self.page.run_js('''
                // 找到z-index最高的可见wrapper（遮罩层），点击关闭对话框
                var wrappers = document.querySelectorAll('.el-dialog__wrapper');
                var best = null;
                var bestZ = -1;
                for (var w of wrappers) {
                    var style = window.getComputedStyle(w);
                    if (style.display === 'none' || style.visibility === 'hidden') continue;
                    var z = parseInt(style.zIndex) || 0;
                    if (z > bestZ) { bestZ = z; best = w; }
                }
                if (best) {
                    // 点击遮罩层的空白区域（非对话框内容区）
                    best.click();
                    return 'clicked overlay z=' + bestZ;
                }
                return 'not_found';
            ''')
            if result and result != 'not_found':
                self.logger.info(f"已关闭结果页 ({result})")
            else:
                self.logger.warning(f"未找到遮罩层: {result}")
                return False
        except Exception as e:
            self.logger.error(f"关闭结果页失败: {e}")
            return False

        # 等待textarea重新可见，确认回到输入页
        for i in range(20):
            time.sleep(0.5)
            visible = self.page.run_js('''
                var tas = document.querySelectorAll('textarea.el-textarea__inner');
                for (var i = 0; i < tas.length; i++) {
                    var r = tas[i].getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return true;
                }
                return false;
            ''')
            if visible:
                self.logger.info("已回到输入页")
                return True

        self.logger.warning("等待回到输入页超时")
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

    def run_keyword_in_plugin(self, keyword, analysis_timeout=120):
        """
        在插件内执行下一个关键词的分析（不导航淘宝页面）

        用于批量模式：第一个关键词用 run_keyword_analysis 打开插件，
        后续关键词用此方法在插件内循环。

        流程：关闭结果页 → 清空输入 → 输入新关键词 → 分析 → 等待结果

        Args:
            keyword: 搜索关键词
            analysis_timeout: 分析结果等待超时（秒）

        Returns:
            bool: 是否成功完成分析
        """
        self.logger.info(f"========== 开始分析(插件内): {keyword} ==========")

        # Step 1: 关闭结果页，回到输入页
        if not self.close_result_and_back():
            self.logger.warning("关闭结果页失败，尝试继续")

        # Step 2: 输入新关键词（会先清空）
        if not self.input_keyword(keyword):
            return False

        # Step 3: 点击开始分析
        if not self.start_analysis():
            return False

        # Step 4: 等待结果
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
