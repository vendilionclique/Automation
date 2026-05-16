# Midscene.js 路线审计记录

日期：2026-05-09

## 安装状态

当前仓库使用 JS 版 Midscene：

- `@midscene/web@1.7.10`
- `@midscene/computer@1.7.10`
- `puppeteer@24.43.0`

Puppeteer 安装时跳过了自带浏览器下载，后续如评估 Web/CDP 路线，只连接本机 Chrome。

`npm audit` 当前报告 17 个依赖层级风险，主要来自 Midscene 依赖链中的 `@modelcontextprotocol/sdk`、`js-yaml`、`uuid` 等。`npm audit fix --force` 会做破坏性版本回退/变更，暂不执行；下一步 spike 先用于本机评估，不作为生产采集服务暴露。

## 结论摘要

最贴合淘宝主线边界的是 `@midscene/computer` 路线：

1. 输入来自系统截图：`screenshot-desktop`。
2. 定位来自 Midscene 核心的截图/VLM `aiLocate`。
3. 输出是系统鼠标、滚轮、键盘事件：`@computer-use/libnut`、macOS AppleScript、剪贴板粘贴。
4. 不连接浏览器 CDP，不读取 DOM/HTML/network/cookies/storage。
5. 可以通过 Midscene 自带 MCP server 暴露给 Codex App 调度。

`@midscene/web` 的 Puppeteer/CDP 路线可以作为技术备选，但不推荐作为淘宝主线。它的定位主要仍是截图/VLM，但 Web interface 默认包含页面级辅助能力：`window.innerWidth/innerHeight` eval、`waitForSelector('html')`、`waitForNetworkIdle`、`page.screenshot()`/CDP screenshot、XPath cache 等。即使不用商品 DOM，它仍然不是纯系统视觉。

Bridge/Chrome extension 路线不适合作为淘宝主线。该路径大量使用 `chrome.debugger.sendCommand('Runtime.evaluate')` 注入脚本、读取 `document.readyState`、获取节点树和 XPath cache。

## 推荐路线：`@midscene/computer`

关键实现：

- 截图：`ComputerDevice.screenshotBase64()` 调用 `screenshot-desktop`。
- 屏幕尺寸：`libnut.getScreenSize()`。
- 点击：定位得到 `element.center` 后调用 `libnut.moveMouse` / `mouseToggle` / `mouseClick`。
- 输入：先坐标点击目标，再用剪贴板粘贴文本；macOS 默认用 AppleScript 触发 `Command+V`。
- 滚动：`phased-scroll` helper、AppleScript page up/down 或 `libnut.scrollMouse`。
- MCP：`ComputerMidsceneTools` 提供 `computer_connect`、`computer_list_displays`、动作工具、`take_screenshot`、`act`、`assert`。

安全判断：

- 没有浏览器 DOM/HTML/network/cookie/storage 读取路径。
- 操作发生在真实桌面层，平台看到的是普通可见窗口上的鼠标键盘结果。
- 风险主要变为 macOS 权限、剪贴板短暂占用、误操作其他前台窗口，需要用专用 Chrome profile 和人工可观察节奏控制。

建议边界：

- Codex App 调度 `midscene-computer` MCP。
- 先用 `computer_connect`/`take_screenshot` 做观察。
- FlashX 可用后，采集主线改为 bounded `act`：让 Midscene/外部 VLM 在单个关键词或 tile 的时间、状态和异常边界内完成可见搜索、提交、等待和滚动。`tap`、`input`、`keyboardpress`、`scroll` 仍是可用的系统动作能力和调试/人工修正工具，但不再作为默认采集主线。
- 商品字段仍由 Codex/视觉模型从落盘截图识别，不用 Midscene 的 `aiQuery` 做商品抽取。
- 采集前用 `local/start_taobao_visual_chrome.sh` 启动并聚焦专用 Chrome profile。

## 备选路线：`@midscene/web` Puppeteer/CDP

优点：

- 可连接 Chrome/CDP，MCP 和 CLI 较完整。
- `aiTap`/`aiInput` 的元素定位核心来自截图/VLM。
- 动作输出最终是 `page.mouse.click/move/wheel`、`page.keyboard.type/press`。

问题：

