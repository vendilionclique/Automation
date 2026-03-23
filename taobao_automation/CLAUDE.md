# 淘宝店透视插件自动化工具

万智牌价格数据采集工具。通过 DrissionPage 控制浏览器，使用淘宝"店透视"浏览器插件搜索关键词，从 DOM 提取搜索结果，过滤后导出为 Excel。

## 技术栈

- Python 3.10+
- DrissionPage 4.x（浏览器自动化，对中文电商优化好）
- pandas + openpyxl（Excel 读写）

## 项目结构

```
main.py              # 主入口，TaobaoAutomation 类
modules/
  browser.py         # BrowserManager — Chrome 启动、关闭、下载目录配置
  login.py           # TaobaoLogin — 淘宝登录检测
  search.py          # PluginOperator — 插件操作：打开→输入关键词→分析→等待结果→关闭对话框
  export.py          # PluginExporter — 从 DOM 读取表格数据（非文件下载），支持翻页
  filter.py          # 过滤结果（标题需含"万智牌"/"MTG"及牌名），提取最低价
  input_reader.py    # 从 Excel 读取卡牌名，去重，生成搜索关键词
  checkpoint.py      # 断点续传：记录已处理/失败的关键词
  utils.py           # ConfigManager（读取 settings.ini）、日志、进度条
config/
  settings.ini       # 所有可配置参数
  selectors.json     # 插件 UI 的 DOM 选择器（市场分析按钮、搜索框、导出按钮等）
  keywords.txt       # 关键词示例
chrome_profile/      # Chrome 用户数据目录（含店透视插件），ChromiumPage 使用
data/
  downloads/         # 导出的原始 Excel
  filtered/          # 过滤后的 Excel
  checkpoints/       # 断点文件
  logs/              # 运行日志
  tasks/             # 每次批量任务的合并结果（按时间戳命名目录）
```

## 核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认"万智牌"）生成搜索关键词
2. 检查淘宝登录状态
3. 对每个关键词：打开插件 → 输入 → 分析 → 等待结果 → 从 DOM 读取数据导出 Excel → 过滤
4. 全部完成后合并过滤结果到 `data/tasks/<时间戳>/合并结果.xlsx`
5. 支持断点续传（checkpoint），中断后可 `--resume` 继续

## 运行命令

```bash
python main.py -e cards.xlsx              # 批量处理 Excel 中的卡牌名
python main.py -e cards.xlsx --resume      # 从断点恢复
python main.py -k 中止                     # 单关键词测试
python main.py -c config/settings.ini      # 指定配置文件
```

## 关键配置（settings.ini）

- `[INPUT]` — keyword_prefix 搜索前缀，Excel 列名映射
- `[FILTER]` — 过滤规则：require_magic_prefix、require_card_name
- `[RATE_LIMIT]` — 延迟 5-15s/关键词，每 50 个暂停 60s
- `[PLUGIN]` — 分析超时 120s，selectors.json 路径
- `[CHECKPOINT]` — auto_resume 自动恢复未完成任务

## 经验积累（调试发现、架构决策等）

_此区域用于记录重要的调试经验和架构发现，确保跨设备同步。_

## 开发注意事项

- `chrome_profile/` 包含店透视插件和登录状态，不要删除
- 插件 UI 操作依赖 `selectors.json` 中的文本匹配（如"市场分析"、"搜索内容"），插件更新后可能需要调整
- `export.py` 从 DOM 直接读取表格数据，不依赖文件下载
- 限速参数是为了避免触发淘宝反爬，修改需谨慎
