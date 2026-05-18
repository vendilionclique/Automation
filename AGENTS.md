# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并进入规则/DB/LLM 过滤、统计评估和最终赋值流程。当前核心方向已调整为：本机 Chrome 真实登录态 + 低频 human-in-the-loop 操作 + 纯视觉截图证据 + Codex/视觉模型识别。采集控制层主线为 Midscene computer MCP。

旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集、项目内 Chrome profile 和旧项目副本已经从代码树删除。后续不要重新围绕这些路线新增功能。

## 协作与上下文原则

- 本项目的复杂任务默认使用 subagent team：凡是可交给子 agent 的代码阅读、日志扫描、测试观察、状态汇总、回归定位和风险复核，都应交给 subagent 并由主 agent 汇总。
- 主 agent 只负责调度管理、关键路径决策、少量必要命令、最终验收和对用户汇报；不要把大段代码、长日志、历史线程或测试输出都塞进主上下文。
- 由于 GPT-5.5 在 Codex 中发生上下文压缩后存在卡死风险，必须主动节约主上下文；长任务要用文件状态、项目记忆、subagent 输出和短摘要续航，而不是依赖一个长对话承载全部细节。
- 当任务需要持续监控时，主 agent 应维护简短 checklist 和明确 stop rule；重复轮询、日志 tail、证据枚举和大文件比对尽量交给 subagent 或只读脚本。

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

## 视觉判定复用规则

- 同一张截图只能做一次 VLM/page-state 判定；该判定结果必须同时承担验收、异常判断、关键词边界判断和后续状态推进。
- 禁止对同一张截图先发起 yes/no 式 `assert`，再用同一截图另发一次“怎么推进/是什么状态”的 VLM 判定；需要推进逻辑时，应让单次粗页面状态判定一次性返回 `state`、`visible_search_keyword`、`keyword_match`、`confidence` 和 `reason` 等必要字段。
- Python 控制层只能复用这一次判定产物做确定性分支，例如 `captured`、`needs_review`、`results_end`、关键词阻断或继续滚动；不能为了让流程跑通而对同一截图追加第二轮视觉询问。
- 如果单次判定结果不可解析、限流或置信不足，按 fallback/needs_review/cooldown 处理，并保留截图证据；不要通过重复询问同一截图来制造确认。

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

下一步应做真实 Midscene 留样复核：连接本机 Chrome 登录态，从淘宝首页可见搜索框输入单关键词，搜索后保存首屏和滚动分屏截图，并确认全程没有调用 DOM/HTML/network/storage 读取能力。遇到登录、验证码、安全验证、疑似风控、白屏骨架或未知页面时，只做被动留样和人工介入，不主动诱发风险状态。

### 2026-05-09 进一步审计修正

已安装并审计 JS 版 Midscene 1.7.10。结论更新为：淘宝主线使用 `@midscene/computer`，而不是 Web/CDP 路线。

原因：

- `@midscene/computer` 使用系统截图作为输入，动作输出为系统鼠标、滚轮、键盘事件，不连接浏览器 CDP，也不读 DOM/HTML/network/cookies/storage。
- `@midscene/web` Puppeteer/CDP 路线虽然定位主要来自截图/VLM，但默认仍包含 `window.innerWidth/innerHeight` eval、`waitForSelector('html')`、`waitForNetworkIdle`、XPath cache、`page.screenshot()`/CDP screenshot 等页面辅助能力，只适合作为备选和对照。
- Web bridge/Chrome extension 路线明确会 attach `chrome.debugger` 并多次 `Runtime.evaluate` 注入脚本、读取 `document.readyState`、获取节点树/XPath cache，不适合作为淘宝主线。
- Codex App 接入方向应为注册 `midscene-computer` MCP，由 Codex 作为上层 agent 调度；Midscene 只负责截图、视觉定位、坐标点击、键盘输入、滚动。
- 项目侧已新增 `modules/midscene_computer_driver.py`，当前主线生成 session 级 `midscene_session_worker_request.json` 与 `midscene_session_worker_instructions.md`。
- 当前推荐混合架构：Codex 是任务入口、异常裁判、证据复核和后处理编排；Midscene 可使用外部便宜 VLM 进行局部视觉 grounding（找搜索框、按钮、可见列表区域），但商品字段最终由短命 Codex extract worker 基于保留截图识别，再通过 `visual-apply-extracted-rows` 确定性落盘。外部 VLM key 放在本机 `local/midscene-computer.env`，通过 `local/start_midscene_computer_mcp.sh` 注入 MCP，不提交仓库。

详细记录见 `docs/midscene_route_analysis.md`。

## 当前进展（2026-05-07 至 2026-05-14）

- Midscene computer MVP 已跑通过；当前高级版本继续沿用系统截图 + 系统鼠标/键盘/滚轮的 pure-vision 主线。
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
  通过本机 Midscene computer MCP stdio launcher 执行 contract，保存 viewport
  tile 截图并写标准 `keyword_result.json` / `session_worker_result.json`。如果
  MCP 环境不可用，写 `real_not_available`，不伪装为已采集。
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

## 当前进展（2026-05-15）

