"""
浏览器管理模块
负责浏览器的初始化、配置和会话管理
使用 DrissionPage 4.x 的 ChromiumPage + 项目专用Chrome配置目录
"""
import os
from DrissionPage import ChromiumPage, ChromiumOptions


class BrowserManager:
    """浏览器管理类"""

    def __init__(self, download_dir='data/downloads'):
        self.page = None
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.user_data_dir = os.path.join(self.project_root, 'chrome_profile')
        abs_download_dir = os.path.join(self.project_root, download_dir)
        os.makedirs(abs_download_dir, exist_ok=True)
        self.download_dir = abs_download_dir

    def init_browser(self):
        """
        初始化浏览器

        使用项目专用Chrome配置目录（chrome_profile/）。
        Chrome 146+ 禁止在默认用户数据目录上启用远程调试，
        因此必须使用非默认目录。首次使用需手动登录淘宝并安装店透视插件。
        """
        os.makedirs(self.user_data_dir, exist_ok=True)

        co = ChromiumOptions()
        co.set_user_data_path(self.user_data_dir)
        co.set_argument('--disable-popup-blocking')
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')
        co.set_download_path(self.download_dir)

        try:
            self.page = ChromiumPage(co)
            print(f"浏览器启动成功 (配置目录: {self.user_data_dir})")
            return self.page
        except Exception as e:
            print(f"浏览器启动失败: {e}")
            raise

    def navigate_to(self, url):
        """导航到指定URL"""
        if self.page:
            self.page.get(url)
            return True
        return False

    def close(self):
        """关闭浏览器"""
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None
            print("浏览器已关闭")

    def __enter__(self):
        self.init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
