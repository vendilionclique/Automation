"""
工具函数模块
提供各种辅助功能和工具函数
"""
import os
import sys
import logging
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
        os.makedirs(directory, exist_ok=True)


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
        example = os.path.join(os.path.dirname(self.config_file), "settings.example.ini")
        if os.path.exists(example):
            try:
                import shutil

                shutil.copy2(example, self.config_file)
                print(f"已从模板创建配置文件: {self.config_file}")
                return
            except Exception as e:
                print(f"复制配置模板失败，将创建最小默认配置: {e}")

        config = configparser.ConfigParser()

        config['INPUT'] = {
            'excel_file': '',
            'card_name_column': '中文卡牌名',
            'product_id_column': 'productId',
            'keyword_prefix': '万智牌',
        }

        config['CHECKPOINT'] = {
            'checkpoint_dir': 'data/checkpoints',
            'auto_resume': 'true',
        }

        config['VISUAL_CAPTURE'] = {
            'provider': 'midscene_computer',
            'confidence_threshold': '0.80',
            'screenshot_retention': 'false',
        }

        config['MIDSCENE_COMPUTER'] = {
            'window_width': '1600',
            'window_height': '1000',
            'max_scrolls_per_keyword': '2',
            'page_load_wait': '8',
            'session_keyword_limit': '3',
            'keyword_timeout_seconds': '180',
            'mcp_request_timeout_seconds': '180',
            'consecutive_abnormal_stop': '2',
            'foreground_recovery_enabled': 'true',
            'foreground_recovery_attempts_per_event': '3',
            'foreground_recovery_events_per_keyword': '2',
            'allow_bookmark_home_entry_repair': 'true',
            'require_initial_home_entry': 'true',
            'min_rows_per_keyword': '5',
            'screenshot_prefixes': 'initial,results,scroll_1',
        }

        config['MIDSCENE_MODEL'] = {
            'enabled': 'false',
            'model_name': '',
            'model_family': '',
            'base_url': '',
            'api_key_env': 'MIDSCENE_MODEL_API_KEY',
            'allow_midscene_act': 'true',
            'allow_midscene_query': 'false',
            'final_extraction_owner': 'codex',
        }

        config['SESSION'] = {
            'daily_keyword_budget': '20',
            'hourly_keyword_budget': '5',
            'cooldown_minutes': '60',
            'max_consecutive_abnormal': '2',
            'pause_on_login_required': 'true',
            'pause_on_captcha_required': 'true',
            'pause_on_white_skeleton': 'true',
        }

        config['SCHEDULER'] = {
            'daily_keyword_budget': '120',
            'daily_session_count': '4',
            'capture_freshness_days': '30',
            'session_due_times': '',
            'session_due_interval_minutes': '0',
            'capture_worker_stale_after_minutes': '240',
        }

        config['CODEX_EXTRACT'] = {
            'codex_bin': '',
            'profile': 'taobao_visual_extract',
            'model': 'gpt-5.5',
            'sandbox': 'danger-full-access',
            'approval_policy': 'never',
            'ignore_rules': 'true',
            'json_events': 'true',
            'ephemeral': 'true',
            'max_parallel': '1',
            'advice_enabled': 'false',
            'drain_poll_seconds': '20',
            'drain_idle_timeout_seconds': '900',
        }

        config['CAPTURE_WATCHDOG'] = {
            'poll_seconds': '30',
            'idle_timeout_seconds': '900',
            'max_restarts': '2',
        }

        config['VISUAL_BEHAVIOR'] = {
            'micro_pause_short': '0.8,3,0.82',
            'micro_pause_medium': '3,6,0.14',
            'micro_pause_long': '6,10,0.04',
            'inter_keyword_pause_min': '120',
            'inter_keyword_pause_max': '300',
            'detail_page_peek_probability': '0.08',
            'cart_or_favorites_peek_probability': '0.03',
            'allow_cart_or_favorites_peek': 'true',
            'allow_claim_rewards': 'false',
        }

        config['PAGE_SAMPLING'] = {
            'target_listings_per_keyword': '48',
            'max_tiles_per_keyword': '6',
            'min_retained_tiles_per_keyword': '3',
            'max_tile_scroll_distance_px': '360',
            'tile_scroll_viewport_ratio': '0.80',
            'tile_overlap_ratio': '0.20',
            'min_new_rows_per_tile': '2',
            'allow_second_page': 'false',
            'retain_screenshots': 'human_required_only',
            'allow_page_state_json_classifier': 'true',
            'calibration_top_reserved_ratio': '0.24',
            'calibration_bottom_reserved_ratio': '0.06',
        }

        config['FILTER'] = {
            'require_magic_prefix': 'true',
            'require_card_name': 'true',
            'exclude_title_keywords': 'token,徽记,补充包,补充盒,衍生物,代牌,牌套,卡膜,卡盒,牌盒,卡册,牌本,收纳,周边,海报,指示物',
            'filtered_dir': 'data/filtered',
            'use_db_reference': 'true',
            'enable_llm_filter': 'true',
            'exclude_shop_names': '真橙卡牌',
            'short_name_hard_veto': 'true',
            'short_name_conflict_limit': '200',
        }

        config['PRODUCT_ROUTING'] = {
            'raw_input_file': '',
            'preferred_mode_column': 'preferred_mode',
            'pricing_mode_column': 'pricing_mode',
            'output_price_column': '准确淘宝价',
            'capture_time_output_column': '淘宝采集时间',
        }

        config['LOGGING'] = {
            'level': 'INFO',
            'log_file': 'data/logs/automation.log',
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
