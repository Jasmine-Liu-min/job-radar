"""去重逻辑（对应规划 5.4 节）。

规则优先级：
1. 强去重：official_url 完全一致 → 同一岗位。
2. 主去重键 dedup_key（公司+职位+城市）。
3. 同一 dedup_key 多次出现 → 保留最早 publish_time，并标记"重复发布"风险。
"""
from __future__ import annotations

from typing import List

from .models import Job

# 同一岗位被重复发布超过该次数，打风险标记（呼应规划第 4 章风险扣分项）
REPEAT_POST_THRESHOLD = 3


def _earlier(a: str, b: str) -> str:
    """返回更早的 ISO 时间字符串；空串视为"未知/最晚"。"""
    if not a:
        return b
    if not b:
        return a
    return min(a, b)


def dedup(jobs: List[Job]) -> List[Job]:
    """对归一化后的岗位列表去重，返回去重后的列表。"""
    by_url: dict[str, Job] = {}
    by_key: dict[str, Job] = {}

    for job in jobs:
        # 1) 强去重：official_url 命中即合并
        if job.official_url and job.official_url in by_url:
            _merge_into(by_url[job.official_url], job)
            continue

        # 2) 主键去重
        if job.dedup_key in by_key:
            _merge_into(by_key[job.dedup_key], job)
            continue

        # 新岗位
        by_key[job.dedup_key] = job
        if job.official_url:
            by_url[job.official_url] = job

    result = list(by_key.values())

    # 3) 重复发布标记
    for job in result:
        if job.seen_count >= REPEAT_POST_THRESHOLD and "repeat_posting" not in job.risk_flags:
            job.risk_flags.append("repeat_posting")

    return result


def _merge_into(keep: Job, dup: Job) -> None:
    """把 dup 合并进已保留的 keep：累计出现次数、保留更早发布时间、补全字段。"""
    keep.seen_count += dup.seen_count
    keep.publish_time = _earlier(keep.publish_time, dup.publish_time)
    # 来自不同信源的重复：把另一条链接存为备用（官网优先，已在 keep）
    if dup.official_url and dup.official_url != keep.official_url and not keep.backup_url:
        keep.backup_url = dup.official_url
    # 补全缺失字段
    if not keep.deadline:
        keep.deadline = dup.deadline
    if not keep.jd_text:
        keep.jd_text = dup.jd_text
