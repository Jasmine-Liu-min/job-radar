# AGENTS.md — 给 AI 协作者的工程约定

本文件面向在此仓库工作的 AI（Claude Code / 其他 agent）。人类读者见 [README.md](README.md)。

## 一句话定位

**应届生导向**的个人招聘雷达。用户是 27 届统计学，目标=数据/算法岗 + 央国企/外企/大厂/硬科技/新能源。
**差异化在：大厂自有/校招门户接口、在华外企、央国企公告、学生聚合(牛客/实习僧)、高校就业网**——
官方/直雇源优先，海外 ATS 仅留少量远程参考。完整设计见
[docs/roadmap.md](docs/roadmap.md)，改动前先读它；目录入口见
[docs/project-map.md](docs/project-map.md)。

## 目录速览

- `config/sources.csv`：信源清单。加已有 adapter 支持的源，只改这一行表。
- `config/source_backlog.csv`：27届重点待接信源，记录 blocked/manual_import/research 状态。
- `config/profiles.json`：画像、关键词、城市、行业、阈值。
- `job_radar/`：核心库。adapter 只抓取，归一化/去重/打分在各自模块。
- `scripts/export_html.py`：工作台 UI、Tab、筛选、截止、折叠、看板。
- `scripts/import_feed.py`：群消息/腾讯文档/公众号补录。
- `data/`：产物目录，不把手工状态写回这里；浏览器状态在 localStorage。
- `docs/`：规划、设计、项目地图。

## 硬约束（不要破坏）

1. **核心零外部依赖**（标准库 + `adapters/http.py`）。**唯一例外：Playwright** 是
   *可选* 依赖，仅 SPA/反爬源用（`feishu/uni_spa/sjtu/nowcoder/shixiseng`），且**未装时必须优雅失败**，
   不影响其它源。不要引入 requests/pandas/scrapy。
2. **adapter 只产出 `RawJob`**（models.py），不做归一化/去重/打分——那是后续阶段的职责。
3. **adapter 失败就抛异常，不要 try/except 吞掉。** 健康度闭环（sync.py）统一捕获、记账、
   自动降级。（adapter *内部* 翻页中途失败可 break 保留已抓到的，但整体失败要让它抛。）
4. **去重键逻辑集中在 `normalize.py::make_dedup_key`。** 改去重只动这里，并同步更新
   `scripts/smoke_test.py` 的离线断言。
5. **可复现性**：score.py 不依赖当前时间（截止是否已过等由前端按本地 today 算）；同样输入→同样输出。
6. **雇主层级判定用公司名，不用信源 org_type。** `score.py::_employer_tier` 据公司名判
   央国企/外企/大厂/硬科技——因为聚合源（人社部/高校）的 org_type 是平台属性，曾把民营小公司误判成"事业单位"刷高分。
7. **加性入库不要误删别的源。** 单源补抓时用「只插/刷新该源 key、不动其它」的加性合并；
   `sync.run()` 的全量合并会移除本次未出现的下线岗位。混用会误删。

## 改动后必须自检

```bash
python3 scripts/smoke_test.py     # 必须全绿
python3 -m job_radar.sync         # 跑通完整链路
```

## 常见任务怎么做

- **加信源**：先看 `config/sources.csv` 的 `adapter` 列有没有现成的；有就只加一行 CSV。
- **加信源类型**：在 `adapters/` 新建模块，实现 `def fetch(endpoint) -> List[RawJob]`，
  顶部 `@register("名字")` 即可——`adapters/__init__.py` 会**自动发现并导入**同目录的非下划线模块，无需手动维护 import 列表。
- **嗅探大厂接口**（最佳路子）：用 Playwright 抓包看页面调的列表 JSON 接口，直接打它。
  已这样接通 腾讯校招门户(join.qq.com)、网易(hr.163.com)、牛客(square-search)。优先于 DOM 解析。
- **校招/实习/社招 分类 + 工作台**：分类在 `scripts/export_html.py::_kind`（标题关键词+信源），
  雇主层级标签来自 `score.py` 的 tier。工作台（Tab/看板/截止/筛选）全在 export_html 的内嵌 JS，
  改 UI 改这里；用户状态存浏览器 localStorage，不落 jobs.json。
- **导入群推送/汇总**：`scripts/import_feed.py`（腾讯文档 CSV / 公众号 URL / 群消息 txt），
  纯规则抽取 → 加性并入。牛客/公众号/学校群请显式传 `--source-id` / `--source-name`，避免全混成一个来源。
- **接 AI 抽取**（Phase 3，仍未接）：从 `public_notice.py` 入手。只对粗分过阈值的岗位调 AI，控成本（规划 4.1）。
- **接推送**：新建 `job_radar/notify/`，读 `data/jobs.json` 中 match_score >= 画像 `min_score_to_push` 的岗位。

## 部署形态（已拍板）

GitHub Actions 定时跑 `python3 -m job_radar.sync`，把 `data/*.json` commit 回仓库，
前端纯静态读取。见 `.github/workflows/sync.yml`。不要默认引入常驻后端。
