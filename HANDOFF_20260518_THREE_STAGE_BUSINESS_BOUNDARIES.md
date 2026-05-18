# 2026-05-18 交棒：三段业务边界的 Midscene act 改造

## 背景

本轮目标原本是用 `/Users/zhunshi/Downloads/采数输入表.xlsx` 随机 8 个关键词跑一个长一点的 session，验证刚修过的 bug 后还能否连贯采集，并从更长 batch 中发现新风险。

新建测试 plan：

```text
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337
```

随机关键词：

```text
万智牌 三顾茅庐
万智牌 噬地兽
万智牌 好战不休泰瓦
万智牌 弄时宗师泰菲力
万智牌 恐惧身影乌蔽袭
万智牌 浩劫之树
万智牌 诈缚
万智牌 雷鸣瀑布
```

实际只跑了前 2 个关键词，均在 `pre_keyword_home_entry` 阶段失败，未进入任何 `tile_00` 结果页采集：

```text
needs_review: 2
needs_midscene_computer: 6
session_worker_result.status: cooldown
stop_reason: consecutive_abnormal_limit
cooldown_until: 2026-05-18T11:25:42
```

关键证据：

```text
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337/evidence/万智牌_三顾茅庐/keyword_result.json
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337/evidence/万智牌_三顾茅庐/foreground_exception_pre_keyword_home_entry.png
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337/evidence/万智牌_噬地兽/keyword_result.json
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337/evidence/万智牌_噬地兽/foreground_exception_pre_keyword_home_entry.png
data/tasks/supervisor_20260518_long_batch_8kw_rerun_102337/sessions/session_01/session_worker_result.json
```

## 核心判断

这次不是简单的“Midscene 不会打开淘宝首页”。用户现场观察到 Midscene 明明移动鼠标点击了 Chrome 新标签页上的淘宝导航/书签，并且后置截图也证明页面已到淘宝首页。

真正问题是：`act` 是 Midscene 内部的小 agent，不是裸点击工具。它内部有截图、规划、动作、复查、失败判断循环。项目侧只能看到 `act` 最终返回或抛错后的结果，拿不到每一个中间帧。

本轮证据显示：

- 第 1 个关键词：Midscene 报“当前不是淘宝，像 chat/interface 或其他页面”，异常后项目补拍截图显示 Chrome 新标签页 / Google 风格首页。
- 第 2 个关键词：Midscene 报“仍是 Google homepage”，异常后项目补拍截图显示已经是 `taobao.com` 普通首页。

这更像是 Midscene `act` 点击淘宝书签后，内部复查/断言太早，页面还没稳定就输出 `<error>`。Python 捕获异常再补拍时，页面已经加载到淘宝首页。

因此，不能继续在 Python 中堆“如果 Google 就再点一次、如果淘宝首页就继续”这种兜底。那会把系统变成越来越厚的脚本驾驶层，偏离 pure-vision + Midscene 智能路线。

## 设计精神

主线应从“Python 切碎动作并到处补救”转为：

```text
Midscene act 负责边界内的高层视觉行动
VLM/page-state 负责单次截图证据判断
Python 只做契约、预算、验收、停机和状态落盘
```

也就是：

- 让 Midscene 做“看见页面后选择可见 UI 路径”的智能工作。
- 不让 Python 变成页面状态脚本驾驶员。
- Python 的职责是安全护栏和证据裁判，不是副驾驶抢方向盘。

## 粒度选择：不是越拆越好

本轮讨论中特别确认了一点：拆得越碎并不越安全。拆得过细会把 Midscene 降级成视觉定位器，让 Python 变成页面状态机司机；每多一个边界，就多一次截图、分类、时延窗口、状态衔接和维护成本。未来网页出现随机扰动时，也更容易变成“发现一个页面变化就加一个 Python 分支”。

推荐原则：

```text
按业务不可混淆边界拆，不按 UI 动作拆。
```

调研比较了三种粒度：

1. 一个大 `act` 完成回首页、搜索提交、等待首屏。
2. 按 UI 动作细拆：点搜索框、输入、点按钮、等待、截图、滚动等。
3. 三段业务边界：`home_entry_boundary -> search_submit_boundary -> capture_tiles_boundary`。

推荐默认主线采用第三条：**三段业务边界**。