- 已完成一次 subagent team 代码审查与修复闭环，重点解决 capture/control、extract/apply/export、scheduler 状态机和项目配置便携性问题。
- capture worker 已解析 `@midscene/computer` MCP `act` 返回文本与 `isError`。登录、验证码、安全/风控、弹窗、白屏/骨架、加载失败、`stop/report failure` 等异常不再标记为 `captured`。
- `unknown`、页面状态检测失败或无法确认结果页时，默认进入 `needs_review` / `manual_review_needed` 并保留截图；只有明确可见结果页才进入正常 `captured` 路径。
- `visual-control pause|stop|cooldown|lock` 已接入运行中 worker 轮询；关键词之间、tile 之间、长 sleep 中以及等待 MCP request 时都会尽快响应 supervisor 控制。未来即时通讯软件 + CC connect 到 Codex supervisor 后，也应继续走 supervisor 调用 `visual-control`、scheduler/worker 读控制面的路径，不依赖人工手改配置文件。
- 已实现 keyword deadline、MCP request 分片等待、连续异常计数和 cooldown/人工介入路径。超时和连续异常要记录诊断，条件允许时继续后续关键词；极端或连续异常进入暂停/冷却，不无脑刷新或重复尝试。
- `real_not_available` 表示真实 Midscene computer MCP、权限或本机采集能力不可用；该状态现在映射为 `paused_needs_human`，不再作为可运行 `failed` 反复调度，避免长期堵住 scheduler。
- raw 行 `采集时间` 已改为截图证据时间；`capture_time_for_assignment` 和最终 `淘宝采集时间` 应基于该证据时间链路。缺失截图时间时允许 fallback 当前时间，但必须写 warning/source 以便追溯。
- 低置信行允许进入 raw，因为规则过滤、DB/LLM 和统计链路是后续硬过滤器；但必须保留置信度、坐标、warning、截图证据和人工复核入口。
- `visual-export --filter` 的多关键词路径已改为按 `搜索关键词` 分组推断牌名并过滤，不再把 `run_id` 当业务关键词或牌名。
- Codex extract request/apply 链路已加入 request schema、关键词、截图文件存在性和 stale/mismatch 校验；异常结果进入 `needs_review`，不误标完成。
- `visual-apply-extracted-rows` 已具备幂等性：成功 apply 后即使截图被清理，重复执行也不会把已完成记录覆盖成 `needs_review`。
- `visual-apply-extracted-rows` / `modules.vision_extract.ingest_rows` 已加入确定性脚本去重，不由 Codex extract worker、agent 智能、DB 或 LLM 事后判断。硬去重仍为同 `搜索关键词` + `商品名称` + `现价` + `店铺名称` 完全一致即跳过；软去重只在同关键词、同价格、店铺名相似度达到 `[VISUAL_DEDUPE] store_similarity_threshold`（默认 0.70）后比较标题，标题相似度达到 `title_similarity_threshold`（默认 0.95）才判重复并跳过写入 raw。标题相似度低于阈值时，即使同店同价也保留为同店不同 listing。相似度为脚本内 Levenshtein 归一化，不依赖第三方包，不枚举 MTG 业务 token；`apply_result` / `ingest_result` 记录 `fuzzy_duplicates_removed` 与样例。
- extract worker 启动台账已加入 `launched_at` 和 stale TTL，避免旧 pid 或残留 running 状态长期阻塞 dispatch。
- extract worker 启动命令已修正为本机 Codex CLI 支持的配置覆盖：通过 `-c sandbox_mode=...` 和 `-c approval_policy=...` 显式设置策略，默认追加 `--ignore-rules`；图片通过 `-i` 传入，prompt 通过 stdin 注入，避免 `-i` 变长参数吞掉 prompt。worker stdout/stderr 每次启动覆盖写入，避免旧日志污染判断。
- tracked 项目配置已移除个人机器绝对路径；macOS 是当前主线，Windows/PowerShell 脚本保留为远期/实验路径。
- 已新增聚焦测试和 portable config 检查；当前验证命令为 `.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py`、`.venv/bin/python -m unittest discover -s tests`、`scripts/check_portable_config.sh`。
- 已将 tracked 默认 Midscene grounding 模型切回付费高速 GLM-4.6V-FlashX
  `glm-4.6v-flashx`，包括 `config/settings.example.ini`、
  `local/midscene-computer.env.example`、Codex sync 脚本、README/docs 和相关测试。
  `MIDSCENE_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4`，
  `MIDSCENE_MODEL_FAMILY=glm-v`，`api_key_env` 仍为 `MIDSCENE_MODEL_API_KEY`，
  `MIDSCENE_MODEL_REASONING_ENABLED=false`，`MIDSCENE_MODEL_TEMPERATURE=0`。为降低
  实时 grounding 延迟，thinking/reasoning 默认关闭。
- VLM 供给已确认为当前 capture 主线的核心瓶颈：在 pure-vision 边界下，Midscene
  computer 只是系统截图、坐标点击、键盘输入和滚动动作层；搜索框定位、页面状态判断、
  结果页确认和异常识别都需要稳定视觉 grounding。免费 VLM 不稳定时，capture worker
  必须按 `needs_review` / `cooldown` 停止，不能把失败伪装成 captured。
- 架构判断更新：不推荐让 Codex 长命会话承担实时视觉控制；也不推荐“Midscene 接
  VLM，但每一步点击决策交给 Codex”的双脑方案，因为会增加通讯成本、状态同步失败面和
  调试复杂度。Codex supervisor 只适合低频异常裁判和 `visual-control` 控制面；Codex
  短命 worker 继续适合异步 extract，因为截图已落盘、可重跑、失败可留样。
