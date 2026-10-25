import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.judge import align_checks, build_match_chain, judge
from resume_matcher.schemas import JobRequirement, MatchReport, SkillCheck


def check(skill, matched=True, evidence="原文片段"):
    return SkillCheck(skill=skill, matched=matched, evidence=evidence)


def make_job(required=("Python", "LangChain"), preferred=("FastAPI",)):
    return JobRequirement(title="测试岗位", required_skills=list(required),
                          preferred_skills=list(preferred), min_years=0,
                          min_degree="不限", school_requirement="")


def report_json(required, preferred):
    return json.dumps({
        "required_checks": [c.model_dump() for c in required],
        "preferred_checks": [c.model_dump() for c in preferred],
        "suggestions": ["建议一"],
        "interview_questions": ["问题一"],
    }, ensure_ascii=False)


# ---------- align_checks ----------

def test_align_keeps_jd_order():
    result = align_checks(["A", "B"], [check("B"), check("A")])
    assert [c.skill for c in result] == ["A", "B"]


def test_align_fills_missing_skill_as_not_matched():
    result = align_checks(["A", "B"], [check("A")])
    assert [c.skill for c in result] == ["A", "B"]
    assert result[1].matched is False
    assert "未给出判断" in result[1].evidence


def test_align_drops_skills_not_in_jd():
    result = align_checks(["A"], [check("A"), check("多出来的")])
    assert [c.skill for c in result] == ["A"]


def test_align_keeps_first_when_duplicated():
    result = align_checks(["A"], [check("A", matched=True), check("A", matched=False)])
    assert len(result) == 1
    assert result[0].matched is True


def test_align_ignores_case_and_surrounding_spaces():
    result = align_checks(["LangChain"], [check(" langchain ", matched=True)])
    assert result[0].matched is True
    assert result[0].skill == "LangChain"  # 技能名以 JD 为准


def test_align_with_no_expected_skills_returns_empty():
    assert align_checks([], [check("模型编造的")]) == []


# ---------- build_match_chain / judge ----------

def test_chain_parses_match_report():
    raw = report_json([check("Python")], [])
    chain = build_match_chain(FakeListChatModel(responses=[raw]))
    out = chain.invoke({"resume_text": "简历", "job_title": "岗位",
                        "required_list": "1. Python", "preferred_list": "（无）"})
    assert isinstance(out, MatchReport)
    assert out.suggestions == ["建议一"]


def test_prompt_contains_resume_skills_and_rules():
    chain = build_match_chain(FakeListChatModel(responses=["{}"]))
    text = chain.first.invoke({"resume_text": "这是我的简历原文", "job_title": "某岗位",
                               "required_list": "1. Python\n2. LangChain",
                               "preferred_list": "1. FastAPI"}).to_string()
    for expected in ["这是我的简历原文", "LangChain", "FastAPI", "摘抄", "同义"]:
        assert expected in text


def test_judge_returns_aligned_report_even_if_model_skips_a_skill():
    # 模型只判断了 Python，漏了 LangChain，还多编了一项
    raw = report_json([check("Python"), check("编造的技能")], [check("FastAPI", matched=False)])
    chain = build_match_chain(FakeListChatModel(responses=[raw]))
    report = judge("简历原文", make_job(), chain)
    assert [c.skill for c in report.required_checks] == ["Python", "LangChain"]
    assert report.required_checks[1].matched is False
    assert [c.skill for c in report.preferred_checks] == ["FastAPI"]


def test_judge_downgrades_match_whose_evidence_is_not_in_the_resume():
    resume = "技能：Python、LangChain"
    raw = report_json(
        [check("Python", evidence="技能：Python"), check("LangChain", evidence="用 Docker 部署了服务")],
        [check("FastAPI", matched=False, evidence="无")],
    )
    chain = build_match_chain(FakeListChatModel(responses=[raw]))
    report = judge(resume, make_job(), chain)
    assert report.required_checks[0].matched is True
    assert report.required_checks[1].matched is False
    assert report.required_checks[1].evidence.startswith("【依据存疑】")


def test_judge_with_no_preferred_skills_drops_invented_checks():
    raw = report_json([check("Python")], [check("模型编造的加分项")])
    chain = build_match_chain(FakeListChatModel(responses=[raw]))
    report = judge("简历原文", make_job(required=["Python"], preferred=[]), chain)
    assert report.preferred_checks == []
