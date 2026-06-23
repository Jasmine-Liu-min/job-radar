# 招聘信息工作台规划

> 修订记录：v2（2026-06-18）。基于 GitHub 同类项目调研重写。主要变更：新增同类项目对比与差异化定位（第 0 章）、拍板部署形态为 GitHub Actions + 静态数据、明确去重键、新增信源健康度闭环、AI 改为分层触发、第一版砍掉聚合平台、多画像默认开启。

## 0. 同类项目调研与差异化定位

在动手前先调研了 GitHub，**这个方向已有成熟开源项目**，不必从零自研。

### 0.1 值得参考的项目

| 项目 | 重合度 | 可借鉴点 |
|---|---|---|
| [vesaias/JobNavigator](https://github.com/vesaias/JobNavigator) | 最高 | 自托管、11 个海外 ATS 适配器、AI 对画像打分、简历适配、Telegram 推送、Chrome 插件被动抓 LinkedIn。基本是本规划 Phase 1-3 的完整实现 |
| [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) | 高 | **纯 GitHub Actions 抓取→合并→commit 数据**，无需后端服务器；saved/applied/ignored 状态用 localStorage |
| [adgramigna/job-board-scraper](https://github.com/adgramigna/job-board-scraper) | 中 | Scrapy + Postgres 统一数据模型，按信源类型编排 spider |
| [viktor-shcherb/job-seek](https://github.com/viktor-shcherb/job-seek) | 中 | adapter registry 注册表模式、JS 壳页面 fallback 渲染、卡片 UI |
| [loks666/get_jobs](https://github.com/loks666/get_jobs) | 中（国内向） | 国内平台（Boss/前程无忧/猎聘/智联）抓取与反爬实战经验 |

### 0.2 差异化定位（本项目真正的价值）

- **海外 ATS（Greenhouse/Lever/Ashby/Workday 等）属于已解决问题**，优先复用 JobNavigator 等现成适配器，不重复造轮子。
- **没有现成方案、也最有价值的是国内官网（P0）+ 央国企/事业单位公告（P3）这两层。** 国内现有项目要么做自动投递，要么是教学爬虫合集，没人把"央国企/事业单位公告结构化 + 编制识别 + 报名截止跟踪"做成产品。
- 因此本项目重新定位为：**以国内官方信源与央国企公告为核心、复用海外 ATS 现成能力、加专业画像打分的个人招聘雷达**。

> 实施前先克隆 JobNavigator 跑一遍，确认其海外 ATS 适配器能否直接复用；若能，本项目即作为它的"国内 + 央国企扩展层"，可省掉约一个 Phase 的工作量。

## 1. 项目定位

本项目不是单纯的招聘网站爬虫，而是一个面向个人职业机会管理的"招聘信源雷达工作台"。

核心目标：

- 围绕个人关注公司、专业方向、城市偏好和组织类型，建立可维护的招聘信源库。
- 优先监听公司官网、官方 ATS 招聘系统、央国企/事业单位官方渠道。
- 使用聚合招聘平台、社区内推、邮件订阅作为补充信源（非第一版重点）。
- 自动抓取或订阅新增岗位，标准化入表，去重，打标签，评分，并推送高价值机会。
- 预留 AI 接入能力，用于岗位抽取、匹配解释、风险识别和简历适配。

一句话版本：

> 做一个以"官方信源优先、专业画像定制、AI 可增强"为原则的个人招聘雷达小组件。

## 2. 目标用户与使用场景

### 2.1 目标用户

第一阶段面向个人使用，尤其是：

- 关注特定公司机会的人。
- 关注 AI、数据、产品、增长、BI、数字化转型等专业方向的人。
- 同时关注互联网/科技公司和央国企、金融科技、数字化子公司的人。
- 不想每天手动刷多个招聘网站，但希望及时发现高匹配岗位的人。

### 2.2 核心场景

1. 用户维护一份关注公司清单。
2. 系统自动识别这些公司的招聘官网或 ATS 系统。
3. 系统定时抓取新增岗位。
4. 岗位进入统一表格，并按专业画像打分。
5. 高匹配岗位推送到飞书、企业微信、邮件或桌面组件。
6. 用户在小组件中标记：收藏、忽略、已投递、待跟进。

## 3. 信源分层策略

### 3.1 P0：公司官网招聘页

优先级最高，作为最终真相源。

典型来源：

- 字节跳动招聘：`https://jobs.bytedance.com/`
- 阿里巴巴招聘：`https://talent.alibaba.com/`
- 腾讯招聘：`https://careers.tencent.com/`
- 美团招聘：`https://zhaopin.meituan.com/`
- 国家电网招聘：`https://zhaopin.sgcc.com.cn/`
- 中国移动招聘：`https://job.10086.cn/`
- 中国石化招聘：`https://job.sinopec.com/`
- 工商银行招聘：`https://job.icbc.com.cn/`
- 建设银行招聘：`https://job.ccb.com/`

处理原则：

- 能调用公开接口就调用接口。
- 能从页面请求中找到 JSON 数据就解析 JSON。
- 官网职位与聚合平台职位重复时，以官网为准。

### 3.2 P1：官方 ATS 招聘系统

很多公司使用第三方招聘系统托管岗位，本质仍是官方岗位。**优先复用 JobNavigator 等现成适配器。**

海外常见 ATS：

- Greenhouse
- Lever
- Ashby
- Workday
- SmartRecruiters

国内常见 ATS：

- Moka
- 北森
- 大易
- 仟寻
- 自研招聘系统

处理原则：

- Greenhouse、Lever、Ashby 等优先使用公开 Job Board API。
- Workday、SmartRecruiters 等根据页面结构和公开接口单独适配。
- 国内 ATS 优先识别页面接口，无法接口化时再使用浏览器抓取。

### 3.3 P2：聚合招聘平台（第一版不做重度抓取）

用于补充覆盖，不作为最高可信信源。**第一版仅作只读/手动导入，不做登录态重度抓取**——这些平台反爬+登录会吃掉大部分维护精力，且与"官方信源优先"定位冲突。

典型来源：

- BOSS 直聘、猎聘、拉勾、智联招聘、前程无忧、国聘
- LinkedIn、Indeed、Glassdoor、Google Jobs

处理原则：

- 用于发现新增公司、新增岗位和市场动向。
- 与官网重复时保留官网链接，聚合链接作为备用。
- 反爬强、登录限制强的平台，第一版不做抓取，避免维护成本失控。

### 3.4 P3：公共招聘与央国企渠道（本项目差异化核心）

用于覆盖央国企、事业单位、政府雇员、科研院所、银行和地方国资平台。

典型来源：

- 国聘
- 中国公共招聘网/就业在线
- 国家公务员局
- 中国人事考试网
- 中央和国家机关所属事业单位公开招聘服务平台
- 各省人事考试网
- 地方人社局招聘公告
- 地方国资委招聘公告
- 高校人才网、科研院所官网

处理原则：

- 公告类信息通常不是标准岗位，需要 AI 或规则抽取。
- 应保留公告原文链接、报名时间、资格条件、报名方式。
- 对"编制、合同制、劳务派遣、第三方外包"等字段重点识别。

### 3.5 P4：社区、内推与半结构化来源

用于发现早期机会，但可信度较低。

典型来源：

- V2EX 酷工作、牛客内推、Hacker News Who is Hiring
- 公司公众号招聘推文、邮件订阅、飞书群/微信群手动导入

处理原则：

- 进入系统前先做结构化抽取。
- 标记信源可信度和岗位完整度。
- 对联系方式、公司主体、岗位链接进行校验。

## 4. 专业画像与定制规则

系统从第一天就支持**多画像并行**（数据模型已是多行 `profile_id` 设计，代码上零额外成本，无需等"确认"）。

示例画像：AI 数据产品方向

```json
{
  "profile_name": "AI数据产品方向",
  "target_roles": [
    "数据产品经理", "AI产品经理", "数据分析师",
    "增长分析", "BI", "埋点平台", "用户行为分析"
  ],
  "must_keywords": ["数据", "埋点", "指标体系", "SQL", "A/B", "AI", "大模型"],
  "nice_keywords": ["推荐", "增长", "用户行为", "数据治理", "数据平台", "Agent", "商业分析"],
  "negative_keywords": ["销售", "外包", "电话客服", "纯运营", "劳务派遣"],
  "target_org_types": ["互联网", "科技公司", "央企数字化", "银行科技", "国企数科公司"],
  "cities": ["深圳", "广州", "北京", "上海", "杭州", "远程"]
}
```

岗位评分建议：

```text
总分 = 来源可信度 + 专业匹配 + 公司优先级 + 城市匹配 + 发布时间新鲜度 - 风险扣分
```

风险扣分项：

- 劳务派遣 / 外包 / 薪资不明
- 长期重复发布
- 描述过空
- 聚合平台无官网对应职位
- 报名截止时间已过

### 4.1 评分分两层（控制 AI 成本）

为避免每个新岗位都全量调 AI 导致成本和延迟失控，评分分层：

1. **规则粗分（全量、零成本）**：用关键词命中、城市匹配、来源可信度、新鲜度等规则快速打粗分。
2. **AI 精排（仅过阈值的岗位）**：只有粗分达到 `min_score_to_push` 阈值的岗位才调 AI 做精排、生成匹配原因和风险识别。

这样既保证覆盖面，又把 AI 调用量压到最小。

## 5. 数据模型

### 5.1 sources 信源表

```text
source_id
company_name
org_type: internet / tech / soe / finance / public_institution / research / aggregator / community
source_type: official / ats / aggregator / public_notice / community / email
source_url
ats_vendor
fetch_method: api / rss / html / playwright / email / manual
priority
requires_login
keyword_scope
city_scope
poll_interval_minutes
last_success_at
last_error
consecutive_failures      # 连续失败次数，用于自动降级（见 9.健康度闭环）
status: active / unstable / blocked / deprecated
notes
```

### 5.2 jobs 岗位表

```text
job_id
dedup_key                 # 去重主键，见 5.4
source_id
company_name
title
department
location
org_type
job_type: full_time / campus / intern / contract / public_exam / unknown
salary
experience
education
publish_time
deadline
official_url
backup_url
jd_text
tags
match_score
source_confidence
risk_flags
status: new / pushed / viewed / saved / applied / ignored
created_at
updated_at
```

### 5.3 user_profiles 专业画像表

```text
profile_id
profile_name
target_roles
must_keywords
nice_keywords
negative_keywords
target_org_types
cities
min_score_to_push
notification_channels
```

### 5.4 去重策略（明确定义，避免翻车）

去重是同类项目最容易出问题的地方，必须先定义键：

- **强去重**：`official_url` 完全一致 → 视为同一岗位（同信源更新覆盖）。
- **主去重键 `dedup_key`**：`归一化(公司名) + 归一化(职位名) + 归一化(城市)`。
  - 归一化包括：去空格、统一全半角、去除"（社招）/急聘"等噪声后缀。
- **央国企公告"反复发布"**：同一 `dedup_key` 在窗口期内多次出现时，保留最早 `publish_time`，并对"长期重复发布"打风险标记（呼应第 4 章风险扣分项）。
- 官网与聚合重复时，official_url 取官网，聚合链接进 `backup_url`。

## 6. 小组件形态

第一版做成一个轻量工作台组件，而不是大而全的网站。

### 6.1 展示模块

核心 Tab：

- 今日新增 / 高匹配 / 官网来源 / 央国企 / 待查看 / 已收藏 / 已忽略

岗位卡片字段：

```text
职位名 / 公司 / 城市 / 来源类型 / 来源可信度 / 匹配分数 / 匹配原因
风险提示 / 发布时间·截止时间 / 官网链接
操作：收藏、忽略、标记已投递
```

### 6.2 小组件接口

前端组件示意：

```tsx
<JobRadarWidget
  profileId="ai-data-product"
  mode="compact"
  sourceScope="official-first"
  showReasons
/>
```

后端/数据接口示意（部署形态见第 8 章，第一版可为静态 JSON + 客户端读取）：

```text
GET   /api/job-radar/jobs?profileId=xxx
GET   /api/job-radar/sources
POST  /api/job-radar/sources
POST  /api/job-radar/sync
POST  /api/job-radar/score
POST  /api/job-radar/notify
PATCH /api/job-radar/jobs/:id/status
```

## 7. AI 接入预留

AI 不直接负责抓取，AI 负责标准化之后的理解与判断，且**仅对过阈值岗位调用**（见 4.1）。

建议 AI 能力：

- 从公告、网页、邮件中抽取岗位字段。
- 给岗位打标签、生成匹配原因。
- 识别风险（外包、派遣、报名截止、非正式岗位）。
- 根据用户简历或职业画像计算匹配度。
- 生成投递建议和简历修改建议。

AI 输入：

```json
{
  "profile": {},
  "job": {
    "title": "",
    "company_name": "",
    "jd_text": "",
    "source_type": "",
    "source_confidence": 0
  }
}
```

AI 输出：

```json
{
  "tags": [],
  "match_score": 0,
  "match_reasons": [],
  "risk_flags": [],
  "summary": "",
  "application_suggestion": ""
}
```

## 8. 技术路线

### 8.1 部署形态（已拍板：GitHub Actions + 静态数据）

对个人单用户场景，采用 [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) 的模式，**零服务器成本、零运维**：

- GitHub Actions 定时（cron）跑抓取 → 去重合并 → 把数据 commit 成 JSON/SQLite。
- 前端纯静态读取数据文件；状态（收藏/忽略/已投递）先用 localStorage，后续可升级。
- 仅当需要实时推送或多端同步时，再考虑引入常驻后端。

### 8.2 MVP 技术栈

- 前端：React / Next.js（静态导出）
- 抓取/处理脚本：Python（FastAPI 仅在需要后端时引入）
- 抓取：Playwright + Requests/HTTP Client
- 解析：BeautifulSoup / Cheerio + JSON API 适配器
- 存储：SQLite（随仓库 commit）/ 可选 PostgreSQL
- 表格同步：飞书多维表格 / CSV
- 推送：飞书机器人 / 企业微信机器人 / 邮件
- 调度：GitHub Actions cron

### 8.3 抓取适配器（注册表模式）

参考 job-seek 的 adapter registry：每类信源一个 adapter，统一注册、统一输出。

```text
greenhouse_adapter / lever_adapter / ashby_adapter / workday_adapter
custom_official_adapter        # 国内官网 JSON
public_notice_adapter          # 央国企公告（差异化核心）
aggregator_adapter             # 第一版不启用
rss_adapter / email_adapter
```

统一输出：

```json
{
  "company_name": "",
  "title": "",
  "location": "",
  "publish_time": "",
  "deadline": "",
  "official_url": "",
  "jd_text": "",
  "raw": {}
}
```

## 9. 信源健康度闭环（新增）

国内官网接口改版极其频繁，必须有探活机制，否则会出现"系统在跑但岗位早就抓空了"而不自知。

- 每次抓取更新 `last_success_at` / `last_error` / `consecutive_failures`。
- 连续失败达阈值（如 3 次）自动将 `status` 置为 `unstable`，继续失败置 `blocked`。
- 每日生成一份信源健康报告（各信源成功率、失败信源清单），随推送一并发送。
- 抓取量异常（某信源新增岗位长期为 0）也纳入告警，提示可能是接口失效而非真的没有岗位。

## 10. 里程碑

### Phase 0：信源库调研与样例

目标：

- 建立 30-50 个样例信源，覆盖互联网、科技公司、央国企、银行科技、公共招聘平台。
- 标注抓取方式和难度。
- 克隆 JobNavigator 验证海外 ATS 适配器可复用性。

产出：`config/sources.csv`、`source_research.md`

### Phase 1：最小可用抓取链路

目标：

- 支持 3 类信源：Greenhouse/Lever/Ashby（复用现成）、国内官网 JSON、央国企公告网页。
- 完成去重（按 5.4 定义）、入库、规则粗分。
- 接入信源健康度闭环（第 9 章）。

产出：本地岗位数据库（SQLite）、GitHub Actions 同步脚本、CSV/表格导出。

### Phase 2：小组件工作台

目标：

- 展示岗位列表、筛选、收藏、忽略、已投递状态。
- 展示匹配分数和来源可信度。

产出：`JobRadarWidget`、静态数据接口（jobs / sources）。

### Phase 3：推送与 AI 增强

目标：

- 高匹配岗位自动推送。
- AI 对过阈值岗位生成匹配原因、风险提示、投递建议。

产出：飞书/企业微信/邮件推送、AI 评分接口。

## 11. 第一版建议范围

第一版不追求全网覆盖，聚焦官方信源：

- 10 家互联网/科技公司官网。
- 10 家央国企/银行/数字化子公司官网。
- 3 个公共招聘平台（含央国企公告）。
- **0 个聚合平台**（第一版不做重度抓取，见 3.3）。
- 1 个社区/内推源。

先验证：

- 是否能稳定抓到新增岗位（健康度闭环可观测）。
- 去重是否可靠（按 5.4 的 dedup_key）。
- 专业画像评分是否有用。
- 推送是否真的减少人工搜索时间。

## 12. 待确认问题

进入实现前需确认：

1. 第一批关注公司名单。
2. 目标城市（画像方向已定为多画像并行，无需再确认）。
3. 是否优先接飞书多维表格。
4. 推送渠道选飞书、企业微信、邮件，还是只做本地工作台。
5. 央国企公告需保留哪些字段（报名截止、笔试/面试时间、编制类型等）。
6. 是否采用 GitHub Actions + 静态数据部署形态（第 8.1 章默认建议）。
