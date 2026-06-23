# File Layout

这个项目的目录原则：根目录只放入口，长期配置放 `config/`，运行产物放 `data/`，可执行维护脚本放 `scripts/`，业务代码放 `job_radar/`，说明和设计放 `docs/`。

## Root

| Path | Keep Here Because |
|---|---|
| `README.md` | 项目第一入口，给人读 |
| `AGENTS.md` | 给 AI/自动化协作者的工程约束 |
| `.gitignore` | 本地临时文件和审核导出规则 |
| `.github/` | GitHub Actions 自动同步和推送 |

根目录不要再放新的 CSV、JSON、临时 HTML、截图或审核导出文件。

## config/

长期可维护配置：

- `sources.csv`：正式抓取信源注册表
- `source_backlog.csv`：待攻信源和人工导入来源
- `profiles.json`：用户画像、偏好、评分配置
- `role_keywords.json`：关键词型信源的主动补抓词

新增稳定信源放这里。临时收集到的群消息、公众号 URL、牛客线索不要放这里，放 `data/inbox/`。

## data/

运行产物和可打开页面：

- `jobs.html`：主工作台
- `jobs.json`：当前岗位库
- `notify_preview.md`：新增推送预览
- `notify_state.json`：已推送状态，真实发送后生成
- `health_report.json` / `source_state.json`：信源健康和运行状态
- `import_preview*.html`：半自动导入审核台
- `inbox/`：牛客、公众号、就业群、腾讯文档的待审核输入

原则：`data/` 可以由脚本重建；不要在这里手写长期说明，除非是 `inbox/README.md` 这种目录说明。

## data/inbox/

放“线索”，不放“已确认岗位”：

- 牛客 URL / 标题发现池
- 公众号 URL 列表
- 就业群复制文本
- 腾讯文档导出的 CSV/TSV

导入前用 `scripts/import_feed.py --review-html` 生成审核台，人工确认后再入库。

## job_radar/

Python 业务核心：

- `adapters/`：各信源抓取器，只返回 `RawJob`
- `models.py`：数据模型
- `normalize.py` / `dedup.py`：归一化和去重
- `industry.py` / `role_rules.py` / `quality_rules.py`：分类、方向、质量规则
- `workbench_rules.py`：工作台展示口径
- `score.py`：规则打分编排
- `sync.py`：同步编排和健康报告

新增 adapter 时，在 `job_radar/adapters/` 新建非 `_` 开头的文件并 `@register`，不需要手改 `adapters/__init__.py`。

## scripts/

人和自动化调用的入口：

- `sync_plan.py`：统一刷新入口
- `export_html.py`：导出工作台
- `import_feed.py`：半结构化导入
- `nowcoder_discover.py`：牛客线索发现
- `notify_preview.py`：新增推送选择
- `send_notify.py`：飞书/企微发送
- `smoke_test.py`：最小自检

脚本应尽量保持可直接运行，并在 README 里暴露常用命令。

## docs/

说明、设计、交接和长期规划：

- `project-map.md`：给维护者/AI 的快速地图
- `file-layout.md`：本文件，说明东西应该放哪
- `roadmap.md`：规划和路线
- `design/`：视觉设计说明和变量

## When Unsure

- 稳定配置：`config/`
- 待审核线索：`data/inbox/`
- 生成结果：`data/`
- 运行入口：`scripts/`
- 可复用业务逻辑：`job_radar/`
- 解释和规划：`docs/`
