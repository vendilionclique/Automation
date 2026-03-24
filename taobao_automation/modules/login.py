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
                # 快速检查：看当前URL是否跳转到了登录页
                current_url = self.browser.page.url
                if 'login.taobao.com' in current_url or 'login' in current_url:
                    return False
                # 检查页面中是否有登录指示元素
                page_source = self.browser.page.html
                return any(ind in page_source for ind in ['我的淘宝', '购物车'])
            else:
                self.browser.navigate_to(self.taobao_url)
                time.sleep(3)
                page_source = self.browser.page.html
                logged_in_indicators = ['我的淘宝', '购物车', '我的订单']
                for indicator in logged_in_indicators:
                    if indicator in page_source:
                        return True
                return False

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

        if self.check_login_status():
            print("已登录淘宝")
            return True

        # 未登录，提示用户手动操作
        print("未检测到登录状态，请在浏览器中手动登录淘宝")
        print("登录完成后按回车键继续...")
        input()

        # 重新检查
        if self.check_login_status():
            print("登录成功")
            return True

        print("仍未检测到登录，请确认后重试")
        return False
