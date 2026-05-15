# 淘宝万智牌价格视觉采集工具

本项目用于采集淘宝上万智牌相关商品的可见价格信息，并接入规则过滤、DB/LLM 过滤、统计评估和最终赋值流程。

当前仓库已经收敛为“本机 Chrome 真实登录态 + 低频 human-in-the-loop + 可见截图证据 + Codex/视觉模型识别”的主线。旧的 AdsPower、代理池、店透视插件、DOM 导出、SKU 插件采集、browser-use/CDP fallback 和项目内 Chrome profile 已从代码树删除。

## 当前状态

- `.venv/bin/python harness.py setup` 自检通过。
- Midscene computer MVP 已跑通过，当前版本继续沿用系统截图 + 系统鼠标键盘 MCP 路线。
- 当前依赖只保留 `@midscene/computer`；Web bridge/CDP 相关依赖已移除。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config/settings.example.ini config/settings.ini
npm install
```

编辑 `config/settings.ini`：

- `[VISUAL_CAPTURE] provider = midscene_computer` 保持默认主线。
- 不要提交 `config/settings.ini`，其中会包含本机路径和可能的密钥。

自检：

```bash
.venv/bin/python harness.py setup
```

启动专用 Chrome 采集 profile，并人工登录淘宝：

```bash
bash scripts/start_taobao_visual_chrome.sh
```

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_taobao_visual_chrome.ps1
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

从全量输入台账生成当天分段采集计划：

```bash
.venv/bin/python harness.py visual-auto-tick --raw-input cards.xlsx
.venv/bin/python harness.py visual-auto-tick --raw-input cards.xlsx --prepare-requests

.venv/bin/python harness.py visual-plan-day --raw-input cards.xlsx
.venv/bin/python harness.py visual-scheduler-status <plan_id>
.venv/bin/python harness.py visual-session-capsule <plan_id> --session 1
.venv/bin/python harness.py visual-session-run <plan_id> --session 1
.venv/bin/python harness.py visual-sync-worker <plan_id> --session 1
.venv/bin/python harness.py visual-session-lease <plan_id> --session 1 --action inspect
```

`visual-auto-tick` 是 automation / Slack / 新 Codex 会话的默认入口：它读取整本台账，自动创建或复用当天 `daily_YYYYMMDD` plan，并根据当前时间和任务状态选择应运行的 session。日常远程触发不需要人工知道 `plan_id` 或 `session`。`visual-plan-day` 会从 `preferred_mode=statistical` 且 `淘宝采集时间` 缺失或过期的牌名中，按日预算和 session 数自动挑选关键词；`skip` 和 `with_keywords` 不进入当前默认统计采集池。`with_keywords` 表示该行未来应使用“万智牌 中文牌名 关键词”这类更具体的搜索结果统计赋值；当前只记录为待处理路由，尚未实现额外关键词采集或赋值。

长程运行不依赖单个 Codex 会话的上下文。每个 session 都可以生成独立
capsule：

```text
data/tasks/<plan_id>/sessions/session_01/
  session_request.json
  session_prompt.md
  lease.json
  events.jsonl
  summary.json
