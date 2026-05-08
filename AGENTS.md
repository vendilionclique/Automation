# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并进入规则/DB/LLM 过滤、统计评估和最终赋值流程。当前仓库已清理为单一主线：开源 browser-use MCP server + 本机 Chrome 真实登录态 + 低频 human-in-the-loop 操作 + 可见截图/状态 + Codex 视觉识别。

旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集、项目内 Chrome profile 和旧项目副本已经从代码树删除。后续不要重新围绕这些路线新增功能。

## 技术栈

- Python 3.10+
- pandas + openpyxl（Excel 读写）
- 视觉采集层：通过 Codex App 调度开源 browser-use MCP server 控制本机 Chrome；Python 项目准备任务、保存证据、ingest 结构化结果
- 视觉识别层：Codex 基于 browser-use MCP 截图/可见页面抽取标题、价格、店铺、地区等字段
- DB/LLM/统计后处理沿用现有模块

## 当前项目结构

```text
main.py                  # 准备视觉采集任务
harness.py               # setup / db / visual-* 入口
run_llm_filter.py        # LLM 过滤 CLI
run_statistical_eval.py  # 统计诊断
run_final_assignment.py  # 最终赋值
modules/
  input_reader.py        # 从 Excel 读取卡牌名、去重、生成搜索关键词
  filter.py              # 过滤商品行，提取最低价
  checkpoint.py          # 关键词级任务状态
  task_state.py          # 任务状态、失败原因、证据目录
  llm_client.py          # LLM 调用与 prompt 拼装
  llm_filter.py          # LLM 批量过滤合并结果 Excel
  mtg_db.py              # MySQL/SSH 隧道查牌名参考与短名冲突
  price_cluster_eval.py  # 统计评估资产
  final_assignment.py    # 最终赋值资产
  utils.py               # 配置、日志、路径工具
  browser_use_driver.py  # browser-use MCP 请求/执行说明/Agent fallback
  page_state.py          # 基于截图判断页面状态
  visual_capture.py      # 截图证据与 capture manifest
  vision_extract.py      # Codex 识别结果写入 JSONL/XLSX
  session_state.py       # 账号健康与安全预算状态
  visual_pipeline.py     # 视觉任务运行、ingest、export 编排
```

## 已废弃并删除的路线

以下路线已通过本机测试判定不适合作为后续主线，并已从当前代码树删除：

1. AdsPower 新指纹 + 本机 IP + 非登录态
2. AdsPower 新指纹 + 代理 IP + 非登录态
3. 本机 Chrome 新 profile + 非登录态
4. 店透视插件路线
5. DOM、接口、CDP 读取路线
6. SKU 插件采集路线
7. 项目内提交的 Chrome profile / 旧项目副本

## 当前进展（2026-05-07）

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
- browser-use MCP 运行策略已确认：`~/.codex/config.toml` 保留 `browser-use-local` 注册。Chrome 136+ 不允许远程调试默认用户数据目录，后续使用专用长期采集 profile：
  `/Users/zhunshi/workspace/automation/local/chrome-taobao-visual-profile`。
  采集前人工用 `local/start_taobao_visual_chrome.sh` 启动该 profile，登录淘宝，并通过本地 CDP `http://127.0.0.1:9222` 让 browser-use MCP 连接同一个可见浏览器。
- `config/settings.ini`、`local/*`、`data/tasks/*`、`data/checkpoints/*` 等本机敏感/大体积运行内容均被 `.gitignore` 忽略。

## 新核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认“万智牌”）生成搜索关键词
2. 为每个关键词创建视觉采集任务与证据目录
3. Codex 通过 browser-use MCP 使用本机 Chrome 真实登录态，低频、可暂停地打开淘宝搜索结果页
4. Codex 通过 browser-use MCP 采集商品列表可视区域截图/可见状态，保存证据
5. Codex 从截图识别商品标题、价格、店铺、地区等字段，输出 raw Excel
6. 复用现有规则/DB/LLM 过滤，生成合并结果
7. 运行统计诊断与最终赋值
8. checkpoint 记录关键词状态、截图目录、识别结果、账号状态、失败原因和人工备注

## 任务调度原则

- 单实例、低频、可中断
- 每日/每小时关键词预算
- 连续异常立即冷却，不反复刷新或重试
- 登录/验证码/风险状态只通知人工接管
- 所有异常保存截图和状态文件，便于 agent 或人工恢复

任务状态：`pending`、`opening_search`、`page_loading`、`visible_ready`、`captured`、`extracted`、`needs_review`、`success`、`cooldown`、`failed`、`skipped`

账号状态：`healthy`、`login_required`、`captcha_required`、`popup_blocked`、`risk_suspected`、`cooling_down`、`locked`

失败原因：`login_required`、`captcha_required`、`page_not_loaded`、`white_skeleton`、`popup_blocked`、`screenshot_failed`、`ocr_low_confidence`、`manual_review_needed`、`rate_limited`、`unknown`

## 远期协作方向（暂不排期）

未来可能拆出员工版轻量采集端，但不作为当前开发日程。员工版不包含 DB/SSH/后处理/最终赋值资产，只负责使用本机 Chrome 登录态和 Zhipu API 驱动 browser-use Agent 采集可见结果，输出标准化 `raw_results.xlsx`、`raw_rows.jsonl`、截图证据和 manifest。

多人协作优先考虑“共享表格任务池 + 共享盘证据仓库”的轻量方案：任务按 `task_id` 领取，记录 assignee、状态、提交时间、结果文件、证据目录和审核备注，避免重复采集。待流程稳定、任务量上升后，再考虑轻量 Web 后台或更强的任务锁/审核系统；GitHub 主要保留给代码和自动化，不优先作为员工采集台账。

## 必须保留的资产

- 输入与关键词：`modules/input_reader.py`
- checkpoint 能力：`modules/checkpoint.py`、`modules/task_state.py`
- 规则过滤：`modules/filter.py`
- DB/LLM 过滤：`modules/llm_filter.py`、`modules/llm_client.py`、`modules/mtg_db.py`
- 统计诊断与最终赋值：`modules/price_cluster_eval.py`、`modules/final_assignment.py`、`run_statistical_eval.py`、`run_final_assignment.py`
- 输出目录结构：`data/downloads/`、`data/filtered/`、`data/tasks/`、`data/checkpoints/`、`data/logs/`

## 当前运行入口

```bash
# 准备视觉采集任务
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
```

## 开发注意事项

- 不自动处理验证码或登录，只检测、暂停、通知人工。
- 不抓接口、不读 cookies/storage、不用隐藏 DOM/HTML/JS eval 提取商品数据。
- browser-use MCP/CDP 只允许读取安全状态摘要用于页面状态判断：URL/title/tabs、可见可交互元素文本、viewport/scroll 元数据和截图。商品标题、价格、店铺、地区等采集结果必须来自保留的可见截图，不能从 HTML/DOM/network/storage 中抽取。
- browser-use MCP 由 Codex App 手动开关控制；平时关闭以避免 Python MCP 进程反复弹出，需要采集时再打开。
- 采集访问路径应从淘宝首页可见搜索框输入关键词并触发搜索，不直接以带关键词的搜索 URL 作为常规采集入口。
- 视觉识别结果必须保留截图证据、坐标、置信度和人工复核入口。
- 采集速度从属于账号安全和数据可审计性。
- 后处理资产必须和采集层解耦，确保视觉采集替换后仍能继续使用现有过滤、DB、LLM、统计和赋值流程。

## 下一步具体计划

1. **截图证据复测**
   - 重启 Codex App 后确认 browser-use MCP 仍可调用，并能打开淘宝搜索结果页。
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
