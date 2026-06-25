# 27届招聘信息台 · Job Radar

这是一个面向 **2027届求职** 的个人招聘信息台，不是单纯爬虫集合。目标是把分散在官网、国聘、央国企公告、高校就业网、牛客、公众号和就业群里的机会，收拢成一个可筛选、可审核、可行动、可推送的工作台。

当前主攻方向：

- 产品、策略产品、AI 产品、数据产品
- 数据分析、商业分析、数据科学、数据挖掘、机器学习/算法
- 靠近决策层的经营分析、战略分析、行业研究、数字化转型、管培/项目管理
- 非互联网机会要单独看：央国企、金融、快消电商、咨询、湖南/长沙、制造数字化

当前 1.0 已可用：`data/jobs.html` 是主工作台，`data/notify_preview.md` 是新增推送预览，牛客/公众号/就业群走审核台，不直接污染主库。

## 快速开始

```bash
# 安装依赖（Playwright 用于牛客/实习僧/部分高校 SPA）
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

# 全量同步：抓所有配置中的信源，增量写入 data/
python3 -m job_radar.sync

# 导出单页工作台：双击 data/jobs.html 即可打开
python3 scripts/export_html.py

# 改了规则/画像后，只重新打分和导出，不重新抓取
python3 scripts/sync_plan.py rescore

# 日常更推荐的快刷
python3 scripts/sync_plan.py core     # 国聘 + 央企公告
python3 scripts/sync_plan.py role     # 产品/数据/算法/决策核心源

# 生成新增推送预览
python3 scripts/notify_preview.py

# 本地试跑推送链路，不真实发送、不写已推状态
python3 scripts/send_notify.py --dry-run
```

核心代码主要使用 Python 标准库；`requirements.txt` 目前只包含 Playwright。未安装 Playwright 时，对应信源会优雅失败，其它信源仍可同步。

## 项目结构

| 路径 | 人看的含义 | AI/维护入口 |
|---|---|---|
| `data/jobs.html` | 招聘信息台页面 | 最终查看入口，数据内嵌，双击可用 |
| `data/jobs.json` | 当前岗位库 | 自动生成，尽量不要手改 |
| `data/jobs_archive.json` | 下线/消失岗位轻量归档 | 自动生成，用于复盘，不进入信息台展示 |
| `data/notify_preview.md` | 新增推送预览 | 每次同步后看这里 |
| `data/notify_state.json` | 已推送记录 | 发送成功后自动写入，用于去重 |
| `data/inbox/` | 牛客/公众号/就业群线索池 | 半自动导入前的暂存区 |
| `config/sources.csv` | 正式抓取信源清单 | 加官网/平台信源优先改这里 |
| `config/source_backlog.csv` | 待攻信源池 | 金融、快消、咨询、湖南等缺口排期 |
| `config/profiles.json` | 用户画像和偏好 | 城市、行业、关键词、阈值 |
| `config/role_keywords.json` | 关键词补抓配置 | 国聘/大厂等关键词型源用 |
| `job_radar/adapters/` | 各网站抓取器 | 新平台类型在这里加 adapter |
| `job_radar/role_rules.py` | 岗位方向和雇主层级 | 加 AI产品/策略/算法/决策等规则 |
| `job_radar/quality_rules.py` | 低质/风险降噪 | 调销售、代招、生产制造等过滤 |
| `job_radar/workbench_rules.py` | 工作台展示分类 | 调 27届、提前批/秋招/春招、地区 |
| `scripts/export_html.py` | 工作台前端模板 | 改页面布局、Tab、筛选、信息台 |
| `scripts/import_feed.py` | 半结构化导入 | 牛客、公众号、就业群、CSV |
| `scripts/nowcoder_discover.py` | 牛客线索发现 | 生成待审核牛客池 |
| `scripts/notify_preview.py` | 新增推送摘要 | 控制推什么、不推什么、去重 |
| `scripts/send_notify.py` | 飞书/企微发送 | 真实 webhook 推送入口 |
| `scripts/sync_plan.py` | 统一刷新入口 | `fast/slow/full/rescore`，Actions 固定用 `fast` |
| `scripts/smoke_test.py` | 最小自检 | 修改后跑，临时目录，不覆盖数据 |
| `docs/project-map.md` | 给维护者/AI 的地图 | 快速理解边界和常见改法 |
| `docs/file-layout.md` | 文件夹整理规则 | 不确定东西放哪时先看这里 |
| `docs/interview-prep.md` | 面试准备稿 | 项目背景、技术选型、结果、困难、反思、问答 |

