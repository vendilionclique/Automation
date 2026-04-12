# 淘宝店透视插件自动化工具

万智牌价格数据采集工具。通过 DrissionPage 控制浏览器，使用淘宝"店透视"浏览器插件搜索关键词，从 DOM 提取搜索结果，过滤后导出为 Excel。

## 技术栈

- Python 3.10+
- DrissionPage 4.x（浏览器自动化，对中文电商优化好）
- pandas + openpyxl（Excel 读写）

## 项目结构

```
main.py                  # 主入口，TaobaoAutomation 类
harness.py               # 统一自检：setup / db / plugin（店透视 DOM 调试）
run_llm_filter.py        # LLM 过滤 CLI
run_sku_scrape.py        # SKU 采集 CLI
modules/
  browser.py             # BrowserManager — Chrome 启动、关闭、下载目录配置
  login.py               # TaobaoLogin — 淘宝登录检测
  search.py              # PluginOperator — 插件操作：打开→输入关键词→分析→等待结果→关闭对话框
  export.py              # PluginExporter — 从 DOM 读取表格数据（非文件下载），支持翻页
  filter.py              # 过滤结果（标题需含"万智牌"/"MTG"及牌名），提取最低价
  input_reader.py        # 从 Excel 读取卡牌名，去重，生成搜索关键词
  checkpoint.py          # 断点续传：记录已处理/失败的关键词
  item_sku_scraper.py    # SKU 采集：逐条打开商品页→店透视复制→解析→输出
  harness_plugin.py      # harness plugin 子命令：单关键词插件交互式调试
  llm_client.py          # LLM 调用与 prompt 拼装（智谱/Minimax 等）
  llm_filter.py          # LLM 批量过滤合并结果 Excel
  mtg_db.py              # MySQL/SSH 隧道查牌名参考与短名冲突
  utils.py               # ConfigManager（读取 settings.ini）、日志、进度条
config/
  settings.ini           # 所有可配置参数（gitignored）
  settings.example.ini   # 模板
  selectors.json         # 插件 UI 的 DOM 选择器（plugin + item_sku 段）
  prompts.json           # LLM 过滤用的 prompt 模板路径/片段
  big_sellers.txt        # SKU 采样用大店名单（每行一店名）
  keywords.txt           # 关键词示例（gitignored）
chrome_profile/          # Chrome 用户数据目录（含店透视插件），ChromiumPage 使用
data/
  downloads/             # 导出的原始 Excel
  filtered/              # 过滤后的 Excel
  checkpoints/           # 断点文件（含 sku_ 前缀的 SKU 采集断点）
  logs/                  # 运行日志
  tasks/                 # 每次批量任务的合并结果（按时间戳命名目录）
```

## 核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认"万智牌"）生成搜索关键词
2. 检查淘宝登录状态
3. 对每个关键词：打开插件 → 输入 → 分析 → 等待结果 → 从 DOM 读取数据导出 Excel → 过滤
4. 全部完成后合并过滤结果到 `data/tasks/<时间戳>/合并结果.xlsx`
5. LLM 过滤（`run_llm_filter.py`）→ 输出 `_llm_filtered.xlsx`（全部 + 已删除 sheet）和 `_llm_filtered_pure.xlsx`（仅保留）
6. SKU 采集（`run_sku_scrape.py`）→ 输入 `_llm_filtered_pure.xlsx`，按牌名做采样后打开商品页，通过店透视复制 SKU 表
   - 常规输出：`listing_meta` + `sku_rows`
   - 海量 listing 快捷：`card_price_proxy`（SPU 一口价 p25/p50/p75）
7. 支持断点续传（checkpoint），中断后可 `--resume` 继续

## 运行命令

