# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并进入规则/DB/LLM 过滤、统计评估和最终赋值流程。当前核心方向已调整为：本机 Chrome 真实登录态 + 低频 human-in-the-loop 操作 + 纯视觉截图证据 + Codex/视觉模型识别。采集控制层主线为 Midscene computer MCP。

旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集、项目内 Chrome profile 和旧项目副本已经从代码树删除。后续不要重新围绕这些路线新增功能。

## 技术栈

- Python 3.10+
- pandas + openpyxl（Excel 读写）
- 视觉采集层：Python 项目准备任务、保存证据、ingest 结构化结果；浏览器控制层使用 Midscene computer pure-vision action
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
  page_sampling.py       # viewport tile 采样配置、结构化事件和 tile 摘要
  midscene_computer_driver.py # Midscene computer MCP 请求与安全边界说明
  page_state.py          # 基于截图判断页面状态
  visual_capture.py      # 截图证据与 capture manifest
  vision_extract.py      # Codex 识别结果写入 JSONL/XLSX
  session_state.py       # 账号健康与安全预算状态
  codex_extract.py       # Codex extract contract、codex exec 启动建议、确定性 rows apply
  visual_scheduler.py    # 从全量台账生成日预算/session 采集计划
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

已安装并审计 JS 版 Midscene 1.7.10。结论更新为：淘宝主线使用 `@midscene/computer`，而不是 Web/CDP 路线。

原因：

- `@midscene/computer` 使用系统截图作为输入，动作输出为系统鼠标、滚轮、键盘事件，不连接浏览器 CDP，也不读 DOM/HTML/network/cookies/storage。
- `@midscene/web` Puppeteer/CDP 路线虽然定位主要来自截图/VLM，但默认仍包含 `window.innerWidth/innerHeight` eval、`waitForSelector('html')`、`waitForNetworkIdle`、XPath cache、`page.screenshot()`/CDP screenshot 等页面辅助能力，只适合作为备选和对照。
- Web bridge/Chrome extension 路线明确会 attach `chrome.debugger` 并多次 `Runtime.evaluate` 注入脚本、读取 `document.readyState`、获取节点树/XPath cache，不适合作为淘宝主线。
- Codex App 接入方向应为注册 `midscene-computer` MCP，由 Codex 作为上层 agent 调度；Midscene 只负责截图、视觉定位、坐标点击、键盘输入、滚动。
- 项目侧已新增 `modules/midscene_computer_driver.py`，`harness.py visual-run` 默认生成 `midscene_computer_request.json` 与 `codex_midscene_computer_instructions.md`。
- 当前推荐混合架构：Codex 是任务入口、异常裁判、证据复核和后处理编排；Midscene 可使用外部便宜 VLM 进行局部视觉 grounding（找搜索框、按钮、可见列表区域），但商品字段最终由短命 Codex extract worker 基于保留截图识别，再通过 `visual-apply-extracted-rows` 确定性落盘。外部 VLM key 放在本机 `local/midscene-computer.env`，通过 `local/start_midscene_computer_mcp.sh` 注入 MCP，不提交仓库。

详细记录见 `docs/midscene_route_analysis.md`。

## 当前进展（2026-05-07 至 2026-05-14）

- Midscene computer MVP 已跑通过；当前高级版本继续沿用系统截图 + 系统鼠标/键盘/滚轮的 pure-vision 主线。
- `harness.py visual-one <牌名>`：创建单关键词视觉任务。
- `harness.py visual-run <run_id> --limit N`：为已准备任务生成 Midscene computer MCP 请求。
- `harness.py visual-session-run <plan_id> --session N` also writes a bounded
  small-session worker contract at
  `data/tasks/<plan_id>/sessions/session_NN/midscene_session_worker_request.json`.
  Midscene may execute the selected keywords continuously inside that contract,
  but Codex remains the owner of daily scheduling, abnormal-state strategy,
  screenshot review, `visual-apply-extracted-rows`, filtering, and downstream assignment.
- `harness.py visual-sync-worker <plan_id> --session N` reads
  `session_worker_result.json` plus each `keyword_result.json` and syncs the
  coarse worker state back into `visual_tasks.json`; it does not ingest product
  rows.
- 2026-05-14 架构已调整为“四层职责”：本地无脑 heartbeat、session 级
  capture worker、异步 Codex extract worker、非常驻 Codex supervisor。Codex 不再作为
  主心跳/主调度器；它通过 `visual-control` 读取状态和发控制命令。
- `harness.py visual-heartbeat --mode sync|prepare|dispatch|all` 是短命心跳入口；
  负责同步 worker 结果、准备 session contract、返回 worker 命令，不打开 Chrome、
  不触碰淘宝页面、不直接启动后台进程。
