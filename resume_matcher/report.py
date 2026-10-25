"""把分析结果排版成文本"""
from resume_matcher.pipeline import AnalysisResult
from resume_matcher.schemas import SkillCheck

RATE_LABELS = {"required": "必备技能", "years": "年限", "preferred": "加分项"}


def _check_lines(checks: list[SkillCheck]) -> list[str]:
    return [f"  {'✓' if c.matched else '✗'} {c.skill}  依据：{c.evidence}" for c in checks]


def format_ranking(recs) -> str:
    """推荐排名的摘要：按总分从高到低，每行一个岗位"""
    if not recs:
        return "没有检索到任何岗位。"
    lines = ["推荐排名（先按语义检索候选岗位，再逐个详细评分）："]
    for i, r in enumerate(recs, 1):
        lines.append(f"  {i}. {r.result.job.title}  {r.result.score} 分  （{r.source}，检索距离 {r.distance:.3f}）")
    return "\n".join(lines)


def format_report(result: AnalysisResult) -> str:
    lines = [
        f"===== {result.job.title} =====",
        f"匹配度：{result.score} 分",
        "各维度满足率：" + "，".join(
            f"{RATE_LABELS[k]} {v:.0%}" for k, v in result.rates.items()) if result.rates else "各维度满足率：无可评估的要求",
        "",
        "学历与院校（单独检查，不计入总分）：",
    ]
    for label, key in (("学历", "degree"), ("学校", "school")):
        item = result.education[key]
        detail = f"：{item['detail']}" if item["detail"] else ""
        lines.append(f"  {label}：{item['status']}{detail}")

    lines += ["", "必备技能："] + _check_lines(result.report.required_checks)
    if result.report.preferred_checks:
        lines += ["", "加分项："] + _check_lines(result.report.preferred_checks)

    lines += ["", "简历修改建议："] + [f"  - {s}" for s in result.report.suggestions]
    lines += ["", "可能被问到的问题："] + [f"  - {q}" for q in result.report.interview_questions]
    return "\n".join(lines)
