"""
搜索模块
负责店透视插件的搜索操作：打开对话框 → 输入关键词 → 开始分析 → 等待结果
"""
import os
import json
import re
import time
import logging
import random
import shutil
from urllib.parse import quote

from utils import get_project_root


class PluginOperator:
    """店透视插件操作类"""

    def __init__(self, page, selectors_file=None, logger=None, user_data_dir=None, extension_id=None):
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
        self.last_wait_diagnosis = {}
        self.user_data_dir = os.path.abspath(
            user_data_dir or os.path.join(get_project_root(), 'chrome_profile')
        )
        self.extension_id = (extension_id or 'ppgdlgnehnajbbngnohepfigdmjbdpfb').strip()
        self.extension_storage_dir = os.path.join(
            self.user_data_dir,
            'Default',
            'Local Extension Settings',
            self.extension_id,
        )

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
                'close_dialog': ['text:取消'],
                'clear_cache': ['text:清理缓存', 'text:清缓存'],
            }

        with open(selectors_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('plugin', {})

    def _find_element(self, selector_key, timeout=10, warn_missing=True):
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

        if warn_missing:
            self.logger.warning(f"未找到元素 [{selector_key}]，已尝试选择器: {selector_list}")
        return None

    def _find_plugin_trigger_fallback(self):
        """
        通过页面文本兜底查找插件入口。

        插件升级后，入口按钮文案可能变化，或按钮本身并不命中
        现有 selectors.json 中的精确文本，因此这里做一次宽松扫描。
        """
        keywords = ["市场分析", "数据分析", "店透视", "透视", "插件", "数据看板"]
        try:
            clicked_text = self.page.run_js(
                '''
                const keywords = arguments[0];
                const visible = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                };

                const nodes = Array.from(document.querySelectorAll(
                    'button, a, span, div, [role="button"], [class*="btn"], [class*="button"]'
                ));

                for (const el of nodes) {
                    const text = (el.innerText || el.textContent || '').trim();
                    if (!text || text.length > 30) continue;
                    if (!visible(el)) continue;
                    if (!keywords.some(k => text.includes(k))) continue;
                    try {
                        el.click();
                        return text;
                    } catch (e) {}
                }
                return '';
                ''',
                keywords,
            )
            if clicked_text:
                self.logger.info(f"通过兜底文本匹配点击了插件入口: {clicked_text}")
                return True
        except Exception as e:
            self.logger.debug(f"插件入口兜底查找失败: {e}")
        return False

    def _is_input_panel_visible(self):
        """当前是否处于插件关键词输入页。"""
        try:
            return bool(self.page.run_js('''
                var tas = document.querySelectorAll('textarea.el-textarea__inner');
                for (var i = 0; i < tas.length; i++) {
                    var r = tas[i].getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return true;
                }
                return false;
            '''))
        except Exception:
            return False

    def ensure_input_panel_ready(self):
        """
        确保当前处于“可输入关键词”的插件页。

        优先级：
        1) 已在输入页 -> 直接返回
        2) 可能在结果页 -> 尝试 close_result_and_back
        3) 仍不在输入页 -> 点击“市场分析”打开插件
        """
        if self._is_input_panel_visible():
            return True

        # 结果页尝试回输入页
        try:
            self.close_result_and_back()
        except Exception:
            pass
        if self._is_input_panel_visible():
            return True

        # 不在插件内则尝试打开
        if not self.open_plugin_dialog():
            return False
        if self._is_input_panel_visible():
            return True

        self.logger.error("未能进入插件关键词输入页")
        return False

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

        if self._is_input_panel_visible():
            self.logger.info("插件输入页已可见，跳过点击“市场分析”")
            return True

        deadline = time.time() + 15
        while time.time() < deadline:
            trigger = self._find_element('trigger_button', timeout=2, warn_missing=False)
            if trigger:
                try:
                    trigger.click()
                    time.sleep(2)
                    if self._is_input_panel_visible():
                        self.logger.info("插件对话框已打开")
                        return True
                except Exception as e:
                    self.logger.warning(f"点击触发按钮失败: {e}")

            if self._find_plugin_trigger_fallback():
                time.sleep(2)
                if self._is_input_panel_visible():
                    self.logger.info("插件对话框已通过兜底方式打开")
                    return True

            time.sleep(1)

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

    def _read_results_summary_text(self):
        """读取当前 results_summary 文案。"""
        try:
            summary = self._find_element('results_summary', timeout=1, warn_missing=False)
            if summary:
                return (summary.text or '').strip()
        except Exception:
            pass
        return ''

    def wait_for_results(self, timeout=120, previous_summary=''):
        """
        等待分析结果加载

        点击"开始分析"后，需要等待旧结果消失后新结果出现。

        Args:
            timeout: 最长等待时间（秒）

        Returns:
            bool: 是否成功加载结果
        """
        self.logger.info(f"等待分析结果加载（最长 {timeout} 秒）...")
        self.last_wait_diagnosis = {
            'timeout': False,
            'summary': '',
            'reason': None,
            'is_rate_limited': False,
        }

        start = time.time()
        result_found = False
        last_text = ''

        # 超时诊断信息：用于判断是否触发限流/风控/验证码等
        last_summary_text = ''
        last_reason = None

        def classify_reason(text):
            """
            基于 results_summary 文案的简易“疑似原因”识别。
            目标是让超时日志更可诊断，而不是保证 100% 准确。
            """
            if not text:
                return None
            t = text.replace(' ', '').replace('\n', '')

            # 1) 已成功加载：N/xxx - 特别关注 N=0
            m = re.search(r'已成功加载[：:]\s*(\d+)\s*/\s*(\d+)', text)
            if m:
                n = int(m.group(1))
                total = int(m.group(2))
                if n == 0:
                    # 常见场景：风控/限流后返回空结果
                    return f"疑似限流/风控：结果摘要显示 0/{total}"
                if total >= 1000 and n < 5:
                    return f"疑似限流/异常：结果极少（{n}/{total}）"

            # 2) 风控/验证码/过频等常见关键词
            for kw in [
                '过于频繁', '访问过于频繁', '操作过于频繁', '请求过于频繁',
                '系统繁忙', '请稍后', '稍后再试', '验证', '验证码',
                '风控', '拦截', '机器人', '异常', '失败',
            ]:
                if kw in t:
                    return f"疑似限流/风控：命中关键词“{kw}”"

            return None

        while time.time() - start < timeout:
            try:
                summary = self._find_element('results_summary', timeout=2)
                if summary:
                    text = summary.text.strip()
                    if text != last_summary_text:
                        last_summary_text = text
                        last_reason = classify_reason(text)
                    match = re.search(r'已成功加载[：:]\s*(\d+)/\d+', text)
                    if match and int(match.group(1)) > 0:
                        # 避免把上一个关键词的旧结果当成新结果
                        if previous_summary and text == previous_summary:
                            continue
                        # 检测到结果，记录文本
                        if not result_found:
                            # 首次检测到结果，等一下确认不是旧结果残留
                            time.sleep(3)
                            new_summary = self._find_element('results_summary', timeout=1)
                            if new_summary:
                                new_text = new_summary.text.strip()
                                if new_text != last_text or not result_found:
                                    self.logger.info(f"检测结果摘要: {new_text}")
                                    self.last_wait_diagnosis = {
                                        'timeout': False,
                                        'summary': new_text,
                                        'reason': None,
                                        'is_rate_limited': False,
                                    }
                                    result_found = True
                                    last_text = new_text
                                    return True
                        else:
                            self.logger.info(f"检测结果摘要: {text}")
                            self.last_wait_diagnosis = {
                                'timeout': False,
                                'summary': text,
                                'reason': None,
                                'is_rate_limited': False,
                            }
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
        final_reason = None
        if last_summary_text:
            # 超时诊断：把最后的 summary 文案与疑似原因打印出来
            self.logger.warning(f"超时前最后结果摘要: {last_summary_text}")
            final_reason = last_reason or classify_reason(last_summary_text)
            if final_reason:
                self.logger.warning(f"疑似原因识别: {final_reason}")
        else:
            self.logger.warning("超时前未能读取到 results_summary 文案（可能 DOM/弹层未加载）")
            final_reason = "未读到结果摘要（可能弹层异常/DOM变化/接口未返回）"

        self.last_wait_diagnosis = {
            'timeout': True,
            'summary': last_summary_text,
            'reason': final_reason,
            'is_rate_limited': bool(final_reason and ('限流' in final_reason or '风控' in final_reason)),
        }

        # 诊断截图（尽量不影响主流程，失败只记录日志）
        try:
            root = get_project_root()
            out_dir = os.path.join(root, "data", "logs", "screenshots")
            os.makedirs(out_dir, exist_ok=True)
            # keyword 在当前函数签名中没有；使用超时标签即可
            path = os.path.join(out_dir, f"timeout_results_{int(time.time())}.png")
            self.page.get_screenshot(path=path)
            self.logger.info(f"超时截图已保存: {path}")
        except Exception as e:
            self.logger.debug(f"超时截图失败: {e}")
        return False

    def get_last_wait_diagnosis(self):
        """返回最近一次 wait_for_results 的诊断信息。"""
        return dict(self.last_wait_diagnosis or {})

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

    def clear_plugin_cache_storage(self):
        """
        广义清理扩展与淘宝站点相关缓存。

        目标优先包含：
        - 扩展 Local/Sync Extension Settings
        - 扩展 Storage/ext 与 DNR 规则缓存
        - 淘宝站点 IndexedDB
        - 当前专用 profile 的 Local Storage / Session Storage

        这里采用“专用自动化 profile”思路，宁可清得宽一点，也避免残留状态
        导致店透视持续返回 0/0。
        """
        base = os.path.join(self.user_data_dir, 'Default')
        targets = [
            os.path.join(base, 'Local Extension Settings', self.extension_id),
            os.path.join(base, 'Sync Extension Settings', self.extension_id),
            os.path.join(base, 'Storage', 'ext', self.extension_id),
            os.path.join(base, 'DNR Extension Rules', self.extension_id),
            os.path.join(base, 'Extension Rules', self.extension_id),
            os.path.join(base, 'IndexedDB', 'https_s.taobao.com_0.indexeddb.blob'),
            os.path.join(base, 'IndexedDB', 'https_s.taobao.com_0.indexeddb.leveldb'),
            os.path.join(base, 'IndexedDB', 'https_www.taobao.com_0.indexeddb.blob'),
            os.path.join(base, 'IndexedDB', 'https_www.taobao.com_0.indexeddb.leveldb'),
            os.path.join(base, 'Local Storage', 'leveldb'),
            os.path.join(base, 'Session Storage'),
        ]

        removed_any = False
        cleared_targets = []
        failed = []

        for target in targets:
            if not os.path.exists(target):
                continue
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)
                removed_any = True
                cleared_targets.append(target)
            except Exception as e:
                failed.append(f"{target}: {e}")

        if removed_any:
            self.logger.info("已尝试广义清理扩展/站点缓存目录: " + " | ".join(cleared_targets[:8]))
        if failed:
            self.logger.warning("广义缓存清理存在未清理项: " + " | ".join(failed[:8]))
        return removed_any and not failed

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

        # Step 2: 确保处于插件输入页（按状态判断，不盲点）
        if not self.ensure_input_panel_ready():
            return False

        # Step 3: 输入关键词
        if not self.input_keyword(keyword):
            return False

        # Step 4: 点击开始分析
        prev_summary = self._read_results_summary_text()
        if not self.start_analysis():
            return False

        # Step 5: 等待结果
        if not self.wait_for_results(timeout=analysis_timeout, previous_summary=prev_summary):
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

        # Step 1: 先尽量退出旧结果页，避免直接复用上一次结果态
        self.close_result_and_back()
        # 再按状态确保在输入页（可能当前在结果页或已退到搜索页）
        if not self.ensure_input_panel_ready():
            return False

        # Step 2: 输入新关键词（会先清空）
        if not self.input_keyword(keyword):
            return False

        # 给插件一点稳定时间，避免刚输入完就立刻点击分析
        time.sleep(random.uniform(1.0, 2.2))

        # Step 3: 点击开始分析
        prev_summary = self._read_results_summary_text()
        if not self.start_analysis():
            return False

        # Step 4: 等待结果
        if not self.wait_for_results(timeout=analysis_timeout, previous_summary=prev_summary):
            return False

        self.logger.info(f"========== 分析完成: {keyword} ==========")
        return True

    def close_dialog(self):
        """
        关闭插件对话框，为下一个关键词做准备

        Returns:
            bool: 是否成功关闭
        """
        close_btn = self._find_element('close_dialog', timeout=3, warn_missing=False)
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
