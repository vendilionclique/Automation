# Capture 主线重建交接计划（2026-05-17）

## 背景

`supervisor_20260517_single_session_8kw_round3/round4` 复测暴露了两个必须先修复的边界问题：

- 前台应用不是 Chrome 时，capture worker 可能保存 WPS、Codex、Terminal 等非淘宝画面。
- 旧淘宝搜索结果页未切换关键词时，worker 可能把旧页面当作新关键词 `captured`。

这些问题不能通过无人值守 Python/AppleScript 循环强制激活 Chrome、反复 `Cmd+L`、输入淘宝域名或刷新跳转来修复。新方案必须保持低频、可停、可观测、可人工打断，并先在本地练习场验证，再恢复真实淘宝采集。

## 重建目标

1. 重新收紧 capture 主线，只负责可靠地产出当前关键词的可见截图证据。
2. 保持 capture 与 extract 分离：capture 不抽商品字段，extract 不控制淘宝页面。
3. 每个关键词从淘宝首页开始，避免旧搜索结果污染新关键词。
4. Chrome 前台恢复必须有明确预算，最多 2 次，失败即停。
5. 首屏关键词边界必须硬验收，验收失败不得标记 `captured`。
6. extract 是截图落盘后的可选后处理，不作为本轮 capture 重建的验收条件。
7. 所有真实淘宝风险动作先在本地练习场完成脱敏演练。

## 新 capture 主线

每个关键词的推荐顺序：

1. 读取 session contract 中的当前关键词。
2. 确认前台是既有 Chrome 采集窗口；如果不是，进入前台恢复流程。
3. 从可见淘宝首页开始搜索当前关键词。
4. 保存 `tile_00` 首屏截图。
5. 对 `tile_00` 做关键词边界硬验收：必须能证明当前关键词已经进入可采集淘宝搜索结果页。
6. 只有首屏硬验收通过，才允许继续滚动并保存后续 viewport tiles。
7. 遇到 `results_end`、相邻可采集 tile 高度相似或达到 tile 上限时，结束当前关键词。
8. 写 `keyword_result.json` 和 `session_worker_result.json`，把证据和 diagnostics 留给后续 extract/apply。

## Chrome 前台恢复规则

- 前台恢复只用于把焦点回到既有 Chrome 采集窗口，不用于自动修复淘宝页面内容。
- 每个关键词最多允许 2 次前台恢复尝试。
- 每次恢复后必须截图复核当前画面是否为 Chrome/淘宝相关页面。
- 2 次后仍不是 Chrome，状态写为 `needs_review` 或 `paused_needs_human`，保留截图和原因。
- 禁止无人值守循环抢焦点、反复打开淘宝域名、反复刷新或长期阻塞人工操作。

## 每关键词首页入口搜索规则

- 新关键词开始前，应通过 bounded `act` 低频、可停地进入淘宝首页或已确认的淘宝首页状态。
- 首页搜索框必须是可见且可输入的普通搜索入口。
- 不把旧搜索结果页中的搜索框内容替换当作默认主线，也不把旧页 reset/retry 当作新关键词入口。
- 不恢复 `Tap`、`Input`、`KeyboardPress`、`ClearInput` 等短动作作为 unattended 默认采集路线。
- 如果回首页失败、页面状态不明、登录/验证码/风险/弹窗/白屏出现，立即停为人工复核或冷却。

## 首屏关键词边界硬验收

`tile_00` / post-act 验收必须同时满足：

- 当前画面是淘宝搜索结果页或可采集的结果列表区域。
- 可见搜索词、页面标题、结果提示或其他强信号能证明它属于当前关键词。
- 没有登录、验证码、安全验证、疑似风控、遮挡弹窗、白屏骨架或非 Chrome 前台。

以下情况必须视为失败：

- 读到旧关键词。
- 读不清关键词且没有其他强信号证明属于当前关键词。
- 画面属于 WPS、Terminal、Codex、VS Code、系统桌面或其他非淘宝内容。
- 页面只是旧结果页、底部页脚或未知中间态，无法证明新关键词已完成搜索。

失败后不得标记 `captured`，也不得用旧结果页 reset/retry 后的任意首屏替代验收。应写入
`needs_review` / `cooldown` 或人工介入，并保留失败截图副本。

## capture/extract 分离

- capture 只产出截图、状态、manifest、diagnostics 和 worker result。
- 商品标题、价格、店铺、地区等字段只能由 Codex extract worker 基于已保存截图抽取。
- `visual-apply-extracted-rows` 仍是确定性落盘入口。
- 本轮重建优先恢复 capture 边界正确性；extract 是截图落盘后的可选后处理，可手动执行或放入下一阶段自动化恢复。
- 不因为 extract 未自动启动而放宽 capture 的 `captured` 判定。

## 本地练习场要求

真实淘宝恢复前，开发线程应提供本地练习场，用于验证：

