# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并进入规则/DB/LLM 过滤、统计评估和最终赋值流程。当前核心方向已调整为：本机 Chrome 真实登录态 + 低频 human-in-the-loop 操作 + 纯视觉截图证据 + Codex/视觉模型识别。采集控制层准备从 browser-use MCP 迁移到更贴近 pure-vision browser automation 的方案，优先评估 Midscene。

旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集、项目内 Chrome profile 和旧项目副本已经从代码树删除。后续不要重新围绕这些路线新增功能。

## 技术栈

- Python 3.10+
- pandas + openpyxl（Excel 读写）
- 视觉采集层：Python 项目准备任务、保存证据、ingest 结构化结果；浏览器控制层优先评估 Midscene pure-vision action，browser-use MCP 不再作为淘宝主线
- 视觉识别层：Codex/视觉模型基于可见截图抽取标题、价格、店铺、地区等字段
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
  browser_use_driver.py  # browser-use MCP 旧试验骨架，保留但不再作为淘宝主线
  midscene_computer_driver.py # Midscene computer MCP 请求与安全边界说明
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

## 选型过程与当前判断（2026-05-08）

项目一路试过多条路线，核心约束逐渐明确：淘宝账号安全优先，商品数据必须来自可见页面证据，不能走接口、插件、隐藏 DOM、HTML、cookies/storage 或 network response。

已碰壁/降级的方向：

1. AdsPower/代理/新指纹路线：登录态、账号画像和环境一致性差，不适合作为主线。
2. 店透视、SKU 插件、DOM/API 路线：数据效率高但边界过重，和“可见证据采集”目标冲突。
3. 本机 Chrome 新 profile 非登录态：结果质量和稳定性不足。
4. browser-use MCP：已完成单关键词 MVP 闭环，但源码审计发现 `browser_get_state` 会触发 DOM/AX/DOMSnapshot、`Runtime.evaluate()`、`DOM.getDocument`、可交互元素 selector map 等；index 点击/输入也依赖该 selector map。其默认 agent/state 体系为了好用会读取页面结构，因此不再适合作为淘宝采集主线。

当前判断：

- CDP/浏览器控制本身不等于平台可直接知道“被 CDP 控制”，平台主要看到的是页面行为后果、事件节奏、账号/IP/设备画像和长期模式。
- 风险重点不是“是否存在 CDP”，而是是否读取隐藏结构/接口/存储，以及操作是否呈现高频、重复、异常路径。
- 后续主线应避免 browser-use 的 state/index/HTML/extract 能力，转向 pure-vision action：模型看截图，输出坐标点击、键盘输入、滚动；商品字段只从保存的截图识别。

## Midscene 评估方向（暂定新主线）

Midscene 是当前优先评估的浏览器视觉自动化方案。源码审计结论：Web 端通过 Puppeteer/Playwright/CDP 或 Chrome Extension bridge 控制浏览器；`Tap/Input/Scroll` 等 action 在 `packages/web-integration/src/web-page.ts` 中主要把视觉定位得到的坐标交给 `page.mouse.click/move/wheel`、`page.keyboard.type/press` 执行。Puppeteer/Playwright 封装在 `packages/web-integration/src/puppeteer/base-page.ts`，截图用 `page.screenshot()` 或 CDP `Page.captureScreenshot`，导航用 `goto/reload/goBack/goForward`。这比 browser-use 的 `browser_get_state/index` 路线更接近 pure-vision action。

但 Midscene 不是“零 DOM/零 JS”的工具。源码中仍存在以下高风险/需禁用能力：`getElementsNodeTree/getElementsInfo` 会注入脚本并 `evaluate` 页面结构；`cacheFeatureForPoint/rectMatchesCacheFeature` 会通过 XPath/DOM 做元素缓存；`domIncluded` 虽默认 false，但一旦打开会把 DOM 加入上下文；Chrome extension bridge 会用 `chrome.debugger.sendCommand('Runtime.evaluate')` 注入动画/获取页面内容/读取 `document.readyState`；部分 `size/scroll/navigationState/waitForNavigation` 会 `evaluate window.innerWidth/innerHeight/document.readyState` 或等待 network idle。淘宝主线必须禁用这些辅助能力。