## 数据链路

```text
config/sources.csv
  -> adapter 抓 RawJob
  -> normalize 归一化
  -> dedup 跨源去重
  -> industry / role / quality 规则打标签
  -> score 排序
  -> data/jobs.json
  -> scripts/export_html.py
  -> data/jobs.html
```

半结构化来源另走一条审核链路：

```text
牛客 / 公众号 / 就业群 / 腾讯文档
  -> data/inbox/
  -> scripts/import_feed.py --review-html
  -> 人工勾选、补公司、补岗位、补截止、补官网链接
  -> scripts/import_feed.py --review-json
  -> data/jobs.json
```

推送链路：

```text
data/jobs.json
  -> scripts/notify_preview.py 只挑未推新增
  -> data/notify_preview.md
  -> scripts/send_notify.py
  -> 飞书/企业微信 webhook
  -> 发送成功后写 data/notify_state.json
```

## 工作台能力

`data/jobs.html` 的默认入口是「信息台」，不是普通岗位列表。它主要回答四个问题：

- 今天该看什么：新增重点、即将截止、待补截止、待审核线索、信源异常
- 27届主线怎么样：提前批、秋招、春招/补录、暑期实习、可转正
- 结构是否偏了：互联网/非互联网、央国企/金融/快消/咨询/湖南机会是否缺
- 下一步做什么：投递、补链接/截止、审核牛客、导入群消息、修信源

主要 Tab：

- `信息台`：首页指挥台和结构诊断
- `27届主线`：2027届机会集合
- `非互联网`：央国企、金融、快消、咨询、制造数字化等
- `转正候选`：实习可转正/留用/return offer
- `湖南/长沙`：本地机会单独看
- `产品/策略`：产品、AI产品、策略产品、决策支持
- `算法/数据`：算法、机器学习、数据科学、数据挖掘、数据分析
- `提前批/暑期(现在投)`：27届当前在招的一波（提前批 ∪ 暑期实习），按真实校招日历口径合并
- `即将截止`：短截止岗位
- `投递看板`：感兴趣、已投递、笔试、面试、Offer，本地备注保存在浏览器
- `📥导入`：粘贴公众号正文/链接，规则抽取；填了 Claude API Key 则用 AI 抽取。结果存浏览器本地（手动收集箱）。链接走「复制命令行」用 `import_feed.py` 正式入库
- `信源健康`：成功/失败、连续失败、异常原因、需关注源

排序口径：

- 默认按主攻方向优先，不让腾讯/字节/纯互联网算法刷屏。
- 产品/策略/AI产品/数据方向优先。
- 算法、机器学习、数据科学、数据挖掘会保留，但泛互联网纯算法不会霸榜。
- 非互联网的产品/数据/经营分析/数字化岗位会被单独抬出来。
- 机械、电气、材料、质检、采购、纯销售、校园大使、生产制造操作类会降噪。

## 日常使用

推荐日常顺序：

```bash
# 1. 快刷核心岗位
python3 scripts/sync_plan.py core
python3 scripts/sync_plan.py role

# 2. 刷牛客线索池，只进审核台
python3 scripts/nowcoder_discover.py --limit-per-keyword 6 --replace
python3 scripts/import_feed.py --preset nowcoder --text data/inbox/nowcoder_discovered.txt --review-html data/import_preview_nowcoder.html

# 3. 生成工作台和新增推送预览
python3 scripts/export_html.py
python3 scripts/notify_preview.py
```

打开：

```bash
open data/jobs.html
open data/notify_preview.md
open data/import_preview_nowcoder.html
```

如果只改了规则或关键词，不需要重新抓：

```bash
python3 scripts/sync_plan.py rescore
```

## 半自动导入

牛客、公众号、就业群和腾讯文档不要直接进主库，先审核。

```bash
# 牛客发现池
python3 scripts/nowcoder_discover.py --limit-per-keyword 6 --replace
python3 scripts/import_feed.py --preset nowcoder --text data/inbox/nowcoder_discovered.txt --review-html data/import_preview_nowcoder.html

# 牛客 URL 列表
python3 scripts/import_feed.py --preset nowcoder --url-file data/inbox/nowcoder_urls.txt --review-html data/import_preview_nowcoder.html

# 公众号 URL 列表
python3 scripts/import_feed.py --preset wechat --url-file data/inbox/wechat_urls.txt --review-html

# 就业群/腾讯文档导出，把 txt/md/csv/tsv 放进 data/inbox/
python3 scripts/import_feed.py --preset group --inbox data/inbox --review-html
```

