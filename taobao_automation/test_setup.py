"""
安装测试脚本
用于验证环境和依赖是否正确安装
"""
import sys
import os


def test_python_version():
    """测试Python版本"""
    print("检查Python版本...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print(f"✓ Python版本: {sys.version}")
        return True
    else:
        print(f"✗ Python版本过低: {sys.version}")
        print("  需要Python 3.10或更高版本")
        return False


def test_imports():
    """测试依赖包导入"""
    print("\n检查依赖包...")

    required_packages = [
        ('DrissionPage', 'DrissionPage'),
        ('pandas', 'pandas'),
        ('openpyxl', 'openpyxl'),
        ('configparser', 'configparser'),
    ]

    missing_packages = []
    for name, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name} - 未安装")
            missing_packages.append(name)

    if missing_packages:
        print(f"\n缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    return True


def test_project_structure():
    """测试项目结构"""
    print("\n检查项目结构...")

    required_files = [
        'main.py',
        'config/settings.ini',
        'config/keywords.txt',
        'modules/__init__.py',
        'modules/browser.py',
        'modules/login.py',
        'modules/search.py',
        'modules/export.py',
        'modules/utils.py',
    ]

    missing_files = []
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} - 不存在")
            missing_files.append(file_path)

    if missing_files:
        print(f"\n缺少文件: {', '.join(missing_files)}")
        return False
    return True


def test_browser():
    """测试浏览器驱动"""
    print("\n检查浏览器环境...")

    try:
        from DrissionPage import ChromiumOptions

        # 尝试初始化浏览器选项
        co = ChromiumOptions()
        print("✓ DrissionPage配置正常")

        # 检查Chrome浏览器
        try:
            from DrissionPage import WebPage
            print("✓ 浏览器驱动可用")
            return True
        except Exception as e:
            print(f"✗ 浏览器驱动异常: {e}")
            print("  请确保Chrome浏览器已正确安装")
            return False

    except ImportError as e:
        print(f"✗ DrissionPage导入失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 浏览器检查失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("淘宝店透视插件自动化工具 - 安装测试")
    print("=" * 60)

    tests = [
        ("Python版本", test_python_version),
        ("依赖包", test_imports),
        ("项目结构", test_project_structure),
        ("浏览器环境", test_browser),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name}测试出错: {e}")
            results.append((test_name, False))

    # 显示测试结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")

    # 总体结果
    all_passed = all(result for _, result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有测试通过！环境配置正确")
        print("可以运行: python main.py")
    else:
        print("✗ 部分测试失败，请根据上述提示修复问题")
    print("=" * 60)

    return all_passed


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