```

新的 Codex 线程、cron automation、Slack/远程触发器只需要读取
`session_request.json` 和 `session_prompt.md`，再执行对应 session。任务进度以
`visual_tasks.json`、`task_events.jsonl`、`tile_summary.jsonl`、`raw_rows.jsonl`
和 session capsule 为准，不依赖旧聊天历史。视觉识别上下文按“关键词”拆分；
同一关键词的 3-4 个 viewport tiles 可以放在同一个识别上下文里批量去重。

大项目开发默认采用 subagent team：主 agent 只做需求拆解、任务调度、代码审查、
集成和最终汇报，具体实现/局部排查/测试修复交给边界清晰的 worker 或 explorer
subagent。小修、验证、补丁收尾等也优先复用仍有上下文余量的已有 subagent，避免
主 agent 消耗自己的上下文；只有没有可用 subagent 或复用成本明显高于任务本身时才
由主 agent 直接处理。上下文接近耗尽、压缩不可靠，或遇到 GPT-5.5 上下文压缩卡死
迹象时，先把进度写入 session capsule、`summary.json`、`events.jsonl`、
`task_events.jsonl` 或控制/状态文件，再切换到新线程继续；新线程读取这些文件和
`AGENTS.md` 后接棒。随着 Codex App 更新，这类压缩问题可能会缓解，但项目状态仍以
文件为准。

`visual-run` 默认会在 evidence 目录生成 `midscene_computer_request.json`
和 `codex_midscene_computer_instructions.md`。Codex App 通过
midscene-computer MCP 使用系统截图、坐标点击、键盘输入和滚动完成采集；
截图落盘后，Codex extract worker 按 keyword 级 contract 看图抽取商品行；
确定性落盘由 `visual-apply-extracted-rows` 完成：

`visual-capture-worker --contract ...` 会通过本机
`local/start_midscene_computer_mcp.sh` 连接 Midscene computer MCP 执行真实
bounded capture，环境不可用时写 `real_not_available`，不会伪装成已采集。
新路线里只有 Codex extract worker 负责看截图抽取商品行：
`visual-codex-extract-prepare` 为 captured keyword
生成 `extract_request.json` / `extract_prompt.md`，`visual-codex-extract-dispatch`
返回或用 `codex exec` 启动短命非交互式 worker，worker 写
`rows_result.json` 后运行 `visual-apply-extracted-rows`。`visual-apply-extracted-rows`
只是确定性应用已抽取 rows 到 `raw_rows.jsonl` / `raw_results.xlsx`，不是第二种抽取
worker。

`visual-codex-extract-dispatch` 会在命令级显式传入 configured
`approval_policy` / `sandbox_mode`，默认加 `--ignore-rules`，并把
`effective_extract_config` 输出到 summary，降低本地 profile 漂移和 execpolicy
rules 的影响；extract prompt 自包含，并明确要求 worker 不读取项目规则文件。若
`launch_state.json` 里的旧 PID 已死亡，会标记为
`stale` / `previous_pid_dead` 并允许重派。

本地 scheduler / launcher 可以启动 `codex exec` 短命 worker，但不能创建 Codex App
UI 中可见的新聊天会话；需要可见会话和人工追踪时，应由 Codex App automation、
人工 supervisor 或未来 CC-connect/飞书触发 supervisor 会话。

```bash
.venv/bin/python harness.py visual-codex-extract-prepare --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1 --start
.venv/bin/python harness.py visual-apply-extracted-rows \
  --request data/tasks/<plan_id>/sessions/session_01/codex_extract/<keyword>/extract_request.json
