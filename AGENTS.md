# 淘宝店透视插件自动化工具

万智牌价格数据采集工具。新采集路线基于 AdsPower 指纹浏览器、国内短效代理池、Playwright CDP 接管和淘宝"店透视"浏览器插件，采集淘宝非登录公开搜索结果，从 DOM 提取表格数据，过滤后导出为 Excel。

## 技术栈

- Python 3.10+
- Playwright（通过 CDP 接管 AdsPower profile）
- AdsPower Local API（profile 生命周期、扩展缓存、指纹浏览器）
- pandas + openpyxl（Excel 读写）

## 项目结构

```
main.py                  # 主入口（将围绕 AdsPower + Playwright 重构）
harness.py               # 统一诊断入口：setup / db / ip-pool / adspower / plugin
run_llm_filter.py        # LLM 过滤 CLI
modules/
  adspower.py            # AdsPower Local API 诊断客户端
  proxy_pool.py          # 代理池拉取与出口 IP 连通性诊断
  task_state.py          # 任务状态、失败原因、证据目录基础结构
  browser.py             # 旧采集层：待重构或删除
  login.py               # 旧登录态检查：待删除
  search.py              # 旧插件操作：待重构
  export.py              # 旧 DOM 导出：可借鉴，采集耦合部分可重写
  filter.py              # 过滤结果（标题需含"万智牌"/"MTG"及牌名），提取最低价
  input_reader.py        # 从 Excel 读取卡牌名，去重，生成搜索关键词
  checkpoint.py          # 断点续传：记录已处理/失败的关键词
  harness_plugin.py      # harness plugin 子命令：单关键词插件交互式调试
  llm_client.py          # LLM 调用与 prompt 拼装（智谱/Minimax 等）
  llm_filter.py          # LLM 批量过滤合并结果 Excel
  mtg_db.py              # MySQL/SSH 隧道查牌名参考与短名冲突
  utils.py               # ConfigManager（读取 settings.ini）、日志、进度条
config/
  settings.ini           # 所有可配置参数（gitignored）
  settings.example.ini   # 模板
  selectors.json         # 插件 UI 的 DOM 选择器（搜索分析插件相关）
  prompts.json           # LLM 过滤用的 prompt 模板路径/片段
  keywords.txt           # 关键词示例（gitignored）
data/
  downloads/             # 导出的原始 Excel
  filtered/              # 过滤后的 Excel
  checkpoints/           # 关键词级断点文件
  logs/                  # 运行日志
  tasks/                 # 每次批量任务的合并结果（按时间戳命名目录）
```

## 核心流程

1. 从 Excel 读取卡牌名，加上前缀（默认"万智牌"）生成搜索关键词
2. 通过代理池和 AdsPower profile 建立非登录公开搜索采集环境
3. 对每个关键词：打开公开搜索页 → 打开店透视插件 → 输入 → 分析 → 等待结果 → 从 DOM 读取数据导出 Excel → 过滤
4. 全部完成后合并过滤结果到 `data/tasks/<时间戳>/合并结果.xlsx`
5. LLM 过滤（`run_llm_filter.py`）→ 输出 `_llm_filtered.xlsx`（全部 + 已删除 sheet）和 `_llm_filtered_pure.xlsx`（仅保留）
6. 统计诊断与最终赋值（`run_statistical_eval.py`、`run_final_assignment.py`）
7. 支持关键词级断点续传（checkpoint），中断后可 `--resume` 继续

## 运行命令

```bash
# 搜索 + 导出
python main.py -e cards.xlsx              # 批量处理 Excel 中的卡牌名
python main.py -e cards.xlsx --resume      # 从断点恢复
python main.py -k 中止                     # 单关键词测试
python main.py -c config/settings.ini      # 指定配置文件

# LLM 过滤
python run_llm_filter.py -i data/tasks/xxx/合并结果.xlsx

# 自检与插件调试（替代原 test_*.py）
python harness.py setup
python harness.py db
python harness.py ip-pool
python harness.py adspower
python harness.py plugin 中止
```

## 关键配置（settings.ini）

- `[INPUT]` — keyword_prefix 搜索前缀，Excel 列名映射
- `[FILTER]` — 过滤规则：require_magic_prefix、require_card_name、short_name_hard_veto、exclude_shop_names（默认拦截“真橙卡牌”）
- `[RATE_LIMIT]` — 延迟 5-15s/关键词，每 50 个暂停 60s
- `[ADSPOWER]` — Local API 地址、profile_id、超时
- `[IP_POOL]` — 代理供应商接口、健康检查 URL、超时
- `[PLUGIN]` — 分析超时、selectors.json 路径
- `[CHECKPOINT]` — auto_resume 自动恢复未完成任务
- `[LLM]` — provider、batch_size、web_search_fallback 等