```bash
# 搜索 + 导出
python main.py -e cards.xlsx              # 批量处理 Excel 中的卡牌名
python main.py -e cards.xlsx --resume      # 从断点恢复
python main.py -k 中止                     # 单关键词测试
python main.py -c config/settings.ini      # 指定配置文件

# LLM 过滤
python run_llm_filter.py -i data/tasks/xxx/合并结果.xlsx

# SKU 采集（在 LLM 过滤之后）
python run_sku_scrape.py -i data/tasks/xxx/合并结果_llm_filtered_pure.xlsx
python run_sku_scrape.py -i filtered_pure.xlsx --resume   # 从断点恢复

# 自检与插件调试（替代原 test_*.py）
python harness.py setup
python harness.py db
python harness.py plugin 中止
```

## 关键配置（settings.ini）

- `[INPUT]` — keyword_prefix 搜索前缀，Excel 列名映射
- `[FILTER]` — 过滤规则：require_magic_prefix、require_card_name、short_name_hard_veto、exclude_shop_names（默认拦截“真橙卡牌”）
- `[RATE_LIMIT]` — 延迟 5-15s/关键词，每 50 个暂停 60s
- `[PLUGIN]` — 分析超时 120s，selectors.json 路径
- `[CHECKPOINT]` — auto_resume 自动恢复未完成任务
- `[LLM]` — provider、batch_size、web_search_fallback 等
- `[SKU_SCRAPE]` — delay_min/max（3-12s）、pause_every/pause_duration、page_load_timeout、copy_wait
- `[SKU_SAMPLING]` — max_open_urls（默认 5）、pay_top_k、big_sellers_file、massive_* 阈值

## 经验积累（调试发现、架构决策等）

_此区域用于记录重要的调试经验和架构发现，确保跨设备同步。_

## SKU 采集：失败枚举与恢复

`run_sku_scrape.py` 对每个商品链接产出一个 status：

| status | 含义 | 建议操作 |
|--------|------|----------|
| `success` | 正常采集 | — |
| `need_login` | 登录态失效 | 手动登录后 `--resume` |
| `captcha` | 验证码/滑块 | 手动通过后 `--resume` |
| `plugin_missing` | 未找到店透视复制按钮 | 确认插件安装 |
| `clipboard_empty` | 插件复制后剪贴板为空 | 手动检查页面 |
| `parse_error` | 剪贴板 TSV 解析失败 | 查看 listing_meta.clipboard_preview |
| `nav_error` | 页面加载失败 | 检查网络/URL 有效性 |
| `success_no_sku_fallback` | 无SKU时自动合成一条 SKU（SPU标题/一口价/stock=1） | 正常使用 |
| `skipped_sampling` | 命中采样策略，本轮不打开 URL | 正常使用（可调 max_open_urls） |
| `massive_spu_price_only` | 命中海量策略，仅统计 SPU 一口价 | 查看 `card_price_proxy` |

恢复流程：`python run_sku_scrape.py -i xxx.xlsx --resume`，自动跳过已成功 URL。

## 开发注意事项

- `chrome_profile/` 包含店透视插件和登录状态，不要删除
- 插件 UI 操作依赖 `selectors.json` 中的文本匹配（如"市场分析"、"搜索内容"），插件更新后可能需要调整
- `selectors.json` 包含 `plugin`（搜索分析用）和 `item_sku`（商品页 SKU 采集用）两段
- `export.py` 从 DOM 直接读取表格数据，不依赖文件下载
- 限速参数是为了避免触发淘宝反爬，修改需谨慎
- SKU 采集单线程串行，以降低风控概率；如需加速可缩短 delay 但需权衡风险
- `config/big_sellers.txt` 一行一个店名，用于 A/B/C 采样优先级

## 验证建议

- 准备三类样本：正常多 SKU、无 SKU、海量 listing
- 检查 `listing_meta.status` 是否出现 `success` / `success_no_sku_fallback` / `skipped_sampling` / `massive_spu_price_only`
- 检查 `sku_rows` 是否存在 `raw_row="__fallback_no_sku__"` 行
- 检查 `card_price_proxy` 是否产出 `p25/p50/p75`
