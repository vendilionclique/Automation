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

Windows 暂不纳入当前业务主线；PowerShell 脚本仅作为远期/实验辅助保留。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_taobao_visual_chrome.ps1
```

配置 Midscene computer MCP 的外部 VLM key：

```bash
cp local/midscene-computer.env.example local/midscene-computer.env
# 默认示例使用智谱 glm-4.6v-flash；编辑本机文件，只填写 MIDSCENE_MODEL_API_KEY。
```

Codex App 的 MCP server 使用 `local/start_midscene_computer_mcp.sh` 启动，
该脚本会读取本机 env 文件；key 不写入仓库，也不写入 `~/.codex/config.toml`。

准备单关键词视觉任务：

```bash
.venv/bin/python harness.py visual-one 中止
```

从全量输入台账生成当天分段采集计划：

```bash
.venv/bin/python harness.py visual-plan-day --raw-input cards.xlsx
.venv/bin/python harness.py visual-scheduler-status <plan_id>
.venv/bin/python harness.py visual-heartbeat --mode prepare --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-heartbeat --mode dispatch --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-capture-watchdog --plan-id <plan_id> --session 1 --start
.venv/bin/python harness.py visual-control status --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-sync-worker <plan_id> --session 1
```

`visual-heartbeat` 是当前本地 scheduler / automation 的短命心跳入口：它根据已有 plan、session 状态和 `control.json` 执行 `sync`、`prepare`、`dispatch` 或 `all`，只做确定性判断、准备 session worker contract、返回 worker 命令；不打开 Chrome、不触碰淘宝页面、不直接启动后台进程。`visual-auto-tick` 是旧的 plan/session 选择辅助入口，`visual-automation-tick --start-capture` 是旧 automation 的兼容薄入口；两者都不再作为文档主线。`visual-plan-day` 会从 `preferred_mode=statistical` 且 `淘宝采集时间` 缺失或过期的牌名中，按日预算和 session 数自动挑选关键词；`skip` 和 `with_keywords` 不进入当前默认统计采集池。`with_keywords` 表示该行未来应使用“万智牌 中文牌名 关键词”这类更具体的搜索结果统计赋值；当前只记录为待处理路由，尚未实现额外关键词采集或赋值。

术语约定：

- `scheduler`：确定性计划层，负责 daily plan、session 切分和 due session 选择。
- `heartbeat`：短命唤醒动作，负责 sync / prepare / dispatch advice；由 Codex App Automation 或等价可见定时器按小时级触发。
- `capture watchdog`：session 级 bounded watchdog，在单个 session 生命周期内常驻监督一个 capture worker；worker 正常活着就等待，异常死亡/stale/recoverable failed 时按规则恢复，session 完成、人工异常、control block 或 idle timeout 后退出。
- `supervisor`：非常驻人工/Codex 监督者，只做状态查看、异常裁判和 `visual-control`，不承担全天常驻调度。

session due-time 可配置在 `[SCHEDULER]`。生产建议使用固定时刻，例如 `session_due_times = 09:00,13:00,17:00,21:00`，数量必须等于 `daily_session_count`；短间隔测试可临时设置 `session_due_interval_minutes = 3`，表示从 plan 创建时间起每 3 分钟到期一个 session。大于 0 的 interval 会优先于固定时刻。

`visual-heartbeat --mode dispatch` 会返回 `capture_start_allowed` 和 `capture_worker_liveness`。外部 automation 只有在 `capture_start_allowed=true` 时才能启动 `worker_commands.capture`；如果 runtime 显示 capture worker 仍 active，不要重复启动。若 runtime 显示 `running` 但 pid 已消失或超过 `[SCHEDULER] capture_worker_stale_after_minutes` 且没有 `session_worker_result.json`，heartbeat 会标记 `capture_worker_stale` / `failed_recoverable`，让该 session 后续可恢复重跑。

Codex App Automation 推荐到点启动当前 due session 的 bounded watchdog，而不是直接启动 capture worker：

```bash
.venv/bin/python harness.py visual-capture-watchdog \
  --plan-id <plan_id> \
  --session 1 \
  --start \
  --poll-seconds 30 \
  --idle-timeout-seconds 900 \
  --max-restarts 2
```

该命令不是全天 scheduler，也不是系统 daemon。它只在这个 session 生命周期内运行：循环调用 heartbeat、读取 liveness 和 `capture_start_allowed`，只在允许且有 `worker_commands.capture` 时启动一个 capture worker；worker 活着就轮询等待，worker 退出后 sync，再判断是否需要恢复或退出。省略 `--start` 时是 dry-run / advice 模式，不打开 Chrome、不启动采集。`visual-automation-tick --start-capture` 仍保留为兼容薄入口，但文档主线改为 `visual-capture-watchdog`。

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
- Codex 负责 plan/session 监督、异常裁判、证据复核和后处理编排；长期在线调度交给短命 heartbeat、worker contract 和文件状态。
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
.venv/bin/python harness.py visual-plan-day --raw-input cards.xlsx
.venv/bin/python harness.py visual-heartbeat --mode prepare --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-heartbeat --mode dispatch --plan-id <plan_id> --session 1
.venv/bin/python harness.py visual-capture-watchdog --plan-id <plan_id> --session 1 --start
.venv/bin/python harness.py visual-control status --plan-id <plan_id> --session 1
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
scripts/check_portable_config.sh
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