## 经验积累（调试发现、架构决策等）

_此区域用于记录重要的调试经验和架构发现，确保跨设备同步。_

## 项目级记忆：AdsPower 非登录公开搜索采集迁移方案（2026-04-28）

当前项目核心业务仍是：万智牌淘宝公开搜索结果采集 → 规则/DB/LLM 过滤 → 统计评估 → 最终赋值。采集运行时可以大改，但输入读取、过滤、DB/LLM、统计诊断、最终赋值这些后处理资产必须和采集层解耦并保留下来。

### 已确认的问题与路线切换

- 旧路线是本机 `chrome_profile/`、淘宝登录态、DrissionPage、店透视插件。实际运行中出现账号被封，说明即使主要交互发生在店透视插件内，店透视服务器与淘宝通信时仍可能携带本机登录账号相关信息。
- 后续采集限定为淘宝非登录态可公开商品列表信息，不维护淘宝登录态，不采集登录态信息。
- 技术路线将迁移到 AdsPower 指纹浏览器 + 国内短效代理池 + 店透视插件。
- AdsPower profile 中的店透视插件优先通过 AdsPower 扩展中心安装和维护；插件缓存清理使用 AdsPower 的 `extension_cache` 能力，不再通过删除本机 Chrome profile 下的 extension 目录实现。
- 浏览器自动化路线优先验证 Playwright Python + AdsPower CDP 接管；如果验证失败，再考虑 Puppeteer。旧 DrissionPage 路线不保留 legacy backend。
- v1 先做单实例轮换，不做并发。稳定跑通单 profile / 单代理 / 单关键词，再扩展到小批量和后续并发。

### 即将删除或重构的采集层

- 重构原则：不要为了迁就旧结构而保留采集层代码。除“必须保留的独立业务模块”中明确列出的资产外，凡是和旧采集本身耦合的模块、CLI、配置、目录、状态枚举、调试脚本，都可以推倒重建。
- 新架构优先按 AdsPower + 代理池 + Playwright + 非登录公开搜索采集的真实边界重新组织代码；旧文件名、旧类名、旧调用链不构成兼容要求。
- 旧本机 Chrome / `chrome_profile/` / 淘宝登录检查路线将整体删除，不保留兼容分支。
- SKU 采集整块将删除，包括 `run_sku_scrape.py` 和 `modules/item_sku_scraper.py`。SKU 属于登录态相关采集，不纳入当前公开搜索结果采集路线；未来如需恢复必须另开设计。
- `main.py`、`modules/search.py`、`modules/export.py`、`modules/checkpoint.py`、`harness.py`、`config/settings.example.ini` 将围绕 AdsPower、代理池、Playwright、非登录态公开搜索结果采集进行重构。
- `config/selectors.json` 后续只保留搜索分析插件相关选择器，删除 `item_sku` 段。

### 必须保留的独立业务模块

- 输入与关键词：`modules/input_reader.py`
- 关键词级 checkpoint 能力：`modules/checkpoint.py`（字段可扩展 profile/proxy/status）
- 搜索结果过滤：`modules/filter.py`
- DB/LLM 过滤：`modules/llm_filter.py`、`modules/llm_client.py`、`modules/mtg_db.py`
- 统计诊断与最终赋值：`modules/price_cluster_eval.py`、`modules/final_assignment.py`、`run_statistical_eval.py`、`run_final_assignment.py`
- 输出目录结构：`data/downloads/`、`data/filtered/`、`data/tasks/`、`data/checkpoints/`、`data/logs/`

### 下一阶段建议的验证顺序

1. `harness.py ip-pool`：验证代理供应商接口、返回格式和代理连通性。未配置供应商时可做直连出口 IP 检查；配置供应商后用 `--limit N` 测试前 N 个代理；要求必须拿到代理时加 `--require-proxy`。
2. `harness.py adspower`：验证 AdsPower Local API 创建/更新/启动/停止 profile。
3. `harness.py plugin 中止`：验证非登录态公开搜索页可以打开店透视、输入关键词、等待结果并导出表格。
4. `python main.py -k 中止`：单关键词端到端生成原始导出与过滤结果。
5. 小批量验证 checkpoint、profile/proxy 轮换、失败分类和合并结果。

### AdsPower 与插件资源发现

- 本机 AdsPower Local API 使用 `http://localhost:50325` 可正常访问；`http://local.adspower.net:50325` 在当前环境返回 503。
- AdsPower 开启安全验证时，Local API 请求需要 `Authorization: Bearer <api_key>` header；本机 key 写入 gitignored 的 `config/settings.ini`，不要提交。
- 当前测试 profile_id 为 `k1bhu4iu`，已能通过 `harness.py adspower --start` 启动并返回 `ws.puppeteer`，也能通过 `--probe-url http://httpbin.org/ip` 被 Playwright CDP 接管并截图。
- 店透视 CRX 已复制到 `resources/extensions/店透视-Chrome_5.0.6.crx`。AdsPower 官方文档建议扩展通过 Extensions → Team 上传/管理，而不是直接在 profile 内安装；自动化安装方式需单独验证，不要假设 CRX 可直接注入 profile。
- `harness.py adspower --set-proxy-from-pool` 已能从 `[IP_POOL]` 提取 1 个代理并写入 AdsPower profile 的 `user_proxy_config`。