理由：

- 每段仍然是高层视觉任务，Midscene 仍能自主选择可见 UI 路径，不退回短动作工具。
- 每段对应一个业务风险，目标清楚，Midscene 更容易规划，也更容易等待页面稳定。
- 风险定位更清楚：失败是“回首页失败”“搜索提交失败”还是“结果页滚动采集失败”可以分开看。
- 长 batch 中遇到活动页、旧关键词页、Chrome 新标签页、其他无关页时，可以在搜索前挡住。
- `tile_00` 仍保留为最终搜索提交硬验收，不让首页 feed 或旧结果页混进 captured。
- 结果页滚动阶段保留连续采集能力，不把每一次滚动都拆成 Python 驾驶动作。

一个大 `act` 可以作为“已确认普通淘宝首页”的 smoke/快速实验路径，但不适合作为长批量默认主线。

按 UI 动作细拆也不适合作为主线。比如“点击搜索框、输入关键词、点击搜索按钮、等待结果页”都交给 Python 分段监督，看起来更可控，实际会损失 Midscene 的视觉适应和自恢复能力，也会平添很多衔接 bug。

## 三段业务边界

### 1. Home Entry Boundary

目标：

```text
把当前可见 Chrome 状态推进到“已验证的普通淘宝首页/首页搜索入口”。
不输入关键词，不提交搜索。
```

这一段允许 Midscene 自主选择可见 UI 路径，但路径只限业务预期内的安全状态。

业务预期状态枚举：

| 场景 | 状态名 | 是否可直接搜索 | 允许动作 | 验收 |
|---|---|---:|---|---|
| 普通淘宝首页 | `ordinary_taobao_home` | 是 | 停止在首页搜索入口 | `home_entry_ready=true` |
| Chrome 新标签页 / Google 风格首页，有淘宝书签 | `chrome_start_page_with_taobao_bookmark` | 否 | 点击可见淘宝书签打开淘宝首页 | 再验收首页 |
| 旧淘宝结果页 / 底部结果页 / 旧关键词页 | `old_taobao_results_page` | 否 | 可见淘宝 logo、首页入口、已有首页 tab、或允许时新标签+淘宝书签 | 再验收首页 |
| 其他任何无关页 | `unrelated_page` | 否 | 优先关闭或离开无关页；若 Chrome 前台且淘宝书签可见，可用淘宝书签回首页；无安全可见路径则停 | `home_entry_unavailable` 或再验收首页 |
| 非 Chrome 前台 | `chrome_not_foreground` | 否 | 只做前台恢复，不导航 | 恢复后重拍判断 |
| 登录/验证码/风控/权限 | `hard_blocked` | 否 | 停止 | `needs_review` |

特别注意：Chrome 新标签页长得很像 Google 首页，有巨大 Google logo 和搜索框。但如果能看到书签栏里的“淘宝”按钮，它在业务上是可恢复的 Chrome start page，不应直接当成硬错误。

### 淘宝首页验收规则

普通淘宝首页不能只靠“有搜索框”或“有商品卡”。必须同时满足：

```text
home_entry_ready == true
home_url_status == normal_taobao_home
home_structure_status == ordinary_home_search_entry
source_state == ordinary_taobao_home
hard_blocking_reason == ""
confidence >= 0.70
```

URL/地址证据：

- 接受：可见地址栏或页面证据显示 `taobao.com` / `www.taobao.com` 普通首页。
- 拒绝：`s.taobao.com/search`、`huodong.taobao.com`、`dailygroup`、`world.taobao.com`、`tmall.com`、`search?`、采购优选、活动/会场/频道页。

页面结构证据：

- 接受：淘宝首页 logo、普通首页大搜索框、首页频道、推荐、热搜、猜你喜欢等首页结构。
- 拒绝：结果页排序栏、筛选栏、分页、上一页/下一页、跳页、底部结果页页码、活动会场、采购优选结构。

### 2. Search Submit Boundary

目标：

```text
在已验证的普通淘宝首页搜索框中输入当前关键词，优先点击可见搜索按钮，等待当前关键词结果页首屏稳定。
```

这一段不再承担“回首页”职责。它只负责搜索提交。

成功证据仍按 `tile_00` 硬验收：