- DeepSeek 本地视觉路线已评估：DeepSeek-VL2 / Janus-Pro 更偏通用视觉理解或研究模型，
  不是 Midscene 原生适配的 GUI grounding 主力。DeepSeek-VL2-tiny 可作为研究备选，
  但需要自建 OpenAI-compatible image endpoint、坐标格式映射、prompt/解析和回归测试；
  Janus-Pro 不推荐用于淘宝页面坐标点击。
- 本机硬件为 Apple M4 Mac mini、16GB 统一内存、10 核 GPU、Metal 支持；可以实验
  2B-4B 量化本地 VLM 做低频 grounding，7B 量化可能可跑但会有明显内存和延迟压力。
  当前未安装全局 Ollama/llama.cpp/MLX/torch/transformers/vLLM。若走本地实验，优先
  考虑 Midscene 生态更匹配的 Qwen2.5-VL/Qwen3-VL 小尺寸量化或 UI-TARS，而不是
  DeepSeek；生产主线更推荐购买稳定云端 VLM API key。

## 当前进展（2026-05-16）

- 术语固定：`scheduler` 是确定性计划层，负责从全量台账生成 daily plan、按
  `daily_session_count` 切 session、选择 due session；`heartbeat` 是短命唤醒动作，
  负责 `sync` / `prepare` / `dispatch advice`，不打开 Chrome、不触碰淘宝、不常驻；
  `supervisor` 是人工或 Codex App automation 唤起的非常驻监督者，只做状态查看、
  异常裁判和 `visual-control`。
- scheduler 本身仍不做长期会话；整日生存性依赖 Codex App Automations 或等价可见
  定时器按小时级唤醒 `visual-heartbeat --mode all`。推荐 3-4 个每日固定唤醒点，
  与 `daily_session_count` 对齐；不要用长驻聊天会话承担全天调度。
- session due-time 已进入 daily plan：生产可配置 `[SCHEDULER] session_due_times`
  为 `09:00,13:00,17:00,21:00` 这类固定时刻，数量必须等于
  `daily_session_count`；短间隔观察测试可设置 `session_due_interval_minutes`
  为几分钟，从 plan 创建时间起依次让 session 到期，且 interval 优先于固定时刻。
- heartbeat 已新增 capture worker 活性兜底：每次 `sync` / `dispatch` 被唤醒时检查
  `capture_worker_runtime.json`。如果 runtime 仍是 `running`，但无
  `session_worker_result.json` 且 pid 已不存在，或 `updated_at` 超过
  `[SCHEDULER] capture_worker_stale_after_minutes`，则标记为
  `failed_recoverable` / `capture_worker_stale`，并把该 session 未完成记录恢复为可重跑。
- `visual-heartbeat --mode dispatch` 的返回中已加入 `capture_worker_liveness`、
  `capture_worker_stale` 和 `capture_start_allowed`。外部 automation 只有在
  `capture_start_allowed=true` 时才能启动 `worker_commands.capture`；如果 worker
  仍然 active，不得重复启动 capture worker。
- `harness.py visual-capture-watchdog --plan-id <plan_id> --session N --start`
  是 Codex App Automation 推荐调用的 session 级 bounded watchdog：到点后在该
  session 生命周期内常驻，循环 heartbeat/liveness，只在
  `capture_start_allowed=true` 且 capture 命令存在时启动或恢复单个 capture worker。
  session 完成、人工异常、control block、idle timeout 或 restart 预算耗尽后退出；
  不加 `--start` 时仅 dry-run/advice。旧 `visual-automation-tick` CLI 已下线，
  automation 应直接使用 heartbeat 或 session 级 watchdog。
- 历史真实测试显示 GLM-V 可用于 Midscene grounding；当前默认已切回
  GLM-4.6V-FlashX `glm-4.6v-flashx`。thinking/reasoning 默认关闭，避免实时 grounding 变慢。
- 真实测试中 `ClearInput` 在结果页搜索框上出现失焦风险，表现为页面级全选/清空倾向。
  GLM-4.6V-FlashX 后采集主线已改为 bounded act 搜索/滚动，由 prompt 约束可见搜索框定位、输入、
  提交、等待和滚动；`Tap`、`Input`、`KeyboardPress`、`Scroll` 等短动作工具只保留为
  调试/人工修正/后续 fallback 能力，不再作为默认采集路线。
- capture worker 已接入截图文件级 VLM JSON page-state classifier：当
  `allow_page_state_json_classifier=true` 时，
  `tile_00` 和后续 tile 截图会先落盘，再由 OpenAI-compatible image chat 端点只基于该截图
  返回结构化 operational state
  (`visible_ready` / `visible_results` / `search_results` / `results_page` /
  `empty_result` / `login_required` / `captcha_required` / `risk_suspected` /
  `white_skeleton` / `popup_blocked` / `unknown`)。这里不调用 Midscene MCP `assert`
  来承载 JSON 分类；本地 `page_state.py` 的颜色/区域 heuristic 只作为 classifier
  关闭、不可用、超时或无法解析时的 fallback；`unknown`、
  登录、验证码、风控、白屏和弹窗仍必须进入 `needs_review`，不能为跑通 session
  自动标记 `captured`。
