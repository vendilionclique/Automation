# 淘宝店透视插件自动化工具

## 项目简介

这是一个基于Python开发的淘宝自动化工具，专门用于使用店透视插件批量搜索关键词并导出数据。工具支持模块化设计，可以方便地进行功能扩展和优化。

## 主要功能

- ✅ 自动登录淘宝（支持Cookie保存，避免重复登录）
- ✅ 使用店透视插件搜索关键词
- ✅ 批量处理关键词列表
- ✅ 多种数据导出格式（Excel、CSV、JSON）
- ✅ 可配置的运行参数
- ✅ 交互式和命令行两种运行模式
- ✅ 可打包为独立exe文件

## 技术栈

- **语言**: Python 3.10+
- **浏览器自动化**: DrissionPage（专为中文电商网站设计）
- **数据处理**: pandas, openpyxl
- **打包工具**: PyInstaller

## 项目结构

```
taobao_automation/
├── main.py                 # 主程序入口
├── config/
│   ├── keywords.txt        # 关键词列表
│   └── settings.ini       # 配置文件
├── modules/
│   ├── __init__.py        # 模块包初始化
│   ├── browser.py         # 浏览器管理模块
│   ├── login.py           # 登录模块
│   ├── search.py          # 搜索模块
│   ├── export.py          # 导出模块
│   └── utils.py           # 工具函数模块
├── data/                  # 数据输出目录
├── requirements.txt       # 依赖列表
└── README.md             # 使用说明文档
```

## 安装和配置

### 1. 环境要求

- Python 3.10 或更高版本
- Chrome 浏览器（最新版本）
- Windows 操作系统

### 2. 安装依赖

```bash
# 进入项目目录
cd taobao_automation

# 安装依赖包
pip install -r requirements.txt
```

### 3. 配置店透视插件

1. 在Chrome浏览器中安装店透视插件
2. 登录淘宝账号
3. 测试插件是否正常工作

## 使用方法

### 方法一：命令行模式

#### 基础使用

```bash
# 使用默认关键词文件
python main.py

# 指定关键词文件
python main.py -f config/keywords.txt

# 直接指定关键词
python main.py -k "手机,电脑,平板"

# 指定导出格式
python main.py -f config/keywords.txt --format excel

# 强制重新登录
python main.py -f config/keywords.txt --force-login
```

#### 高级参数

```bash
# 查看帮助信息
python main.py --help

# 指定配置文件
python main.py -c custom_settings.ini

# 使用CSV格式导出
python main.py -k "手机,电脑" --format csv

# 使用JSON格式导出
python main.py -k "手机,电脑" --format json
```

### 方法二：交互模式

```bash
# 启动交互模式
python main.py -i
```

交互模式支持：
1. 从文件加载关键词
2. 手动输入关键词
3. 实时选择操作

### 方法三：作为Python模块使用

```python
from modules import TaobaoAutomation

# 创建自动化工具实例
automation = TaobaoAutomation()

# 初始化
automation.initialize()

# 运行自动化流程
keywords = ['手机', '电脑', '平板']
results = automation.run(keywords, export_format='excel')

# 查看结果
print(f"成功导出: {results['successful_exports']}/{results['total_keywords']}")
```

## 配置说明

### settings.ini 配置文件

```ini
[BROWSER]
# 是否使用无头模式（后台运行）
headless = False
# 用户数据目录（用于保存登录状态）
user_data_dir =

[SEARCH]
# 关键词搜索之间的延迟时间（秒）
delay_between_keywords = 2
# 搜索结果最大等待时间（秒）
max_wait_time = 30

[EXPORT]
# 默认导出格式：excel, csv, json
default_format = excel
# 数据输出目录
output_dir = data

[LOGGING]
# 日志级别：DEBUG, INFO, WARNING, ERROR
level = INFO
# 日志文件路径
log_file = data/automation.log
```

### keywords.txt 关键词文件

```
# 每行一个关键词
# 以#开头的行是注释
手机
电脑
平板
```

## 打包为EXE文件

### 打包步骤

1. **安装打包工具**

```bash
pip install pyinstaller
```

2. **打包为单个exe文件**

```bash
# 基础打包
pyinstaller --onefile main.py

# 完整打包（推荐）
pyinstaller --onefile --windowed --add-data "config;config" --add-data "modules;modules" --name "淘宝自动化工具" main.py
```

3. **打包选项说明**

- `--onefile`: 打包为单个exe文件
- `--windowed`: 不显示控制台窗口（GUI模式）
- `--add-data`: 添加数据文件
- `--name`: 指定输出文件名

### 使用打包后的exe

```bash
# 直接运行
淘宝自动化工具.exe

# 指定关键词文件
淘宝自动化工具.exe -f keywords.txt

# 交互模式
淘宝自动化工具.exe -i
```

## 注意事项

### 1. 店透视插件选择器

由于店透视插件版本可能不同，插件按钮和导出按钮的选择器可能需要调整。请根据实际插件版本修改以下文件中的选择器：

- `modules/search.py`: `plugin_selectors` 字典
- `modules/export.py`: 导出按钮选择器列表

### 2. 登录问题

- 首次运行需要手动登录
- 登录信息会保存在cookie文件中
- 如遇登录失败，使用 `--force-login` 参数强制重新登录

### 3. 反爬虫机制

- 淘宝有反爬虫机制，请注意请求频率
- 建议在配置文件中设置适当的延迟时间
- 避免在短时间内进行大量请求

### 4. 浏览器兼容性

- 确保Chrome浏览器是最新版本
- 如遇到兼容性问题，请更新Chrome和DrissionPage

## 功能扩展

### 1. 添加新的导出格式

在 `modules/export.py` 中添加新的导出方法：

```python
def export_to_custom_format(self, data, filename=None):
    # 实现自定义导出逻辑
    pass
```

### 2. 添加新的搜索功能

在 `modules/search.py` 中扩展搜索功能：

```python
def advanced_search(self, keyword, filters=None):
    # 实现高级搜索功能
    pass
```

### 3. 添加代理支持

修改 `modules/browser.py` 添加代理配置：

```python
co.set_proxy('http://proxy.example.com:8080')
```

## 常见问题

### Q1: 运行时提示找不到Chrome浏览器

**A**: 请确保Chrome浏览器已安装并设置为默认浏览器。DrissionPage会自动检测Chrome安装位置。

### Q2: 插件按钮找不到

**A**: 可能是插件版本不同，需要使用浏览器开发者工具查看插件按钮的实际选择器，然后修改代码。

### Q3: Cookie保存失败

**A**: 检查data目录是否有写入权限，确保程序有权限创建和修改文件。

### Q4: 打包后exe无法运行

**A**: 可能是依赖文件未正确包含。尝试使用 `--onedir` 模式打包，检查是否缺少文件。

## 技术支持

如有问题，请检查：
1. 日志文件：`data/automation.log`
2. 错误信息的堆栈跟踪
3. 浏览器控制台的错误信息

## 版本历史

- **v1.0.0** (2026-03-18)
  - 初始版本发布
  - 支持基本的搜索和导出功能
  - 支持多种导出格式

## 许可证

本项目仅供学习和研究使用，请遵守淘宝平台的使用条款和相关法律法规。

---

**免责声明**: 本工具仅用于合法的数据采集和分析目的。使用本工具进行大规模数据爬取或商业用途时，请确保遵守相关网站的服务条款和当地法律法规。开发者不对因使用本工具而产生的任何法律问题或经济损失承担责任。