# Project Map

这个项目是 27届个人招聘信息台，不是通用爬虫框架。核心目标是让用户优先看到产品、策略产品、AI产品、数据分析、数据科学、数据挖掘、机器学习/算法，以及靠近决策层的经营分析/战略/数字化机会；同时避免被互联网大厂和纯算法岗位淹没。

## Current Product

- 主入口：`data/jobs.html`
- 新增推送预览：`data/notify_preview.md`
- 半结构化审核台：`data/import_preview*.html`
- 当前数据：`data/jobs.json`
- 信源健康：`data/health_report.json` + `data/source_state.json`
- 已推送状态：`data/notify_state.json`

## Where Things Live

| Path | Purpose | Edit When |
|---|---|---|
| `config/sources.csv` | 正式自动信源注册表 | Add/remove automatic sources |
| `config/source_backlog.csv` | 27届重点待攻信源 | Track financial/FMCG/consulting/Hunan/manual sources |
| `config/profiles.json` | User profile and preferences | Tune cities, industries, keywords, thresholds |
| `config/role_keywords.json` | Keyword expansion for source adapters | Change proactive search terms |
| `job_radar/models.py` | `RawJob` and normalized `Job` schema | Data shape changes |
| `job_radar/adapters/` | Fetchers. Each adapter returns `RawJob` only | Add a website/platform type |
| `job_radar/adapters/__init__.py` | Adapter auto-discovery | Usually do not edit |
| `job_radar/normalize.py` | Text normalization and `dedup_key` | Dedup key behavior changes |
| `job_radar/dedup.py` | Cross-source merge rules | Duplicate merge behavior changes |
| `job_radar/industry.py` | Industry classification | Industry labels are wrong |
| `job_radar/role_rules.py` | Role tags and employer tiers | Product/data/algorithm/decision rules change |
| `job_radar/quality_rules.py` | Low-quality/risk tags | Sales/agency/manufacturing/noise filtering changes |
| `job_radar/workbench_rules.py` | Workbench display taxonomy | 2027 cycle/stage/region/category changes |
| `job_radar/score.py` | Deterministic scoring orchestration | Scoring flow changes |
| `job_radar/sync.py` | Sync orchestration and health reports | Pipeline/state behavior changes |
| `scripts/export_html.py` | Static workbench UI | Tabs, station homepage, card layout, filters change |
| `scripts/import_feed.py` | Manual feed/table/article import | 牛客/公众号/群消息 import improves |
| `scripts/nowcoder_discover.py` | 牛客 discussion/referral discovery | 牛客线索池 strategy changes |
| `scripts/notify_preview.py` | New-only notification selection | Push sections, thresholds, dedup change |
| `scripts/send_notify.py` | Webhook sender | Feishu/WeCom sending behavior changes |
| `scripts/sync_plan.py` | Unified run plans | core/role/full/rescore behavior changes |
| `scripts/smoke_test.py` | Minimal verification | Regression coverage changes |
| `data/` | Generated artifacts | Inspect outputs; avoid hand edits |
| `docs/roadmap.md` | Product/technical plan | Strategy changes |

## Runbook

```bash
# Daily-ish refresh
python3 scripts/sync_plan.py core
python3 scripts/sync_plan.py role
python3 scripts/export_html.py
python3 scripts/notify_preview.py

# Semi-structured leads
python3 scripts/nowcoder_discover.py --limit-per-keyword 6 --replace
python3 scripts/import_feed.py --preset nowcoder --text data/inbox/nowcoder_discovered.txt --review-html data/import_preview_nowcoder.html

# Verification
python3 -m py_compile scripts/*.py job_radar/*.py job_radar/adapters/*.py
python3 scripts/send_notify.py --dry-run
python3 scripts/smoke_test.py
```

`scripts/smoke_test.py` writes to a temp directory, so it will not overwrite `data/`.

## Boundaries

- The product is an information station. Do not optimize for “more crawled pages” if it makes action quality worse.
- Official sources and verified import beat noisy scraping.
- 牛客/公众号/就业群 are lead sources, not truth sources. They should enter inbox/review first.
- Keep the core mostly dependency-free. Playwright is optional and source-specific.
- Adapters return `RawJob` only. Do not score, dedup, or classify inside adapters.
- Do not silently swallow whole-source failures. Let `sync.py` record health.
- `score.py` should stay deterministic and should not depend on the current date.
- Full sync can remove disappeared jobs; partial/manual imports should preserve unrelated sources.
- Browser-side application status and notes live in localStorage, not `data/jobs.json`.
- Push notifications should default to **new-only and unpushed-only**. Do not send daily stock repeats.

## Common Changes

### Add an automatic source

1. Check existing adapters in `job_radar/adapters/`.
2. Add one row to `config/sources.csv`.
3. If a new adapter is needed, create a non-underscore file in `job_radar/adapters/` and register it with `@register("name")`.
4. Do not edit `job_radar/adapters/__init__.py` unless auto-discovery itself breaks.
5. Run:

```bash
python3 scripts/smoke_test.py
python3 scripts/export_html.py
```

### Add a semi-structured source

1. Put raw txt/md/csv/tsv or URL lists under `data/inbox/`.
2. Use `scripts/import_feed.py --review-html`.
3. Open the review HTML, verify company/title/deadline/link.
4. Import reviewed JSON with `scripts/import_feed.py --review-json ...`.

### Tune ranking

1. Profile-specific preferences: `config/profiles.json`.
2. Role tags and employer tiers: `job_radar/role_rules.py`.
3. Quality/noise rules: `job_radar/quality_rules.py`.
4. Workbench taxonomy: `job_radar/workbench_rules.py`.
5. Re-run:

```bash
python3 scripts/sync_plan.py rescore
python3 scripts/export_html.py
python3 scripts/notify_preview.py
```

### Improve workbench UX

1. Edit `scripts/export_html.py`.
2. Re-run `python3 scripts/export_html.py`.
3. Open `data/jobs.html`.
4. Check desktop and narrow viewport if layout changed.

### Change notification behavior

1. Edit `scripts/notify_preview.py` for selection/sections/thresholds.
2. Edit `scripts/send_notify.py` only for transport behavior.
3. Dry-run:

```bash
python3 scripts/send_notify.py --dry-run --state /private/tmp/jobradar_notify_state_test.json
```

4. Real sending should mark state only after webhook success.