- JSON page-state classifier 的边界是“粗页面状态”，不输出商品标题、价格、店铺、
  价格可信度、业务过滤或统计决策；商品字段仍只由 Codex extract worker 基于保留的
  可见截图抽取，再由 `visual-apply-extracted-rows` 确定性落盘。
- bounded act 搜索和滚动 prompt 已补强：搜索框填入关键词后鼠标点击可见搜索按钮优先，
  Enter 只在按钮不可见/不可点击时作为降级，并记录 diagnostics；如果 Codex、
  Terminal、Cursor、VS Code 或其他 app 在前台，先切回既有
  Chrome 采集窗口，不得把关键词或滚动动作打到非 Chrome 应用。Python 侧负责截图、
  粗页面状态判断、tile 保存、异常停机和 watchdog 自恢复，不把商品字段交给 Midscene。
- heartbeat 在 control 已 cooling/pause/stop 时仍会先同步已落盘的 worker 结果和
  stale runtime，再返回 paused，避免半截 capture 结果因控制面阻断而长期不同步。
- 已完成 bounded act 路线收口清理：旧 `visual-one` / `visual-run` 单关键词 MVP
  入口、`visual-auto-tick` / `visual-automation-tick` 兼容 CLI、旧
  `MidsceneComputerRequest`/per-keyword request 生成器、`modules/visual_automation_tick.py`
  和对应测试已下线。当前采集入口只保留 daily plan、heartbeat、session contract、
  session watchdog、capture worker、Codex extract worker 和 deterministic apply/export。
- Midscene MCP 预批准面已收窄为主线必要工具：`computer_connect`、`take_screenshot`、
  `act` 与 display/list/connect 辅助；`assert` 不再作为 unattended page-state classifier
  或关键词边界工具预批准；`Tap`、`Input`、`KeyboardPress`、
  `Scroll`、`ClearInput` 不再由项目同步脚本默认批准。若未来要恢复短动作 fallback，
  必须重新作为显式实验设计、补测试和文档，不可悄悄接回默认采集路线。
- 已清理本机可重建缓存和明显临时残留：`.DS_Store`、Python `__pycache__`、
  `midscene_run/log/ai-*.log`、泛名测试运行目录 `data/tasks/plan` 与 `data/tasks/run`。
  不清理 `config/settings.ini`、`local/midscene-computer.env`、Chrome profile 和真实
  `data/tasks/supervisor_20260516_*` 证据目录。

## 当前进展（2026-05-17）

- 单 session 8 关键词测试使用同一输入表生成 `supervisor_20260517_single_session_8kw`，
  确认 watchdog、capture worker 和 extract
  drain 可以按文件状态协同：extract drain 在无 keyword_result 时等待，watchdog 不重复
  启动已有 capture worker，capture worker 能从淘宝结果页保存 viewport tile。
- 真实留样显示 `万智牌 力量护手` 在 `tile_03` 已到淘宝搜索结果底部，页面出现长页码条、
  上一页/下一页、跳页输入、规则协议、版权/备案/友情链接和右侧滚动条到底等典型底部
  特征；`tile_04` 与 `tile_03` 高度相似，实测脚本相似度约 `0.999974`。
- Midscene/VLM 和 JSON page-state classifier 都按无状态 API 使用；每次 `act` 只依赖当前
  prompt 和当前可见屏幕，classifier 只依赖当前已落盘截图。因此 prompt 已补强：淘宝底部不要求固定 `1/100` 这类页码分母，也不要求出现
  字面“没有更多”；只要长页码条、页码 current/total、页脚/协议/版权/ICP/备案/友情链接
  或滚动条到底等底部信号清楚可见，就应判为 `results_end` 或报告已到底，不继续滚动。
- capture worker 已加入 Python 侧相邻 tile 相似度早停：只在前后两张截图都属于可采集
  结果页状态时比较；若高度相似，则记录 `similar_adjacent_tile` / `capture_stop`，删除当前
  重复 tile，只保留第一张证据图并进入下一个关键词。`unknown`、登录、验证码、风控、白屏、
  弹窗等非可采集状态不触发删除，仍保留证据供人工复核。
- 搜索框关键词确认规则已调整为更严格的关键词边界策略：每个新关键词必须先从淘宝首页或已确认的
  首页状态进入普通搜索框并提交搜索，`tile_00` / post-act 验收必须证明当前关键词已经进入可采集
  结果页。JSON page-state classifier 读出旧关键词、读不清且没有强证据，或画面仍是旧结果页时，
  capture worker 不得把旧页 reset/retry 后的任意首屏当作成功，也不得直接标记 `captured`；
  应保留失败截图和 diagnostics，进入 `needs_review` / cooldown / 人工介入。
- 普通未到底滚动期间不要求必须看清搜索框内容；只要当前 viewport 被判断为可采集结果页，就
  继续滚动截图。新搜索后的 `tile_00` / post-act 验收是防止旧关键词污染新关键词的硬边界；
  相邻 tile 高相似早停和 `results_end` 只是当前关键词采集边界，不触发当前关键词重搜。
