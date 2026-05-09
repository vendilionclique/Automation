# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并接入规则过滤、DB/LLM 过滤、统计评估和最终赋值流程。

当前仓库已经清理为“本机 Chrome 真实登录态 + 低频 human-in-the-loop + 可见截图证据 + Codex/视觉模型识别”的主线。旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集和项目内 Chrome profile 已从代码树删除。

browser-use MCP 已完成过单关键词 MVP，但源码审计后降级为历史试验：其默认 state/index 能力会读取 DOM/AX/snapshot/selector map。当前优先评估 Midscene.js，其中 `@midscene/computer` 是最贴近纯视觉边界的候选。

## 当前状态

- `.venv/bin/python harness.py setup` 自检通过。
- 已验证 browser-use 本地工具可以打开淘宝搜索页并看到商品列表；该路线现已降级为历史 MVP。
- 单关键词 `万智牌 中止` 已跑通可见页面闭环：
  - browser-use 打开淘宝搜索结果页
  - Codex 从可见截图整理 6 条商品行
  - `visual-ingest` 写入 `raw_rows.jsonl` / `raw_results.xlsx`
  - `visual-export --filter` 接入现有规则过滤，6 行过滤为 5 行，最低价为 80
- 已安装 JS 版 Midscene 评估依赖：`@midscene/web`、`@midscene/computer`、`puppeteer`。
- 当前判断见 [Midscene.js 路线审计记录](docs/midscene_route_analysis.md)：后续优先走 `@midscene/computer` 的系统截图 + 系统鼠标键盘 MCP 路线，不优先走 Web bridge/CDP。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config/settings.example.ini config/settings.ini
npm install
```

编辑 `config/settings.ini`：

- `[VISUAL_CAPTURE] provider = midscene_computer` 保持默认主线。
- 旧 browser-use/CDP 对照测试才需要填写 `[BROWSER_USE] chrome_user_data_dir` / `chrome_profile_directory`。
- 不要提交 `config/settings.ini`，其中会包含本机路径和可能的密钥。

自检：

```bash
.venv/bin/python harness.py setup
```

启动专用 Chrome 采集 profile，并人工登录淘宝：

```bash
local/start_taobao_visual_chrome.sh
```

配置 Midscene computer MCP 的外部 VLM key：

```bash
cp local/midscene-computer.env.example local/midscene-computer.env
# 编辑 local/midscene-computer.env，填写 MIDSCENE_MODEL_*。
```

Codex App 的 MCP server 使用 `local/start_midscene_computer_mcp.sh` 启动，
该脚本会读取本机 env 文件；key 不写入仓库，也不写入 `~/.codex/config.toml`。

准备单关键词视觉任务：

```bash
.venv/bin/python harness.py visual-one 中止
```

`visual-run` 默认会在 evidence 目录生成 `midscene_computer_request.json`
和 `codex_midscene_computer_instructions.md`。Codex App 通过
midscene-computer MCP 使用系统截图、坐标点击、键盘输入和滚动完成采集；
截图落盘后，再把识别结果写入结构化结果：

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

## 安全边界

- 不自动登录。
- 不处理验证码、短信、安全验证。
- 不读 DOM、接口、cookies、storage、CDP 数据；淘宝主线不使用 browser-use state/index 或 Midscene Web bridge。
- 只采集真实登录用户当前可见页面里的标题、价格、店铺、地区等信息。
- 优先评估 Midscene computer MCP：系统截图输入，系统鼠标键盘输出。
- 如果刚给 Codex App、Chrome、终端或自动化组件打开 macOS 权限，或刚切换 MCP 开关，请先重启/刷新 Codex App 再测试。

## Midscene.js 评估

```bash
npm run midscene:version
npm run midscene:computer:help
npm run midscene:web:help
```

当前优先评估 `midscene-computer` MCP：

- 输入：系统截图。
- 定位：截图/VLM。
- 输出：系统鼠标、键盘、滚轮。
- 不连接浏览器 CDP，不读 DOM/HTML/network/cookies/storage。
- Codex 仍是长期任务入口和调度 agent；Midscene 的外部 VLM 只做局部视觉定位/操作。
- 商品字段最终以保留截图为证据，由 Codex 复核后进入 `visual-ingest`。

`@midscene/web` 只作为对照和备选。其 Puppeteer/CDP 路线仍包含窗口尺寸 eval、导航等待、XPath cache 等页面辅助能力；Bridge/Chrome extension 路线会主动 `Runtime.evaluate` 注入脚本，淘宝主线不采用。

## browser-use MCP 开关

browser-use MCP 仅保留历史 MVP/对照用途。若临时需要复现旧测试，采用 Codex App 里的手动开关作为兜底控制：

- 平时关闭 `browser-use-local`，避免 macOS 反复弹出 Python。
- 开始采集前手动开启 `browser-use-local`，必要时重启/刷新 Codex App，让当前会话重新发现工具。
- 采集结束后手动关闭 `browser-use-local`。
- 如果关闭后仍残留 Python 进程，可手动清理：

```bash
pkill -f '/Users/zhunshi/workspace/automation/.venv/bin/browser-use --mcp'
```

`~/.codex/config.toml` 中仍保留 `browser-use-local` MCP 注册；是否启动由 Codex App 开关控制。

## 主要入口

```bash
# 准备视觉采集任务
.venv/bin/python main.py -e cards.xlsx
.venv/bin/python main.py -k 中止

# 旧 browser-use MVP 入口（历史试验）
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
```

## 项目结构

```text
main.py                  # 准备视觉采集任务
harness.py               # setup / db / visual-* 入口
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
  browser_use_driver.py  # browser-use MCP 请求/执行说明/Agent fallback
  midscene_computer_driver.py # Midscene computer MCP 请求/执行说明
  page_state.py          # 基于截图的页面状态判断
  visual_capture.py      # 截图证据与 capture manifest
  vision_extract.py      # 视觉识别结果写入 JSONL/XLSX
  session_state.py       # 账号健康与安全预算状态
  visual_pipeline.py     # 视觉任务运行、ingest、export 编排
docs/
  midscene_route_analysis.md # Midscene.js 路线审计记录
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

## 下一步

1. 在 Codex App 注册并验证 `midscene-computer` MCP。
2. 启动专用 Chrome profile，人工登录淘宝，确认系统截图和鼠标键盘权限可用。
3. 用 Midscene computer 单步完成首页搜索、首屏截图、滚动截图。
4. 截图落盘后接 `visual-ingest` / `visual-export --filter`。
5. 补异常状态样例：登录弹窗、验证码/安全验证、白框架、空结果。

## 免责声明

本工具仅用于合法的数据采集和分析目的。使用时请遵守相关网站服务条款和当地法律法规。采集速度从属于账号安全和数据可审计性。
