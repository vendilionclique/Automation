# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并进入规则/DB/LLM 过滤、统计评估和最终赋值流程。项目正在重构中：旧的“非登录态 + AdsPower 指纹浏览器 + 代理池 + 店透视插件 + DOM 导出”路线已经通过实测判定不可行，后续切换为“开源 browser-use MCP server + 本机 Chrome 真实登录态 + 低频 human-in-the-loop 操作 + 可见截图/状态 + Codex 视觉识别”的采集路线。

## 技术栈

- Python 3.10+
- pandas + openpyxl（Excel 读写）
- 视觉采集层：通过 Codex App 调度开源 browser-use MCP server 控制本机 Chrome；Python 项目准备任务、保存证据、ingest 结构化结果
- 视觉识别层：Codex 基于 browser-use MCP 截图/可见页面抽取标题、价格、店铺、地区等字段
- DB/LLM/统计后处理沿用现有模块

## 当前项目结构

```
main.py                  # 新主入口：准备视觉采集任务，不再运行旧插件/DOM 采集
harness.py               # 诊断入口：setup / db；旧 adspower/ip-pool/plugin 为 legacy 诊断
run_llm_filter.py        # LLM 过滤 CLI
run_statistical_eval.py  # 统计诊断
run_final_assignment.py  # 最终赋值
modules/
  input_reader.py        # 保留：从 Excel 读取卡牌名、去重、生成搜索关键词
  filter.py              # 保留：过滤商品行，提取最低价
  checkpoint.py          # 保留/待扩展：关键词级任务状态
  task_state.py          # 保留/待扩展：任务状态、失败原因、证据目录
  llm_client.py          # 保留：LLM 调用与 prompt 拼装
  llm_filter.py          # 保留：LLM 批量过滤合并结果 Excel
  mtg_db.py              # 保留：MySQL/SSH 隧道查牌名参考与短名冲突
  price_cluster_eval.py  # 保留：统计评估资产
  final_assignment.py    # 保留：最终赋值资产
  utils.py               # 保留：配置、日志、路径工具
  visual_driver.py       # legacy fallback：PyAutoGUI 系统级 Chrome 启动、输入、截图
  browser_use_driver.py  # 新主线：生成 browser-use MCP 采集请求，不使用 Browser Use Cloud
  page_state.py          # MVP：基于截图判断页面状态
  visual_capture.py      # MVP：截图证据与 capture manifest
  vision_extract.py      # MVP：Codex 识别结果写入 JSONL/XLSX
  session_state.py       # MVP：账号健康与安全预算状态
  visual_pipeline.py     # MVP：视觉任务运行、ingest、export 编排

  # legacy：旧采集层，不再作为主流程使用
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

## 已废弃路线

以下路线已通过本机测试判定不适合作为后续主线：

1. **AdsPower 新指纹 + 本机 IP + 非登录态**  
   Chromium 内核指纹浏览器新实例，即使 UA、WebRTC、时区、语言、Canvas/WebGL、AudioContext、ClientRects、SpeechVoices、CPU/RAM/设备名等都与本机保持一致，淘宝首页可以打开，但手动搜索关键词仍只返回白框架，无法返回商品列表内容。

2. **AdsPower 新指纹 + 代理 IP + 非登录态**  
   在本机 IP 都无法返回商品列表的前提下，短效代理池和新指纹轮换只会进一步降低会话置信度，不再作为采集主线。

3. **本机 Chrome 新 profile + 非登录态**  
   重新安装 Chrome 后，第一个新 profile 在本机 IP、非登录态下可以返回内容不完整的商品列表；但刷新、搜索第二个关键词、再次新建 profile 或删除后重建 profile，均无法稳定返回商品列表。说明淘宝会把“冷 profile/频繁新身份/匿名会话”视为低置信度访问，非登录态并不稳定。

4. **店透视插件路线**  
   店透视插件本身属于高风险行为，且旧实现依赖 DOM/插件 UI/扩展缓存。新路线不再依赖店透视，不再从插件或页面 DOM 导出数据。

5. **DOM、接口、CDP 读取路线**  
   后续采集不读 DOM、不抓接口、不通过 CDP/Playwright 获取页面结构数据。采集层只处理系统截图中已经对登录用户可见的信息。

## 新判断逻辑

- 淘宝并非绝对不向非登录态返回商品结果，但匿名冷会话窗口极脆弱，不适合批量采集。
- 本机长期使用的真实登录态是当前唯一被验证可稳定看到商品列表的底座；Browser Use MCP 的登录态由 本机 Chrome profile 维护。
- 频繁创建新 profile、新指纹、新代理并不像“新用户”，更像高风险身份制造行为。
- 后续项目应从“伪装新匿名用户”转为“登录用户低频人工辅助采集”，以账号安全和可中断恢复为第一优先级。

## 当前进展（2026-05-07）

- 旧 AdsPower/代理池/店透视/DOM 采集模块已标记为 legacy，`main.py` 不再启动旧采集链路。
- browser-use MCP 采集骨架已实现：
  - `harness.py visual-one <牌名>`：创建单关键词视觉任务，并生成 browser-use MCP 采集请求。
  - `harness.py visual-run <run_id> --limit N`：为已准备任务生成 browser-use MCP 请求。
  - `harness.py visual-ingest <task_dir> --keyword ... --rows-json/--rows-file ...`：Codex 看图后把结构化商品行写入 `raw_rows.jsonl` 和 `raw_results.xlsx`。
  - `harness.py visual-export <run_id>`：从 `raw_rows.jsonl` 生成现有后处理可读的 raw Excel；`--filter` 可接入规则过滤。
- 当前本机依赖自检已通过：`.venv/bin/python harness.py setup` 全绿；`pandas`、`openpyxl`、`Pillow`、`pyperclip`、`browser-use` 均可导入。
- 已完成单关键词可见页面闭环测试：
  - run_id：`20260507_171144`
  - 关键词：`万智牌 中止`
  - browser-use 本地 Chrome 可以打开淘宝搜索结果页，并显示真实商品列表。
  - Codex 基于可见截图整理 6 条商品行，`visual-ingest` 成功写入 `raw_rows.jsonl` / `raw_results.xlsx`。
  - `visual-export --filter --keyword "万智牌 中止" --card "中止"` 成功接入规则过滤：6 行进，5 行出，最低价 `80`。
- 发现待补强点：Codex App/macOS 权限刚打开后需要重启 Codex App；截图自动落盘到 evidence 目录仍需重启后复测，目前可见截图能用于识别，但 `screencapture` 曾报 `could not create image from display`。
- 本机 `config/settings.ini` 已重建为新视觉配置，并写入长期 Chrome profile：
  - 当前常用真实登录态 profile：`/Users/zhunshi/Library/Application Support/Google/Chrome` + `Default`
  - 旧专用 profile 路径仍可按需重建：`/Users/zhunshi/workspace/automation/local/chrome-taobao-visual-profile`
- `config/settings.ini`、`local/*`、`data/tasks/*`、`data/checkpoints/*` 等本机敏感/大体积运行内容均被 `.gitignore` 忽略。
- Git 只同步代码、配置模板和空目录骨架；换终端后需重新安装依赖、复制/生成 `settings.ini`、配置 Chrome profile 并人工登录淘宝。

## 新核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认“万智牌”）生成搜索关键词
2. 为每个关键词创建视觉采集任务与证据目录
3. Codex 通过 browser-use MCP 使用本机 Chrome 真实登录态，低频、可暂停地打开淘宝搜索结果页
4. Codex 通过 browser-use MCP 采集商品列表可视区域截图/可见状态，保存证据
5. Codex 从截图识别商品标题、价格、店铺、地区等字段，输出 raw Excel
6. 复用现有规则/DB/LLM 过滤，生成合并结果
7. 运行统计诊断与最终赋值
8. checkpoint 记录关键词状态、截图目录、识别结果、账号状态、失败原因和人工备注

## 下一阶段重构计划

### 1. 采集层替换

新增 开源 browser-use MCP server 模块，旧插件/DOM/AdsPower 采集层全部 legacy：

- `modules/browser_use_driver.py`：生成 browser-use MCP 采集请求、执行说明和证据目标路径；运行开源 `browser-use --mcp`，由 Codex App 作为 agent 调度。
- `modules/visual_driver.py`：legacy fallback；系统级鼠标、键盘、窗口、截图抽象。
- `modules/page_state.py`：基于截图判断页面状态，如商品可见、登录态异常、验证码、弹窗、白框架、加载中。
- `modules/visual_capture.py`：保存关键词截图、证据、屏幕状态和任务上下文。
- `modules/vision_extract.py`：调用 OCR/VLM，把截图中的商品卡片结构化为 raw rows。
- `modules/session_state.py`：账号健康、冷却、中断、人工接管状态。
- `modules/visual_checkpoint.py` 或扩展 `checkpoint.py`：记录视觉采集任务恢复信息。

### 2. 自动化层选型

MVP 主线：开源 browser-use MCP server + 本机 Chrome。

- 优点：智能浏览器操作由 Codex 承担；browser-use MCP 提供本机 Chrome 工具；Python 侧保留任务状态、证据、checkpoint、ingest/export。
- PyAutoGUI/Hammerspoon：只作为备用外部执行器，不作为主线。
- 商用 RPA：只作为备用外部执行器，不作为主状态持有方。

自动化层只暴露窄接口：

- `start_keyword(keyword)`
- `capture_screen()`
- `get_page_state()`
- `pause(reason)`
- `resume()`
- `cooldown(minutes)`
- `abort_task()`
- `mark_manual_done()`

验证码、登录、风险页不自动破解；检测到后暂停并要求人工处理。

### 3. 任务调度层

长期目标是接入 Codex + Slack 或类似 agent 框架。调度层不直接操作浏览器，只根据状态和证据决策：

- 任务状态：`pending`、`opening_search`、`page_loading`、`visible_ready`、`captured`、`extracted`、`needs_review`、`success`、`cooldown`、`failed`、`skipped`
- 账号状态：`healthy`、`login_required`、`captcha_required`、`popup_blocked`、`risk_suspected`、`cooling_down`、`locked`
- 失败原因：`login_required`、`captcha_required`、`page_not_loaded`、`white_skeleton`、`popup_blocked`、`screenshot_failed`、`ocr_low_confidence`、`manual_review_needed`、`rate_limited`、`unknown`

调度策略：

- 单实例、低频、可中断
- 每日/每小时关键词预算
- 连续异常立即冷却，不反复刷新或重试
- 登录/验证码/风险状态只通知人工接管
- 所有异常保存截图和状态文件，便于 agent 或人工恢复

## 必须保留的资产

- 输入与关键词：`modules/input_reader.py`
- checkpoint 能力：`modules/checkpoint.py`、`modules/task_state.py`
- 规则过滤：`modules/filter.py`
- DB/LLM 过滤：`modules/llm_filter.py`、`modules/llm_client.py`、`modules/mtg_db.py`
- 统计诊断与最终赋值：`modules/price_cluster_eval.py`、`modules/final_assignment.py`、`run_statistical_eval.py`、`run_final_assignment.py`
- 输出目录结构：`data/downloads/`、`data/filtered/`、`data/tasks/`、`data/checkpoints/`、`data/logs/`

## 当前运行入口

```bash
# 准备视觉采集任务（不启动旧浏览器/插件采集）
python main.py -e cards.xlsx
python main.py -k 中止

# Codex 开源 browser-use MCP server
python harness.py visual-one 中止
python harness.py visual-run <run_id> --limit 1
python harness.py visual-ingest data/tasks/<run_id> --keyword "万智牌 中止" --rows-file rows.json
python harness.py visual-export <run_id>

# 后处理
python run_llm_filter.py -i data/tasks/xxx/合并结果.xlsx
python run_statistical_eval.py -i data/tasks/xxx/合并结果.xlsx
python run_final_assignment.py -i data/tasks/xxx/合并结果.xlsx

# 自检
python harness.py setup
python harness.py db

# legacy 诊断，仅用于历史排查，不再代表主线
python harness.py ip-pool
python harness.py adspower
python harness.py plugin 中止
```

## 开发注意事项

- 不再围绕 AdsPower、代理池、店透视插件、DOM 导出设计新功能。
- 不自动处理验证码或登录，只检测、暂停、通知人工。
- 视觉识别结果必须保留截图证据、坐标、置信度和人工复核入口。
- 采集速度从属于账号安全和数据可审计性。
- 后处理资产必须和采集层解耦，确保视觉采集替换后仍能继续使用现有过滤、DB、LLM、统计和赋值流程。

## 下一步具体计划

1. **重启 Codex App 并复测权限**
   - 刚才 Codex/macOS 相关权限打开不全，需要重启 Codex App 后再继续浏览器测试。
   - 重启后确认 browser-use MCP 仍可调用，并能打开淘宝搜索结果页。
   - 重点复测截图保存到 `data/tasks/<run_id>/evidence/`，确保审计证据链完整。

2. **单关键词视觉闭环复测**
   - 运行 `python harness.py visual-one 中止` 生成 `browser_use_request.json` 和 `codex_browser_use_instructions.md`。
   - Codex 通过 browser-use MCP 使用本机 Chrome 打开目标页、截图、判断页面状态。
   - Codex 从截图整理至少 5 条商品行，调用 `visual-ingest` 写入 `raw_rows.jsonl`/`raw_results.xlsx`。
   - 运行 `visual-export <run_id>`，确认 raw Excel 字段满足现有过滤链。

3. **异常状态验证**
   - 人工制造或截取登录弹窗、白框架、验证码/安全验证场景。
   - 确认系统标记 `login_required`、`white_skeleton`、`captcha_required` 或 `needs_review`，并保留异常截图。
   - 连续异常达到阈值后进入 `cooldown`，不自动刷新、不重复尝试。

4. **小批量试跑**
   - 用 3-5 个关键词创建任务，`visual-run <run_id> --limit 1` 分批运行。
   - 每个关键词之间保持人工可观察节奏，先验证稳定性，不追求速度。
   - 输出 raw Excel 后接 `filter_exported_results`、DB/LLM 过滤和统计赋值。

5. **后续增强**
   - 改进 `page_state.py` 的截图状态识别规则。
   - 为 Codex 识别结果建立更严格的字段校验和人工复核入口。
   - 未来接入 Slack/Codex agent 调度：agent 只读任务状态和截图证据、发通知和建议，不直接绕过登录/验证码。
