"""
单关键词交互式调试脚本
用于调试店透视插件的DOM选择器和操作流程

用法: python test_single_keyword.py "中止"
"""
import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))


def load_selectors(path):
    """加载选择器配置"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('plugin', {})
    return {}


def try_find(page, selector_list, label, timeout=5):
    """尝试多个选择器查找元素"""
    print(f"\n  查找 [{label}]...")
    for selector in selector_list:
        try:
            el = page.ele(selector, timeout=timeout)
            if el:
                print(f"    OK: '{selector}' -> {el.tag}")
                return el
            print(f"    MISS: '{selector}'")
        except Exception as e:
            print(f"    ERR: '{selector}' -> {e}")
    print(f"  结果: 未找到 [{label}]")
    return None


def take_screenshot(page, name, output_dir='data/logs/screenshots'):
    """截图"""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{name}_{datetime.now().strftime('%H%M%S')}.png")
    try:
        page.get_screenshot(path=path)
        print(f"  截图已保存: {path}")
    except Exception as e:
        print(f"  截图失败: {e}")


def main():
    if len(sys.argv) < 2:
        print("用法: python test_single_keyword.py <牌名>")
        print("示例: python test_single_keyword.py 中止")
        return

    card_name = sys.argv[1]
    keyword = f"万智牌 {card_name}"

    print("=" * 60)
    print(f"单关键词调试模式: {keyword}")
    print("=" * 60)

    # 加载配置
    selectors = load_selectors('config/selectors.json')
    print(f"\n已加载 {len(selectors)} 组选择器配置")

    # 启动浏览器
    print("\n[Step 1] 启动浏览器...")

    # 使用项目专用Chrome配置目录
    # Chrome 146+ 禁止在默认用户数据目录上启用远程调试
    # 首次使用需要手动登录淘宝并安装店透视插件
    user_data_dir = os.path.join(os.path.dirname(__file__), 'chrome_profile')
    os.makedirs(user_data_dir, exist_ok=True)

    # 检查是否已初始化（有Cookie文件说明已登录过）
    cookie_file = os.path.join(user_data_dir, 'Default', 'Network', 'Cookies')
    is_fresh = not os.path.exists(cookie_file)

    from DrissionPage import ChromiumPage, ChromiumOptions

    co = ChromiumOptions()
    co.set_user_data_path(user_data_dir)
    co.set_argument('--disable-popup-blocking')
    co.set_argument('--no-first-run')
    co.set_argument('--no-default-browser-check')

    if is_fresh:
        print(f"  专用配置目录: {user_data_dir}")
        print("  首次使用！启动后请手动：")
        print("  1. 登录淘宝账号")
        print("  2. 安装店透视插件")
        print("  3. 关闭Chrome后重新运行脚本")
    else:
        print(f"  使用专用配置目录: {user_data_dir}")

    co.set_download_path('data/downloads')

    try:
        page = ChromiumPage(co)
        print("  浏览器启动成功")
    except Exception as e:
        print(f"  浏览器启动失败: {e}")
        print("  提示: 请先关闭所有Chrome窗口")
        return

    try:
        # Step 2: 导航到淘宝搜索
        print(f"\n[Step 2] 导航到淘宝搜索...")
        from urllib.parse import quote
        url = f'https://s.taobao.com/search?q={quote(keyword)}'
        page.get(url)
        time.sleep(3)
        take_screenshot(page, '01_search_page')
        print("  请确认页面已加载淘宝搜索结果")
        input("  按 Enter 继续...")

        # Step 3: 查找插件触发按钮
        print(f"\n[Step 3] 查找店透视插件触发按钮...")
        trigger = try_find(page, selectors.get('trigger_button', ['text:市场分析']), '触发按钮')
        if trigger:
            trigger.click()
            time.sleep(2)
            take_screenshot(page, '02_after_trigger')
            print("  请确认插件对话框是否已打开")
            input("  按 Enter 继续...")

            # Step 4: 查找对话框元素
            print(f"\n[Step 4] 查找对话框内的元素...")
            dialog = try_find(page, selectors.get('dialog_container', []), '对话框容器', timeout=2)
            search_input = try_find(page, selectors.get('search_input', []), '搜索输入框')
            start_btn = try_find(page, selectors.get('start_analysis', []), '开始分析按钮')

            # Step 5: 输入关键词
            if search_input:
                print(f"\n[Step 5] 输入关键词: {keyword}")
                search_input.clear()
                time.sleep(0.5)
                search_input.input(keyword)
                time.sleep(1)
                take_screenshot(page, '03_keyword_input')
                input("  按 Enter 继续...")
            else:
                print("\n  未找到搜索输入框！请手动检查DOM并更新 config/selectors.json")
                input("  按 Enter 继续尝试手动操作...")

            # Step 6: 点击开始分析
            if start_btn:
                print(f"\n[Step 6] 点击\"开始分析\"...")
                start_btn.click()

                print("  等待分析结果（最长120秒）...")
                for sec in range(0, 121, 5):
                    time.sleep(5)
                    # 检查结果
                    summary = try_find(page, selectors.get('results_summary', []), '结果摘要', timeout=1)
                    if summary:
                        print(f"  检测到结果: {summary.text}")
                        break
                    print(f"  等待中... {sec}s")

                take_screenshot(page, '04_results')
            else:
                print("\n  未找到\"开始分析\"按钮！")
                input("  按 Enter 跳过...")

            # Step 7: 测试从DOM读取表格数据（替代导出按钮）
            print(f"\n[Step 7] 测试从DOM直接读取表格数据...")

            # 尝试找到页面上的表格
            tables = page.eles('tag:table')
            print(f"  页面上找到 {len(tables)} 个 table 元素")

            for idx, table in enumerate(tables):
                rows = table.eles('tag:tr')
                if len(rows) < 2:
                    continue
                print(f"\n  表格 {idx}: {len(rows)} 行")
                # 打印表头
                header_cells = rows[0].eles('tag:th') or rows[0].eles('tag:td')
                headers = [cell.text.strip() for cell in header_cells]
                print(f"  表头: {headers}")
                # 打印前3行数据
                for row_idx, row in enumerate(rows[1:4]):
                    cells = row.eles('tag:td')
                    values = [cell.text.strip()[:30] for cell in cells]
                    print(f"  行{row_idx+1}: {values}")

            # 也测试"复制表格"按钮是否能工作（复制到剪贴板后用pyperclip读取）
            copy_btn = None
            for sel in ['text:复制表格', 'text:复制']:
                try:
                    copy_btn = page.ele(sel, timeout=2)
                    if copy_btn:
                        print(f"\n  找到复制按钮: '{sel}' -> {copy_btn.tag}")
                        break
                except:
                    continue

            if copy_btn:
                print("  点击复制按钮...")
                copy_btn.click()
                time.sleep(2)
                try:
                    import pyperclip
                    clipboard_data = pyperclip.paste()
                    if clipboard_data:
                        lines = clipboard_data.split('\n')
                        print(f"  剪贴板读取成功！共 {len(lines)} 行")
                        print(f"  前3行:")
                        for line in lines[:3]:
                            print(f"    {line[:100]}")
                    else:
                        print("  剪贴板为空")
                except Exception as e:
                    print(f"  剪贴板读取失败: {e}")
            else:
                print("\n  未找到\"复制表格\"按钮")

            take_screenshot(page, '05_dom_read')

            input("\n  按 Enter 结束测试...")
        else:
            print("\n  未找到插件触发按钮！")
            print("  可能原因:")
            print("  1. 店透视插件未安装")
            print("  2. 插件按钮不是DOM元素（需要其他方式触发）")
            print("  3. 选择器配置不正确")
            print("  请手动打开插件后按 Enter 继续...")
            input("  按 Enter 继续...")

            # 即使手动打开，也尝试查找对话框内的元素
            print(f"\n  查找对话框内的元素...")
            search_input = try_find(page, selectors.get('search_input', []), '搜索输入框')
            start_btn = try_find(page, selectors.get('start_analysis', []), '开始分析按钮')
            export_btn = try_find(page, selectors.get('export_button', []), '导出按钮')

            if search_input:
                print("\n  找到了搜索输入框！可以在手动打开对话框后进行测试。")
            else:
                print("\n  未找到任何对话框元素。请在浏览器中手动打开店透视插件，")
                print("  然后使用开发者工具（F12）检查DOM，更新 config/selectors.json")

            input("\n  按 Enter 结束测试...")

    except KeyboardInterrupt:
        print("\n测试被中断")
    finally:
        page.close()
        print("浏览器已关闭")


if __name__ == '__main__':
    main()