```text
keyword_match == matched/true
search_submitted == true
search_box_text_kind == actual_input
is_home_feed != true
result_page_evidence 非空
url_or_page_evidence 非空
页面结构是淘宝搜索结果页
```

`tile_00.png` 不建议改名，因为 extract worker 和下游已经围绕它工作。语义上把它定义为：

```text
search submit boundary accepted first result viewport
```

### 3. Capture Tiles Boundary

目标：

```text
在已经验收通过的当前关键词淘宝结果页中，连续保存可见 viewport 截图并按规则滚动，直到达到采样预算、结果页到底、相邻 tile 高相似、或出现硬异常。
```

这一段不再承担“回首页”或“提交搜索”职责。它只在当前关键词结果页内工作。

允许 Midscene 做的智能工作：

- 判断可见结果列表区域和下一屏方向。
- 做页面级低频滚动。
- 在普通弹窗遮挡且有明确弹窗灰色 X 时关闭弹窗。
- 识别底部信号，如分页、页脚、备案/协议、滚动条到底、相邻截图高度相似。

Python 保留的 gate：

- 每张 tile 只做一次 page-state/VLM 粗分类。
- 登录、验证码、风控、白屏、权限、未知高风险状态立即停。
- `results_end` 和相邻 tile 高相似只结束当前关键词，不触发重搜。
- 不把滚动失败写成 captured。

不要把 capture tiles 再拆成“滚一下、等一下、截图一下、判断一下”的 Python 驾驶模式。这里的边界是“当前结果页内采集”，不是每一次滚动。

## Prompt 草案

### Home Entry Boundary Prompt

```text
Prepare the verified ordinary Taobao homepage boundary before searching the next keyword.

Use only visible-screen reasoning and system mouse/keyboard actions. Do not read DOM, HTML, network, cookies, storage, selector maps, page source, JS-evaluated data, URL via automation, or clipboard contents. Do not type into the address bar, do not type a URL, and do not run scripts.

The page is ready only when BOTH are visible:
1. URL/address evidence shows the ordinary Taobao homepage, such as taobao.com or www.taobao.com, not s.taobao.com/search, huodong.taobao.com, dailygroup, world.taobao.com, tmall.com, search?, purchase-selection, campaign, or activity pages.
2. Page structure shows the ordinary Taobao homepage/search-entry surface: Taobao homepage branding/logo, ordinary homepage search box, homepage channels/recommendations/hot search/suggestions. A results sort/filter bar, pagination, previous/next/jump controls, or bottom results footer means this is not homepage-ready.

Expected source states:
- If the ordinary Taobao homepage is already visible, stop there.
- If Chrome new tab/start page or Google-style start page is visible and a Taobao bookmark is visible in the bookmarks bar, click that visible Taobao bookmark to open the ordinary Taobao homepage. Do not type anything into the address bar.
- If an old Taobao results page is visible, do not use its search box. Leave it through a visible Taobao logo/Home entry/return-home control/already visible ordinary home tab, or use the visible Taobao bookmark repair if allowed.
- If any unrelated page is visible, do not use its search box. Close or leave the unrelated page only through visible safe browser/UI controls, or use the visible Taobao bookmark if it is clearly available. If no safe visible path exists, stop and report home_entry_unavailable.

If Codex, Terminal, Cursor, VS Code, WPS, or another non-Chrome app is visible, report chrome_not_foreground and do not navigate.

Stop when the ordinary Taobao homepage/search-entry is visible and ready. Do not type the keyword yet. Final message must include: home_entry_prepared=true/false, source_state, home_url_status, home_structure_status, bookmark_home_entry_used=true/false, recovered_from_old_results=true/false.
```

### Search Submit Boundary Prompt

```text
Submit the current keyword search from the already verified ordinary Taobao homepage.

Use only visible-screen reasoning and system mouse/keyboard actions. Do not read DOM, HTML, network, cookies, storage, selector maps, page source, JS-evaluated data, or clipboard contents. Do not use the browser address bar, do not type a URL, and do not run scripts.

The current page should already be the ordinary Taobao homepage/search-entry surface. If it is not, stop and report search_submit_requires_home_entry. Do not repair or navigate home in this step.

Click the ordinary Taobao homepage search box, enter the exact keyword "<keyword>", and submit the search. Prefer clicking the visible orange search button. Use Enter only if the search button is not visible or not safely clickable.

After submission, wait until the visible page is a Taobao search results page for the exact keyword. The page must show result-page structure, not homepage recommendations, not an activity/campaign page, and not an old keyword page.

Stop on the first stable search results viewport. Final message must include: search_submitted=true/false, submission_method=search_button|enter|unknown, visible_search_keyword, result_page_ready=true/false, blocker if any.
```

