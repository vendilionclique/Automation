"""
淘宝店透视插件自动化工具 - 主程序
"""
import os
import sys
import time
import random
import argparse
import logging
from datetime import datetime
import configparser

# 添加模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

from browser import BrowserManager
from login import TaobaoLogin
from search import PluginOperator
from export import PluginExporter
from filter import filter_exported_results, merge_filtered_results
from input_reader import process_excel
from checkpoint import CheckpointManager
from utils import setup_logging, ConfigManager, format_duration, print_progress
from warmup import run_warmup
from modules.llm_filter import filter_with_llm, filter_with_db_only


class TaobaoAutomation:
    """淘宝自动化主类"""

    def __init__(self, config_file='config/settings.ini'):
        self.config = ConfigManager(config_file)
        self.browser_manager = None
        self.page = None
        self.plugin_operator = None
        self.exporter = None
        self.checkpoint = None
        self.logger = logging.getLogger('taobao_automation')

        # 项目根目录
        self.project_root = os.path.dirname(os.path.abspath(__file__))

        # 路径配置
        self.download_dir = os.path.join(
            self.project_root,
            self.config.get('BROWSER', 'download_dir', 'data/downloads')
        )
        self.filtered_dir = os.path.join(
            self.project_root,
            self.config.get('FILTER', 'filtered_dir', 'data/filtered')
        )
        self.checkpoint_dir = os.path.join(
            self.project_root,
            self.config.get('CHECKPOINT', 'checkpoint_dir', 'data/checkpoints')
        )
        self.selectors_file = os.path.join(
            self.project_root,
            self.config.get('PLUGIN', 'selectors_file', 'config/selectors.json')
        )

    def _setup_logging(self):
        """配置日志"""
        log_file = self.config.get('LOGGING', 'log_file', 'data/logs/automation.log')
        level_name = self.config.get('LOGGING', 'level', 'INFO')
        level = getattr(logging, level_name, logging.INFO)
        self.logger = setup_logging(
            os.path.join(self.project_root, log_file),
            level=level
        )

    def _init_browser_components(self, run_page_warmup=False):
        """初始化浏览器、插件操作器和导出器。"""
        _ud = self.config.get('BROWSER', 'user_data_dir', '').strip()
        self.browser_manager = BrowserManager(
            download_dir=self.download_dir,
            user_data_dir=_ud or None,
        )
        self.page = self.browser_manager.init_browser()

        self.plugin_operator = PluginOperator(
            self.page,
            selectors_file=self.selectors_file,
            logger=self.logger,
            user_data_dir=self.browser_manager.user_data_dir,
            extension_id=self.config.get('PLUGIN', 'extension_id', 'ppgdlgnehnajbbngnohepfigdmjbdpfb'),
        )
        self.exporter = PluginExporter(
            self.page,
            self.download_dir,
            selectors_file=self.selectors_file,
            logger=self.logger
        )

        for d in [self.download_dir, self.filtered_dir, self.checkpoint_dir]:
            os.makedirs(d, exist_ok=True)

        if run_page_warmup:
            run_warmup(self.page, self.config, self.logger)

    def _restart_browser_and_clear_plugin_cache(self):
        """关闭浏览器，清理扩展本地缓存，再重新拉起浏览器会话。"""
        cache_cleared = False
        storage_dir = None

        if self.plugin_operator:
            storage_dir = self.plugin_operator.extension_storage_dir

        try:
            if self.browser_manager:
                self.browser_manager.close()
        finally:
            self.browser_manager = None
            self.page = None
            self.exporter = None

        if self.plugin_operator:
            try:
                cache_cleared = self.plugin_operator.clear_plugin_cache_storage()
            except Exception as e:
                self.logger.warning(f"清理扩展本地缓存目录失败: {e}")
            storage_dir = storage_dir or self.plugin_operator.extension_storage_dir

        self.plugin_operator = None

        if storage_dir:
            if cache_cleared:
                self.logger.warning(f"已清理扩展本地缓存目录并准备重启浏览器: {storage_dir}")
            else:
                self.logger.warning(f"扩展本地缓存目录未完全清理，仍将重启浏览器继续重试: {storage_dir}")

        self._init_browser_components(run_page_warmup=True)

        login_mgr = TaobaoLogin(self.browser_manager)
        if not login_mgr.auto_login():
            raise RuntimeError("浏览器重启后淘宝登录状态失效")

    def initialize(self):
        """初始化浏览器和所有组件"""
        self._setup_logging()

        print("=" * 60)
        print("淘宝店透视插件自动化工具")
        print("=" * 60)
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 初始化浏览器
        print("\n初始化浏览器...")
        self._init_browser_components(run_page_warmup=False)

        print("所有组件初始化完成\n")
        run_warmup(self.page, self.config, self.logger)

        return True

    def run_batch(self, excel_file, resume=False):
        """
        批量运行：从Excel读取关键词，逐一搜索、导出、过滤

        Args:
            excel_file: Excel输入文件路径
            resume: 是否从检查点恢复
        """
        start_time = datetime.now()

        # 读取Excel并提取关键词
        prefix = self.config.get('INPUT', 'keyword_prefix', '万智牌')
        df, unique_names, keywords, name_to_ids = process_excel(
            excel_file, prefix=prefix, checkpoint_dir=self.checkpoint_dir
        )

        if not keywords:
            print("错误: 没有有效的搜索关键词")
            return

        # 初始化检查点
        self.checkpoint = CheckpointManager(self.checkpoint_dir)

        if resume or self.config.getboolean('CHECKPOINT', 'auto_resume', False):
            latest = self.checkpoint.find_latest()
            if latest:
                print(f"\n发现未完成的任务: {latest}")
                self.checkpoint.load(latest)
                remaining = self.checkpoint.get_remaining_keywords()
                if remaining:
                    print(f"将从中断处继续，剩余 {len(remaining)} 个关键词\n")
                    keywords = remaining
                else:
                    print("任务已完成，无需继续")
                    return

        if not self.checkpoint.data:
            self.checkpoint.create(excel_file, keywords)

        # 登录检查
        print("=" * 60)
        print("检查登录状态")
        print("=" * 60)
        login_mgr = TaobaoLogin(self.browser_manager)
        if not login_mgr.auto_login():
            print("错误: 未登录淘宝，无法继续")
            return

        # 限速参数
        delay_min = self.config.getint('RATE_LIMIT', 'delay_min', 5)
        delay_max = self.config.getint('RATE_LIMIT', 'delay_max', 15)
        pause_every = self.config.getint('RATE_LIMIT', 'pause_every', 50)
        pause_duration = self.config.getint('RATE_LIMIT', 'pause_duration', 60)
        rate_limit_retry_attempts = self.config.getint('RATE_LIMIT', 'rate_limit_retry_attempts', 2)
        rate_limit_cooldown = self.config.getint('RATE_LIMIT', 'rate_limit_cooldown', 180)
        rate_limit_backoff = self.config.getfloat('RATE_LIMIT', 'rate_limit_backoff', 1.5)

        # 过滤参数
        require_magic = self.config.getboolean('FILTER', 'require_magic_prefix', True)
        require_name = self.config.getboolean('FILTER', 'require_card_name', True)
        exclude_shop_names = self.config.get('FILTER', 'exclude_shop_names', '真橙卡牌')
        exclude_title_keywords = self.config.get(
            'FILTER',
            'exclude_title_keywords',
            'token,徽记,补充包,补充盒,衍生物,代牌,牌套,卡膜,卡盒,牌盒,卡册,牌本,收纳,周边,海报,指示物'
        )

        # 分析超时
        analysis_timeout = self.config.getint('PLUGIN', 'analysis_timeout', 20)
        export_max_pages = self.config.getint('PLUGIN', 'export_max_pages', 3)
        page_interval = self.config.getfloat('PLUGIN', 'page_interval', 2)
        export_next_page_timeout = self.config.getfloat('PLUGIN', 'next_page_timeout', 4)
        export_copy_wait = self.config.getfloat('PLUGIN', 'copy_wait', 1.6)

        # 逐个关键词处理
        total = len(keywords)
        print(f"\n开始批量处理，共 {total} 个关键词")
        print("=" * 60)

        for i, keyword in enumerate(keywords):
            card_name = keyword.replace(f'{prefix} ', '', 1)
            idx = i + 1

            print(f"\n[{idx}/{total}] {keyword}")
            print(f"  进度: ", end='')
            print_progress(len(self.checkpoint.data['processed']), total)

            # 每个关键词前检查登录状态
            if not login_mgr.check_login_status(quick=True):
                print("\n  登录已过期，请重新登录淘宝...")
                if not login_mgr.auto_login():
                    print("  无法恢复登录，跳过剩余关键词")
                    self.checkpoint.mark_failed(keyword, '登录过期')
                    break

            try:
                # 执行搜索分析
                success = False
                force_full_flow = (idx == 1)
                attempts = max(1, rate_limit_retry_attempts)
                quick_cache_retry_count = 0
                for attempt in range(1, attempts + 1):
                    if force_full_flow:
                        # 首个关键词或限流重试时，走完整路径（重新导航 + 打开插件）
                        success = self.plugin_operator.run_keyword_analysis(
                            keyword,
                            analysis_timeout=analysis_timeout
                        )
                    else:
                        # 正常后续关键词：在插件内循环，不碰淘宝页面
                        success = self.plugin_operator.run_keyword_in_plugin(
                            keyword,
                            analysis_timeout=analysis_timeout
                        )

                    if success:
                        break

                    diagnosis = self.plugin_operator.get_last_wait_diagnosis()
                    suspected_limit = diagnosis.get('is_rate_limited', False)
                    if (not suspected_limit) or (attempt >= attempts):
                        break

                    # 优先走“关闭浏览器 -> 删除扩展缓存 -> 重启浏览器 -> 立即重试”
                    if quick_cache_retry_count < 2:
                        quick_cache_retry_count += 1
                        reason = diagnosis.get('reason') or '疑似限流/风控'
                        print(
                            f"  检测到 {reason}，先尝试重启浏览器并删除扩展本地缓存后立即重试"
                            f"（{quick_cache_retry_count}/2）..."
                        )
                        self.logger.warning(
                            f"关键词 {keyword} 疑似限流，执行重启浏览器+删除扩展缓存快速重试 "
                            f"({quick_cache_retry_count}/2)"
                        )
                        try:
                            self._restart_browser_and_clear_plugin_cache()
                        except Exception as e:
                            self.logger.warning(f"重启浏览器并清理扩展缓存失败: {e}")

                        # 快速重试改为重新走完整链路，确保缓存删除后重新注入扩展状态
                        success = self.plugin_operator.run_keyword_analysis(
                            keyword,
                            analysis_timeout=analysis_timeout
                        )
                        if success:
                            break

                        diagnosis = self.plugin_operator.get_last_wait_diagnosis()
                        suspected_limit = diagnosis.get('is_rate_limited', False)
                        if not suspected_limit:
                            # 已非限流态，继续走外层 attempt 即可
                            continue
                        if quick_cache_retry_count < 2:
                            # 第二次重启+删缓存快速重试，不先冷却
                            continue

                    cooldown_seconds = int(
                        rate_limit_cooldown * (rate_limit_backoff ** (attempt - 1))
                    )
                    jitter = random.randint(5, 20)
                    cooldown_seconds += jitter

                    reason = diagnosis.get('reason') or '疑似限流/风控'
                    print(f"  检测到 {reason}，第 {attempt}/{attempts} 次重试前冷却 {cooldown_seconds} 秒...")
                    self.logger.warning(
                        f"关键词 {keyword} 疑似限流，冷却 {cooldown_seconds}s 后重试 "
                        f"({attempt}/{attempts})，诊断: {diagnosis}"
                    )

                    # 冷却兜底：回到淘宝首页再重走完整流程
                    try:
                        self.plugin_operator.close_dialog()
                    except Exception:
                        pass
                    try:
                        self.browser_manager.navigate_to('https://www.taobao.com')
                    except Exception:
                        pass

                    time.sleep(cooldown_seconds)
                    force_full_flow = True

                if success:
                    # 导出结果（从DOM读取）
                    export_result = self.exporter.export_results(
                        keyword,
                        max_pages=export_max_pages,
                        page_interval=page_interval,
                        next_page_timeout=export_next_page_timeout,
                        copy_wait=export_copy_wait,
                    )

                    if export_result and export_result.get('success'):
                        export_file = export_result['export_file']
                        # 过滤结果
                        filter_result = filter_exported_results(
                            export_file,
                            keyword=keyword,
                            card_name=card_name,
                            output_dir=self.filtered_dir,
                            require_magic_prefix=require_magic,
                            require_card_name=require_name,
                            exclude_shop_names=exclude_shop_names,
                            exclude_title_keywords=exclude_title_keywords,
                            logger=self.logger
                        )

                        self.checkpoint.mark_processed(keyword, {
                            'status': 'success',
                            'export_file': export_file,
                            'filtered_file': filter_result.get('filtered_file'),
                            'audit_file': filter_result.get('audit_file'),
                            'min_price': filter_result.get('min_price'),
                            'filtered_count': filter_result.get('filtered_rows', 0),
                        })
                    else:
                        self.checkpoint.mark_failed(keyword, '导出失败')
                else:
                    self.checkpoint.mark_failed(keyword, '分析失败')

            except Exception as e:
                self.logger.error(f"处理关键词 '{keyword}' 时出错: {e}")
                self.checkpoint.mark_failed(keyword, str(e))

            # 关闭对话框（如果还开着）
            try:
                self.plugin_operator.close_dialog()
            except Exception:
                pass

            # 限速延迟
            if i < total - 1:
                delay = random.uniform(delay_min, delay_max)
                time.sleep(delay)

            # 定期暂停
            if (idx % pause_every == 0) and (idx < total):
                print(f"\n  已处理 {idx} 个，暂停 {pause_duration} 秒...")
                time.sleep(pause_duration)

        # 任务完成，合并结果
        self._finalize()

        # 统计
        end_time = datetime.now()
        progress = self.checkpoint.get_progress()
        print("\n" + "=" * 60)
        print("运行结果统计")
        print("=" * 60)
        print(f"总关键词: {progress['total']}")
        print(f"成功处理: {progress['processed']}")
        print(f"失败: {progress['failed']}")
        if progress['total'] > 0:
            print(f"成功率: {progress['processed']/progress['total']*100:.1f}%")
        print(f"总耗时: {format_duration((end_time - start_time).total_seconds())}")

    def _finalize(self):
        """任务完成后的收尾工作：合并过滤结果到任务目录"""
        print("\n合并过滤结果...")

        # 创建任务专用目录
        task_dir = os.path.join(self.project_root, 'data', 'tasks',
                                datetime.now().strftime('%Y%m%d_%H%M%S'))
        os.makedirs(task_dir, exist_ok=True)

        keyword_order = []
        if self.checkpoint and self.checkpoint.data:
            keyword_order = self.checkpoint.data.get('keywords', []) or []

        merged_file = merge_filtered_results(
            self.filtered_dir,
            output_file=os.path.join(task_dir, '合并结果.xlsx'),
            keyword_order=keyword_order,
        )
        if merged_file:
            print("\n?? DB ??????????????...")
            try:
                db_out = os.path.join(task_dir, "????_db_filtered.xlsx")
                db_result = filter_with_db_only(
                    input_file=merged_file,
                    output_file=db_out,
                    logger=self.logger,
                )
                if db_result and db_result.get("success") is False:
                    print(f"DB????: {db_result.get('error')}")
                else:
                    print("DB????")
            except Exception as e:
                print(f"DB????: {e}")
            print(f"合并完成: {merged_file}")
            # LLM 二次过滤（可选）
            try:
                cfg_path = os.path.join(self.project_root, "config", "settings.ini")
                cfg = configparser.ConfigParser()
                cfg.read(cfg_path, encoding="utf-8")
                enable_llm = cfg.getboolean("FILTER", "enable_llm_filter", fallback=False)
            except Exception:
                enable_llm = False

            if enable_llm:
                print("\n执行 LLM 二次过滤（URL行筛选）...")
                try:
                    out_base = os.path.join(task_dir, "合并结果_llm_filtered.xlsx")
                    llm_result = filter_with_llm(
                        input_file=merged_file,
                        output_file=out_base,
                        batch_size=self.config.getint("LLM", "batch_size", 10),
                        logger=self.logger,
                    )
                    if llm_result and llm_result.get("success") is False:
                        print(f"LLM过滤失败: {llm_result.get('error')}")
                    else:
                        print("LLM过滤完成")
                except Exception as e:
                    print(f"LLM过滤异常: {e}")
            # 复制检查点文件到任务目录
            if self.checkpoint and self.checkpoint.checkpoint_file:
                import shutil
                try:
                    shutil.copy2(self.checkpoint.checkpoint_file, task_dir)
                except Exception:
                    pass
        else:
            print("没有需要合并的过滤结果")

    def run_single(self, card_name):
        """
        单关键词测试模式

        Args:
            card_name: 牌名（不含前缀）
        """
        prefix = self.config.get('INPUT', 'keyword_prefix', '万智牌')
        keyword = f"{prefix} {card_name}"

        print(f"单关键词模式: {keyword}")
        print("=" * 60)

        # 检查登录
        login_mgr = TaobaoLogin(self.browser_manager)
        login_mgr.auto_login()

        analysis_timeout = self.config.getint('PLUGIN', 'analysis_timeout', 20)
        export_max_pages = self.config.getint('PLUGIN', 'export_max_pages', 3)
        page_interval = self.config.getfloat('PLUGIN', 'page_interval', 2)
        export_next_page_timeout = self.config.getfloat('PLUGIN', 'next_page_timeout', 4)
        export_copy_wait = self.config.getfloat('PLUGIN', 'copy_wait', 1.6)

        # 执行分析
        success = self.plugin_operator.run_keyword_analysis(
            keyword, analysis_timeout=analysis_timeout
        )

        if success:
            print("\n分析成功！尝试导出...")
            export_result = self.exporter.export_results(
                keyword,
                max_pages=export_max_pages,
                page_interval=page_interval,
                next_page_timeout=export_next_page_timeout,
                copy_wait=export_copy_wait,
            )

            if export_result and export_result.get('success'):
                export_file = export_result['export_file']
                print(f"导出文件: {export_file} ({export_result['total_rows']} 行)")

                # 过滤
                filter_result = filter_exported_results(
                    export_file,
                    keyword=keyword,
                    card_name=card_name,
                    output_dir=self.filtered_dir,
                    require_magic_prefix=self.config.getboolean('FILTER', 'require_magic_prefix', True),
                    require_card_name=self.config.getboolean('FILTER', 'require_card_name', True),
                    exclude_shop_names=self.config.get('FILTER', 'exclude_shop_names', '真橙卡牌'),
                    exclude_title_keywords=self.config.get(
                        'FILTER',
                        'exclude_title_keywords',
                        'token,徽记,补充包,补充盒,衍生物,代牌,牌套,卡膜,卡盒,牌盒,卡册,牌本,收纳,周边,海报,指示物'
                    ),
                    logger=self.logger
                )
                print(f"过滤结果: {filter_result.get('filtered_rows', 0)} 行, "
                      f"最低价: {filter_result.get('min_price', 'N/A')}")
            else:
                print("导出失败")
        else:
            print("分析失败")

    def cleanup(self):
        """清理资源"""
        if self.browser_manager:
            self.browser_manager.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='淘宝店透视插件自动化工具 — 万智牌价格搜索'
    )
    parser.add_argument('-e', '--excel', help='Excel输入文件路径')
    parser.add_argument('-k', '--keyword', help='单关键词测试模式（输入牌名，不含前缀）')
    parser.add_argument('-c', '--config', help='配置文件路径',
                        default='config/settings.ini')
    parser.add_argument('--resume', help='从检查点恢复', action='store_true')

    args = parser.parse_args()

    if not args.excel and not args.keyword:
        parser.print_help()
        print("\n示例:")
        print("  python main.py -e cards.xlsx              # 批量处理Excel")
        print("  python main.py -e cards.xlsx --resume      # 从断点恢复")
        print("  python main.py -k 中止                    # 测试单个牌名")
        return

    automation = TaobaoAutomation(config_file=args.config)

    try:
        if not automation.initialize():
            return

        if args.keyword:
            automation.run_single(args.keyword)
        elif args.excel:
            automation.run_batch(args.excel, resume=args.resume)

    except KeyboardInterrupt:
        print("\n\n用户中断程序")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        automation.cleanup()


if __name__ == '__main__':
    main()
