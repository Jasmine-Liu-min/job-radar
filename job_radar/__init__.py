"""招聘信息工作台（Job Radar）核心包。

模块职责一览（人和 AI 都可据此快速定位）：

- models.py      统一数据模型：RawJob（adapter 输出）/ Job（归一化+去重后）
- normalize.py   文本归一化 + dedup_key 生成
- dedup.py       去重逻辑（强去重 official_url + 主键 dedup_key + 重复发布标记）
- score.py       规则粗分（全量、零成本；AI 精排留给后续 Phase 3）
- sync.py        主流程：读 config/sources.csv → 调 adapter → 归一化 → 去重 → 打分 → 写 data/
- adapters/      每类信源一个 adapter，通过 registry 统一注册与分发

设计原则：纯标准库、无外部依赖，可直接 `python3 -m job_radar.sync` 运行。
"""