## Evidence Schema 草案

在现有 page-state JSON 上扩展字段，不破坏旧字段。

### Home Entry Evidence

```json
{
  "schema": "taobao_home_entry_evidence_check_v1",
  "state": "visible_ready",
  "source_state": "ordinary_taobao_home | chrome_start_page_with_taobao_bookmark | old_taobao_results_page | unrelated_page | chrome_not_foreground | hard_blocked | unknown",
  "home_entry_ready": false,
  "home_url_status": "normal_taobao_home | taobao_search_results | taobao_activity_or_campaign | taobao_other | chrome_start_page | unrelated | unreadable",
  "visible_url_or_address_text": "",
  "url_or_page_evidence": [],
  "home_structure_status": "ordinary_home_search_entry | results_page_structure | activity_or_campaign_structure | purchase_selection_structure | unrelated_structure | unreadable",
  "home_structure_evidence": [],
  "bookmark_visible": false,
  "bookmark_home_entry_used": false,
  "recovered_from_old_results": false,
  "search_box_text_kind": "placeholder | suggestion | hot_search | actual_input | unreadable | none",
  "is_home_feed": true,
  "hard_blocking_reason": "",
  "recommended_next": "accept_home | repair_home_entry | stop",
  "confidence": 0.0,
  "reason": ""
}
```

### Search Submit Evidence

继续复用现有字段，重点保持：

```json
{
  "state": "search_results | results_page | visible_results | visible_ready | unknown",
  "visible_search_keyword": "",
  "keyword_match": true,
  "search_box_text_kind": "actual_input",
  "search_submitted": true,
  "is_home_feed": false,
  "result_page_evidence": [],
  "url_or_page_evidence": [],
  "confidence": 0.0,
  "reason": ""
}
```

## 开发落点

### 1. Capture worker 主流程

文件：

```text
modules/visual_capture_worker.py
```

目标是在 `_capture_keyword_from_home_with_mcp()` 中显式形成三段：

```text
home_entry_boundary -> search_submit_boundary -> capture_tiles_boundary
```

现有函数对应关系：

- `_prepare_home_entry_before_keyword()`：保留为第一段，建议包一层或改名为 `_perform_home_entry_boundary()`。
- `_perform_keyword_search()`：改成第二段 `_perform_search_submit_boundary()`，不再负责回首页。
- `_verify_keyword_after_act()`：继续作为 search-submit 后置截图验收，stage 名改成 `search_submit_boundary_verification`。
- 现有 tile loop 保留为第三段，建议用 `capture_tiles_boundary` 明确命名其 stage/diagnostics；不要把每次滚动拆成独立 Python 编排动作。

首个关键词也必须走 home-entry gate。不要依赖“第 2 个及以后关键词才强制回首页”。

### 2. Prompt 拆分

文件：

```text
modules/visual_capture_worker.py
```

改造点：

- `_pre_keyword_home_entry_prompt()`：保留，不输入关键词，不提交搜索。
- `_keyword_search_home_entry_prompt()`：降级/替换为 `_search_submit_boundary_prompt()`，删除回首页、书签修复、旧结果页修复内容。
- `_keyword_search_home_entry_retry_after_exception_prompt()`：不要继续做“回首页+搜索”一体化补救。
- `_keyword_search_reset_prompt()`：降级或删除，避免一段 act 包办 reset+search。
- capture tiles 的滚动 prompt 保持目标导向：在当前结果页内保存下一屏可见商品区域；不要让它承担回首页、重搜、清空搜索框等职责。

### 3. Home-entry gate

文件：

```text
modules/page_state_classifier.py
modules/visual_capture_worker.py
```

改造点：