审核流程：

1. 打开生成的 `data/import_preview*.html`。
2. 勾选真正有价值的 27届机会。
3. 补公司、岗位名、截止日期、官网/投递链接。
4. 从审核台导出 `job_import_review.json`。
5. 导入审核结果：

```bash
python3 scripts/import_feed.py --review-json job_import_review.json
```

牛客边界：

- 当前不做登录态、代理池、绕限流的重爬。
- 职位列表可抓，讨论/内推帖只做发现池。
- 过滤面经、求拷打、offer 比较、路线咨询等弱行动帖。
- 线索不等于岗位，必须审核后再入库。

## 新增推送

默认只推“未推过的新增”，不是每天重复推荐存量。

```bash
python3 scripts/notify_preview.py
```

预览会生成 `data/notify_preview.md`，包括：

- 新增优先看
- 新增非互联网产品/数据
- 新增 7 天内截止
- 新增待补截止
- 待审核牛客线索数量
- 信源需关注数量

进入推送至少要满足：

- `first_seen` 属于本次新增范围
- 未出现在 `data/notify_state.json`
- 方向和匹配分过阈值：`--min-focus`、`--min-match`
- 不是明显弱相关或低质岗位

真实发送：

```bash
# 本地 dry-run，不发送、不写状态
python3 scripts/send_notify.py --dry-run

# 配好环境变量后真实发送
FEISHU_WEBHOOK_URL="https://..." python3 scripts/send_notify.py
WECHAT_WEBHOOK_URL="https://..." python3 scripts/send_notify.py
```

支持的环境变量 / GitHub Secrets：

- `FEISHU_WEBHOOK_URL`
- `WECHAT_WEBHOOK_URL`
- `WECOM_WEBHOOK_URL`

发送成功后，`scripts/send_notify.py` 会写 `data/notify_state.json`。下次推送会自动过滤这些岗位。只想生成预览但不写状态，就不要加 `--mark-pushed`，也不要真实发送。

复盘存量时才用：

```bash
python3 scripts/notify_preview.py --mode all
python3 scripts/notify_preview.py --include-existing-due
```

## 定时自动推送

### GitHub Actions（推荐，无需开机）

托管到 GitHub 后，有三条 workflow：

| Workflow | 触发方式 | 做什么 | 大概耗时 |
|---|---|---|---|
| `job-radar-sync` | 每天 07:00 定时；也可手动 Run workflow | 快扫稳定信源、增量合并、生成预览、发送新增推送、提交 `data/` | 通常较短 |
| `job-radar-slow` | 每周三/周日 09:47 定时；也可手动 Run workflow | 补扫牛客、实习僧、SPA 高校、飞书招聘等慢源 | 较慢 |
| `job-radar-pages` | `job-radar-sync` 成功后自动触发；push 页面/README/展示逻辑后也会触发；也可手动 | 只部署 GitHub Pages，不抓取、不推送 | 通常几十秒 |

所以平时改样式、README、信息台展示，不会再跑完整抓取；真正的招聘同步只在定时或你手动点 `job-radar-sync` 时运行。

GitHub Actions 定时逻辑保持和 `TechDailyPush` 一样简单：

- 每天 `07:00`：固定跑 `fast` 快扫。
- `workflow_dispatch`：手动触发时也固定跑 `fast`。
- `fast` 只跑稳定 API/HTML 源，如国聘、国家平台、央企公告、大厂/外企官网，不装浏览器。
- 每周三/周日 `09:47`：`job-radar-slow` 固定跑 `slow`，补牛客、实习僧、SPA 高校、飞书招聘等慢源。

### 日常怎么操作

多数时候不用手动跑，等自动任务即可：

1. 每天看飞书推送：只看新增机会和即将截止重点项。
2. 打开在线信息台：

```text
https://jasmine-liu-min.github.io/job-radar/
```

3. 在信息台里看 `27届主线`、`产品/策略`、`算法/数据`、`非互联网`、`即将截止`。
4. 对值得投的岗位标记到投递看板，后续用 `感兴趣 -> 已投递 -> 笔试 -> 面试 -> Offer` 跟踪。

需要手动刷新时：

1. 打开 GitHub 仓库 `Actions`。
2. 日常快刷选 `job-radar-sync`；怀疑牛客/实习僧漏了选 `job-radar-slow`。
3. 点击 `Run workflow`。
4. 不需要选参数，直接运行即可。

跑完怎么看：

