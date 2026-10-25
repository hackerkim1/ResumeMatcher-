"""完整流程：简历 + 岗位描述 → 匹配结果

各条链和缓存都从参数传入，测试时可以换成假模型。
"""
from dataclasses import dataclass

from resume_matcher.extractors import extract_job_cached
from resume_matcher.judge import judge
from resume_matcher.schemas import JobRequirement, MatchReport, ResumeInfo
from resume_matcher.scoring import compute_score, education_check


@dataclass
class AnalysisResult:
    resume: ResumeInfo
    job: JobRequirement
    report: MatchReport
    score: int
    rates: dict
    education: dict


def analyze_job(resume: ResumeInfo, resume_text: str, jd_text: str, job_chain, match_chain,
                cache, schools: dict) -> AnalysisResult:
    """简历已经抽取好时，只对一个岗位做评分。一份简历对多个岗位时避免重复抽取简历"""
    job = extract_job_cached(jd_text, job_chain, cache)
    report = judge(resume_text, job, match_chain)
    score, rates = compute_score(resume, job, report)
    education = education_check(resume, job, schools)
    return AnalysisResult(resume=resume, job=job, report=report,
                          score=score, rates=rates, education=education)


def analyze(resume_text: str, jd_text: str, resume_chain, job_chain, match_chain,
            cache, schools: dict) -> AnalysisResult:
    resume = resume_chain.invoke({"text": resume_text})
    return analyze_job(resume, resume_text, jd_text, job_chain, match_chain, cache, schools)