预期使用边界：

- 只用 Midscene 的视觉定位、坐标点击、输入、页面级滚动和截图能力。
- 不用 Midscene 的 DOM extraction、HTML extraction、接口/network、cookies/storage、JS eval。
- 禁用/避免 Midscene 的元素缓存与 XPath 回放：不要启用 cache；每个 locate/action 传 `cacheable: false` 或使用等价配置，避免 `cacheFeatureForPoint` 和 `rectMatchesCacheFeature`。
- 避免 Chrome extension bridge 作为淘宝主线，优先审计 Puppeteer/Playwright 连接已有 Chrome profile 的路径；extension bridge 会主动 `Runtime.evaluate` 注入脚本和动画。
- 避免 `scrollToTop/Bottom` 这类依赖页面尺寸辅助计算的动作；优先使用明确距离的页面级滚动，并评估是否会触发 `window.innerHeight` 读取。
- 商品标题、价格、店铺、地区等字段仍由 Codex/视觉模型从截图证据识别，不从页面结构读取。
- 截图证据优先使用系统截图或确认不会触发 DOM state 的截图入口。
- 继续使用本机长期 Chrome 采集 profile 和真实登录态，人工登录、人工处理验证码/安全验证。
- 保持低频、可暂停、异常即停、checkpoint 可恢复。

下一步应做一个 Midscene spike：连接专用 Chrome profile，打开淘宝首页，从可见搜索框输入单关键词，搜索后保存首屏和滚动分屏截图，并确认全程没有调用 DOM/HTML/network/storage 读取能力。

### 2026-05-09 进一步审计修正

已安装并审计 JS 版 Midscene 1.7.10：`@midscene/web`、`@midscene/computer`、`puppeteer`。结论更新为：淘宝主线优先评估 `@midscene/computer`，而不是 `@midscene/web`。

原因：

- `@midscene/computer` 使用系统截图作为输入，动作输出为系统鼠标、滚轮、键盘事件，不连接浏览器 CDP，也不读 DOM/HTML/network/cookies/storage。
- `@midscene/web` Puppeteer/CDP 路线虽然定位主要来自截图/VLM，但默认仍包含 `window.innerWidth/innerHeight` eval、`waitForSelector('html')`、`waitForNetworkIdle`、XPath cache、`page.screenshot()`/CDP screenshot 等页面辅助能力，只适合作为备选和对照。
- Web bridge/Chrome extension 路线明确会 attach `chrome.debugger` 并多次 `Runtime.evaluate` 注入脚本、读取 `document.readyState`、获取节点树/XPath cache，不适合作为淘宝主线。
- Codex App 接入方向应为注册 `midscene-computer` MCP，由 Codex 作为上层 agent 调度；Midscene 只负责截图、视觉定位、坐标点击、键盘输入、滚动。
- 项目侧已新增 `modules/midscene_computer_driver.py`，`harness.py visual-run` 默认生成 `midscene_computer_request.json` 与 `codex_midscene_computer_instructions.md`；旧 browser-use 入口保留为显式 fallback/对照。
- 当前推荐混合架构：Codex 是长期任务入口、调度 agent、异常裁判、证据复核和后处理编排；Midscene 可使用外部便宜 VLM 进行局部视觉 grounding（找搜索框、按钮、可见列表区域），但商品字段最终仍以保留截图为证据由 Codex 复核后 `visual-ingest`。外部 VLM key 放在本机 `local/midscene-computer.env`，通过 `local/start_midscene_computer_mcp.sh` 注入 MCP，不提交仓库。

详细记录见 `docs/midscene_route_analysis.md`。

