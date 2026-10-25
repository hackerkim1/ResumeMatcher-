import json

from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.cache import JobCache
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.library import JobLibrary
from resume_matcher.recommend import recommend, resume_query
from resume_matcher.report import format_ranking
from resume_matcher.schemas import ResumeInfo

RESUME_TEXT = "清华大学 本科\n技能：Python\n项目：做过一个问答系统"
SCHOOLS = {"985": ["清华大学"], "211": []}


def resume_json():
    return json.dumps({"name": "张三", "school": "清华大学", "degree": "本科", "skills": ["Python"],
                       "years_of_experience": 0, "projects": ["问答系统"]}, ensure_ascii=False)


def job_json(title):
    return json.dumps({"title": title, "required_skills": ["Python"], "preferred_skills": [],
                       "min_years": 0, "min_degree": "不限", "school_requirement": ""}, ensure_ascii=False)


def judge_json(matched):
    return json.dumps({
        "required_checks": [{"skill": "Python", "matched": matched,
                             "evidence": "技能：Python" if matched else "无"}],
        "preferred_checks": [], "suggestions": ["建议"], "interview_questions": ["问题"],
    }, ensure_ascii=False)


class CountingChain:
    """包一层，记录被调用的次数"""

    def __init__(self, chain):
        self.chain, self.calls = chain, 0

    def invoke(self, *args, **kwargs):
        self.calls += 1
        return self.chain.invoke(*args, **kwargs)


def make_library(tmp_path, n=2):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    for i in range(n):
        (jobs_dir / f"job{i}.txt").write_text(f"岗位{i}：需要 Python，做第 {i} 类业务", encoding="utf-8")
    lib = JobLibrary(DeterministicFakeEmbedding(size=32), tmp_path / "db")
    lib.sync(jobs_dir)
    return lib


def run(tmp_path, judge_replies, n_jobs=2, k=2):
    resume_chain = CountingChain(build_resume_chain(FakeListChatModel(responses=[resume_json()])))
    recs = recommend(
        RESUME_TEXT, make_library(tmp_path, n_jobs), k,
        resume_chain=resume_chain,
        job_chain=build_job_chain(FakeListChatModel(responses=[job_json("岗位甲"), job_json("岗位乙")])),
        match_chain=build_match_chain(FakeListChatModel(responses=judge_replies)),
        cache=JobCache(tmp_path / "cache"),
        schools=SCHOOLS,
    )
    return recs, resume_chain


# ---------- resume_query ----------

def test_resume_query_contains_skills_and_projects_but_not_the_name():
    resume = ResumeInfo(name="张三", school="某某大学", degree="本科", skills=["Python", "SQL"],
                        years_of_experience=0, projects=["问答系统", "文本分类"])
    q = resume_query(resume)
    for expected in ["Python", "SQL", "问答系统", "文本分类"]:
        assert expected in q
    assert "张三" not in q and "某某大学" not in q


# ---------- recommend ----------

def test_results_are_sorted_by_score_not_by_retrieval_order(tmp_path):
    # 第一个被评分的岗位拿到“全满足”，第二个拿到“全不满足”；不管检索顺序如何，高分都应排在前面
    recs, _ = run(tmp_path, [judge_json(True), judge_json(False)])
    assert [r.result.score for r in recs] == [100, 0]


def test_resume_is_extracted_only_once(tmp_path):
    _, resume_chain = run(tmp_path, [judge_json(True), judge_json(False)])
    assert resume_chain.calls == 1


def test_each_recommendation_keeps_its_source_and_distance(tmp_path):
    recs, _ = run(tmp_path, [judge_json(True), judge_json(False)])
    assert {r.source for r in recs} == {"job0.txt", "job1.txt"}
    assert all(r.distance >= 0 for r in recs)


def test_k_limits_how_many_jobs_are_scored(tmp_path):
    recs, _ = run(tmp_path, [judge_json(True)], n_jobs=3, k=1)
    assert len(recs) == 1


def test_recommend_on_empty_library_returns_empty_list(tmp_path):
    recs, _ = run(tmp_path, [judge_json(True)], n_jobs=0, k=3)
    assert recs == []


# ---------- format_ranking ----------

def test_ranking_lists_titles_scores_and_sources_in_order(tmp_path):
    recs, _ = run(tmp_path, [judge_json(True), judge_json(False)])
    text = format_ranking(recs)
    assert "job0.txt" in text and "job1.txt" in text
    first, second = text.splitlines()[1:3]  # 第 0 行是标题
    assert "100 分" in first
    assert "100" not in second and " 0 分" in second


def test_ranking_for_no_results_says_so():
    assert "没有" in format_ranking([])
