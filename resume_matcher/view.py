"""网页上的结果展示

整理表格行的函数是纯函数，可以单独测试；render_result 只负责把整理好的数据交给 Streamlit。
"""
import pandas as pd
import streamlit as st

from resume_matcher.grounding import SUSPECT_PREFIX
from resume_matcher.pipeline import AnalysisResult
from resume_matcher.report import RATE_LABELS
from resume_matcher.schemas import SkillCheck

RATE_ORDER = ("required", "years", "preferred")
EDUCATION_RESULTS = {
    "满足": "✓ 满足",
    "不满足": "✗ 不满足",
    "无法判断": "？ 无法判断",
    "未要求": "— 未要求",
}


def skill_rows(checks: list[SkillCheck]) -> list[dict]:
    """每项技能一行：状态、技能、依据。依据存疑的单独标出，不和普通的“未体现”混在一起"""
    rows = []
    for c in checks:
        if c.evidence.startswith(SUSPECT_PREFIX):
            quoted = c.evidence[len(SUSPECT_PREFIX):]
            rows.append({"状态": "⚠ 依据存疑", "技能": c.skill,
                         "依据": f"模型给出的依据在简历中找不到：{quoted}"})
        elif c.matched:
            rows.append({"状态": "✓ 满足", "技能": c.skill, "依据": c.evidence})
        else:
            rows.append({"状态": "✗ 未体现", "技能": c.skill,
                         "依据": "—" if c.evidence.strip() in ("", "无") else c.evidence})
    return rows


def education_rows(education: dict) -> list[dict]:
    return [
        {"项目": label, "结果": EDUCATION_RESULTS[education[key]["status"]], "说明": education[key]["detail"]}
        for label, key in (("学历", "degree"), ("学校", "school"))
    ]


def ranking_rows(recs) -> list[dict]:
    """推荐排名表：recs 已按总分从高到低排好"""
    return [
        {"排名": i, "总分": r.result.score, "岗位": r.result.job.title,
         "文件": r.source, "检索距离": round(r.distance, 3)}
        for i, r in enumerate(recs, 1)
    ]


def rate_rows(rates: dict) -> list[tuple[str, float]]:
    return [(RATE_LABELS[k], rates[k]) for k in RATE_ORDER if k in rates]


def _table(rows: list[dict], index: str) -> None:
    """依据可能很长，st.dataframe 的单元格不换行会把它截断；st.table 会换行，完整显示。
    把第一列设成索引，既去掉默认的行号，也让它成为醒目的第一列"""
    st.table(pd.DataFrame(rows).set_index(index))


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_result(result: AnalysisResult) -> None:
    st.subheader(result.job.title)

    score_col, rate_col = st.columns([1, 2])
    with score_col:
        st.metric("匹配度", f"{result.score} 分")
    with rate_col:
        rows = rate_rows(result.rates)
        for label, value in rows:
            st.progress(value, text=f"{label}　{value:.0%}")
        if not rows:
            st.caption("岗位没有可评估的要求")
    st.caption("分数反映的是岗位要求的技能被满足的比例，不是对候选人能力的全面评价。")

    st.markdown("**学历与院校**　单独检查，不计入总分")
    _table(education_rows(result.education), index="项目")

    st.markdown("**必备技能**")
    if result.report.required_checks:
        _table(skill_rows(result.report.required_checks), index="状态")
    else:
        st.caption("岗位没有列出必备技能")

    if result.report.preferred_checks:
        st.markdown("**加分项**")
        _table(skill_rows(result.report.preferred_checks), index="状态")

    st.caption("技能是否满足由模型判断，请对照“依据”核对；"
               "“依据存疑”表示模型给出的依据在简历原文里找不到，已按未满足处理。")

    left, right = st.columns(2)
    with left:
        st.markdown("**简历修改建议**")
        st.markdown(_bullets(result.report.suggestions))
    with right:
        st.markdown("**可能被问到的问题**")
        st.markdown(_bullets(result.report.interview_questions))