- `commonContextParser()` 会调用 interface `size()` 和 `screenshotBase64()`；Web `size()` 默认 `evaluate(() => window.innerWidth/innerHeight)`。
- Web `waitForNavigation()` 默认 `waitForSelector('html')`，Puppeteer 还会 `waitForNetworkIdle()`。
- `scrollUp/Down/Left/Right` 未传 distance 时会 `evaluate(window.innerHeight/innerWidth)`。
- locate cache 默认可走 `cacheFeatureForPoint()` 和 `rectMatchesCacheFeature()`，这会注入 element inspector 并通过 XPath/DOM 找元素。
- Playwright screenshot 失败时会回落到 CDP `Page.captureScreenshot`。

若必须评估该路线，应强制：

- `cache: false` / 每次 action `cacheable: false`。
- `waitForNavigationTimeout: 0`，`waitForNetworkIdleTimeout: 0`。
- 所有 scroll 显式传 `distance`。
- 不用 `evaluateJavaScript`、`getElementsInfo`、`getElementsNodeTree`、`aiQuery({ domIncluded: ... })`。

即便如此，它仍然保留浏览器自动化栈，不是首选主线。

## 不推荐路线：Bridge/Chrome Extension

源码显示该路线会：

- attach `chrome.debugger`；
- 多次 `Runtime.evaluate` 注入脚本和动画；
- 读取 `document.readyState`；
- 注入/调用 element inspector；
- 使用 XPath cache；
- 截图走 `Page.captureScreenshot`。

这和“纯视觉截图证据 + 鼠标键盘动作”的边界冲突，淘宝主线应避开。

## Codex App 接入判断

可行路线是把 `midscene-computer` 注册为 Codex App 的 MCP server，由 Codex 作为上层 agent 调度。Midscene 负责：

- 截屏；
- 基于截图定位；
- 坐标点击；
- 键盘输入；
- 滚动。

Codex 负责：

- 决定低频任务节奏；
- 判断登录/验证码/风险时暂停；
- 保存证据；
- 从截图识别商品字段；
- 调用现有 `visual-ingest` / `visual-export` / 后处理。

不建议把淘宝主线接到 Midscene Web bridge MCP；若要连浏览器，优先只做隔离实验。

## 2026-05-09 实施状态更新

当前落地为混合架构：

- Codex 负责计划入口、异常裁判、证据复核和后处理编排；长期在线调度交给短命 heartbeat、worker contract 和文件状态。
- Midscene computer 作为系统级视觉操作层，可调用外部便宜 VLM 做 bounded session 内的可见屏幕判断和操作推进，例如前台确认、淘宝搜索框定位、搜索提交、结果页等待和 viewport 滚动。
- 外部 VLM 的职责只到“看屏幕并辅助操作”为止；商品字段最终仍以保留截图为证据，由 Codex 复核后写入 `visual-ingest`。
- Midscene MCP 通过 `local/start_midscene_computer_mcp.sh` 启动，读取本机 `local/midscene-computer.env`。真实 key 不进入仓库，也不写入 `~/.codex/config.toml`。
- 当前默认非敏感模型配置记录为：`MIDSCENE_MODEL_NAME=glm-4.6v-flashx`、`MIDSCENE_MODEL_FAMILY=glm-v`、`MIDSCENE_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4`、`MIDSCENE_MODEL_REASONING_ENABLED=false`、`MIDSCENE_MODEL_TEMPERATURE=0`。FlashX 是付费高速 GLM 主线；Kimi/Moonshot 已放弃，不作为主线；GLM-5V-Turbo 仅保留为后续 A/B 评估候选。

边界策略：

- capture worker 的真实路线必须通过 Midscene computer MCP 执行；环境不可用时写 `real_not_available`，不再保留模拟成功路线。
- 对 session capture，使用 bounded `act` 作为搜索和滚动主线，让 Midscene/外部 VLM 基于当前可见屏幕在受限 prompt、deadline、控制面和异常停机规则内推进。Python 负责 contract、节奏、截图落盘、粗页面状态判断、保存 viewport tile、结果文件、异常停机和 watchdog 自恢复；短动作工具只是可用能力，不是默认采集路线。
- 不使用 Midscene Web / Chrome extension bridge 作为淘宝主线。
- 不让 Midscene 的结构化输出直接成为最终商品数据来源。

## 下一步建议

1. 重启/刷新 Codex App，使 `midscene-computer` MCP 注册生效。
2. 先验证 `computer_connect`、`computer_list_displays`、`take_screenshot`。
3. 启动 `local/start_taobao_visual_chrome.sh`，人工登录并确认 Chrome 在前台。
4. 用 `tap`/`input`/`keyboardpress` 单步从淘宝首页搜索 smoke 关键词。
5. 截图落盘后接现有 `visual-ingest`，不让 Midscene 做最终商品结构抽取。
