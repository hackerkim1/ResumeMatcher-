"""依据核对：模型说“满足”时，检查它给的依据是否真的来自简历原文

容错做法：把依据按标点和空白拆成片段，只要有一个“有分量”的片段能在原文里找到，
就算有依据。这样模型给原文加了括号注释也不会被误伤，只拦凭空编造的依据。
这是一道便宜的保险，不是证明：编造的依据恰好含有原文里的长片段时拦不住。
"""
import re

from resume_matcher.schemas import SkillCheck

SUSPECT_PREFIX = "【依据存疑】"

# 不含 - / .，避免把 scikit-learn、A/B 这类词拆碎
_SPLIT = re.compile(r"[\s，。；;、,：:（）()\[\]【】\"“”'‘’！!？?《》<>|]+")

# 英文技术术语（Python、SQL、scikit-learn、TF-IDF、C++）；中英文连写时也能取出，如“技能中列出Python”
_ASCII_TERM = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{2,}")


def _is_substantial(segment: str) -> bool:
    """长度 >= 4，或纯英文数字且长度 >= 3（SQL、RAG、Git 这类短词要算）；太短的中文词太常见，不算证据"""
    return len(segment) >= 4 or (len(segment) >= 3 and segment.isascii())


def is_grounded(evidence: str, resume_text: str) -> bool:
    """依据是否出自简历（忽略大小写和空白差异）。满足下面任一条就算有依据：

    1. 有至少一个“有分量”的片段原样出现在简历里（模型逐字摘抄时）；
    2. 依据里提到的英文术语全部出现在简历里（模型改写成自己的话时）；
       只要有一个术语简历里没有，就仍然判为存疑。
    """
    haystack = re.sub(r"\s+", "", resume_text).casefold()
    for segment in _SPLIT.split(evidence):
        segment = segment.casefold()
        if _is_substantial(segment) and segment in haystack:
            return True

    terms = _ASCII_TERM.findall(evidence)
    return bool(terms) and all(term.casefold() in haystack for term in terms)


def verify_checks(checks: list[SkillCheck], resume_text: str) -> list[SkillCheck]:
    """把“声称满足但依据对不上原文”的判断降级为不满足，并标记存疑；不修改传入的对象"""
    verified = []
    for c in checks:
        if c.matched and not is_grounded(c.evidence, resume_text):
            c = c.model_copy(update={
                "matched": False,
                "evidence": f"{SUSPECT_PREFIX}{c.evidence}",
            })
        verified.append(c)
    return verified
