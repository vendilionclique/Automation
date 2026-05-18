# 2026-05-18 边界审查与清理交棒

## 当前状态

分支：

```text
codex/three-stage-business-boundaries
```

当前工作树仍未提交。旧 handoff 已按用户要求删除，只保留本文件作为唯一交接入口。

本轮接手后新增完成：

- 修复 `modules/midscene_computer_driver.py` 中 `business_boundaries_enabled` 兼容读取问题：不再调用 `ConfigManager` 不支持的 `has_option`，改为用项目现有 `get(..., fallback=sentinel)` 风格判断新旧配置名。
- 删除过时 handoff：
  - `HANDOFF_20260518_HOME_ENTRY_SIMPLE_RESET.md`
  - `HANDOFF_20260518_MIDSCENE_BOUNDARY_REWORK.md`
  - `HANDOFF_20260518_THREE_STAGE_BUSINESS_BOUNDARIES.md`
  - `HANDOFF_20260518_THREE_STAGE_IMPLEMENTATION_STOPPOINT.md`
- 清理低风险可重建缓存和临时物：
  - `data/tasks/plan/`
  - `data/tasks/run/`
  - 项目层 `.DS_Store`
  - 项目层 `__pycache__`
  - `midscene_run/`
  - `local/midscene-run/log/`
  - `local/midscene-run/report/`
  - `local/midscene-run/action_preflight_*.json`
  - `local/midscene-run/latest_action_preflight.json`
  - `local/midscene-run/manual_action_preflight_check.json`

未删除真实运行证据、本机密钥或本机配置。继续保护：

- `config/settings.ini`
- `local/midscene-computer.env`
- `local/chrome-taobao-visual-profile/`
- `data/tasks/20260517_172653/`
- 近期真实 `data/tasks/supervisor_*`、`three_stage_*` evidence
- `goal_contract.json`、`action_trace.jsonl`、`evidence_check.jsonl`、`capture_decision.jsonl`
- `keyword_result.json`、`tile_00*.png`、异常截图、extract/apply 产物

## 已确认业务口径

不要再把当前模型说成“只有三段业务边界”。

当前完整业务边界集合是：

```text
desktop_chrome_ready_boundary
home_entry_boundary
search_submit_boundary
capture_tiles_boundary
safe_popup_repair_boundary
human_stop_boundary
```

其中 `home_entry_boundary -> search_submit_boundary -> capture_tiles_boundary` 只是采集主干三段；Chrome 不在前台、Chrome 未处于可继续采集状态、普通营销弹窗 repair、登录/验证码/风控/权限/未知高风险停机，都已经是业务边界模型的一部分。

## 已完成改动范围

### 边界命名收口

- `config/settings.example.ini` 新增主配置名：

```ini
business_boundaries_enabled = true
```

- 旧 `three_stage_business_boundaries` 只作为兼容读取保留，避免旧 contract 或旧本机配置立刻失效。
- `modules/midscene_computer_driver.py` 的 contract 同时写：
  - `business_boundaries_enabled`
  - `three_stage_business_boundaries` 兼容字段
  - 完整 `business_boundaries` 列表
- `modules/visual_capture_worker.py` 内部判断函数为 `_business_boundaries_enabled()`，优先读新字段，再读旧字段。
- `modules/visual_goal_contract.py` 的 goal contract 已加入完整六类边界。
- `README.md`、`AGENTS.md`、`docs/agent_project_setup.md`、`local/README.md` 已修正口径：六类业务边界 + 三段采集主干。

### Midscene 边界与 preflight

- `modules/midscene_computer_driver.py`
  - 新增 `MIDSCENE_INTERNAL_ACTION_POLICY`
  - contract 中加入 `desktop_chrome_ready_boundary`、`safe_popup_repair_boundary`、`human_stop_boundary`
  - 文案从“Midscene 不得使用短动作”改为“Python/Codex 不直接调用短动作；Midscene act 内部可使用可见 GUI 原语”
- `modules/visual_capture_worker.py`
  - 增加 Midscene MCP lifecycle diagnostics
  - 增加 `_run_midscene_preflight()`
  - prompt 加入 `boundary_name`、`boundary_completed`、`actions_summary` 等结构化交付字段
  - foreground recovery、safe popup repair、home-entry/search-submit/capture-tiles 边界文案已扩展
- `modules/visual_capture_watchdog.py`
  - watchdog 退出时读取 capture runtime 中的 `mcp_pgid`，尝试清理残留 Midscene MCP 进程组