- `results_end` 现在按“当前关键词已经到底”处理：即使底部搜索框关键词读不清或读出疑似旧关键词，
  也只把 `visible_search_keyword` / `keyword_match` 信息写入 diagnostics，保留当前到底 tile 并结束
  当前关键词，不 reset/retry 后把重搜首屏当作完整采集。新关键词 `tile_00` / post-act 验收失败时，
  失败截图副本（例如 `tile_00_initial_failed.png`）必须保留，并进入人工复核或冷却。
  硬异常如登录、验证码、风控、弹窗、白屏、限流等不能被 reset 掩盖，仍进入人工复核/冷却。
- 不恢复“点搜索框、全选、复制、读剪贴板”的默认主线；也不把 `Tap`、`Input`、
  `KeyboardPress`、`ClearInput` 等短动作接回 unattended capture。搜索入口只走每关键词首页
  bounded `act`，Python 只用截图 JSON page-state classifier 做验收与停机决策。
- 架构判断：暂不新增 session orchestrator，也不把 `visual-capture-watchdog` 和
  `visual-codex-extract-drain` 合并。二者都是 session 级看护/排水进程，但失败域不同：
  watchdog 管 heartbeat、Midscene/capture worker、restart budget 和账号/控制面异常；
  extract drain 管 captured 截图队列、Codex extract worker、apply 和 stale launch。
  合并核心 loop 会增加第三套 runtime/lock/汇总语义和跨域状态机复杂度，当前收益不足。
  保持现状：需要联动测试时同时启动 watchdog 与 extract drain；未来如确有需要，只考虑
  很薄的 wrapper 统一启动和汇总，不改两个核心状态机。
- `supervisor_20260517_single_session_8kw_round3/round4` 复测暴露了前台与旧关键词边界问题：
  WPS 前台截图、旧淘宝搜索词未切换都必须停为诊断状态，不能标记 captured。更重要的是，
  不得用无人值守 Python/AppleScript 循环强制激活 Chrome、`Cmd+L`、输入淘宝域名或反复跳转
  来“修复”旧关键词；这会造成抢焦点、无法人工打断和淘宝风控风险。旧关键词页切换必须先
  重新设计成可停、可观测、低频、有硬 stop rule 的方案，并经过脱敏/非淘宝页面测试后才能
  恢复真实淘宝采集。
- 目标契约链路已落地为 `Goal Contract -> VLM Evidence Check -> Python Gate`：每个关键词
  保留 `goal_contract.json`、`action_trace.jsonl`、`evidence_check.jsonl`、
  `capture_decision.jsonl` 和 `keyword_result.json`。Python 只保存目标、结构化验收结果、
  repair 预算和保险丝；页面判断仍交给 VLM，gate 只做 `accept` / `repair_once` / `stop`。
- 旧结果页/到底页的 home-entry repair 已明确允许一条可见 UI 路径：配置
  `[MIDSCENE_COMPUTER] allow_bookmark_home_entry_repair=true` 时，bounded act 可点击可见
  新标签页按钮，再点击书签栏淘宝按钮进入首页。仍禁止地址栏、URL 输入、脚本和页面结构读取；
  `new_tab_policy=bookmark_home_entry_repair_only`，旧标签页只有在可见确认关闭后仍至少保留
  一个 Chrome 标签页时才可关闭。
- Midscene grounding 主线已切回付费高速 GLM-4.6V-FlashX：`model_name=glm-4.6v-flashx`、
  `base_url=https://open.bigmodel.cn/api/paas/v4`、`model_family=glm-v`，thinking/reasoning 默认关闭。
  本机 `local/midscene-computer.env` 也必须同步，否则真实 capture 会继续用旧模型。
- 当前验证通过：`.venv/bin/python -m unittest tests.test_visual_capture_worker`、
  `.venv/bin/python -m unittest tests.test_codex_extract tests.test_visual_capture_watchdog`、
  `.venv/bin/python -m unittest discover -s tests`、`.venv/bin/python -m py_compile harness.py
  modules/*.py tests/*.py`、`scripts/check_portable_config.sh`。
- page-state 已从“Midscene MCP `assert` + heuristic 兜底”收口为“已落盘截图文件 ->
  OpenAI-compatible VLM JSON classifier -> Python gate”。新模块
  `modules/page_state_classifier.py` 只读取截图文件，使用 `[MIDSCENE_MODEL]` /
  `MIDSCENE_MODEL_API_KEY`，不碰 DOM/network/storage/CDP/cookies/clipboard；输出
  `state`、`confidence`、`reason`、`visible_search_keyword`、`keyword_match`。本地
  `page_state.py` heuristic 只作为 classifier 不可用时的降级诊断，登录、验证码、风控、
  弹窗、白屏、限流、unknown 等仍不得误标 `captured`。
- 本机 `local/midscene-computer.env` 支持 `export MIDSCENE_MODEL_API_KEY=...` 写法；
  Python classifier 请求显式使用 `certifi` CA bundle，解决 macOS venv 下
  `CERTIFICATE_VERIFY_FAILED` 导致的 `URLError`。
- 真实 1 关键词 smoke `20260517_172653` 已通过：关键词 `万智牌 白袍甘道夫`，
  watchdog `session_complete`，session result `captured`，`page_state_v2.jsonl`
  三次状态均为 `source=json_classifier`，`tile_00` 读到
  `visible_search_keyword=万智牌 白袍甘道夫` 且 `keyword_match=true`；`tile_02`
  因与 `tile_01` 相似度 `0.994123` 被删除，保留 `tile_01` 作为证据。
