"""文本归一化与 dedup_key 生成（对应规划 5.4 节）。

去重是同类项目最容易翻车的地方，所有归一化规则集中在这里，方便审查和扩展。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# 职位名里常见的噪声后缀/标记，归一化时剥除，避免"同岗不同名"漏去重
_TITLE_NOISE = [
    "（社招）", "(社招)", "（校招）", "(校招)", "（急聘）", "(急聘)",
    "【急聘】", "急聘", "诚聘", "热招", "（多地）", "(多地)",
    "（J\\d+）", "\\(J\\d+\\)",  # 部分官网带 JD 编号
]
_NOISE_RE = re.compile("|".join(_TITLE_NOISE))
_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """统一全半角、去首尾与内部多余空白、转小写。"""
    if not text:
        return ""
    # NFKC 把全角字符/罗马数字等折叠为半角标准形式
    text = unicodedata.normalize("NFKC", text)
    text = _SPACE_RE.sub(" ", text).strip().lower()
    return text


def normalize_title(title: str) -> str:
    """职位名归一化：先剥噪声后缀，再做通用归一化。"""
    title = _NOISE_RE.sub("", title or "")
    return normalize_text(title)


def normalize_city(location: str) -> str:
    """城市归一化：取第一个城市 token，去掉"市/区"和国家后缀。

    例："深圳市·南山区" / "Shenzhen, China" → "深圳" / "shenzhen"
    """
    if not location:
        return ""
    loc = normalize_text(location)
    # 以常见分隔符切分，取首段
    loc = re.split(r"[·,，/、|\-]", loc)[0].strip()
    loc = re.sub(r"(市|区|县|省)$", "", loc)
    return loc


_SAL_NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize_salary(raw: str):
    """把异构薪资字符串解析成可比的 (月薪下限, 月薪上限) 整数（人民币/月）。

    支持："5.0-15.0K/月" "3000-10000元/月" "1.5-2万/月" "20-30万/年" 等；
    无法解析或面议返回 (0, 0)。年薪自动 /12 折成月薪。
    """
    s = (raw or "").strip()
    if not s or "面议" in s:
        return (0, 0)
    nums = [float(x) for x in _SAL_NUM.findall(s)]
    if not nums:
        return (0, 0)
    lo = nums[0]
    hi = nums[1] if len(nums) > 1 else nums[0]
    unit = 10000 if "万" in s else (1000 if "k" in s.lower() else 1)
    lo, hi = lo * unit, hi * unit
    if "年" in s:                      # 年薪折月薪
        lo, hi = lo / 12, hi / 12
    if lo > hi:
        lo, hi = hi, lo
    return (int(lo), int(hi))


def make_dedup_key(company_name: str, title: str, location: str) -> str:
    """主去重键 = 归一化(公司名) + 归一化(职位名) + 归一化(城市) 的短哈希。

    用哈希而非拼接原文，是为了让 key 长度稳定、可直接做主键/文件名。
    """
    parts = [
        normalize_text(company_name),
        normalize_title(title),
        normalize_city(location),
    ]
    raw = "||".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