- `job-radar-sync` 绿色：抓取、预览、推送、提交数据完成。
- 随后 `job-radar-pages` 会自动跑一次：页面部署完成。
- 飞书没有消息不一定是失败，可能只是没有未推过的新增。
- Pages 刚部署完可能有 1-3 分钟缓存，手机打不开或没更新时先刷新。

不把慢源塞进主定时。慢源容易被限流，也会浪费 Actions 时间；平时 `fast` 兜住主源，`slow` 每周补两次，也可以手动补。

常见情况：

| 现象 | 含义 | 处理 |
|---|---|---|
| 飞书没收到 | 没有新增，或 webhook secret 没配/名字不对 | 先看 `Send new-only notify` 日志，再检查 `FEISHU_WEBHOOK_URL` |
| Pages 没更新 | 轻量部署还没跑完或缓存未刷新 | 看 `job-radar-pages` 是否绿色，等 1-3 分钟刷新 |
| `send-pack` 提示 `fetch first` | 远端有 Actions 生成的新提交 | 先 `git fetch`，再 `git rebase FETCH_HEAD`，最后重新 send-pack |
| `job-radar-slow` 很慢 | 正在装 Playwright 或慢源响应慢 | 正常等待；主链路 `job-radar-sync` 不受影响 |
| 某个源失败 | 单源失败不会阻断其它源，会进信源健康报告 | 看信息台 `信源健康`，连续失败再处理 |

配置网页托管：

1. 打开 GitHub 仓库 `Settings -> Pages`。
2. `Source` 选择 `GitHub Actions`。
3. workflow 跑完后，信息台会发布到：

```text
https://jasmine-liu-min.github.io/job-radar/
```

配置推送：

1. 在飞书或企业微信群里添加自定义机器人，复制 webhook URL。
2. 打开 GitHub 仓库 `Settings -> Secrets and variables -> Actions`。
3. 点击 `New repository secret`，填下面任意一个 secret：

| Secret | 说明 |
|---|---|
| `FEISHU_WEBHOOK_URL` | 飞书机器人 webhook |
| `WECHAT_WEBHOOK_URL` | 企业微信机器人 webhook |
| `WECOM_WEBHOOK_URL` | 企业微信机器人 webhook，备用别名 |

4. 去 `Actions -> job-radar-sync -> Run workflow` 手动触发一次快扫测试；需要时再去 `job-radar-slow -> Run workflow` 测慢源。

成功后每天北京时间 **07:00** 左右自动快扫，周三/周日北京时间 **09:47** 左右自动慢源补扫。GitHub Actions 的定时触发可能有几分钟延迟，这是正常现象；手动触发是即时的。

完整同步 workflow 会执行：

```text
sync -> export_html -> notify_preview -> send_notify -> commit data/
```

完整同步成功后会自动触发 `job-radar-pages`，把最新 `data/jobs.html` 发布到 GitHub Pages。

有 webhook secret 时会推送“未推过的新增”；没有 secret 时只生成 `data/notify_preview.md`，不会报错。发送成功后会更新 `data/notify_state.json`，下一次自动过滤已推岗位。飞书/企微推送里会附带在线信息台链接，不需要本地打开 `data/jobs.html`。

修改推送时间：编辑 `.github/workflows/sync.yml` 里的 `cron` 和 `timezone`。

### 历史数据说明

`data/jobs.json` 是当前岗位库：同步时会增量合并新岗位、刷新已有岗位、处理下线岗位，并保留 `first_seen` 等时间字段。`data/jobs_archive.json` 会保存下线/消失岗位的轻量归档，用于之后复盘，不进入信息台展示。`data/notify_state.json` 记录已经推送过的岗位，保证飞书/企微只推新增。

如果要做更完整的长期历史快照，下一步可以再加 `data/archive/YYYY-MM-DD.json` 或每周汇总表；当前 1.0 先保证信息台在架数据、新增推送、下线轻量归档稳定。

## 信源现状

已接入且相对稳定：

- 大厂官网：字节、腾讯社招、腾讯校招门户、京东、网易、蔚来等
- 央国企/国家平台：国聘、央企公告、国家大学生就业平台、人社部公共招聘
- 高校就业网：中山、中南、湖大、华南师范、西电、复旦、南大、上交、浙大等
- 实习平台：实习僧、牛客职位列表
- ATS/外企：Workday、Greenhouse、Ashby、Lever、北森
- 半结构化：牛客讨论/内推、公众号、就业群、腾讯文档导入

仍需持续补强：

