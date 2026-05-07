# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并接入规则过滤、DB/LLM 过滤、统计评估和最终赋值流程。

当前主线已经从旧的“非登录态 + AdsPower 指纹浏览器 + 代理池 + 店透视插件 + DOM 导出”切换为：

```text
开源 browser-use MCP server
+ 本机 Chrome 真实登录态
+ Codex App 低频人工辅助操作
+ 可见截图/状态
+ Codex 视觉识别
```

旧模块仍保留为 legacy 诊断，不再作为新增功能的设计基础。

## 当前状态

- 依赖自检已通过：`.venv/bin/python harness.py setup`
- 已验证 browser-use 本地工具可以打开淘宝搜索页并看到商品列表。
- 单关键词 `万智牌 中止` 已跑通可见页面闭环：
  - browser-use 打开淘宝搜索结果页
  - Codex 从可见截图整理 6 条商品行
  - `visual-ingest` 写入 `raw_rows.jsonl` / `raw_results.xlsx`
  - `visual-export --filter` 接入现有规则过滤，6 行过滤为 5 行，最低价为 80
- 待补强：Codex App/macOS 权限刚调整后需要重启 Codex App；截图文件自动落盘仍需复测并补齐。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config/settings.example.ini config/settings.ini
```

编辑 `config/settings.ini`：

- `[BROWSER_USE] chrome_executable_path` 指向本机 Chrome。
- `[BROWSER_USE] chrome_user_data_dir` / `chrome_profile_directory` 指向已人工登录淘宝的 Chrome profile。
- 不要把 `config/settings.ini` 提交到 Git，它会包含本机路径和可能的密钥。

自检：

```bash
.venv/bin/python harness.py setup
```

准备单关键词视觉任务：

```bash
.venv/bin/python harness.py visual-one 中止
```

Codex App 通过 browser-use MCP 打开任务中的淘宝 URL，确认页面状态并从可见截图整理商品行后，写入结构化结果：

```bash
.venv/bin/python harness.py visual-ingest data/tasks/<run_id> \
  --keyword "万智牌 中止" \
  --rows-file rows.json \
  --screenshot "data/tasks/<run_id>/evidence/万智牌 中止/<screenshot>.png" \
  --retain-screenshot
```

导出 raw Excel，并可选接入规则过滤：

```bash
.venv/bin/python harness.py visual-export <run_id>
.venv/bin/python harness.py visual-export <run_id> --filter --keyword "万智牌 中止" --card "中止"
```

## Codex App / browser-use 权限提醒

如果刚给 Codex App、Chrome、终端或自动化组件打开了 macOS 权限，请先重启 Codex App 再测试。否则可能出现浏览器能打开但截图、屏幕读取、辅助功能控制不稳定的情况。

测试时只做低频、可观察操作：

- 不自动登录。
- 不处理验证码、短信、安全验证。
- 不读 DOM、接口、cookies、storage、CDP 数据。
- 只采集真实登录用户当前可见页面里的标题、价格、店铺、地区等信息。

## 主要入口

```bash
# 准备视觉采集任务
.venv/bin/python main.py -e cards.xlsx
.venv/bin/python main.py -k 中止

# 视觉采集任务
.venv/bin/python harness.py visual-one 中止
.venv/bin/python harness.py visual-run <run_id> --limit 1
.venv/bin/python harness.py visual-ingest data/tasks/<run_id> --keyword "万智牌 中止" --rows-file rows.json
.venv/bin/python harness.py visual-export <run_id>

# 后处理
.venv/bin/python run_llm_filter.py -i data/tasks/<run_id>/合并结果.xlsx
.venv/bin/python run_statistical_eval.py -i data/tasks/<run_id>/合并结果.xlsx
.venv/bin/python run_final_assignment.py -i data/tasks/<run_id>/合并结果.xlsx

# 自检
.venv/bin/python harness.py setup
.venv/bin/python harness.py db

# legacy 诊断，仅用于历史排查
.venv/bin/python harness.py ip-pool
.venv/bin/python harness.py adspower
.venv/bin/python harness.py plugin 中止
```

## 项目结构

```text
main.py                  # 新主入口：准备视觉采集任务
harness.py               # 诊断与视觉任务入口
run_llm_filter.py        # LLM 过滤 CLI
run_statistical_eval.py  # 统计诊断
run_final_assignment.py  # 最终赋值
modules/
  input_reader.py        # Excel 输入、去重、关键词生成
  filter.py              # 规则过滤与最低价提取
  checkpoint.py          # checkpoint 能力
  task_state.py          # 任务状态、失败原因、证据目录
  llm_client.py          # LLM 调用与 prompt 拼装
  llm_filter.py          # LLM 批量过滤合并结果 Excel
  mtg_db.py              # MySQL/SSH 隧道查牌名参考与短名冲突
  price_cluster_eval.py  # 统计评估
  final_assignment.py    # 最终赋值
  browser_use_driver.py  # browser-use MCP 请求/执行说明/agent fallback
  page_state.py          # 基于截图的页面状态判断
  visual_capture.py      # 截图证据与 capture manifest
  vision_extract.py      # 视觉识别结果写入 JSONL/XLSX
  session_state.py       # 账号健康与安全预算状态
  visual_pipeline.py     # 视觉任务运行、ingest、export 编排

  # legacy
  adspower.py
  proxy_pool.py
  browser.py
  login.py
  search.py
  export.py
  harness_plugin.py
  warmup.py
  item_sku_scraper.py
```

## 输出与本机文件

Git 只同步代码、配置模板和空目录骨架。以下内容不提交：

- `config/settings.ini`
- `config/keywords.txt`
- `local/*`
- `data/tasks/*`
- `data/checkpoints/*`
- `data/logs/*`
- 浏览器 profile、cookies、截图证据、运行 Excel

换机器或重启环境后，需要重新安装依赖、复制 `settings.ini`、配置 Chrome profile，并人工确认淘宝登录态。

## 已废弃路线

以下路线已经通过实测判定不适合作为后续主线：

- AdsPower 新指纹 + 本机 IP + 非登录态
- AdsPower 新指纹 + 代理 IP + 非登录态
- 本机 Chrome 新 profile + 非登录态
- 店透视插件路线
- DOM、接口、CDP 读取路线

后续开发不要围绕这些路线新增功能。保留相关代码只为历史诊断和对照排查。

## 下一步

1. 重启 Codex App，确认新开的权限生效。
2. 复测 browser-use 可见截图自动保存到 `data/tasks/<run_id>/evidence/`。
3. 用 3-5 个关键词做小批量试跑，每个关键词之间保持人工可观察节奏。
4. 补异常状态样例：登录弹窗、验证码/安全验证、白框架、空结果。
5. 加强视觉行字段校验和人工复核入口。

## 免责声明

本工具仅用于合法的数据采集和分析目的。使用时请遵守相关网站服务条款和当地法律法规。采集速度从属于账号安全和数据可审计性。
