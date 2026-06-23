"""统一数据模型。

对应规划文档第 5 章。adapter 只负责产出 RawJob，归一化/去重/打分阶段
把 RawJob 升级成 Job（带 dedup_key、match_score、risk_flags 等）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RawJob:
    """adapter 的统一输出（规划 8.3 节）。字段尽量浅，原始数据放 raw。"""
    company_name: str
    title: str
    location: str = ""
    publish_time: str = ""      # ISO8601 字符串，未知留空
    deadline: str = ""          # 央国企公告的报名截止时间
    official_url: str = ""
    jd_text: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Job:
    """归一化 + 去重 + 打分后的岗位（规划 5.2 节 jobs 表）。

    字段对齐 schema.org JobPosting / Google for Jobs：
      title→title  company_name→hiringOrganization  location→jobLocation
      publish_time→datePosted  deadline→validThrough  salary→baseSalary
      employment_type→employmentType  identifier→identifier  official_url→url
    """
    job_id: str
    dedup_key: str
    source_id: str
    company_name: str
    title: str
    location: str = ""
    org_type: str = ""
    industry: str = ""          # 行业分类（见 industry.py），同时作为"行业:X"标签
    job_type: str = "unknown"   # full_time/campus/intern/contract/public_exam/unknown
    publish_time: str = ""
    deadline: str = ""
    official_url: str = ""
    backup_url: str = ""
    salary: str = ""            # 薪资（规划 5.2）= schema.org baseSalary
    employment_type: str = ""   # schema.org employmentType（FULL_TIME/INTERN…）
    identifier: str = ""        # schema.org identifier（雇主侧职位编号，去重更准）
    jd_text: str = ""
    tags: List[str] = field(default_factory=list)
    match_score: int = 0
    source_confidence: int = 0
    risk_flags: List[str] = field(default_factory=list)
    status: str = "new"         # new/pushed/viewed/saved/applied/ignored（用户状态，跨同步保留）
    seen_count: int = 1         # 同一 dedup_key 出现次数，用于"重复发布"判断
    first_seen: str = ""        # 首次入库时间（增量累积：判断"新增"）
    last_seen: str = ""         # 最近一次仍在信源出现的时间
    gone: bool = False          # 信源列表里已不再出现（已下线，保留不删）
    extra: Dict[str, Any] = field(default_factory=dict)  # 承载 adapter 原始附加字段(单位性质/学历/省份/来源等)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 信源类型 → 来源可信度基础分（规划第 4 章评分项之一）
SOURCE_CONFIDENCE = {
    "official": 100,
    "ats": 90,
    "public_notice": 70,
    "aggregator": 50,
    "community": 30,
    "email": 40,
}