- 前台不是 Chrome 时能停住并记录诊断。
- Chrome 前台恢复最多 2 次，失败可观测、可退出。
- 每关键词回首页搜索流程可以在脱敏页面上跑通。
- 旧关键词结果页不会被新关键词标记为 `captured`。
- 登录、验证码、风控、弹窗、白屏、未知页面不会被 reset 或重搜掩盖。

练习场应尽量模拟首页、结果页、旧关键词页、底部页、异常遮罩和非目标前台等状态，但不得依赖真实淘宝风险动作作为主要测试素材。

## 验收条件

- 只改造 capture 主线时，不要求自动 extract 全链路成功。
- 单关键词练习场测试能证明：旧页面不能按新关键词 `captured`。
- 前台不是 Chrome 时，最多 2 次恢复后仍失败会停机并保留证据。
- 新关键词必须从淘宝首页入口搜索，并通过首屏关键词边界硬验收后才继续滚动。
- 真实淘宝测试只做低频小样本；一旦出现登录、验证码、风控、弹窗、白屏或未知状态，立即停止并保留证据。

## 交接给开发线程

开发线程先提供本地练习场和最小回归测试，再改 capture worker。完成后再由 supervisor 线程安排真实淘宝小样本复测。不要在没有练习场证明之前直接恢复 unattended 真实采集。

## 本线程即时交棒状态（2026-05-17）

本线程在用户要求“先交棒”时停止，没有继续实施核心 capture v2 代码。当前已完成：

- 已新增本文件，记录 capture 主线重建计划。
- 已更新 `AGENTS.md`，追加 capture 重建新主线规则。
- 已启动 subagent 只读分析 extract 解耦影响面；结论如下。

当前工作树在接手时已有上一轮未提交改动，且仍然存在：

- `AGENTS.md`
- `config/settings.example.ini`
- `modules/midscene_computer_driver.py`
- `modules/visual_capture_worker.py`
- `tests/test_midscene_config.py`
- `tests/test_visual_capture_worker.py`
- `HANDOFF_20260517_CAPTURE_REBUILD_PLAN.md`

接班线程必须先看 `git diff`，不要回退既有改动。

## extract 解耦观察

当前 capture worker / watchdog 本身不会自动启动 extract。真正会启动 extract 的路径是显式 CLI：

- `visual-codex-extract-prepare`
- `visual-codex-extract-dispatch`
- `visual-codex-extract-drain`

已落地的调度门控：`visual-heartbeat --mode dispatch/all` 只有在
`[CODEX_EXTRACT] advice_enabled = true` 时，才会在 `worker_commands` 里建议：

- `codex_extract_prepare`
- `codex_extract_dispatch_advice`
- `codex_extract_dispatch_start`

capture-only 阶段的最小策略：

- 只运行 `visual-heartbeat` / `visual-capture-watchdog --start`。
- 不运行 `visual-codex-extract-drain`。
- 保持 `[CODEX_EXTRACT] advice_enabled = false`，让 heartbeat 不返回 `codex_extract_*` 命令。

本轮已落地：

- scheduler dispatch advice 已由 `[CODEX_EXTRACT] advice_enabled` 控制；配置为 false 时不返回 `codex_extract_*`。
- `config/settings.example.ini` 和默认配置已加入 `advice_enabled = false`，capture-only 是默认文档语义。
- `modules.codex_extract.run_codex_extract_drain()` 的函数默认值已改为 `start=False`，避免程序内省略参数时直接启动 Codex extract worker。
- README 与 `modules/session_capsule.py` 已把 extract 描述改为截图落盘后的可选后处理，而不是 capture 的自动续段。
- capture worker 主线已拆出首页入口版本：旧 `_capture_keyword_with_mcp` 现在只是兼容外壳，实际进入每关键词首页入口搜索、`tile_00` 严格验收、再滚动截图的流程。
- session worker contract / instructions 已改为 `taobao_homepage_visible_search_entry_required`，不再暗示旧结果页搜索框可作为默认入口。

仍待验证：

- 单元测试已覆盖 `advice_enabled=false/true` 的 heartbeat advice 行为；真实计划上仍建议用 dry-run 跑一次 `visual-heartbeat --mode dispatch/all` 看本机配置是否同步。
- 仍需真实淘宝低频小样本留样，确认“可见淘宝首页入口”在不同结果页、底部页和活动页上足够稳定；出现登录、验证码、风控、弹窗、白屏或未知状态时仍立即停机。

## 下一线程推荐顺序

1. 先读取 `AGENTS.md` 和本文件。
2. 跑 `git status --short` / `git diff --stat`，确认未提交范围。
3. 不要再恢复旧结果页替换搜索词的默认主线；如需处理旧页，只能通过首页入口 retry，并重新验收 `tile_00`。
4. 用 heartbeat dry-run 验证本机 `advice_enabled` 配置门，避免 heartbeat advice 误触发 extract。
5. 安排真实淘宝低频小样本复测，先单关键词，再小 session；异常即停，保留证据。
