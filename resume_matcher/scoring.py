"""评分与学历/学校检查：纯代码，不调用模型，输入输出确定，便于写测试"""
import json

from resume_matcher.config import SCHOOLS_FILE, WEIGHTS
from resume_matcher.schemas import ResumeInfo, JobRequirement, MatchReport

DEGREE_LEVEL = {"专科": 1, "本科": 2, "硕士": 3, "博士": 4}
TIER_RANK = {"985": 2, "211": 1, "未收录": 0}


def load_schools() -> dict:
    return json.loads(SCHOOLS_FILE.read_text(encoding="utf-8"))


def school_tier(name: str, schools: dict) -> str:
    """查院校名单，返回 985 / 211 / 未收录"""
    name = name.strip()
    if name in schools.get("985", []):
        return "985"
    if name in schools.get("211", []):
        return "211"
    return "未收录"


def _result(status: str, detail: str = "") -> dict:
    return {"status": status, "detail": detail}


def education_check(resume: ResumeInfo, job: JobRequirement, schools: dict) -> dict:
    """学历和学校是否达标，单独展示，不计入总分。status 取 满足/不满足/无法判断/未要求"""
    need = DEGREE_LEVEL.get(job.min_degree)
    have = DEGREE_LEVEL.get(resume.degree)
    if need is None:
        degree = _result("未要求")
    elif have is None:
        degree = _result("无法判断", "简历未写明学历")
    elif have >= need:
        degree = _result("满足", f"要求{job.min_degree}，简历为{resume.degree}")
    else:
        degree = _result("不满足", f"要求{job.min_degree}，简历为{resume.degree}")

    req = job.school_requirement.strip()
    if not req:
        school = _result("未要求")
    else:
        tier = school_tier(resume.school, schools)
        if tier == "未收录":
            # 名单里查不到不等于不达标，只能说无法判断
            school = _result("无法判断", f"{resume.school}不在院校名单中，岗位要求：{req}")
        else:
            # 要求里同时提到多个层次（如“985/211优先”）时，取最低的作为门槛
            mentioned = [TIER_RANK[t] for t in ("985", "211") if t in req]
            need_rank = min(mentioned) if mentioned else 0
            ok = TIER_RANK[tier] >= need_rank
            school = _result("满足" if ok else "不满足", f"{resume.school}属于{tier}，岗位要求：{req}")
    return {"degree": degree, "school": school}


def compute_score(resume: ResumeInfo, job: JobRequirement, report: MatchReport):
    """按权重加总出总分；不存在的维度不参与，剩余权重按比例放大。返回 (总分, 各维度满足率)"""
    rates = {}
    if report.required_checks:
        rates["required"] = sum(c.matched for c in report.required_checks) / len(report.required_checks)
    if report.preferred_checks:
        rates["preferred"] = sum(c.matched for c in report.preferred_checks) / len(report.preferred_checks)
    if job.min_years > 0:
        rates["years"] = min(resume.years_of_experience / job.min_years, 1)

    total_weight = sum(WEIGHTS[k] for k in rates)
    if total_weight == 0:
        return 0, rates
    score = sum(WEIGHTS[k] * v for k, v in rates.items()) / total_weight * 100
    return round(score), rates