- `harness.py visual-control status|pause|resume|stop|cooldown|lock|unlock --plan-id ...`
  是 Codex/人工 supervisor 控制面，状态写入 `control.json` 和事件日志。
- `harness.py visual-capture-worker --contract <midscene_session_worker_request.json>`
  默认安全模拟；加 `--no-simulate` 时尝试通过本机 Midscene computer MCP stdio
  launcher 执行 contract，保存 viewport tile 截图并写标准 `keyword_result.json` /
  `session_worker_result.json`。如果 MCP 环境不可用，写 `real_not_available`，
  不伪装为已采集。
- `harness.py visual-codex-extract-prepare --plan-id <plan_id> --session N`
  为 captured keyword 生成 keyword 级 `extract_request.json` / `extract_prompt.md`。
- `harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session N`
  返回或通过 `--start` 使用 `codex exec` 启动短命非交互式 Codex extract worker。
  本地 scheduler / launcher 可以启动这种用完即弃 worker，但不能创建 Codex App
  UI 中可见的新聊天会话；可见 supervisor 会话应由人工、Codex App automation
  或未来 CC-connect/飞书入口触发。
- `harness.py visual-apply-extracted-rows --request <extract_request.json>`
  是确定性 rows apply 入口：读取 Codex extract worker 写出的 `rows_result.json`，
  写 `rows_pending.json`、`raw_rows.jsonl`、`raw_results.xlsx` 并更新 manifest。
  它不是抽取 worker；新路线中只有 Codex extract worker 负责看截图抽取商品行。
- `harness.py visual-ingest <task_dir> --keyword ... --rows-json/--rows-file ...`：底层 rows 写入能力，保留给人工修正和兼容场景；主线由 `visual-apply-extracted-rows` 调用落盘。
- `harness.py visual-export <run_id>`：从 `raw_rows.jsonl` 生成现有后处理可读的 raw Excel；`--filter` 可接入规则过滤。
- 当前代码级自检：`.venv/bin/python -m py_compile harness.py modules/*.py` 通过；
  `pandas`、`openpyxl`、`Pillow`、`pyperclip` 均可导入。本机
  `config/settings.ini` 需要从 `config/settings.example.ini` 同步新配置项，例如
  `[MIDSCENE_COMPUTER] session_keyword_limit` 和 `[CODEX_EXTRACT] profile`，否则
  `harness.py setup` 会提示失败。
- 旧 browser-use/CDP fallback、兼容垫片和 Web/CDP Midscene 依赖已经从代码树移除。
- `config/settings.ini`、`local/*`、`data/tasks/*`、`data/checkpoints/*` 等本机敏感/大体积运行内容均被 `.gitignore` 忽略。

## 新核心流程

1. 从全量输入台账读取卡牌名、`preferred_mode` 和 `淘宝采集时间`
2. 默认只选择 `preferred_mode=statistical` 且 `淘宝采集时间` 缺失或过期的牌名进入当天候选；`skip` 和 `with_keywords` 不进入当前默认统计采集池
3. 按日预算和 session 数自动生成分段采集计划，无需人工切表
4. 为每个关键词创建视觉采集任务与证据目录
5. heartbeat 根据 `control.json`、session 状态和 worker 结果决定是否准备下一段
   session；它只做短命确定性判断，不调用大模型、不控制浏览器
6. capture worker 使用本机 Chrome 真实登录态，低频、可暂停地从淘宝首页可见搜索框
   搜索，并通过 pure-vision action / 系统截图采集 viewport tiles
7. Codex extract worker 异步消费 captured keyword 的批量 tile 截图，抽取商品标题、
   价格、店铺、地区等字段；`visual-apply-extracted-rows` 负责轻量去重、落 raw 行并写入 `采集时间`
8. 复用现有规则/DB/LLM 过滤，生成合并结果
9. 运行统计诊断与最终赋值；只有 `statistical_assigned` 行回填 `准确淘宝价` 和 `淘宝采集时间`
10. checkpoint/manifest 记录关键词状态、截图目录、识别结果、账号状态、失败原因和人工备注

## 任务调度原则

- 单实例、低频、可中断
- 每日关键词预算默认由 `SCHEDULER.daily_keyword_budget` 控制，默认一天拆成 4 个 collection session
- heartbeat 的语义是“醒来检查是否该启动一个 session”，不是每次只跑一个关键词
- heartbeat 必须短命、可重复运行、可从文件恢复；不要把 Codex/聊天 agent 会话
  当作长期在线主调度器
- capture worker 和 Codex extract worker 通过文件、lease/runtime 和事件日志解耦；Codex
  supervisor 只通过 `visual-control` 介入，不直接改 worker 产物
