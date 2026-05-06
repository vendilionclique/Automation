"""
System-level visual automation driver.

This module deliberately avoids CDP, DOM, browser extensions, and network
inspection. It only launches/activates Chrome, types through the OS keyboard,
and captures screenshots through PyAutoGUI.
"""
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Optional, Tuple
from urllib.parse import quote


DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TAOBAO_HOME = "https://www.taobao.com"
TAOBAO_SEARCH = "https://s.taobao.com/search?q={keyword}"


@dataclass
class ChromeConfig:
    chrome_path: str = DEFAULT_CHROME_PATH
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = ""
    window_x: int = 0
    window_y: int = 0
    window_width: int = 1600
    window_height: int = 1000
    startup_wait: float = 4.0
    page_load_wait: float = 8.0
    search_mode: str = "url"

    def to_dict(self):
        return asdict(self)


class VisualDriver:
    def __init__(self, config: ChromeConfig):
        self.config = config

    def launch_chrome(self):
        args = [
            self.config.chrome_path,
            f"--window-position={self.config.window_x},{self.config.window_y}",
            f"--window-size={self.config.window_width},{self.config.window_height}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.config.chrome_user_data_dir:
            args.append(f"--user-data-dir={os.path.expanduser(self.config.chrome_user_data_dir)}")
        if self.config.chrome_profile_directory:
            args.append(f"--profile-directory={self.config.chrome_profile_directory}")
        args.append(TAOBAO_HOME)
        subprocess.Popen(args)
        time.sleep(self.config.startup_wait)

    def search_keyword(self, keyword: str):
        self._require_pyautogui()
        import pyautogui

        if self.config.search_mode == "home":
            pyautogui.hotkey("command", "l")
            time.sleep(0.2)
            self._paste_text(TAOBAO_HOME)
            pyautogui.press("enter")
            time.sleep(self.config.page_load_wait)
            pyautogui.hotkey("command", "l")
            time.sleep(0.2)
            self._paste_text(TAOBAO_SEARCH.format(keyword=quote(keyword)))
            pyautogui.press("enter")
        else:
            pyautogui.hotkey("command", "l")
            time.sleep(0.2)
            self._paste_text(TAOBAO_SEARCH.format(keyword=quote(keyword)))
            pyautogui.press("enter")
        time.sleep(self.config.page_load_wait)

    def capture_screen(self, path: str, region: Optional[Tuple[int, int, int, int]] = None):
        self._require_pyautogui()
        import pyautogui

        os.makedirs(os.path.dirname(path), exist_ok=True)
        image = pyautogui.screenshot(region=region)
        image.save(path)
        return path

    def _require_pyautogui(self):
        try:
            import pyautogui  # noqa: F401
        except ImportError as e:
            raise RuntimeError("pyautogui 未安装，请运行 pip install -r requirements.txt") from e

    def _paste_text(self, text: str):
        self._require_pyautogui()
        import pyautogui

        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("command", "v")
        except Exception:
            # ASCII fallback only; Chinese keywords require clipboard paste.
            pyautogui.write(text)


def chrome_config_from_settings(config) -> ChromeConfig:
    section = "VISUAL_CAPTURE"
    return ChromeConfig(
        chrome_path=config.get(section, "chrome_path", fallback=DEFAULT_CHROME_PATH),
        chrome_user_data_dir=config.get(section, "chrome_user_data_dir", fallback=""),
        chrome_profile_directory=config.get(section, "chrome_profile_directory", fallback=""),
        window_x=config.getint(section, "window_x", fallback=0),
        window_y=config.getint(section, "window_y", fallback=0),
        window_width=config.getint(section, "window_width", fallback=1600),
        window_height=config.getint(section, "window_height", fallback=1000),
        startup_wait=config.getfloat(section, "startup_wait", fallback=4.0),
        page_load_wait=config.getfloat(section, "page_load_wait", fallback=8.0),
        search_mode=config.get(section, "search_mode", fallback="url"),
    )
