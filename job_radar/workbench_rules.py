"""工作台展示分类规则。

这些规则只影响 data/jobs.html 的视图、Tab 和筛选，不影响抓取与入库。
"""
from __future__ import annotations

HIDDEN_INDUSTRIES = {"房地产/建筑/工程", "化工"}

INTERN_KW = ("实习", "intern", "見習", "见习")
CAMPUS_KW = ("校招", "校园招聘", "应届", "管培", "培训生", "储备干部", "储备生",
             "届毕业", "届校", "2025届", "2026届", "2027届", "校招生", "campus",
             "graduate", "新锐", "潜力生", "毕业生")
SOCIAL_KW = ("社招", "社会招聘", "资深", "高级专家", "首席", "总监", "年经验",
             "年以上", "年工作经验", "experienced", "senior", "principal", "staff ")
C27_KW = ("2027届", "2027 届", "27届", "27 届", "二零二七", "2027校园", "2027校招",
          "2027 campus", "2027 graduate")
ADVANCE_KW = ("提前批", "提前批次", "提前批招聘", "提前批专项", "提前批校园", "校招提前",
              "提前招", "提前面试", "预招聘", "预招", "预录用", "抢先批", "抢鲜批", "内推批",
              "A批", "早鸟", "开放日", "体验营", "训练营", "夏令营", "飞星计划",
              "优才计划", "菁英计划", "启航计划", "春雷计划", "鲲鹏计划", "锋芒计划")
AUTUMN_KW = ("秋招", "秋季招聘", "秋季校园招聘", "正式批", "校园招聘正式启动")
SPRING_KW = ("春招", "春季招聘", "补录", "补招", "春季校园招聘")
SUMMER_KW = ("暑期实习", "暑期实践", "summer intern", "summer internship", "日常实习",
             "实习生", "intern", "pre留学生实习", "pre 留学生实习")
EVENT_KW = ("宣讲会", "招聘会", "双选会", "开放日", "校园大使", "招生宣讲", "专场招聘",
            "技术沙龙", "空中宣讲", "入校宣讲")
CONVERT_KW = ("可转正", "转正机会", "转正实习", "留用", "return offer")

REGION_RULES = [
    ("上海", ["上海"]),
    ("广东", ["广东", "广州", "深圳", "珠海", "东莞", "佛山", "中山", "江门", "台山", "梅州", "汕头", "惠州"]),
    ("湖南", ["湖南", "长沙", "株洲", "湘潭"]),
    ("江苏", ["江苏", "南京", "苏州", "无锡", "江阴", "常州", "高淳", "洪泽", "徐州", "南通"]),
    ("浙江", ["浙江", "杭州", "宁波", "温州", "海宁", "嘉兴"]),
    ("北京", ["北京"]),
    ("远程/海外", ["remote", "海外", "美国", "英国", "新加坡", "香港", "global", "united", "canada", "germany"]),
]


def industry_display(ind: str) -> str:
    return "其他" if (not ind or ind in HIDDEN_INDUSTRIES) else ind


def text_blob(*parts: str) -> str:
    return " ".join(p or "" for p in parts)


def kind(sid: str, title: str) -> str:
    t = title or ""
    tl = t.lower()
    if any(k in t or k in tl for k in INTERN_KW):
        return "实习"
    if any(k in t or k in tl for k in CAMPUS_KW):
        return "校招"
    if sid in ("nk-intern", "sxs-intern"):
        return "实习"
    if sid == "cn-tencent-campus" or sid == "nk-campus" or sid.startswith("edu-") or sid in ("gov-ncss", "gov-qyzp"):
        return "校招"
    if any(k in t or k in tl for k in SOCIAL_KW):
        return "社招"
    if sid in ("cn-bytedance", "cn-tencent", "cn-jd") or sid.startswith("wd-"):
        return "社招"
    return "其他"


def stage(title: str, jd: str) -> str:
    text = text_blob(title, jd)
    low = text.lower()
    if any(k in text or k in low for k in SPRING_KW):
        return "春招/补录"
    if any(k in text or k in low for k in ADVANCE_KW):
        return "提前批"
    if any(k in text or k in low for k in AUTUMN_KW):
        return "秋招"
    if any(k in text or k in low for k in SUMMER_KW):
        return "暑期实习"
    if any(k in text or k in low for k in EVENT_KW):
        return "宣讲/活动"
    if any(k in text or k in low for k in CAMPUS_KW):
        return "校招"
    return "其他"


def is_2027_cycle(sid: str, job_kind: str, title: str, jd: str, publish: str, job_stage: str) -> bool:
    text = text_blob(title, jd)
    low = text.lower()
    if any(k in text or k in low for k in C27_KW):
        return True
    recent_2026 = publish >= "2026-05-01"
    campus_source = sid == "cn-tencent-campus" or sid == "nk-campus" or sid.startswith("edu-") or sid in ("gov-ncss", "gov-qyzp")
    student_source = sid in ("nk-intern", "sxs-intern")
    if sid == "cn-tencent-campus":
        return True
    if recent_2026 and campus_source and job_kind == "校招":
        return True
    if recent_2026 and student_source and job_stage == "暑期实习":
        return True
    if recent_2026 and job_stage in ("提前批", "秋招", "春招/补录"):
        return True
    return False


def category(sid: str) -> str:
    if sid == "cn-iguopin":
        return "国聘"
    if sid.startswith(("nk-", "sxs-")):
        return "实习平台"
    if sid.startswith("feed-"):
        return "群推送"
    if sid.startswith("gov-"):
        return "国家平台"
    if sid.startswith("edu-"):
        return "高校"
    if sid.startswith("cn-"):
        return "大厂官网"
    if sid.startswith(("gh-", "ashby-", "lever-")):
        return "海外ATS"
    return "其他"


def region(loc: str) -> str:
    low = (loc or "").lower()
    for name, kws in REGION_RULES:
        if any(k.lower() in low for k in kws):
            return name
    return "其他"


def region_of(cat: str, loc: str) -> str:
    if cat == "高校":
        return "其他"
    r = region(loc)
    if cat == "海外ATS" and r == "其他":
        return "远程/海外"
    return r