## 当前进展（2026-05-07 至 2026-05-08）

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
- 2026-05-08 源码审计后修正：browser-use MCP 的 `browser_get_state` 和 index 操作会读取 DOM/AX/snapshot 等页面结构，和淘宝主线安全边界冲突。该 MVP 证明了视觉闭环可行，但 browser-use 默认能力不再作为后续主线。
- `config/settings.ini`、`local/*`、`data/tasks/*`、`data/checkpoints/*` 等本机敏感/大体积运行内容均被 `.gitignore` 忽略。

## 新核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认“万智牌”）生成搜索关键词
2. 为每个关键词创建视觉采集任务与证据目录
3. Codex/视觉自动化层使用本机 Chrome 真实登录态，低频、可暂停地打开淘宝首页并从可见搜索框搜索
4. 通过 pure-vision action 或系统级截图采集商品列表可视区域截图，保存证据
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

未来可能拆出员工版轻量采集端，但不作为当前开发日程。员工版不包含 DB/SSH/后处理/最终赋值资产，只负责使用本机 Chrome 登录态和 Zhipu API/视觉自动化 Agent 采集可见结果，输出标准化 `raw_results.xlsx`、`raw_rows.jsonl`、截图证据和 manifest。

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

# 旧 browser-use MCP MVP 入口（已降级为历史试验，不作为淘宝主线）
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
- 不抓接口、不读 cookies/storage、不读隐藏 DOM/HTML，不用 JS eval/DOMSnapshot/AX tree 提取页面结构或商品数据。
- 淘宝主线禁用 browser-use MCP 的 `browser_get_state`、`browser_get_html`、`browser_extract_content`、index 点击/输入和任何依赖 selector map 的操作。
- 允许的浏览器自动化方向是 pure-vision：截图识别页面，坐标点击、键盘输入、页面级滚动。商品标题、价格、店铺、地区等采集结果必须来自保留的可见截图，不能从 HTML/DOM/network/storage 中抽取。
- browser-use MCP 由 Codex App 手动开关控制；平时关闭以避免 Python MCP 进程反复弹出，需要采集时再打开。
- 采集访问路径应从淘宝首页可见搜索框输入关键词并触发搜索，不直接以带关键词的搜索 URL 作为常规采集入口。
- 视觉识别结果必须保留截图证据、坐标、置信度和人工复核入口。
- 采集速度从属于账号安全和数据可审计性。
- 后处理资产必须和采集层解耦，确保视觉采集替换后仍能继续使用现有过滤、DB、LLM、统计和赋值流程。

## 下一步具体计划

1. **Midscene spike**
   - 连接专用 Chrome profile：`local/chrome-taobao-visual-profile`。
   - 从淘宝首页可见搜索框输入单关键词并触发搜索。
   - 保存首屏和滚动分屏截图到 `data/tasks/<run_id>/evidence/`。
   - 审计确认没有调用 DOM/HTML/network/storage/JS eval 读取能力。

2. **单关键词视觉闭环复测**
   - 运行 `python harness.py visual-one 中止` 或后续 Midscene 等价入口创建任务。
   - Codex/视觉模型从截图整理至少 5 条商品行，调用 `visual-ingest` 写入 `raw_rows.jsonl`/`raw_results.xlsx`。
   - 运行 `visual-export <run_id>`，确认 raw Excel 字段满足现有过滤链。

3. **异常状态验证**
   - 人工制造或截取登录弹窗、白框架、验证码/安全验证场景。
   - 确认系统标记 `login_required`、`white_skeleton`、`captcha_required` 或 `needs_review`，并保留异常截图。
   - 连续异常达到阈值后进入 `cooldown`，不自动刷新、不重复尝试。

4. **小批量试跑**
   - 用 3-5 个关键词创建任务，`visual-run <run_id> --limit 1` 分批运行。
   - 每个关键词之间保持人工可观察节奏，先验证稳定性，不追求速度。
   - 输出 raw Excel 后接 `filter_exported_results`、DB/LLM 过滤和统计赋值。