- 每个 session 内处理一批关键词；关键词之间使用分钟级长暂停，关键词内部使用分段概率短暂停
- 连续异常立即冷却，不反复刷新或重试
- 登录/验证码/风险状态只通知人工接管
- 结构化事件写入 `task_events.jsonl`，tile 摘要写入 `tile_summary.jsonl`
- 截图默认仅在人工介入级异常时保留；低置信或可自愈异常只记录日志和状态
- Codex extract worker 不允许“单张图抽完即删”；必须等同一 keyword 完成 rows apply 且质量
  达标后，按 keyword 粒度删除成功截图；异常、低置信、人工介入状态保留截图
- 自然节奏层只用于降低误操作和保持可观察节奏，不作为反检测承诺；购物车/收藏夹只允许关键词之间低频只读 peek，不允许加购、收藏、删除、结算、领红包或其他账号状态变更

采集时间语义：

- `采集时间` 是视觉 raw 行的证据时间。
- `capture_time_for_assignment` 是统计评估按牌名聚合出的有效样本最新采集时间。
- `淘宝采集时间` 是原输入台账里的回填列，只在最终状态为 `statistical_assigned` 时写入；`skip`、`with_keywords_pending`、`statistical_blocked_pending_with_keywords` 均留空。
- `with_keywords` 取代旧的 `open_url` 语义：不再表示 URL/SKU 级采集，而是表示该行未来应使用“万智牌 中文牌名 关键词”这类更具体的搜索词做统计采集和赋值；当前只记录为远期待处理路由，不实现额外关键词采集或回填。

viewport tile 采样语义：

- 不用 DOM 扫描、CDP/full-page screenshot 或页面结构读取来计算滚动距离。
- session 启动时可用系统截图/屏幕几何做视觉校准，估算 `tile_scroll_distance_px`。
- `tile_00` 是首屏，`tile_01`、`tile_02` 等是滚动后的可见窗口截图。
- v1 默认按 `PAGE_SAMPLING.max_tiles_per_keyword` 采完整页可见 tiles，不按商品数早停，不翻页。
- `PAGE_SAMPLING.target_listings_per_keyword` 只是第一页结果的近似保护上限；淘宝会夹杂广告、评价、占位等内容，真实商品数会在该数字附近波动。
- v1 采用“capture worker 批量截图 + Codex extract worker keyword 级抽取 + `visual-apply-extracted-rows` 去重/落盘”；
  稀疏早停和逐 tile 动态识别留作后续优化。

任务状态：`pending`、`running`、`opening_search`、`page_loading`、`visible_ready`、
`captured`、`extracting`、`extracted`、`needs_review`、`success`、`cooldown`、
`paused_needs_human`、`paused_needs_supervisor`、`cooling_down`、
`failed_recoverable`、`failed_hard`、`failed`、`skipped`

账号状态：`healthy`、`login_required`、`captcha_required`、`popup_blocked`、`risk_suspected`、`cooling_down`、`locked`

失败原因：`login_required`、`captcha_required`、`page_not_loaded`、`white_skeleton`、`popup_blocked`、`screenshot_failed`、`ocr_low_confidence`、`manual_review_needed`、`rate_limited`、`unknown`

## 远期协作方向（暂不排期）

未来可能拆出员工版轻量采集端，但不作为当前开发日程。员工版不包含 DB/SSH/后处理/最终赋值资产，只负责使用本机 Chrome 登录态和 Zhipu API/视觉自动化 Agent 采集可见结果，输出标准化 `raw_results.xlsx`、`raw_rows.jsonl`、截图证据和 manifest。

多人协作优先考虑“共享表格任务池 + 共享盘证据仓库”的轻量方案：任务按 `task_id` 领取，记录 assignee、状态、提交时间、结果文件、证据目录和审核备注，避免重复采集。待流程稳定、任务量上升后，再考虑轻量 Web 后台或更强的任务锁/审核系统；GitHub 主要保留给代码和自动化，不优先作为员工采集台账。

通知能力暂不排期，但保留远期方向：未来可新增独立 notifier 层，把登录失效、验证码、安全验证、疑似风控、session 异常暂停、日预算完成等事件推送到企微/飞书/钉钉/PushPlus 等 webhook 渠道。不要自动化个人微信客户端作为主线。

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
python3 main.py -e cards.xlsx
python3 main.py -k 中止

