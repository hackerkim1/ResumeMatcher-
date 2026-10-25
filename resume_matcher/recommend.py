"""岗位库推荐：向量检索粗筛候选岗位，再逐个详细评分，最后按总分排序

检索只说明“话题相近”，不说明“够不够格”，所以最终排名以评分为准，不以检索距离为准。
"""
from dataclasses import dataclass

from resume_matcher.pipeline import AnalysisResult, analyze_job
from resume_matcher.schemas import ResumeInfo


@dataclass
class Recommendation:
    source: str
    distance: float
    result: AnalysisResult


def resume_query(resume: ResumeInfo) -> str:
    """检索用的查询文本：只取技能和项目，去掉姓名、学校等与岗位语义无关的信息"""
    return "技能：" + "、".join(resume.skills) + "。项目：" + "；".join(resume.projects)


def recommend(resume_text: str, library, k: int, resume_chain, job_chain, match_chain,
              cache, schools: dict) -> list[Recommendation]:
    resume = resume_chain.invoke({"text": resume_text})  # 简历只抽取一次
    hits = library.search(resume_query(resume), k)
    recs = [
        Recommendation(
            source=hit.source,
            distance=hit.distance,
            result=analyze_job(resume, resume_text, hit.text, job_chain, match_chain, cache, schools),
        )
        for hit in hits
    ]
    return sorted(recs, key=lambda r: r.result.score, reverse=True)
