"""
登录模块
负责淘宝网站的登录状态检查
使用真实Chrome配置文件，通常已保持登录状态
"""
import time


class TaobaoLogin:
    """淘宝登录管理类"""

    def __init__(self, browser_manager):
        """
        初始化登录管理器

        Args:
            browser_manager: 浏览器管理器实例
        """
        self.browser = browser_manager
        self.taobao_url = 'https://www.taobao.com'

    def _has_explicit_login_markers(self):
        """仅在明确看到登录页/登录表单时判定为未登录。"""
        try:
            current_url = (self.browser.page.url or '').lower()
        except Exception:
            current_url = ''

        if any(x in current_url for x in ['login.taobao.com', 'havanaone/login', 'passport', 'login_unusual']):
            return True

        try:
            return bool(self.browser.page.run_js('''
                return !!(
                    document.querySelector("input[name='TPL_username']") ||
                    document.querySelector("input[name='TPL_password']") ||
                    document.querySelector("input[name='fm-login-id']") ||
                    document.querySelector("input[type='password']") ||
                    document.querySelector(".login-content") ||
                    document.querySelector(".havana-login-container")
                );
            '''))
        except Exception:
            return False

    def check_login_status(self, quick=False):
        """
        检查当前是否已登录淘宝

        Args:
            quick: 快速模式，仅检查当前页面URL，不跳转

        Returns:
            bool: 是否已登录
        """
        if not self.browser.page:
            return False

        try:
            if quick:
                # 快速模式下，只在“明确进入登录页/出现登录表单”时判定掉线。
                # 插件弹层、搜索页、结果页未出现“我的淘宝”并不代表登录失效。
                return not self._has_explicit_login_markers()
            else:
                self.browser.navigate_to(self.taobao_url)
                time.sleep(3)
                if self._has_explicit_login_markers():
                    return False
                # 淘宝首页文案和 DOM 经常变化，且已登录状态下也未必稳定出现
                # “我的淘宝/购物车/我的订单”等固定文案。这里改成：
                # 只要没有明确落到登录页，就默认认为登录仍然有效。
                return True

        except Exception as e:
            print(f"检查登录状态时出错: {e}")
            return False

    def auto_login(self, force_manual=False):
        """
        检查登录状态，未登录则提示手动登录

        Args:
            force_manual: 未使用，保持接口兼容

        Returns:
            bool: 是否已登录
        """
        print("检查淘宝登录状态...")

        # 启动阶段和处理中都基于“当前页是否明确落到登录页/出现登录表单”判断，
        # 不再主动跳淘宝首页，以免被首页不稳定文案误判为掉线。
        if self.check_login_status(quick=True):
            print("已登录淘宝")
            return True

        # 未登录，提示用户手动操作
        print("未检测到登录状态，请在浏览器中手动登录淘宝")
        print("登录完成后按回车键继续...")
        input()

        # 重新检查
        if self.check_login_status(quick=True):
            print("登录成功")
            return True

        print("仍未检测到登录，请确认后重试")
        return False