- 清理边界已执行：保留已验证成功资产 `data/tasks/20260517_172653`、所有真实
  `supervisor_*` 证据、`config/settings.ini`、`local/midscene-computer.env` 和 Chrome
  profile；删除项目层 `__pycache__` / `.DS_Store`、泛名测试任务 `data/tasks/plan` /
  `data/tasks/run`、成功前非 `supervisor_*` 的失败临时 plan
  `20260517_172227` / `20260517_172444`，以及可重建的 `local/midscene-run` 报告日志。
- unattended Midscene MCP 预批准面进一步收窄：只预批准 display/list/connect、
  `take_screenshot` 和 bounded `act`；`assert`、`Tap`、`Input`、`KeyboardPress`、
  `Scroll`、`ClearInput` 等仅保留为人工/调试能力，不再作为 cron 默认批准工具。

## 当前进展（2026-05-18）

- Home-entry 朴素 reset 边界已完成并通过单元验证：每个关键词开头只接受普通
  `taobao.com` 首页/首页搜索入口；旧结果页、到底页、`huodong.taobao.com`、
  `dailygroup`、`s.taobao.com/search`、`world.taobao.com`、`tmall.com`、采购优选、
  明确活动页/会场/campaign/purchase-selection 页面或外站，都不能直接使用当前搜索框搜下一个关键词。
- JSON page-state classifier 已禁止把 `is_home_feed` 当作 `state` 输出；如果模型误把
  `state=is_home_feed` 返回，普通淘宝首页推荐流会归一为 `visible_ready`，但带结果页结构、
  已提交搜索证据或明确非普通首页证据时归为 `unknown`。不要用裸“活动”二字判断异常，
  普通首页的活动推荐/促销入口不能被误伤。
- pre-keyword home-entry 失败现在允许一次 bounded reset/retry；retry 后仍无法确认普通淘宝首页时，
  stop reason 统一为 `home_entry_reset_failed`，并在 session 层立即停批次，避免继续采下一个关键词污染上下文。
  登录、验证码、风控、权限面板、非 Chrome 前台等硬异常仍不走该 retry。
- 本轮没有改变 `post_keyword_cleanup` / `Command+W` 行为；cleanup 仍只作为已成功关键词后的诊断/清场尝试，
  不能替代下一个关键词自己的 pre-entry 验收。
- 429 / rate limit 是 Midscene/VLM 视觉供给临时限流，不属于某个业务阶段的页面失败；home-entry、
  search-submit、capture scroll、清场以及辅助前台/弹窗 `act` 都必须走统一冷却重试：
  保留脱敏诊断与 `rate_limit_retries` 记录，按 `[RATE_LIMIT] rate_limit_retry_attempts`、
  `rate_limit_cooldown`、`rate_limit_backoff` 在原业务阶段内有限重试；预算耗尽后才停为
  `rate_limited` / cooldown / supervisor 复核，不能把限流伪装成 captured，也不能只在 home-entry 特判。
- 当前验证通过：`.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py`、
  `.venv/bin/python -m unittest discover -s tests`（175 tests, 1 skipped）、
  `scripts/check_portable_config.sh`。本轮未启动真实淘宝采集。

## 新核心流程

1. 从全量输入台账读取卡牌名、`preferred_mode` 和 `淘宝采集时间`
2. 默认只选择 `preferred_mode=statistical` 且 `淘宝采集时间` 缺失或过期的牌名进入当天候选；`skip` 和 `with_keywords` 不进入当前默认统计采集池
3. 按日预算和 session 数自动生成分段采集计划，无需人工切表
4. 为每个关键词创建视觉采集任务与证据目录
5. heartbeat 根据 `control.json`、session 状态和 worker 结果决定是否准备下一段
   session；它只做短命确定性判断，不调用大模型、不控制浏览器
6. capture worker 使用本机 Chrome 真实登录态，低频、可暂停地通过 bounded act 从淘宝
   首页可见搜索框搜索、提交并滚动；Python 负责系统截图、状态判断、保存 viewport tiles
   和异常停机
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
- capture watchdog 的语义是“在一个已到期 session 生命周期内看护 capture worker”；
  它必须 bounded、单实例、按 `capture_start_allowed` 启动/恢复，不能并发或无限重启
- capture worker 和 Codex extract worker 通过文件、lease/runtime 和事件日志解耦；Codex
  supervisor 只通过 `visual-control` 介入，不直接改 worker 产物
- 每个 session 内处理一批关键词；关键词之间使用分钟级长暂停，关键词内部使用分段概率短暂停；8-18 秒这类短间隔只允许在测试/观察配置中显式覆盖，不能作为生产默认
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
- v1 最多按 `PAGE_SAMPLING.max_tiles_per_keyword` 采完整页可见 tiles，不翻页；若 VLM
  当前屏幕判断为 `results_end`，或 Python 判断相邻可采集 tile 高度相似，则提前停止。
- `PAGE_SAMPLING.target_listings_per_keyword` 只是第一页结果的近似保护上限；淘宝会夹杂广告、评价、占位等内容，真实商品数会在该数字附近波动。
- v1 采用“capture worker 批量截图 + Codex extract worker keyword 级抽取 + `visual-apply-extracted-rows` 去重/落盘”；
  逐 tile 商品行动态识别留作后续优化。

