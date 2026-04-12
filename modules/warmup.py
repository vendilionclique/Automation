"""
页面预热模块

浏览器启动后、登录检查前，先导航淘宝首页并尝试关闭营销弹窗，
再可选地等待人工确认（带超时，无人值守时自动继续）。
"""
import sys
import time
import logging
import threading


# ── 自动关闭弹窗 ────────────────────────────────────────────

_CLOSE_BUTTON_JS = r"""
(function() {
    var closed = 0;
    var selectors = [
        '.baxia-dialog-close',
        '.next-dialog-close',
        '.J_CloseBtn',
        '.sufei-dialog-close',
        '.dialog-close',
        '.modal-close',
        '.popup-close',
        'a.close-btn',
        '.close-layer',
        '.tb-notice-close',
        '[aria-label="关闭"]',
        '[aria-label="close"]',
        '[aria-label="Close"]',
        '[class*="close"][class*="btn"]',
        '[class*="Close"][class*="Btn"]',
        'i.iconfont-close',
    ];
    for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        for (var j = 0; j < els.length; j++) {
            var r = els[j].getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                try { els[j].click(); closed++; } catch(e) {}
            }
        }
    }
    return closed;
})()
"""

_CLICK_MASK_JS = r"""
(function() {
    var masks = document.querySelectorAll(
        '.next-overlay-backdrop, .modal-mask, .dialog-mask, '
        + '[class*="overlay"][class*="mask"], [class*="Overlay"][class*="Mask"]'
    );
    var clicked = 0;
    for (var i = 0; i < masks.length; i++) {
        var s = window.getComputedStyle(masks[i]);
        if (s.display !== 'none' && s.visibility !== 'hidden') {
            try { masks[i].click(); clicked++; } catch(e) {}
        }
    }
    return clicked;
})()
"""


def dismiss_overlays(page, logger, max_rounds=3, round_interval=2.0):
    """
    多轮扫描淘宝首页，尝试关闭常见营销弹窗 / 遮罩层。

    Returns:
        int: 累计关闭的弹窗数量
    """
    dismissed = 0

    for round_idx in range(max_rounds):
        closed_this_round = 0

        try:
            n = page.run_js(_CLOSE_BUTTON_JS)
            if n and int(n) > 0:
                closed_this_round += int(n)
                logger.info(f"预热第{round_idx+1}轮: 关闭了 {n} 个弹窗按钮")
        except Exception as e:
            logger.debug(f"JS关闭弹窗异常: {e}")

        try:
            page.actions.key_down('Escape')
            page.actions.key_up('Escape')
        except Exception:
            pass

        try:
            n = page.run_js(_CLICK_MASK_JS)
            if n and int(n) > 0:
                closed_this_round += int(n)
                logger.info(f"预热第{round_idx+1}轮: 点击了 {n} 个遮罩层")
        except Exception:
            pass

        dismissed += closed_this_round

        if closed_this_round == 0 and round_idx > 0:
            logger.debug(f"预热第{round_idx+1}轮: 未发现新弹窗，结束扫描")
            break

        if round_idx < max_rounds - 1:
            time.sleep(round_interval)

    return dismissed


# ── 搜索框就绪检测 ──────────────────────────────────────────

_SEARCH_READY_JS = r"""
(function() {
    var input = document.querySelector('#q')
             || document.querySelector('input[name="q"]')
             || document.querySelector('.search-combobox-input');
    if (!input) return 'no_element';
    var rect = input.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return 'not_visible';
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var top = document.elementFromPoint(cx, cy);
    if (top === input || input.contains(top)
        || (top && top.closest && top.closest('form'))) {
        return 'ready';
    }
    return 'blocked';
})()
"""


def check_search_ready(page, logger):
    """搜索框是否可见且未被遮挡。"""
    try:
        result = page.run_js(_SEARCH_READY_JS)
        logger.debug(f"搜索框就绪检测: {result}")
        return result == 'ready'
    except Exception as e:
        logger.debug(f"搜索框检测异常: {e}")
        return False


