import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from streamlit.testing.v1 import AppTest

from resume_matcher.cache import JobCache
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.services import Services

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SCHOOLS = {"985": ["清华大学"], "211": []}

RESUME_JSON = json.dumps({"name": "张三", "school": "清华大学", "degree": "本科", "skills": ["Python"],
                          "years_of_experience": 0, "projects": ["问答系统"]}, ensure_ascii=False)
JOB_JSON = json.dumps({"title": "测试工程师", "required_skills": ["Python", "LangChain"],
                       "preferred_skills": ["FastAPI"], "min_years": 0, "min_degree": "本科",
                       "school_requirement": ""}, ensure_ascii=False)
JUDGE_JSON = json.dumps({
    "required_checks": [{"skill": "Python", "matched": True, "evidence": "技能：Python"},
                        {"skill": "LangChain", "matched": False, "evidence": "无"}],
    "preferred_checks": [{"skill": "FastAPI", "matched": False, "evidence": "无"}],
    "suggestions": ["补充 LangChain 相关项目"], "interview_questions": ["介绍一下你的问答系统"],
}, ensure_ascii=False)

RESUME_TEXT = "清华大学 本科\n技能：Python\n项目：做过一个问答系统"
JD_TEXT = "岗位：测试工程师\n必备：Python、LangChain\n加分：FastAPI"


def fake_services(tmp_path):
    def chain(builder, reply):
        return builder(FakeListChatModel(responses=[reply]))

    return Services(
        resume_chain=chain(build_resume_chain, RESUME_JSON),
        job_chain=chain(build_job_chain, JOB_JSON),
        match_chain=chain(build_match_chain, JUDGE_JSON),
        cache=JobCache(tmp_path / "cache"),
        schools=SCHOOLS,
    )


class ExplodingChain:
    def invoke(self, *args, **kwargs):
        raise RuntimeError("secret-key-sk-12345")


def start(services):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["_services"] = services
    at.run()
    assert not at.exception
    return at


def fill_and_click(at, resume=RESUME_TEXT, job=JD_TEXT):
    at.text_area(key="resume_text").set_value(resume)
    at.text_area(key="job_text").set_value(job)
    at.button(key="run_match").click()
    at.run()
    return at


def page_text(at):
    elements = [at.markdown, at.text, at.error, at.subheader, at.caption]
    parts = [e.value for group in elements for e in group]
    return "\n".join(str(p) for p in parts)


# ---------- 岗位库推荐标签页 ----------

def job_json(title):
    return json.dumps({"title": title, "required_skills": ["Python"], "preferred_skills": [],
                       "min_years": 0, "min_degree": "不限", "school_requirement": ""}, ensure_ascii=False)


def judge_json(matched):
    return json.dumps({
        "required_checks": [{"skill": "Python", "matched": matched,
                             "evidence": "技能：Python" if matched else "无"}],
        "preferred_checks": [], "suggestions": ["建议"], "interview_questions": ["问题"],
    }, ensure_ascii=False)


def recommend_services(tmp_path, judge_replies):
    return Services(
        resume_chain=build_resume_chain(FakeListChatModel(responses=[RESUME_JSON])),
        job_chain=build_job_chain(FakeListChatModel(responses=[job_json("岗位甲"), job_json("岗位乙")])),
        match_chain=build_match_chain(FakeListChatModel(responses=judge_replies)),
        cache=JobCache(tmp_path / "cache"),
        schools=SCHOOLS,
    )


def make_library(tmp_path, n_jobs=2):
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from resume_matcher.library import JobLibrary

    jobs = tmp_path / "jobs"
    jobs.mkdir()
    for i in range(n_jobs):
        (jobs / f"job{i}.txt").write_text(f"岗位{i}：需要 Python，做第 {i} 类业务", encoding="utf-8")
    library = JobLibrary(DeterministicFakeEmbedding(size=16), tmp_path / "db")
    return library, library.sync(jobs)


