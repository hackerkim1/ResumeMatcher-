from resume_matcher.schemas import ResumeInfo, JobRequirement, MatchReport, SkillCheck
from resume_matcher.scoring import compute_score, education_check, school_tier

SCHOOLS = {"985": ["清华大学"], "211": ["北京邮电大学"]}


def make_resume(**kw):
    base = dict(name="张三", school="某某学院", degree="本科", skills=[],
                years_of_experience=0, projects=[])
    return ResumeInfo(**{**base, **kw})


def make_job(**kw):
    base = dict(title="测试岗位", required_skills=[], preferred_skills=[],
                min_years=0, min_degree="不限", school_requirement="")
    return JobRequirement(**{**base, **kw})


def make_report(required=(), preferred=()):
    """required / preferred 传一串 True/False，表示每项技能是否满足"""
    def checks(flags):
        return [SkillCheck(skill=f"s{i}", matched=m, evidence="") for i, m in enumerate(flags)]
    return MatchReport(required_checks=checks(required), preferred_checks=checks(preferred),
                       suggestions=[], interview_questions=[])


# ---------- compute_score ----------

def test_all_satisfied_gets_full_score():
    score, _ = compute_score(
        make_resume(years_of_experience=2),
        make_job(min_years=1),
        make_report(required=[True, True], preferred=[True]),
    )
    assert score == 100


def test_partial_match():
    # 必备 1/2 → 35，加分 0/1 → 0，年限满足 → 15
    score, _ = compute_score(
        make_resume(years_of_experience=1),
        make_job(min_years=1),
        make_report(required=[True, False], preferred=[False]),
    )
    assert score == 50


def test_missing_dimensions_are_skipped_and_weights_rescaled():
    # 没有加分项、没有年限要求，只剩必备：1/2 → 50
    score, _ = compute_score(
        make_resume(),
        make_job(),
        make_report(required=[True, False]),
    )
    assert score == 50


def test_years_partially_met():
    # 必备 2/2 → 70，年限 1/2 → 7.5，没有加分项：(70+7.5)/85*100 ≈ 91
    score, _ = compute_score(
        make_resume(years_of_experience=1),
        make_job(min_years=2),
        make_report(required=[True, True]),
    )
    assert score == 91


def test_years_rate_is_capped_at_one():
    score, rates = compute_score(
        make_resume(years_of_experience=10),
        make_job(min_years=2),
        make_report(required=[True]),
    )
    assert rates["years"] == 1
    assert score == 100


def test_no_requirements_gives_zero():
    score, rates = compute_score(make_resume(), make_job(), make_report())
    assert score == 0
    assert rates == {}


# ---------- school_tier ----------

def test_school_tier_lookup():
    assert school_tier("清华大学", SCHOOLS) == "985"
    assert school_tier("北京邮电大学", SCHOOLS) == "211"
    assert school_tier("某某学院", SCHOOLS) == "未收录"


def test_school_tier_ignores_surrounding_spaces():
    assert school_tier(" 清华大学 ", SCHOOLS) == "985"


# ---------- education_check ----------

def test_degree_met():
    r = education_check(make_resume(degree="硕士"), make_job(min_degree="本科"), SCHOOLS)
    assert r["degree"]["status"] == "满足"


def test_degree_not_met():
    r = education_check(make_resume(degree="本科"), make_job(min_degree="硕士"), SCHOOLS)
    assert r["degree"]["status"] == "不满足"


def test_degree_not_required():
    r = education_check(make_resume(), make_job(min_degree="不限"), SCHOOLS)
    assert r["degree"]["status"] == "未要求"


def test_degree_unknown_in_resume():
    r = education_check(make_resume(degree="未知"), make_job(min_degree="本科"), SCHOOLS)
    assert r["degree"]["status"] == "无法判断"


def test_school_985_satisfies_985_or_211_requirement():
    r = education_check(make_resume(school="清华大学"), make_job(school_requirement="985/211优先"), SCHOOLS)
    assert r["school"]["status"] == "满足"


def test_school_211_does_not_satisfy_985_requirement():
    r = education_check(make_resume(school="北京邮电大学"), make_job(school_requirement="985"), SCHOOLS)
    assert r["school"]["status"] == "不满足"


def test_school_not_in_list_cannot_be_judged():
    # 名单里查不到不等于不达标，只能说无法判断
    r = education_check(make_resume(school="某某学院"), make_job(school_requirement="211"), SCHOOLS)
    assert r["school"]["status"] == "无法判断"


def test_school_not_required():
    r = education_check(make_resume(), make_job(school_requirement=""), SCHOOLS)
    assert r["school"]["status"] == "未要求"