任务状态：`pending`、`running`、`opening_search`、`page_loading`、`visible_ready`、
`captured`、`extracting`、`extracted`、`needs_review`、`success`、`cooldown`、
`paused_needs_human`、`paused_needs_supervisor`、`cooling_down`、
`failed_recoverable`、`failed_hard`、`failed`、`skipped`

账号状态：`healthy`、`login_required`、`captcha_required`、`popup_blocked`、`risk_suspected`、`cooling_down`、`locked`

失败原因：`login_required`、`captcha_required`、`page_not_loaded`、`white_skeleton`、`popup_blocked`、`screenshot_failed`、`ocr_low_confidence`、`manual_review_needed`、`rate_limited`、`unknown`

## 远期协作方向（暂不排期）

未来可能拆出员工版轻量采集端，但不作为当前开发日程。员工版不包含 DB/SSH/后处理/最终赋值资产，只负责使用本机 Chrome 登录态和付费高速 GLM-4.6V-FlashX / 视觉自动化 Agent 采集可见结果，输出标准化 `raw_results.xlsx`、`raw_rows.jsonl`、截图证据和 manifest；thinking/reasoning 默认关闭。

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
python3 harness.py visual-capture-watchdog --plan-id <plan_id> --session 1 --start --poll-seconds 30 --idle-timeout-seconds 900 --max-restarts 2
python3 harness.py visual-control status --plan-id <plan_id> --session 1
python3 harness.py visual-control pause --plan-id <plan_id> --session 1 --reason manual
python3 harness.py visual-control resume --plan-id <plan_id> --session 1 --reason manual
python3 harness.py visual-capture-worker --contract data/tasks/<plan_id>/sessions/session_01/midscene_session_worker_request.json
python3 harness.py visual-codex-extract-prepare --plan-id <plan_id> --session 1
python3 harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1
python3 harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1 --start
python3 harness.py visual-apply-extracted-rows --request data/tasks/<plan_id>/sessions/session_01/codex_extract/<keyword>/extract_request.json

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
- capture 与 extract 必须分离：capture worker 只负责 Chrome 前台/淘宝页面状态、关键词搜索、截图证据、manifest 和 diagnostics；商品标题、价格、店铺、地区等字段只由 Codex extract worker 基于已保存截图抽取，再由 `visual-apply-extracted-rows` 确定性落盘。
- 当前 capture 重建主线要求每个关键词先回到淘宝首页或已有淘宝首页状态，再从首页可见搜索框低频搜索当前关键词；旧搜索结果页不能直接当作新关键词入口。
- 2026-05-17 接棒收口后，朴素业务流程固定为：关键词开始前先确认淘宝首页/普通搜索入口；从首页搜索框提交当前关键词；`tile_00` 必须证明商品列表页属于当前关键词；滚动采集可见 tiles，遇到到底或相邻可采集 tile 高度相似则结束当前关键词；商品字段抽取仍在 capture 之后由 Codex extract worker 处理。
- `visible_ready` 只表示当前截图是正常可用页面，不是登录、验证码、风控、白屏、阻断弹窗或非 Chrome 前台。首页/search-entry 阶段只要 VLM 判为 `visible_ready` 就可作为入口继续，搜索框里的推荐词、placeholder、热搜词或旧文案不作为阻断依据；关键词是否正确只在商品列表页/结果页阶段通过 `visible_search_keyword` / `keyword_match` 做硬边界。
- 第一个关键词也应默认走首页入口确认：session contract 写入 `require_initial_home_entry=true`。后续关键词无条件先做 pre-entry；如果上一个关键词的 post-keyword cleanup 未能确认回到首页，只记录诊断并把机会交给下一个关键词的 pre-entry repair，pre-entry 仍失败时再停为人工复核/由 watchdog 后续恢复。
- post-keyword cleanup 只对干净 `captured` 且后面还有关键词时执行，用低频可见 UI 动作关闭/离开当前结果页并尝试露出淘宝首页入口；cleanup 失败不能把已采集关键词改成失败，也不能立刻截断 session，只写入 `post_keyword_cleanup` diagnostics。
- 旧结果页/到底页允许的有限 home-entry repair 是：在配置
  `[MIDSCENE_COMPUTER] allow_bookmark_home_entry_repair=true` 时，仅通过可见 UI
  点击浏览器新标签页按钮，再点击书签栏淘宝按钮回首页；仍禁止地址栏、URL 输入、脚本、
  DOM/HTML/network/storage 读取。修复产生的旧标签页只有在可见标签栏确认关闭后仍至少
  保留一个 Chrome 标签页时才允许关闭，不能关闭最后一个标签页。
