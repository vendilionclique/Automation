"""
工具函数模块
提供各种辅助功能和工具函数
"""
import os
import sys
import time
import logging
from datetime import datetime
from functools import wraps
import configparser


def setup_logging(log_file=None, level=logging.INFO):
    """
    设置日志记录

    Args:
        log_file: 日志文件路径，如果为None则不写入文件
        level: 日志级别

    Returns:
        logging.Logger: 日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger('taobao_automation')
    logger.setLevel(level)

    # 清除已有的处理器
    logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def retry(max_attempts=3, delay=1, backoff=2, exceptions=(Exception,)):
    """
    重试装饰器

    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数
        exceptions: 需要重试的异常类型

    Returns:
        decorator: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        print(f"操作失败，{current_delay}秒后重试 ({attempt + 1}/{max_attempts})...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"操作失败，已达到最大重试次数")

            raise last_exception

        return wrapper
    return decorator


def measure_time(func):
    """
    测量函数执行时间的装饰器

    Args:
        func: 要测量的函数

    Returns:
        wrapper: 包装函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"{func.__name__} 执行时间: {execution_time:.2f} 秒")
        return result
    return wrapper


def load_config(config_file):
    """
    加载配置文件

    Args:
        config_file: 配置文件路径

    Returns:
        configparser.ConfigParser: 配置对象
    """
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')
    return config


def save_config(config, config_file):
    """
    保存配置文件

    Args:
        config: 配置对象
        config_file: 配置文件路径

    Returns:
        bool: 是否保存成功
    """
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False


def load_keywords(keywords_file):
    """
    加载关键词列表

    Args:
        keywords_file: 关键词文件路径

    Returns:
        list: 关键词列表
    """
    keywords = []

    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释行（以#开头的行）
                if line and not line.startswith('#'):
                    keywords.append(line)

        print(f"成功加载 {len(keywords)} 个关键词")
        return keywords

    except Exception as e:
        print(f"加载关键词文件失败: {e}")
        return []


def save_keywords(keywords, keywords_file):
    """
    保存关键词列表

    Args:
        keywords: 关键词列表
        keywords_file: 关键词文件路径

    Returns:
        bool: 是否保存成功
    """
    try:
        with open(keywords_file, 'w', encoding='utf-8') as f:
            for keyword in keywords:
                f.write(keyword + '\n')

        print(f"成功保存 {len(keywords)} 个关键词到 {keywords_file}")
        return True

    except Exception as e:
        print(f"保存关键词文件失败: {e}")
        return False


def get_project_root():
    """
    获取项目根目录

    Returns:
        str: 项目根目录路径
    """
    # 获取当前文件的绝对路径
    current_file = os.path.abspath(__file__)
    # 获取项目根目录（向上两级）
    project_root = os.path.dirname(os.path.dirname(current_file))
    return project_root


def ensure_dir(directory):
    """
    确保目录存在，不存在则创建

    Args:
        directory: 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory)


def get_timestamp():
    """
    获取当前时间戳字符串

    Returns:
        str: 时间戳字符串
    """
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def format_duration(seconds):
    """
    格式化时间持续时间

    Args:
        seconds: 秒数

    Returns:
        str: 格式化的时间字符串
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}小时{minutes}分钟{secs}秒"
    elif minutes > 0:
        return f"{minutes}分钟{secs}秒"
    else:
        return f"{secs}秒"


def validate_keyword(keyword):
    """
    验证关键词是否有效

    Args:
        keyword: 要验证的关键词

    Returns:
        bool: 关键词是否有效
    """
    if not keyword or not isinstance(keyword, str):
        return False

    keyword = keyword.strip()
    if len(keyword) == 0:
        return False

    if len(keyword) > 100:
        print(f"关键词过长: {keyword}")
        return False

    return True


def sanitize_filename(filename):
    """
    清理文件名，移除非法字符

    Args:
        filename: 原始文件名

    Returns:
        str: 清理后的文件名
    """
    # Windows文件系统不允许的字符
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')

    # 移除首尾空格和点
    filename = filename.strip('. ')

    return filename if filename else 'unnamed'


def get_file_size(filepath):
    """
    获取文件大小（人类可读格式）

    Args:
        filepath: 文件路径

    Returns:
        str: 文件大小字符串
    """
    if not os.path.exists(filepath):
        return "文件不存在"

    size = os.path.getsize(filepath)

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

    return f"{size:.2f} TB"


def print_progress(current, total, prefix='', suffix=''):
    """
    打印进度条

    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀
        suffix: 后缀
    """
    percent = (current / total) * 100
    filled_length = int(50 * current // total)
    bar = '█' * filled_length + '-' * (50 - filled_length)
    print(f'\r{prefix} |{bar}| {percent:.1f}% {suffix}', end='', flush=True)


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file='config/settings.ini'):
        """
        初始化配置管理器

        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        """加载配置文件"""
        # 确保配置目录存在
        ensure_dir(os.path.dirname(self.config_file))

        # 如果配置文件不存在，创建默认配置
        if not os.path.exists(self.config_file):
            self._create_default_config()

        return load_config(self.config_file)

    def _create_default_config(self):
        """创建默认配置文件"""
        config = configparser.ConfigParser()

        # 浏览器设置
        config['BROWSER'] = {
            'headless': 'False',
            'user_data_dir': '',
            'timeout': '30'
        }

        # 搜索设置
        config['SEARCH'] = {
            'delay_between_keywords': '2',
            'max_wait_time': '30',
            'retry_attempts': '3'
        }

        # 导出设置
        config['EXPORT'] = {
            'default_format': 'excel',
            'output_dir': 'data',
            'auto_download': 'True'
        }

        # 日志设置
        config['LOGGING'] = {
            'level': 'INFO',
            'log_file': 'data/automation.log',
            'max_size': '10'
        }

        # 保存默认配置
        save_config(config, self.config_file)
        print(f"已创建默认配置文件: {self.config_file}")

    def get(self, section, key, fallback=None):
        """
        获取配置值

        Args:
            section: 配置节
            key: 配置键
            fallback: 默认值

        Returns:
            str: 配置值
        """
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getboolean(self, section, key, fallback=False):
        """
        获取布尔型配置值

        Args:
            section: 配置节
            key: 配置键
            fallback: 默认值

        Returns:
            bool: 配置值
        """
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getint(self, section, key, fallback=0):
        """
        获取整型配置值

        Args:
            section: 配置节
            key: 配置键
            fallback: 默认值

        Returns:
            int: 配置值
        """
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getfloat(self, section, key, fallback=0.0):
        """
        获取浮点型配置值

        Args:
            section: 配置节
            key: 配置键
            fallback: 默认值

        Returns:
            float: 配置值
        """
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def set(self, section, key, value):
        """
        设置配置值

        Args:
            section: 配置节
            key: 配置键
            value: 配置值
        """
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        save_config(self.config, self.config_file)