### 跨设备恢复步骤

- 换电脑后不要假设 AdsPower Local API 地址、端口、API key、profile_id 不变；这些都属于本机状态，应重新在新电脑的 `config/settings.ini` 填写。
- AdsPower 官方默认地址可能是 `http://local.adspower.net:50325` 或 `http://localhost:50325`；如其中一个 503，优先试另一个。必要时在 AdsPower 客户端 Automation/API 页面确认端口和 key。
- 新电脑恢复顺序：复制 `config/settings.example.ini` 为 `config/settings.ini` → 填 `[IP_POOL]`、`[ADSPOWER]` → 运行 `python harness.py ip-pool --limit 1 --require-proxy` → 运行 `python harness.py adspower` → 运行 `python harness.py adspower --set-proxy-from-pool` → 运行 `python harness.py adspower --probe-url http://httpbin.org/ip`。
- 当前执行进度：代理池可提取 20 个标准文本 `ip:port`，`http://httpbin.org/ip` 健康检查可用；AdsPower 使用 `localhost:50325` + Bearer key 可用；profile `k1bhu4iu` 已成功写入代理、启动并被 Playwright CDP 接管；profile 已通过 `harness.py adspower --stop` 停止。
- 下一步计划：验证店透视扩展在 AdsPower profile 中的安装/可见性；将 `harness.py plugin 中止` 从旧 DrissionPage 实现迁移为 AdsPower + Playwright + 非登录公开搜索页 + 店透视 DOM 诊断。

### 长期任务调度与 Agent 接管边界

- 系统长期应分为三层：采集执行层、状态与证据层、智能调度/Agent skill 层。
- MVP 阶段优先跑通单实例采集闭环，不急于实现完整 agent 自动调度；但必须把任务状态、失败证据和恢复入口设计成 agent 可读、可判断、可接管。
- 采集执行层保持机械化：给定关键词、profile、代理，执行一次公开搜索采集，输出结构化结果和失败证据，不在采集层塞复杂策略。
- 状态与证据层必须保留足够现场：checkpoint、日志、截图、当前 URL、关键 DOM 文本、profile_id、proxy、时间戳、错误消息、任务目录。
- 关键词任务状态先采用粗粒度枚举：`pending`、`running`、`success`、`failed`、`retryable`、`needs_human`、`skipped`。
- 失败原因先粗分，不追求一次穷尽：`proxy_error`、`adspower_error`、`plugin_error`、`captcha_or_risk`、`no_results`、`dom_changed`、`timeout`、`unknown`。
- checkpoint 字段预留 `agent_notes`、`evidence_dir`、`retry_count`、`last_action`、`profile_id`、`proxy`、`status`，方便后续 Codex agent 或 skill 根据证据决定下一步。
- 未来可封装若干 agent skill：任务诊断、代理处理、AdsPower profile 处理、插件恢复、批量恢复、结果审计。不要在 MVP 阶段过早把这些 skill 写死成复杂自动驾驶逻辑。
- 所有恢复动作优先做成明确 CLI 子命令或函数，例如 `harness.py ip-pool`、`harness.py adspower`、`harness.py plugin`、`main.py --resume`，让人工和 agent 都能调用同一套入口。

## 开发注意事项

- 不再维护本机 `chrome_profile/` 和淘宝登录态；后续采集限定为非登录公开搜索结果
- 插件 UI 操作依赖 `selectors.json` 中的文本匹配（如"市场分析"、"搜索内容"），插件更新后可能需要调整
- `selectors.json` 后续只保留搜索分析插件相关选择器，不再保留 `item_sku` 段
- `export.py` 从 DOM 直接读取表格数据，不依赖文件下载
- 限速参数是为了避免触发淘宝反爬，修改需谨慎
- AdsPower profile、代理池、失败分类和 checkpoint 需要先在单实例轮换中验证稳定，再考虑小批量

## 验证建议

- 准备三类公开搜索样本：正常有结果、低结果/无结果、疑似风控或验证码场景
- 检查 `harness.py ip-pool`、`harness.py adspower`、`harness.py plugin 中止` 是否能按顺序跑通
- 检查单关键词 `python main.py -k 中止` 是否能生成原始导出、过滤结果和任务目录
- 检查 checkpoint 是否记录 profile/proxy/status，并能在中断后恢复关键词级处理
