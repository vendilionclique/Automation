# 2026-05-18 Home-Entry Simple Reset Handoff

## Current State

User asked to implement the "淘宝 Home-Entry 朴素化修复计划", but then asked to stop before context pressure and hand off. I stopped mid-implementation after a safe partial patch. No tests have been run after these edits.

Current `git status --short`:

```text
 M modules/page_state_classifier.py
 M modules/visual_capture_worker.py
 M tests/test_page_state_classifier.py
 M tests/test_visual_capture_worker.py
?? HANDOFF_20260518_HOME_ENTRY_SIMPLE_RESET.md
```

## What Has Been Changed

### `modules/page_state_classifier.py`

- Prompt now says `is_home_feed` must not be used as `state`; it is only the boolean field.
- `_normalize_classifier_payload()` now has a helper `_normalize_classifier_state()`.
- `state == "is_home_feed"` now maps:
  - to `visible_ready` when it looks like a normal homepage feed;
  - to `unknown` when it has submitted-search/result evidence or looks like non-ordinary Taobao home.
- Added `_looks_like_non_ordinary_taobao_home()` with markers such as `huodong.taobao.com`, `dailygroup`, `s.taobao.com/search`, `采购优选`.

Important review point: this helper currently treats any reason containing `活动` as non-ordinary. That may be too broad; next agent should review before finalizing.

### `modules/visual_capture_worker.py`

- Added `home_entry_reset_failed` to `HARD_ABNORMAL_REASONS`.
- Session loop now stops session immediately when a keyword returns:
  - `status == "needs_review"`
  - `stop_reason in {"home_entry_unverified", "home_entry_not_reached", "home_entry_reset_failed"}`
- `_prepare_home_entry_before_keyword()` now converts a failed retry from `home_entry_unverified` / `home_entry_not_reached` into `home_entry_reset_failed`.
- `_home_entry_review_reason()` now rejects `visible_ready` if URL/page evidence indicates a non-ordinary Taobao surface.
- `_should_retry_pre_keyword_home_entry()` now retries once on `home_entry_unverified`.
- Pre-keyword and retry prompts now use the simple business rule: only ordinary `taobao.com` homepage is acceptable before searching; activity/campaign/purchase-selection/old result pages must not have their search boxes used.

Important review point: session loop stop happens before `_should_stop_immediately()`, so it returns session `needs_review` without calling `_request_worker_cooldown()`. This is intentional-ish, but the next agent should decide whether to write control pause/cooldown as well.

### Tests Partially Updated

`tests/test_page_state_classifier.py`:

- Added tests for:
  - `state=is_home_feed` on normal `taobao.com` homepage -> `visible_ready`
  - `state=is_home_feed` on `huodong.taobao.com/...dailygroup...` -> `unknown`
  - conflicting home feed + result evidence -> `unknown`
- Updated prompt test to expect "Never use is_home_feed as the state value".

`tests/test_visual_capture_worker.py`:

- Test helper now allows raw `state=is_home_feed` and routes parsed payloads through the real classifier normalizer.

## Still To Do

1. Run compile/tests and fix failures:

```bash
.venv/bin/python -m py_compile harness.py modules/*.py tests/*.py
.venv/bin/python -m unittest discover -s tests
scripts/check_portable_config.sh
```

2. Add/adjust worker tests:

- `test_pre_keyword_home_entry_unverified_retries_bounded_reset_once_then_searches_when_verified`
- `test_pre_keyword_home_entry_unverified_retry_failure_stops_before_keyword_search`
- Session-level test that home-entry reset failure stops the batch before the next keyword.
- Update old test around `unknown` not retrying. Search for:

```bash
rg -n "unknown|home_entry_unverified|pre_keyword_home_entry_retry|Command\\+W|is_home_feed" tests/test_visual_capture_worker.py
```

3. Review exact business boundary:

- "普通淘宝首页" should probably mean explicit normal `taobao.com` homepage/search-entry.
- Do not accept `huodong.taobao.com`, `dailygroup`, `s.taobao.com/search`, purchase-selection pages, activity pages, old result pages, or unrelated sites as home-entry success.
- Keep `post_keyword_cleanup` `Command+W` unchanged for this round, per user instruction.

4. Review prompt wording for over-broad Chinese words:

- `_looks_like_non_ordinary_taobao_home()` currently includes `活动`; this may mark too much as non-ordinary from classifier reason text. Consider relying more on URL/page evidence markers and less on generic words.

5. After tests pass, run a small dry-run or unit-only evidence check. Do not start real Taobao capture unless user explicitly asks.

## Subagent Notes Already Received

- Classifier explorer suggested not adding `is_home_feed` to `CLASSIFIER_STATES`; keep it as a boolean attribute.
- Capture-worker explorer suggested:
  - retry once for `home_entry_unverified`;
  - stop the session when pre-keyword home-entry fails after bounded reset;
  - split old tests that expected unknown not to retry.

## User Intent

The user's desired business rule is deliberately simple:

> 每个关键词开头，只要不是普通淘宝首页，就别管它是什么页面，关/回/开淘宝首页。不要在活动页、采购优选页、旧结果页、外站或奇怪页面的搜索框里搜。

They also explicitly said:

- Do not spend more time investigating why the first keyword seemed to start from purchase-selection page; leave it for a future run with better evidence.
- Do not modify `post_keyword_cleanup` / `Command+W` in this round.