- 在 classifier prompt/normalizer 中加入 `source_state`、`home_entry_ready`、`home_url_status`、`home_structure_status`。
- `_home_entry_review_reason()` 从“`visible_ready` 加排除词”改为“显式 home-entry evidence gate”。
- `visible_ready` 以后只表示粗状态，不再单独代表普通淘宝首页成功。

### 4. Goal contract / evidence gate

文件：

```text
modules/visual_goal_contract.py
```

改造点：

- 拆出两个阶段：`HOME_ENTRY_BOUNDARY` 和 `SEARCH_SUBMIT_BOUNDARY`。
- 保留或补充第三阶段语义：`CAPTURE_TILES_BOUNDARY`。
- `HOME_ENTRY_BOUNDARY` 只验普通首页入口和硬异常缺席。
- `SEARCH_SUBMIT_BOUNDARY` 才验当前关键词、提交、结果页结构。
- `CAPTURE_TILES_BOUNDARY` 只验当前结果页内继续采样、到底、重复、或硬异常；不做关键词重搜决策。
- `_boundary_search_submission_issue()` 逻辑继续复用，但不要让 home-entry 阶段调用。

### 5. Contract / config

文件：

```text
modules/midscene_computer_driver.py
config/settings.example.ini
```

建议增加或明确：

```text
home_entry_boundary_required = true
search_submit_boundary_required = true
capture_tiles_boundary_required = true
three_stage_business_boundaries = true
home_entry_boundary_path
search_submit_boundary_tile_id = tile_00
```

`require_initial_home_entry=true` 和 `allow_bookmark_home_entry_repair=true` 保留。

不要新增第三条路线，不要恢复短动作工具为默认无人值守主线。

### 6. 证据文件命名

兼容式新增，不要破坏下游：

```text
home_entry_boundary.png
home_entry_boundary_retry.png
home_entry_boundary.json
search_submit_boundary.json
capture_tiles_boundary.json
tile_00.png
tile_00_initial_failed.png
keyword_boundary.json
```

说明：

- `tile_00.png` 保留，作为 search-submit 通过后的第一张结果页截图。
- 后续 `tile_01.png`、`tile_02.png` 等继续属于 capture tiles boundary，不要改名影响 extract。
- `keyword_boundary.json` 保留为兼容摘要，但新增 JSON 中要分清两个 boundary。
- 失败截图可继续兼容 `tile_00_initial_failed.png`，同时在 diagnostics 中称为 `search_submit_boundary_initial_failed`。

## 状态与 stop_reason

`status` 不建议扩展太多，继续使用现有状态：

```text
captured
needs_review
failed_recoverable
paused_needs_human
paused_needs_supervisor
cooldown
real_not_available
```

建议固定 stop_reason：

Home-entry 阶段：

```text
home_entry_unverified
home_entry_not_reached
home_entry_reset_failed
bookmark_home_entry_unavailable
home_entry_unavailable
```

Search-submit 阶段：

```text
search_submit_unconfirmed
search_results_structure_unverified
visible_keyword_mismatch
visible_keyword_unverified
submission_method_unconfirmed
search_submit_requires_home_entry
```

Capture-tiles 阶段：

```text
results_end
similar_adjacent_tile
tile_page_state_unverified
capture_tiles_interrupted
capture_tiles_budget_exhausted
```

硬停：

```text
chrome_not_foreground
foreground_recovery_exhausted
login_required
captcha_required
risk_suspected
popup_blocked
white_skeleton
rate_limited
page_state_detection_failed
```

prompt 中如果出现 `search_submit_failed`，Python 归一到 `search_submit_unconfirmed`，不要散成新状态。

## 降级或删除的旧逻辑

- `_perform_keyword_search()`：不再负责回首页。
- `_keyword_search_home_entry_prompt()`：旧名可留兼容，但内部走纯 submit prompt。
- `_keyword_search_home_entry_retry_after_exception_prompt()`：取消“一体化 repair+search”职责。
- `_reset_and_retry_keyword_search_once()`：改为先 home-entry boundary retry，再 search-submit boundary retry。
- `_should_reset_retry_search()`：收窄为 search-submit boundary 的一次重试决策；不要让 `manual_review_needed/page_state_detection_failed` 轻易重搜。
- `post_keyword_cleanup`：降级为诊断性清场，失败不阻断下一关键词；下一关键词自己跑 home-entry boundary。
- tile loop：保持为结果页内连续采集边界，不要进一步按每个 UI 小动作拆成 Python 状态机。
- 继续禁止 `Tap/Input/KeyboardPress/Scroll/ClearInput` 回默认主线。

