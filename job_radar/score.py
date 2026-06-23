"""规则粗分（对应规划 4.1 节第一层）。

全量、零成本、可解释。只有粗分 >= min_score_to_push 的岗位，
后续 Phase 3 才会调 AI 做精排和匹配原因（4.1 节第二层）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .models import Job
from .normalize import normalize_city
from .role_rules import employer_tier, has_target_role_signal, role_signal_score
_C27_KW = ("2027届", "2027 届", "27届", "27 届", "2027校园", "2027校招", "二零二七")
_ADVANCE_KW = ("提前批", "提前招", "预招聘", "预招", "开放日", "体验营", "训练营", "夏令营")
_AUTUMN_KW = ("秋招", "秋季招聘", "秋季校园招聘", "正式批")
_SPRING_KW = ("春招", "春季招聘", "补录", "补招")
_SUMMER_KW = ("暑期实习", "暑期实践", "实习生", "intern")
_CONVERT_KW = ("可转正", "转正机会", "转正实习", "留用", "return offer")


# 风险关键词 → 扣分（规划第 4 章风险扣分项）
RISK_KEYWORDS = {
    "劳务派遣": 40,
    "派遣": 30,
    "外包": 30,
    "第三方": 15,
    "电话客服": 25,
}


@dataclass
class ScoreResult:
    """单画像打分结果（纯数据，不改 Job）。"""
    score: int = 0
    tags: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)


def score_job(job: Job, profile: Dict) -> ScoreResult:
    """按单个画像给 job 打粗分，返回结果对象——**不修改 job**（便于对多画像取最优）。

    总分 = 来源可信度 + 专业匹配 + 城市匹配 - 风险扣分（规划第 4 章公式简化版）。
    """
    text = (job.title + " " + job.jd_text).lower()
    score = int(job.source_confidence * 0.2)  # 来源可信度（权重调低，避免聚合源虚高）
    tags: List[str] = []

    # 专业匹配（关键词命中**封顶**：防止 JD 堆词把无名小公司刷到第一）
    must = [k for k in profile.get("must_keywords", []) if k.lower() in text]
    nice = [k for k in profile.get("nice_keywords", []) if k.lower() in text]
    neg = [k for k in profile.get("negative_keywords", []) if k.lower() in text]
    score += min(len(must), 4) * 12 + min(len(nice), 3) * 5 - len(neg) * 20
    tags += must[:4] + nice[:3]

    # 目标岗位名直接命中（对口是硬指标）
    if any(r.lower() in job.title.lower() for r in profile.get("target_roles", [])):
        score += 25
        tags.append("role_match")

    role_score, role_tags = role_signal_score(job.title, job.jd_text)
    score += role_score
    tags += role_tags

    # 27届周期信号：提前批/秋招/春招/暑期实习是当前主线，适度加权但不压过岗位匹配。
    cycle_text = (job.title + " " + job.jd_text).lower()
    is_c27 = any(k.lower() in cycle_text for k in _C27_KW)
    if is_c27:
        score += 18
        tags.append("27届")
    has_advance = any(k.lower() in cycle_text for k in _ADVANCE_KW)
    if has_advance:
        score += 10
        tags.append("提前批")
    if not has_advance and any(k.lower() in cycle_text for k in _AUTUMN_KW):
        score += 8
        tags.append("秋招")
    if any(k.lower() in cycle_text for k in _SPRING_KW):
        score += 8
        tags.append("春招/补录")
    if any(k.lower() in cycle_text for k in _SUMMER_KW):
        score += 6
        tags.append("暑期实习")
    if any(k.lower() in cycle_text for k in _CONVERT_KW):
        score += 6
        tags.append("可转正")

    # 行业匹配：偏好行业加分、回避行业减分（如"金融一般"→降权）
    if job.industry and job.industry in profile.get("target_industries", []):
        score += 20
        tags.append("industry_match")
    if job.industry and job.industry in profile.get("negative_industries", []):
        score -= 20

    # 雇主层级：从**公司名**判央国企/外企/大厂/硬科技（不再用信源 org_type，
    # 否则人社部/高校聚合源里的民营小公司会被误判成"事业单位"而虚高）。用户最看重此维度。
    tier, boost = employer_tier(job.company_name, job.industry, job.source_id or "")
    if tier:
        score += boost
        tags.append(tier)

    # 城市匹配
    job_city = normalize_city(job.location)
    if job_city and any(normalize_city(c) == job_city for c in profile.get("cities", [])):
        score += 10
        tags.append("city_match")

    # 地点可达性：国外岗位（地点无中文 且 非远程）对国内求职者基本投不了 → 降权。
    # 中文地点（国内大厂/央国企/高校）与远程岗不受影响。offshore_penalty=0 可关闭。
    off = profile.get("offshore_penalty", 0)
    if off and job.location:
        loc = job.location.lower()
        has_cjk = any("一" <= c <= "鿿" for c in job.location)
        # 仅放过"明确全球远程/中国"的；"Remote - California"等外企区域远程要美国工签，照罚
        global_ok = any(k in loc for k in ("worldwide", "global", "anywhere", "中国", "china"))
        if not has_cjk and not global_ok:
            score -= off
            tags.append("offshore")

    # 岗位是否对口：标题含统计/数据/算法/CS 等"对口信号"即视为相关，
    # 否则命中任一"非对口词"(蓝领+跨专业，如 检测/审计/电气/销售内勤/机械/UI)就重罚隐藏。
    # 这样无需穷举：异常"检测"算法、"销售"数据分析等含对口信号的不会被误伤。
    title = job.title or ""
    low = title.lower()
    sid = job.source_id or ""
    # 公告/高校源标题是单位名而非岗位名，不按角色词判定（仍由行业/Tab 浏览）
    exempt = sid.startswith("edu-") or sid in ("gov-sasac", "gov-qyzp")
    if not exempt:
        off = profile.get("exclude_keywords", []) + profile.get("exclude_roles", [])
        if not has_target_role_signal(low) and any(k.lower() in low for k in off):
            score -= 100
            tags.append("非目标岗")

    # 县级 base 地降权（用户不考虑县/县级市岗位）。区(urban)不算。
    cp = profile.get("county_penalty", 0)
    if cp and "县" in (job.location or ""):
        score -= cp
        tags.append("县级")

    # 风险扣分
    risk: List[str] = []
    for kw, penalty in RISK_KEYWORDS.items():
        if kw in text:
            score -= penalty
            risk.append(kw)

    # 央国企公告"报名截止已过"等时间相关风险：依赖 today，交调用方判定，
    # 此处不计，保持纯函数可复现。

    return ScoreResult(score=max(0, score),
                       tags=list(dict.fromkeys(tags)),
                       risk_flags=risk)
