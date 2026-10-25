import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.cache import JobCache
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.pipeline import analyze
from resume_matcher.report import format_report

SCHOOLS = {"985": ["清华大学"], "211": []}
RESUME_TEXT = "清华大学 本科\n技能：Python\n项目：做过一个问答系统"
JD_TEXT = "岗位：测试工程师\n必备：Python、LangChain\n加分：FastAPI\n学历：本科\n院校：985优先"

RESUME_JSON = json.dumps({
    "name": "张三", "school": "清华大学", "degree": "本科", "skills": ["Python"],
    "years_of_experience": 0, "projects": ["问答系统"],
}, ensure_ascii=False)

JOB_JSON = json.dumps({
    "title": "测试工程师", "required_skills": ["Python", "LangChain"],
    "preferred_skills": ["FastAPI"], "min_years": 0, "min_degree": "本科",
    "school_requirement": "985优先",
}, ensure_ascii=False)

JUDGE_JSON = json.dumps({
    "required_checks": [
        {"skill": "Python", "matched": True, "evidence": "技能：Python"},
        {"skill": "LangChain", "matched": False, "evidence": "无"},
    ],
    "preferred_checks": [{"skill": "FastAPI", "matched": False, "evidence": "无"}],
    "suggestions": ["补充 LangChain 相关项目"],
    "interview_questions": ["介绍一下你的问答系统"],
}, ensure_ascii=False)


def fake(reply):
    return FakeListChatModel(responses=[reply])


def run(tmp_path):
    return analyze(
        RESUME_TEXT, JD_TEXT,
        resume_chain=build_resume_chain(fake(RESUME_JSON)),
        job_chain=build_job_chain(fake(JOB_JSON)),
        match_chain=build_match_chain(fake(JUDGE_JSON)),
        cache=JobCache(tmp_path),
        schools=SCHOOLS,
    )


# ---------- analyze ----------

def test_analyze_computes_the_hand_calculated_score(tmp_path):
    # 必备 1/2 → 70×0.5 = 35；加分 0/1 → 0；没有年限要求；(35+0)/(70+15)×100 = 41.18 → 41
    result = run(tmp_path)
    assert result.score == 41
    assert result.rates == {"required": 0.5, "preferred": 0.0}


def test_analyze_returns_extracted_objects(tmp_path):
    result = run(tmp_path)
    assert result.resume.name == "张三"
    assert result.job.title == "测试工程师"
    assert [c.skill for c in result.report.required_checks] == ["Python", "LangChain"]


def test_analyze_checks_education_and_school(tmp_path):
    result = run(tmp_path)
    assert result.education["degree"]["status"] == "满足"
    assert result.education["school"]["status"] == "满足"


def test_analyze_writes_the_job_to_cache(tmp_path):
    run(tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 1


# ---------- format_report ----------

def test_report_contains_the_key_information(tmp_path):
    text = format_report(run(tmp_path))
    for expected in ["测试工程师", "41", "Python", "LangChain", "FastAPI",
                     "技能：Python", "满足", "补充 LangChain 相关项目", "介绍一下你的问答系统"]:
        assert expected in text


def test_report_marks_matched_and_unmatched_skills(tmp_path):
    text = format_report(run(tmp_path))
    def line_for(skill):
        return next(l for l in text.splitlines() if skill in l and ("✓" in l or "✗" in l))

    assert "✓" in line_for("Python")
    assert "✗" in line_for("LangChain")


def test_report_says_education_is_separate_from_the_score(tmp_path):
    assert "不计入总分" in format_report(run(tmp_path))
