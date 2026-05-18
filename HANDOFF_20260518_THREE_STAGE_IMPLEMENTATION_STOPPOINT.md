# 2026-05-18 三段业务边界实现收口

## 当前状态

分支：

```text
codex/three-stage-business-boundaries
```

本轮基于 `HANDOFF_20260518_THREE_STAGE_BUSINESS_BOUNDARIES.md` 的设计，把采集动作收口为：

```text
home_entry_boundary -> search_submit_boundary -> capture_tiles_boundary
```

原则仍是：按业务不可混淆边界拆，不按 UI 动作拆。

## 已收口内容

- 三段边界主干已进入提交 `ebd7102 统一三段采集边界与429冷却重试`。
- `home_entry_boundary` 在每个关键词前验证普通淘宝首页，不在活动页、采购优选页、旧结果页或外站搜索框里直接提交关键词。
- `search_submit_boundary` 只负责在已验证普通首页提交当前关键词，`tile_00` 继续作为搜索提交后的首屏硬验收。
- `capture_tiles_boundary` 只在已验收的当前关键词结果页内滚动采样；`results_end` 和相邻截图高相似只结束当前关键词，不触发重搜。
- Midscene 429 / rate-limit 在 home-entry act 阶段触发时，会先把 `pre_keyword_home_entry` diagnostics 落盘，再停为 rate-limited。
- 普通淘宝营销弹窗的处理已作为 act 内部“视觉工具箱”注入 home-entry、home-entry retry、search-submit 和 cleanup 边界：只允许点击弹窗自身安全灰色 X，不能点击登录、验证码、风控、购物车、收藏、领取/使用权益或其他账号状态按钮。
- page-state classifier 现在把遮挡首页搜索框、搜索按钮或结果控件的普通营销弹窗优先判为 `closeable_popup_overlay`，不让它被普通 `visible_ready` 掩盖。
- watchdog 启动 capture worker 时使用独立进程组；watchdog 退出时会清理该进程组，即使主 worker 已退出，也会尝试终止同组残留的 Midscene MCP launcher。

## 已处理的中断现场

原线程 `019e3943-b349-7c21-ac4d-ef6422a32a12` 卡死前的真实测试 plan：

```text
supervisor_20260518_three_stage_8kw_valid_120853
```

已通过控制面暂停：

```text
reason=user_interrupted_popup_tooling_review
```

接手后复查并清理了残留的本项目 `midscene_computer_mcp_launcher.cjs` 进程；复查时已无 `visual-capture-watchdog`、`visual-capture-worker`、`midscene_computer_mcp_launcher` 残留。

## 验证结果

```bash
.venv/bin/python -m unittest tests.test_visual_capture_watchdog
.venv/bin/python -m unittest tests.test_visual_capture_worker tests.test_page_state_classifier
.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py
.venv/bin/python -m unittest discover -s tests
scripts/check_portable_config.sh
```

结果：

```text
visual_capture_watchdog: 17 tests OK
visual_capture_worker + page_state_classifier: 110 tests OK
py_compile: OK
full unittest discover: 177 tests OK, 1 skipped
portable config checks: passed
```

## 仍未做

- 没有重新启动真实淘宝 8 关键词长跑。
- 营销弹窗处理仍是 prompt/classifier 层面的受限视觉行为，需要下一次真实留样观察 Midscene 是否稳定只点灰色 X。
- 滚动采集阶段仍保持保守：普通营销弹窗如果在 capture tiles 中出现，不把关闭弹窗作为默认滚动工具，优先交给 page-state/gate 停机复核。

## 下一步建议

下一次真实验证只做小批量、低频、可中断运行，重点观察：

- 首页红包/优惠券弹窗是否被安全关闭。
- 是否出现误点领取、使用权益、登录、验证码或账号状态按钮。
- watchdog 被暂停/中断后是否仍有 Midscene MCP launcher 残留。
- `tile_00` 是否继续严格要求搜索已提交且页面为当前关键词结果页。