### 旧 wrapper 收口

已从 `modules/visual_capture_worker.py` 删除只剩测试引用的旧 wrapper：

```text
_perform_keyword_search
_keyword_search_prompt
_keyword_search_home_entry_prompt
_keyword_search_home_entry_retry_after_exception_prompt
_keyword_search_reset_prompt
```

测试已改为直接调用当前名称：

```text
_perform_search_submit_boundary
_search_submit_boundary_prompt
```

### 依赖自检轻量清理

- `harness.py setup` 已移除 `pyperclip` import 自检。
- `requirements.txt` 里的 `pyperclip>=1.8.0` 已移除，`AGENTS.md` 旧的 `pyperclip` 自检历史描述已清掉。

### post-keyword cleanup 收口

- `post_keyword_cleanup` 确认是交给 Midscene `act` 的可见 UI prompt，不是 Python 短动作驾驶代码。
- prompt 已移除固定 `Command+W` / `Ctrl+W` 要求，改为让 Midscene 优先选择低风险可见 UI 路径离开当前结果页。
- cleanup 仍只对干净 `captured` 且后面还有关键词时执行；失败只写 diagnostics，不替代下一个关键词自己的 pre-entry 验收。

### 行为模拟默认关闭

- 当前主线默认关闭详情页、购物车/收藏等“更像真人浏览”的额外动作：
  - `detail_page_peek_probability=0`
  - `cart_or_favorites_peek_probability=0`
  - `allow_cart_or_favorites_peek=false`
- 这些字段作为远期实验占位保留。未来若恢复鼠标自然移动、输入退格、首页推荐流商品随机打开/滚动/关闭、商品详情页、购物车或收藏页等行为模拟，必须作为单独实验重新设计 prompt、行为预算、账号安全 stop rule 和测试，不能静默接回默认采集主线。

## 已运行验证

本轮接手后重新跑过：

```bash
.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py
.venv/bin/python -m unittest tests.test_visual_capture_worker tests.test_visual_capture_watchdog tests.test_page_state_classifier tests.test_midscene_config tests.test_visual_goal_contract
scripts/check_portable_config.sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m unittest tests.test_visual_capture_worker tests.test_midscene_config tests.test_codex_extract
```

结果：

```text
py_compile: OK
targeted unittest: 153 tests OK
portable config checks: passed
full unittest: 180 tests OK, 1 skipped
latest targeted unittest after cleanup/prompt changes: 122 tests OK
```

额外检查：

```bash
rg -n "_perform_keyword_search|_keyword_search_prompt|_keyword_search_home_entry_prompt|_keyword_search_reset_prompt" modules tests
```

结果：无命中。

```bash
rg -n "three_stage_business_boundaries" modules config tests README.md docs AGENTS.md
```

结果：只剩兼容读取、兼容字段和对应测试断言。

## 当前主路径

```text
visual-plan-day
-> visual-heartbeat / visual-session-run
-> visual-capture-watchdog
-> visual-capture-worker
-> business boundaries with Midscene computer MCP
-> visual-codex-extract-prepare / dispatch / drain
-> visual-apply-extracted-rows
```

## 后续建议

1. 若继续清理，建议逐个处理并分别跑测试：
   - `allow_midscene_page_state_probe` 兼容读取和测试
   - `docs/midscene_route_analysis.md` 里的旧安装/下一步描述
   - `scripts/save_midscene_computer_screenshot.cjs`
   - `data/tasks/probe_seed_1779077294/`
2. 不要启动真实淘宝长跑，除非用户明确要求。当前任务是代码审查、收口和清理，不是新一轮采集验证。
3. 提交前再跑一次：

```bash
.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py
.venv/bin/python -m unittest discover -s tests
scripts/check_portable_config.sh
```

## 当前风险提示

- `partial captured` 语义仍偏宽：后续滚动失败、超时或 supervisor interrupt 后，只要已有可采集截图，可能仍写 `captured`。这是当前有意接受的策略，因为 extract 可以消费这些有效截图；远期应把 `captured_partial_*` stop reason / diagnostics 继续传到后处理、写回输入台账，并让 scheduler 结合采集时间、partial 标记和赋值质量决定下次是否重采。
- `post_keyword_cleanup` 已不再固定快捷键，但仍是成功关键词后的可选清场 prompt；它不能替代下一个关键词自己的 home-entry 验收。
- 行为模拟字段当前默认关闭，只保留远期实验占位；未来不能静默接回默认采集主线。