def start_recommend(tmp_path, judge_replies=None, n_jobs=2):
    judge_replies = judge_replies or [judge_json(True), judge_json(False)]
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["_services"] = recommend_services(tmp_path, judge_replies)
    library_and_stats = make_library(tmp_path, n_jobs)
    at.session_state["_library_factory"] = lambda: library_and_stats
    at.run()
    assert not at.exception
    return at


def click_recommend(at, resume=RESUME_TEXT):
    at.text_area(key="rec_resume_text").set_value(resume)
    at.button(key="run_recommend").click()
    at.run()
    return at


def test_page_has_two_tabs(tmp_path):
    at = start(fake_services(tmp_path))
    assert [t.label for t in at.tabs] == ["单岗位匹配", "岗位库推荐"]


def test_recommend_shows_a_ranking_sorted_by_score(tmp_path):
    at = click_recommend(start_recommend(tmp_path))
    assert not at.exception and not at.error
    recs = at.session_state["recommend_results"]
    assert [r.result.score for r in recs] == [100, 0]
    assert at.dataframe[0].value["总分"].tolist() == [100, 0]  # 第一张表是排名表


def test_recommend_shows_one_expander_per_job(tmp_path):
    at = click_recommend(start_recommend(tmp_path))
    assert len(at.expander) == 2


def test_recommend_k_slider_limits_the_candidates(tmp_path):
    at = start_recommend(tmp_path)
    at.slider(key="rec_k").set_value(1)
    click_recommend(at)
    assert len(at.session_state["recommend_results"]) == 1


def test_recommend_with_empty_resume_shows_a_clear_message(tmp_path):
    at = click_recommend(start_recommend(tmp_path), resume="")
    assert any("简历" in e.value for e in at.error)
    assert "recommend_results" not in at.session_state


def test_recommend_failure_shows_only_the_error_type(tmp_path):
    at = start_recommend(tmp_path)
    at.session_state["_services"].resume_chain = ExplodingChain()
    click_recommend(at)
    assert any("RuntimeError" in e.value for e in at.error)
    assert "secret-key-sk-12345" not in page_text(at)


def test_the_two_tabs_do_not_share_their_results(tmp_path):
    at = click_recommend(start_recommend(tmp_path))
    assert "match_result" not in at.session_state


def test_page_loads_without_errors(tmp_path):
    at = start(fake_services(tmp_path))
    assert at.title[0].value
    assert not at.error


def test_pasting_text_and_clicking_runs_the_analysis(tmp_path):
    at = fill_and_click(start(fake_services(tmp_path)))
    assert not at.exception and not at.error
    assert at.session_state["match_result"].score == 41
    assert "测试工程师" in page_text(at)


def test_result_is_shown_as_a_score_card_and_tables(tmp_path):
    at = fill_and_click(start(fake_services(tmp_path)))
    assert at.metric[0].label == "匹配度"
    assert at.metric[0].value == "41 分"
    # 学历院校一张表、必备技能一张表、加分项一张表（用 st.table，长依据才会换行而不是被截断）
    assert len(at.table) == 3
    assert "不计入总分" in page_text(at)


def test_clicking_with_empty_inputs_shows_a_clear_message(tmp_path):
    at = fill_and_click(start(fake_services(tmp_path)), resume="", job="")
    assert any("简历" in e.value for e in at.error)
    assert "match_result" not in at.session_state


def test_a_failed_analysis_shows_only_the_error_type(tmp_path):
    services = fake_services(tmp_path)
    services.resume_chain = ExplodingChain()
    at = fill_and_click(start(services))
    shown = "\n".join(e.value for e in at.error)
    assert "RuntimeError" in shown
    assert "secret-key-sk-12345" not in page_text(at)


def test_old_result_is_cleared_when_the_next_analysis_fails(tmp_path):
    services = fake_services(tmp_path)
    at = fill_and_click(start(services))
    assert "match_result" in at.session_state

    services.resume_chain = ExplodingChain()
    at.button(key="run_match").click()
    at.run()
    assert "match_result" not in at.session_state