- 金融、快消、电商、咨询的 27届正式来源
- 湖南/长沙本地产品、数据、数字化、经营分析岗位
- 公众号历史文章和就业群闭群消息，只能半自动导入
- 牛客深翻页/详情页受限流影响，默认不做高风险抓取

## 加信源

优先复用已有 adapter：

- `iguopin`：国聘/央国企职位
- `gov_notice` / `public_notice`：公告类
- `uni_career` / `uni_bysjy` / `uni_spa`：高校就业网
- `workday` / `greenhouse` / `lever` / `ashby` / `beisen`：ATS
- `bytedance` / `tencent` / `tencent_campus` / `jd` / `netease`：国内官网 API

步骤：

1. 在 `config/sources.csv` 加一行。
2. 如果已有 adapter 能用，只填 `adapter` 和 `endpoint`。
3. 如果需要新 adapter，在 `job_radar/adapters/` 新建非 `_` 开头的文件，并用 `@register("adapter_name")` 注册。
4. 不需要手动改 `job_radar/adapters/__init__.py`，它会自动发现 adapter。
5. 跑自检：

```bash
python3 scripts/smoke_test.py
python3 scripts/export_html.py
```

## 改规则

加岗位方向，例如“安全风控”：

1. 改 `config/profiles.json`：用户画像、关键词、城市/行业偏好。
2. 改 `job_radar/role_rules.py`：方向词、标签、加分。
3. 需要独立 Tab 时改 `scripts/export_html.py`。
4. 关键词型信源要主动补抓时改 `config/role_keywords.json`。
5. 跑：

```bash
python3 scripts/sync_plan.py rescore
python3 scripts/smoke_test.py
```

调降噪：

1. 改 `job_radar/quality_rules.py`。
2. 改完跑 `python3 scripts/sync_plan.py rescore`。
3. 确认 `data/jobs.html` 主视图没有被弱相关岗位污染。

调 27届/阶段/地区：

1. 改 `job_radar/workbench_rules.py`。
2. 跑 `python3 scripts/export_html.py`。

## 自动化部署

GitHub Actions：

- `.github/workflows/sync.yml`：完整同步，定时或手动触发。
- `.github/workflows/slow.yml`：慢源补扫，定时或手动触发。
- `.github/workflows/pages.yml`：轻量 Pages 部署，完整同步成功后或 push 展示层变更时触发。

同步流程：

1. 定时或手动触发。
2. 不安装 Playwright，保持主链路轻量。
3. 运行 `python3 scripts/sync_plan.py fast`。
4. 导出 `data/jobs.html`。
5. 生成 `data/notify_preview.md`。
6. 运行 `scripts/send_notify.py`，有 webhook secret 时发送新增摘要。
7. commit `data/`，包括岗位库、工作台、健康报告、推送预览、已推送状态。
8. 完整同步成功后触发 `job-radar-pages`，部署在线信息台。

没有 webhook secret 时，发送步骤会安全跳过，不影响同步。

## 验证

修改后建议至少跑：

```bash
python3 -m py_compile scripts/*.py job_radar/*.py job_radar/adapters/*.py
python3 scripts/export_html.py
python3 scripts/notify_preview.py
python3 scripts/send_notify.py --dry-run
python3 scripts/smoke_test.py
```

`scripts/smoke_test.py` 会写临时目录，不覆盖正式 `data/`。实时抓取部分只要求至少一个稳定 ATS 成功，避免单个外部源波动导致误判。

## 诚实现状

已完成：

- 信息台 1.0：正式岗位库、线索池、审核台、投递看板、信源健康。
- 27届主线：提前批、秋招、春招/补录、暑期实习、可转正。
- 主攻排序：产品/策略/AI产品/数据优先，算法保留但不让泛互联网纯算法霸榜。
- 半自动导入：牛客、公众号、就业群先审核再入库。
- 新增推送：只推未推新增，发送成功后记录状态，避免重复打扰。

还没完美：

- 大量岗位缺截止，需要继续补官网公告、公众号原文或截图。
- 金融、快消、电商、咨询、湖南/长沙还要继续加信源和人工导入。
- 牛客、公众号历史、就业群闭群内容无法完全自动化。
- 投递状态和备注还在浏览器 localStorage，换设备不会同步。
- AI 摘要未接入；当前全部是规则化、可解释、零成本。

## 参考文档

- [docs/project-map.md](docs/project-map.md)：给维护者和 AI 的项目地图
- [docs/roadmap.md](docs/roadmap.md)：早期规划和扩展路线
- [AGENTS.md](AGENTS.md)：开发约束和协作规则