## 最小实验计划

先不要直接开 8 关键词长跑。下一线程应先做 1 关键词边界实验。

准备：

```text
人工把 Chrome 放到新标签页，确认书签栏可见“淘宝”。
使用非敏感低风险关键词。
max_tiles_per_keyword=1。
不做商品抽取，不滚动。
```

实验流程：

1. `act A`: `home_entry_boundary`，只从当前页到普通淘宝首页，不输入关键词。
2. Python 立即截图，等 2 秒再截图，跑一次 home-entry evidence check。
3. `act B`: `search_submit_boundary`，只在已验证首页输入关键词并点击搜索。
4. Python 立即截图，等 2 秒再截图，验收当前关键词结果页。
5. `act C`: `capture_tiles_boundary`，在已验证结果页内保存 `tile_00` 后做 1 次滚动并保存下一屏；不抽取商品，不继续长滚。

接受标准：

```text
act A 文本、即时截图、延迟截图都指向 ordinary_taobao_home
act B 文本、即时截图、延迟截图都指向当前关键词 search_results
act C 只在当前关键词结果页内滚动采样，没有回首页、重搜或跳到活动页
无 act 内部错误与后置截图冲突
```

失败判据：

```text
act 报 Google，但后置截图已经是淘宝
act 报首页失败，但 home-entry evidence 已经满足 URL+结构双证据
act B 在非首页上尝试搜索
tile_00 是首页 feed 或旧关键词页
act C 试图修复首页、重搜、操作无关页、或把异常状态当作普通滚动
```

失败时不要加 Python 猜测兜底，先归档为观察面冲突或 prompt/等待策略问题。

## 测试清单

建议测试文件：

```text
tests/test_visual_capture_worker.py
tests/test_visual_goal_contract.py
tests/test_midscene_config.py
tests/test_page_state_classifier.py
```

新增/修改测试：

- home-entry prompt 和 submit prompt 职责分离。
- 三段业务边界职责分离：home-entry、search-submit、capture-tiles。
- submit prompt 不包含 return home、bookmark repair、old results repair。
- capture tiles prompt 不包含 return home、bookmark repair、search submit。
- home-entry 失败时不调用 submit act。
- home-entry 成功后 submit 失败，保留 failed tile，再按边界重试一次。
- search-submit 失败时不进入 capture tiles。
- `search_submit_failed` / `submission_method=unconfirmed` 归一为 `search_submit_unconfirmed`。
- activity / `huodong.taobao.com` / 采购优选页面不能通过 home-entry。
- Chrome 新标签页 / Google 风格首页 + 可见淘宝书签应被分类为可修复 source，而不是普通首页。
- `tile_00` 仍要求当前关键词、已提交搜索、非首页 feed、结果页结构证据。
- `results_end`、相邻 tile 高相似、普通滚动预算耗尽只能结束当前关键词，不能触发重搜。

验证命令：

```bash
.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py
.venv/bin/python -m unittest tests.test_visual_capture_worker tests.test_visual_goal_contract tests.test_midscene_config tests.test_page_state_classifier
.venv/bin/python -m unittest discover -s tests
scripts/check_portable_config.sh
```

## 不要做的事

- 不要把 Google/淘宝/旧结果页各种情况写成越来越多 Python 分支驾驶动作。
- 不要把三段业务边界继续细拆成 UI 微动作边界。
- 不要恢复短动作工具作为无人值守主线。
- 不要让 Python 用地址栏、URL、脚本、剪贴板、DOM、network、storage 去“聪明修复”。
- 不要把首页推荐流、活动页商品卡、旧关键词结果页当 captured。
- 不要开新 orchestrator 或合并 watchdog/extract drain。
- 不要在未完成 1 关键词边界实验前重开 8 关键词长跑。

## 当前状态

本交棒只做调研和方案，没有修改代码。

当前工作树在写入本交棒前是干净的。若后续要开发，建议先创建分支：

```bash
git checkout -b codex/three-stage-business-boundaries
```

然后按上述开发落点逐步改，先跑单测，再做 1 关键词三段业务边界真实实验。