# 从全量台账生成当天分段采集计划
python3 harness.py visual-plan-day --raw-input cards.xlsx
python3 harness.py visual-scheduler-status <plan_id>
python3 harness.py visual-session-run <plan_id> --session 1
python3 harness.py visual-heartbeat --mode prepare --plan-id <plan_id> --session 1
python3 harness.py visual-heartbeat --mode dispatch --plan-id <plan_id> --session 1
python3 harness.py visual-control status --plan-id <plan_id> --session 1
python3 harness.py visual-control pause --plan-id <plan_id> --session 1 --reason manual
python3 harness.py visual-control resume --plan-id <plan_id> --session 1 --reason manual
python3 harness.py visual-capture-worker --contract data/tasks/<plan_id>/sessions/session_01/midscene_session_worker_request.json
python3 harness.py visual-codex-extract-prepare --plan-id <plan_id> --session 1
python3 harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1
python3 harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1 --start
python3 harness.py visual-apply-extracted-rows --request data/tasks/<plan_id>/sessions/session_01/codex_extract/<keyword>/extract_request.json

python3 harness.py visual-one 中止
python3 harness.py visual-run <run_id> --limit 1
python3 harness.py visual-apply-extracted-rows --request data/tasks/<run_id>/sessions/session_01/codex_extract/<keyword>/extract_request.json
python3 harness.py visual-export <run_id>

# 后处理
python3 run_llm_filter.py -i data/tasks/xxx/合并结果.xlsx
python3 run_statistical_eval.py -i data/tasks/xxx/合并结果.xlsx
python3 run_final_assignment.py -i data/tasks/xxx/合并结果.xlsx

# 自检
python3 harness.py setup
python3 harness.py db
```

## 开发注意事项

- 不自动处理验证码或登录，只检测、暂停、通知人工。
- 如果页面显示登录提示，但人工明确确认当前采集 profile 已登录，允许仅刷新当前可见页面一次做状态复核；刷新后仍显示登录/风险状态则立即暂停并记录 `login_required` 或对应异常。
- 不抓接口、不读 cookies/storage、不读隐藏 DOM/HTML，不用 JS eval/DOMSnapshot/AX tree 提取页面结构或商品数据。
- 允许的浏览器自动化方向是 pure-vision：截图识别页面，坐标点击、键盘输入、页面级滚动。商品标题、价格、店铺、地区等采集结果必须来自保留的可见截图，不能从 HTML/DOM/network/storage 中抽取。
- 暂不采用 CDP/full-page screenshot 作为淘宝主线；它虽然未必能被网页 JS 直接感知，但会把路线带回浏览器调试控制层，并可能引入 layout/evaluate/network/viewport 等附带能力与长期环境画像风险。
- 采集访问路径应从淘宝首页可见搜索框输入关键词并触发搜索，不直接以带关键词的搜索 URL 作为常规采集入口。
- 视觉识别结果必须保留坐标、置信度和人工复核入口；正常 ingest 成功后删除原始截图，低置信/可自愈异常只写日志，登录/验证码/安全验证/疑似风控/连续异常等人工介入级别必须保留截图。
- 采集速度从属于账号安全和数据可审计性。
- 后处理资产必须和采集层解耦，确保视觉采集替换后仍能继续使用现有过滤、DB、LLM、统计和赋值流程。

## 下一步具体计划

1. **Midscene spike**
   - 连接专用 Chrome profile：`local/chrome-taobao-visual-profile`。
   - 从淘宝首页可见搜索框输入单关键词并触发搜索。
   - 保存首屏和滚动分屏截图到 `data/tasks/<run_id>/evidence/`。
   - 审计确认没有调用 DOM/HTML/network/storage/JS eval 读取能力。

2. **单关键词视觉闭环复测**
   - 运行 `python3 harness.py visual-one 中止` 创建任务。
   - Codex extract worker 从截图整理至少 5 条商品行，写 `rows_result.json`，再调用 `visual-apply-extracted-rows` 写入 `raw_rows.jsonl`/`raw_results.xlsx`。
   - 运行 `visual-export <run_id>`，确认 raw Excel 字段满足现有过滤链。

3. **异常状态验证**
   - 不为了测试主动诱发淘宝验证码、安全验证或风控；账号资产优先于异常覆盖率。
   - 优先用脱敏历史截图、手工构造/本地图片、非敏感页面模拟登录弹窗、白框架、验证码/安全验证遮罩，验证 `login_required`、`white_skeleton`、`captcha_required`、`needs_review` 等状态路径。
   - 真实淘宝环境只做被动留样：如果自然遇到登录、验证码、安全验证、疑似风控、白框架或连续异常，立即暂停、保留截图和事件日志，把该样本加入后续回归样本集。
   - 连续异常达到阈值后进入 `cooldown`，不自动刷新、不重复尝试。

4. **小批量试跑**
   - 用 3-5 个关键词创建任务，`visual-run <run_id> --limit 1` 分批运行。
   - 每个关键词之间保持人工可观察节奏，先验证稳定性，不追求速度。
   - 输出 raw Excel 后接 `filter_exported_results`、DB/LLM 过滤和统计赋值。
