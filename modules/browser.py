"""
浏览器管理模块
负责浏览器的初始化、配置和会话管理
使用 DrissionPage 4.x 的 ChromiumPage + 项目专用Chrome配置目录
"""
import os
import socket
import time
import subprocess
import platform
import psutil
from DrissionPage import ChromiumPage, ChromiumOptions


def _pick_free_port():
    """为本机 Chrome 调试口选一个当前空闲端口（勿用 0，DrissionPage 无法对 :0 做 test_connect）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BrowserManager:
    """浏览器管理类"""

    def __init__(self, download_dir='data/downloads', user_data_dir=None):
        self.page = None
        self.local_port = None
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 默认用项目内 chrome_profile；也可在 settings.ini [BROWSER] user_data_dir 指向已有插件的目录
        if user_data_dir and str(user_data_dir).strip():
            self.user_data_dir = os.path.abspath(
                os.path.expanduser(str(user_data_dir).strip())
            )
        else:
            self.user_data_dir = os.path.join(self.project_root, 'chrome_profile')
        abs_download_dir = os.path.join(self.project_root, download_dir)
        os.makedirs(abs_download_dir, exist_ok=True)
        self.download_dir = abs_download_dir

    def init_browser(self):
        """
        初始化浏览器

        使用项目内 chrome_profile/，或 settings.ini 中配置的 user_data_dir。
        注意：若你平时手动打开的是「系统默认 Chrome 用户数据」而不是本项目的
        chrome_profile，两边插件与登录态互不共享，需把店透视装到当前使用的目录，
        或在配置里把 user_data_dir 指到已有插件的目录（勿与正在手动打开的 Chrome
        同时占用同一目录）。Chrome 146+ 对系统默认配置目录的远程调试有限制。
        """
        os.makedirs(self.user_data_dir, exist_ok=True)

        co = ChromiumOptions()
        co.set_user_data_path(self.user_data_dir)
        # DrissionPage 全局 configs.ini 可能残留旧调试端口；set_user_data_path 会关掉 auto_port 且不清 address。
        # 显式绑定空闲端口（不能用 0：connect_browser 会对该端口做 HTTP 探测）。
        self.local_port = _pick_free_port()
        co.set_local_port(self.local_port)
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

    def _kill_chrome_using_profile(self):
        """
        结束命令行中带本机 chrome_profile 路径的 chrome.exe，避免误杀用户其它 Chrome。
        """
        path = os.path.normcase(os.path.abspath(self.user_data_dir))
        killed = False

        # 先用 psutil 在当前用户上下文里精确匹配，避免部分环境下 CIM / WMI 权限不足。
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = (proc.info.get('name') or '').lower()
                if name != 'chrome.exe':
                    continue
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                cmdline_norm = os.path.normcase(cmdline)
                if path not in cmdline_norm:
                    if self.local_port and f'--remote-debugging-port={self.local_port}' in cmdline_norm:
                        pass
                    else:
                        continue
                proc.kill()
                killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if platform.system().lower() != 'windows':
            return killed

        # PowerShell：按 user-data-dir 路径匹配进程命令行
        safe = path.replace("'", "''")
        ps_cmd = (
            f"$p = [regex]::Escape('{safe}'); "
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Where-Object { $_.CommandLine -and ($_.CommandLine -match $p) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                [
                    'powershell',
                    '-NoProfile',
                    '-NonInteractive',
                    '-Command',
                    ps_cmd,
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except Exception:
            pass
        return killed

    def close(self):
        """
        先 CDP 正常退出，再按 profile 路径清理残留 chrome，避免锁文件/端口占用。
        若环境变量 TAOBAO_AUTOMATION_KILL_ALL_CHROME=1，则额外 taskkill 全部 chrome.exe（旧行为）。
        """
        page = self.page
        self.page = None
        if page:
            try:
                page.quit(timeout=10, force=True)
            except Exception:
                pass
        time.sleep(0.6)
        self._kill_chrome_using_profile()
        time.sleep(0.3)
        if os.environ.get('TAOBAO_AUTOMATION_KILL_ALL_CHROME', '').strip() in ('1', 'true', 'yes'):
            try:
                subprocess.run(
                    ['taskkill', '/F', '/IM', 'chrome.exe'],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except Exception:
                pass
        print("浏览器已关闭")

    def __enter__(self):
        # __enter__ 抛错时 Python 不会调用 __exit__，必须在这里做清理，否则会残留 Chrome/占端口
        try:
            self.init_browser()
            return self
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