# ── 带超时的人工确认 ────────────────────────────────────────

def _prompt_with_timeout(timeout_seconds):
    """
    等待用户按 Enter 或超时自动返回。

    - 有 stdin TTY: 开守护线程读 Enter，主线程 join(timeout)
    - 无 stdin TTY（计划任务/后台）: 直接跳过
    """
    if not sys.stdin or not sys.stdin.isatty():
        return False

    result = {'pressed': False}

    def _wait_enter():
        try:
            sys.stdin.readline()
            result['pressed'] = True
        except Exception:
            pass

    t = threading.Thread(target=_wait_enter, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)
    return result['pressed']


# ── 预热主流程 ──────────────────────────────────────────────

def run_warmup(page, config, logger=None):
    """
    页面预热主入口。

    1. 导航淘宝首页
    2. 多轮自动关闭弹窗
    3. 检测搜索框是否就绪
    4. 可选：带超时的人工确认

    配置项（[WARMUP] 节）:
        prompt_seconds   – 人工确认等待秒数（0=跳过，默认 0）
        dismiss_rounds   – 自动关弹窗最大轮次（默认 3）
        dismiss_interval – 每轮间隔秒数（默认 2.0）

    Returns:
        bool: 搜索框是否就绪
    """
    logger = logger or logging.getLogger(__name__)
    prompt_seconds = config.getint('WARMUP', 'prompt_seconds', 0)
    dismiss_rounds = config.getint('WARMUP', 'dismiss_rounds', 3)
    dismiss_interval = config.getfloat('WARMUP', 'dismiss_interval', 2.0)

    print("\n" + "=" * 60)
    print("页面预热")
    print("=" * 60)

    # 1. 导航淘宝首页
    logger.info("预热: 导航到淘宝首页...")
    try:
        page.get('https://www.taobao.com')
        time.sleep(3)
    except Exception as e:
        logger.warning(f"预热: 导航淘宝首页失败: {e}")

    # 2. 自动关弹窗
    dismissed = dismiss_overlays(page, logger,
                                 max_rounds=dismiss_rounds,
                                 round_interval=dismiss_interval)
    if dismissed:
        print(f"  自动关闭了 {dismissed} 个弹窗/遮罩")
    else:
        print("  未检测到需要关闭的弹窗")

    # 3. 搜索框就绪检测
    ready = check_search_ready(page, logger)
    if ready:
        print("  搜索框就绪")
        logger.info("预热: 搜索框已就绪")
    else:
        print("  搜索框未就绪（可能仍有弹窗遮挡）")
        logger.warning("预热: 搜索框未就绪")

    # 4. 人工确认
    if prompt_seconds > 0:
        if ready:
            print(f"\n  页面看起来已就绪。按 Enter 确认，或等待 {prompt_seconds} 秒自动继续...")
        else:
            print(f"\n  请在浏览器中手动处理弹窗或异常状态。")
            print(f"  完成后按 Enter 继续，或等待 {prompt_seconds} 秒自动继续...")

        user_confirmed = _prompt_with_timeout(prompt_seconds)

        if user_confirmed:
            print("  用户确认继续")
            logger.info("预热: 用户按 Enter 确认继续")
        else:
            print(f"  等待 {prompt_seconds} 秒后自动继续")
            logger.info(f"预热: {prompt_seconds}s 超时，自动继续")

        ready = check_search_ready(page, logger)
    elif not ready:
        logger.info("预热: prompt_seconds=0，跳过人工确认，再试一轮关弹窗")
        time.sleep(2)
        dismiss_overlays(page, logger, max_rounds=1)
        ready = check_search_ready(page, logger)

    status = "页面就绪" if ready else "页面未完全就绪（后续步骤将继续尝试）"
    print(f"  预热完成: {status}")
    print("=" * 60)
    return ready
