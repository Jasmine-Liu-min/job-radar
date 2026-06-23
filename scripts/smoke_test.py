#!/usr/bin/env python3
"""最小验证脚本（对应规划第 11 章"先验证"）。

目标：用最稳定的海外 ATS 信源，回答两个核心问题——
  1) 能不能稳定抓到新增岗位？
  2) 去重靠不靠谱？

它做三件事：
  A. 真实抓取 Greenhouse/Lever/Ashby，断言至少抓到岗位（验证抓取链路）。
  B. 用构造的"同岗不同名/跨源重复"样本断言去重命中（验证 dedup_key，离线、可复现）。
  C. 打印健康报告摘要（验证健康度闭环可观测）。

运行：python3 scripts/smoke_test.py
任意一步失败会以非零码退出，方便接进 CI / GitHub Actions。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_radar.dedup import dedup
from job_radar.models import Job
from job_radar.normalize import make_dedup_key
from job_radar.adapters.jsonld import parse_jobs
from job_radar import keyword_config, sync
from job_radar.adapters import list_adapters
from job_radar.quality_rules import LOW_QUALITY_TAGS, quality_tags

PASS, FAIL = "✅ PASS", "❌ FAIL"
failures = 0
# 自检写到临时目录，绝不覆盖正式的 data/（与真实同步隔离）
TMP_OUT = tempfile.mkdtemp(prefix="job_radar_smoke_")


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"{PASS if ok else FAIL}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        failures += 1


# ---------- B. 去重单元验证（离线、必过、可复现）----------
def test_dedup_offline() -> None:
    print("\n[B] 去重逻辑（离线构造样本）")

    def mk(company, title, loc, url, src="s1", pub=""):
        key = make_dedup_key(company, title, loc)
        return Job(job_id=f"{src}:{key}", dedup_key=key, source_id=src,
                   company_name=company, title=title, location=loc,
                   official_url=url, publish_time=pub)

    # 同岗不同名（噪声后缀 + 全角空格 + 城市后缀），应归一化为同一 key
    a = mk("字节跳动", "数据产品经理（社招）", "深圳市", "https://x.com/1", pub="2026-06-10")
    b = mk("字节跳动", "数据产品经理", "深圳", "https://x.com/2", pub="2026-06-01")
    check("同岗不同名归一化为同一 dedup_key", a.dedup_key == b.dedup_key,
          f"{a.dedup_key} == {b.dedup_key}")

    # 跨源重复 + 强去重：official_url 完全一致
    c = mk("Spotify", "Backend Engineer", "Remote", "https://x.com/1", src="s2")

    merged = dedup([a, b, c])
    # a/b 合并为 1（同 key），c 与 a 同 url 也合并 → 期望 1 条
    check("跨源/同名重复后只剩 1 条", len(merged) == 1, f"got {len(merged)}")
    if merged:
        m = merged[0]
        check("合并后保留更早 publish_time", m.publish_time == "2026-06-01", m.publish_time)
        check("重复出现次数被累计", m.seen_count == 3, f"seen_count={m.seen_count}")
        check("第二条链接进入 backup_url", bool(m.backup_url), m.backup_url)


# ---------- D. JSON-LD 解析器（离线、必过、可复现）----------
def test_jsonld_offline() -> None:
    print("\n[D] 通用 JobPosting JSON-LD 解析")
    sample = '''
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Data Scientist",
     "hiringOrganization":{"@type":"Organization","name":"Acme AI"},
     "datePosted":"2026-06-01","validThrough":"2026-09-01","employmentType":"FULL_TIME",
     "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
       "addressLocality":"Shanghai","addressCountry":"CN"}},
     "baseSalary":{"@type":"MonetaryAmount","currency":"CNY","value":{
       "@type":"QuantitativeValue","minValue":30000,"maxValue":50000,"unitText":"MONTH"}},
     "identifier":{"@type":"PropertyValue","name":"Acme","value":"DS-001"}}
    </script>
    <script type="application/ld+json">
    {"@graph":[{"@type":"JobPosting","title":"Remote Engineer",
      "hiringOrganization":"Acme AI","jobLocationType":"TELECOMMUTE",
      "applicantLocationRequirements":{"@type":"Country","name":"China"}}]}
    </script>'''
    jobs = parse_jobs(sample, "https://x.com/job")
    check("解析出 2 个 JobPosting（含 @graph）", len(jobs) == 2, f"got {len(jobs)}")
    if jobs:
        a = jobs[0]
        check("title/公司正确", a.title == "Data Scientist" and a.company_name == "Acme AI")
        check("validThrough→deadline", a.deadline == "2026-09-01", a.deadline)
        check("地点解析", "Shanghai" in a.location, a.location)
        check("薪资区间解析", a.raw.get("salary") == "30000-50000 CNY/MONTH", a.raw.get("salary"))
        check("identifier 解析", a.raw.get("identifier") == "DS-001", a.raw.get("identifier"))
    if len(jobs) > 1:
        check("远程岗位识别", jobs[1].location.startswith("远程"), jobs[1].location)


# ---------- E. 配置化与质量规则（离线、必过、可复现）----------
def test_config_and_quality_offline() -> None:
    print("\n[E] 配置化补抓 / adapter 自动发现 / 质量降噪")
    kws = keyword_config.iguopin_keywords()
    check("国聘补抓关键词含 2027 周期词", any(k in kws for k in ("2027", "27届")), str(kws[:8]))
    check("国聘补抓关键词含算法/产品/决策方向", all(k in kws for k in ("算法", "AI产品", "战略分析")),
          str(kws[:12]))
    adapters = set(list_adapters())
    check("adapter 自动发现包含国聘", "iguopin" in adapters, str(sorted(adapters)[:8]))
    check("adapter 自动发现包含央企公告", "gov_notice" in adapters, str(sorted(adapters)[:8]))

    missing_deadline = Job(job_id="x", dedup_key="x", source_id="test",
                           company_name="Acme AI", title="数据科学实习生",
                           location="上海", official_url="https://example.com/job")
    tags, _ = quality_tags(missing_deadline)
    check("缺截止只提示，不默认隐藏", "缺截止" in tags and not (set(tags) & LOW_QUALITY_TAGS), str(tags))

    low_signal = Job(job_id="y", dedup_key="y", source_id="test",
                     company_name="某人力资源管理有限公司", title="销售专员",
                     location="某县", official_url="")
    tags, _ = quality_tags(low_signal)
    check("明显低质岗位会进入默认隐藏标签", bool(set(tags) & LOW_QUALITY_TAGS), str(tags))


# ---------- A. 真实抓取验证（网络，允许个别源失败）----------
def test_live_fetch() -> None:
    print("\n[A] 真实抓取（海外 ATS，网络）")
    stable = {"greenhouse", "lever", "ashby"}
    report = sync.run(only_adapters=stable, verbose=True, out_dir=TMP_OUT)
    got = report["snapshot_after_dedup"]
    check("至少抓到 1 条岗位（抓取链路通）", got > 0, f"{got} 条")
    ok_sources = [s for s in report["sources"] if not s.get("not_run") and not s.get("last_error")]
    check("至少 1 个信源成功", len(ok_sources) >= 1, f"{len(ok_sources)} 个成功")


# ---------- C. 健康度可观测 ----------
def test_health_report() -> None:
    print("\n[C] 健康度闭环")
    path = os.path.join(TMP_OUT, "health_report.json")
    check("生成 health_report.json（临时目录，不覆盖正式 data/）", os.path.exists(path))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rep = json.load(f)
        print(f"     快照 {rep['jobs_raw']} → 去重 {rep['snapshot_after_dedup']} "
              f"→ 累积入库 {rep['store_total']}（新增 {rep['new_this_run']}），"
              f"异常信源 {len(rep['unhealthy'])} 个")


if __name__ == "__main__":
    print("=" * 56)
    print(" Job Radar 最小验证（稳定抓取 + 去重靠谱）")
    print("=" * 56)
    test_dedup_offline()
    test_jsonld_offline()
    test_config_and_quality_offline()
    try:
        test_live_fetch()
        test_health_report()
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL}  实时抓取阶段异常: {type(e).__name__}: {e}")
        failures += 1

    import shutil
    shutil.rmtree(TMP_OUT, ignore_errors=True)

    print("\n" + "=" * 56)
    if failures == 0:
        print(" 全部通过 🎉")
        sys.exit(0)
    print(f" {failures} 项失败")
    sys.exit(1)