- Chrome 前台恢复必须 bounded：每个关键词最多 2 次尝试把焦点恢复到既有 Chrome 采集窗口；2 次后仍不是 Chrome/淘宝相关画面，必须停为 `needs_review` 或 `paused_needs_human`，保留截图和原因，不得无人值守循环抢焦点。
- 新关键词 `tile_00` / post-act 必须做首屏关键词边界硬验收；只有能证明当前关键词已经进入可采集淘宝结果页，才允许继续滚动并最终标记 `captured`。
- 2026-05-17 首页清场测试后新增硬规则：`tile_00` 不能只凭“搜索框里是当前关键词”和“页面有商品卡片”通过；必须同时证明 `search_submitted=true`、`search_box_text_kind=actual_input`、`is_home_feed` 不是 true，并有 `result_page_evidence` / `url_or_page_evidence` 等搜索结果页结构证据。若仍是首页推荐流、猜你喜欢、频道/活动流，或点击搜索未真正提交，应写 `search_submit_unconfirmed` / `search_results_structure_unverified`，先走一次 home-entry retry，仍失败则停为人工复核并保留 `tile_00_initial_failed.png`。
- 旧页面不能按新关键词 `captured`：读到旧关键词、读不清关键词且没有强证据、非 Chrome 前台、未知中间态、底部旧结果页或任何登录/验证码/风控/弹窗/白屏状态，都必须进入 `needs_review`、`cooldown` 或人工介入，不能为了推进 session 放宽为成功。
- extract 是截图落盘后的可选后处理；本轮 capture 重建不得因为 extract 未自动 drain 而改变 capture 的成功边界。
- `config/settings.example.ini` 必须保留可直接迁移的非敏感默认值；API key、数据库/SSH 主机账号密码、本机 Excel 路径等敏感或机器本地项留空，调度、capture、page sampling、watchdog、视觉行为等非敏感参数不要空着，方便新机器复制为 `config/settings.ini` 后只补敏感信息。
- 本地练习场由开发线程提供并先验收：至少覆盖非 Chrome 前台、Chrome 前台恢复 2 次失败、每关键词回首页、旧关键词页防误判、登录/验证码/风控/弹窗/白屏/未知状态停机；真实淘宝恢复前必须先用练习场证明这些边界。
- 如果页面显示登录提示，但人工明确确认当前采集 profile 已登录，允许仅刷新当前可见页面一次做状态复核；刷新后仍显示登录/风险状态则立即暂停并记录 `login_required` 或对应异常。
- 不抓接口、不读 cookies/storage、不读隐藏 DOM/HTML，不用 JS eval/DOMSnapshot/AX tree 提取页面结构或商品数据。
- 允许的浏览器自动化方向是 pure-vision：截图识别页面，坐标点击、键盘输入、页面级滚动。商品标题、价格、店铺、地区等采集结果必须来自保留的可见截图，不能从 HTML/DOM/network/storage 中抽取。
- 暂不采用 CDP/full-page screenshot 作为淘宝主线；它虽然未必能被网页 JS 直接感知，但会把路线带回浏览器调试控制层，并可能引入 layout/evaluate/network/viewport 等附带能力与长期环境画像风险。
- 采集访问路径应从淘宝首页可见搜索框输入关键词并触发搜索，不直接以带关键词的搜索 URL 作为常规采集入口。
- 视觉识别结果必须保留坐标、置信度和人工复核入口；正常 ingest 成功后删除原始截图，低置信/可自愈异常只写日志，登录/验证码/安全验证/疑似风控/连续异常等人工介入级别必须保留截图。
- 采集速度从属于账号安全和数据可审计性。
- 后处理资产必须和采集层解耦，确保视觉采集替换后仍能继续使用现有过滤、DB、LLM、统计和赋值流程。

## 下一步具体计划

1. **单关键词截图到行闭环**
   - 基于已成功的 `20260517_172653` 或新建 1 关键词 plan，运行
     `visual-codex-extract-prepare` / `visual-codex-extract-dispatch --start`。
   - Codex extract worker 从保留截图整理商品行，写 `rows_result.json`，再调用
     `visual-apply-extracted-rows` 写入 `raw_rows.jsonl` / `raw_results.xlsx`。
   - 运行 `visual-export <run_id> --filter`，确认 raw Excel、filtered Excel、LLM/统计输入字段满足现有过滤链。

2. **小型 session 连贯复测**
   - 运行 `python3 harness.py visual-plan-day --raw-input cards.xlsx --random-sample 3 --session-count 1` 创建小型 daily plan。
   - 同时启动 session watchdog 与 extract drain，验证 3 个关键词从 capture 到 extract/apply 的文件协同。
   - 如果未完成，按根因链报告：前台恢复、搜索提交、JSON classifier、关键词边界、滚动/到底、extract/apply 分别定位，不只报 terminal status。

3. **异常状态验证**
   - 不为了测试主动诱发淘宝验证码、安全验证或风控；账号资产优先于异常覆盖率。
   - 优先用脱敏历史截图、手工构造/本地图片、非敏感页面模拟登录弹窗、白框架、验证码/安全验证遮罩，验证 `login_required`、`white_skeleton`、`captcha_required`、`needs_review` 等状态路径。
   - 真实淘宝环境只做被动留样：如果自然遇到登录、验证码、安全验证、疑似风控、白框架或连续异常，立即暂停、保留截图和事件日志，把该样本加入后续回归样本集。
   - 连续异常达到阈值后进入 `cooldown`，不自动刷新、不重复尝试。
   - 验证 supervisor 通过 `visual-control pause/stop/cooldown/resume` 控制 scheduler/worker 的完整链路。

4. **小批量试跑**
   - 用 3-5 个关键词创建 daily plan，`visual-session-run <plan_id> --session 1` 或 `visual-heartbeat --mode prepare/dispatch` 分批推进。
   - 每个关键词之间保持人工可观察节奏，先验证稳定性，不追求速度。
   - 输出 raw Excel 后接 `filter_exported_results`、DB/LLM 过滤和统计赋值。