```

默认截图保留策略是 `human_required_only`：成功任务删除截图；低置信或可自愈异常只写日志；只有登录、验证码、安全验证、疑似风控、连续异常等人工介入级别才保留截图。v1 会按 `PAGE_SAMPLING.max_tiles_per_keyword` 采完整页可见 tiles，不按商品数早停；`visual-apply-extracted-rows` 会对同一任务内重复行做轻量去重，并用 `PAGE_SAMPLING.target_listings_per_keyword` 作为每关键词近似保护上限。

导出 raw Excel，并可选接入规则过滤：

```bash
.venv/bin/python harness.py visual-export <run_id>
.venv/bin/python harness.py visual-export <run_id> --filter --keyword "万智牌 中止" --card "中止"
```

## 安全边界

- 不自动登录。
- 不处理验证码、短信、安全验证。
- 不读 DOM、接口、cookies、storage、CDP 数据；淘宝主线不使用 Web bridge/CDP。
- 只采集真实登录用户当前可见页面里的标题、价格、店铺、地区等信息。
- 优先评估 Midscene computer MCP：系统截图输入，系统鼠标键盘输出。
- 如果刚给 Codex App、Chrome、终端或自动化组件打开 macOS 权限，或刚切换 MCP 开关，请先重启/刷新 Codex App 再测试。

## Midscene.js 评估

```bash
npm run midscene:version
npm run midscene:computer:help
```

当前优先评估 `midscene-computer` MCP：

- 输入：系统截图。
- 定位：截图/VLM。
- 输出：系统鼠标、键盘、滚轮。
- 不连接浏览器 CDP，不读 DOM/HTML/network/cookies/storage。
- Codex 仍是长期任务入口和调度 agent；Midscene 的外部 VLM 只做局部视觉定位/操作。
- `visual-session-run` now also writes a bounded small-session worker contract:
  `sessions/session_NN/midscene_session_worker_request.json`. Midscene may
  continuously capture the selected keywords inside that contract, but Codex
  still owns daily planning, abnormal-state strategy, screenshot review,
  `visual-apply-extracted-rows`, filtering, and downstream assignment.
- 商品字段最终以保留截图为证据，由短命 Codex extract worker 复核后进入
  `visual-apply-extracted-rows`。
- Midscene 请求会包含自然节奏边界：短操作分段随机暂停、关键词间分钟级长暂停，以及只读低副作用动作限制。
- Midscene 请求会包含 viewport tile 采样边界：系统截图分片、视觉/屏幕几何滚动估算、最多 tile 数、禁止翻页和截图保留策略。

## 主要入口

```bash
# 准备视觉采集任务
.venv/bin/python main.py -e cards.xlsx
.venv/bin/python main.py -k 中止

# Midscene computer / 视觉采集入口
.venv/bin/python harness.py visual-one 中止
.venv/bin/python harness.py visual-run <run_id> --limit 1
.venv/bin/python harness.py visual-auto-tick --raw-input cards.xlsx --prepare-requests
.venv/bin/python harness.py visual-plan-day --raw-input cards.xlsx
.venv/bin/python harness.py visual-session-capsule <plan_id> --session 1
.venv/bin/python harness.py visual-session-run <plan_id> --session 1
.venv/bin/python harness.py visual-sync-worker <plan_id> --session 1
.venv/bin/python harness.py visual-codex-extract-prepare --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-codex-extract-dispatch --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-session-lease <plan_id> --session 1 --action inspect
.venv/bin/python harness.py visual-scheduler-status <plan_id>
.venv/bin/python harness.py visual-log-tile <run_id> --keyword "万智牌 中止" --tile-id tile_00
.venv/bin/python harness.py visual-log-event <run_id> --event session_started
.venv/bin/python harness.py visual-apply-extracted-rows --request data/tasks/<plan_id>/sessions/session_01/codex_extract/<keyword>/extract_request.json
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
  midscene_computer_driver.py # Midscene computer MCP 请求/执行说明
  page_sampling.py       # viewport tile 采样配置、事件日志和 tile 摘要
  page_state.py          # 基于截图的页面状态判断
  visual_capture.py      # 截图证据与 capture manifest
  vision_extract.py      # 视觉识别结果写入 JSONL/XLSX
  session_state.py       # 账号健康与安全预算状态
  session_capsule.py     # session capsule / lease / 短线程上下文
  visual_scheduler.py    # 全量台账日预算/session 计划
  codex_extract.py       # Codex extract contract、codex exec 启动建议、确定性 rows apply
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
4. 截图落盘后接 `visual-codex-extract-prepare` / `visual-codex-extract-dispatch` / `visual-apply-extracted-rows`。
5. 补异常状态样例：登录弹窗、验证码/安全验证、白框架、空结果。

## 免责声明

本工具仅用于合法的数据采集和分析目的。使用时请遵守相关网站服务条款和当地法律法规。采集速度从属于账号安全和数据可审计性。
