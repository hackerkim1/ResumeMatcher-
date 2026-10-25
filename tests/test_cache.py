import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.cache import JobCache
from resume_matcher.extractors import build_job_chain, extract_job_cached, job_prompt_version
from resume_matcher.schemas import JobRequirement


def job_json(title):
    return (
        f'{{"title": "{title}", "required_skills": ["Python"], "preferred_skills": [], '
        '"min_years": 0, "min_degree": "不限", "school_requirement": ""}'
    )


def make_chain():
    # 两个不同的回复：如果第二次又调用了模型，就会拿到 B，从而被测试发现
    return build_job_chain(FakeListChatModel(responses=[job_json("A"), job_json("B")]))


def make_job(title="X"):
    return JobRequirement(title=title, required_skills=["Python"], preferred_skills=[],
                          min_years=0, min_degree="不限", school_requirement="")


# ---------- JobCache ----------

def test_get_returns_none_when_empty(tmp_path):
    assert JobCache(tmp_path).get("some jd", "v1") is None


def test_put_then_get_roundtrip(tmp_path):
    cache = JobCache(tmp_path)
    cache.put("some jd", "v1", make_job("岗位甲"))
    assert cache.get("some jd", "v1") == make_job("岗位甲")


def test_put_creates_missing_directory(tmp_path):
    cache = JobCache(tmp_path / "a" / "b")
    cache.put("jd", "v1", make_job())
    assert cache.get("jd", "v1") is not None


def test_different_text_is_a_different_entry(tmp_path):
    cache = JobCache(tmp_path)
    cache.put("jd one", "v1", make_job())
    assert cache.get("jd two", "v1") is None


def test_stale_when_prompt_version_changes(tmp_path):
    cache = JobCache(tmp_path)
    cache.put("jd", "old", make_job())
    assert cache.get("jd", "new") is None


def test_corrupted_file_is_treated_as_miss(tmp_path):
    cache = JobCache(tmp_path)
    cache.put("jd", "v1", make_job())
    for f in tmp_path.glob("*.json"):
        f.write_text("这不是 JSON", encoding="utf-8")
    assert cache.get("jd", "v1") is None


def test_file_with_missing_fields_is_treated_as_miss(tmp_path):
    cache = JobCache(tmp_path)
    cache.put("jd", "v1", make_job())
    for f in tmp_path.glob("*.json"):
        f.write_text(json.dumps({"prompt_version": "v1", "data": {"title": "只有标题"}}), encoding="utf-8")
    assert cache.get("jd", "v1") is None


# ---------- extract_job_cached ----------

def test_second_call_hits_cache_and_skips_the_model(tmp_path):
    chain, cache = make_chain(), JobCache(tmp_path)
    first = extract_job_cached("same jd", chain, cache)
    second = extract_job_cached("same jd", chain, cache)
    assert first.title == "A"
    assert second.title == "A"  # 若又调用了模型，这里会是 B


def test_different_jd_triggers_a_new_extraction(tmp_path):
    chain, cache = make_chain(), JobCache(tmp_path)
    assert extract_job_cached("jd one", chain, cache).title == "A"
    assert extract_job_cached("jd two", chain, cache).title == "B"


def test_corrupted_cache_is_re_extracted_and_repaired(tmp_path):
    chain, cache = make_chain(), JobCache(tmp_path)
    extract_job_cached("jd", chain, cache)
    for f in tmp_path.glob("*.json"):
        f.write_text("坏了", encoding="utf-8")
    assert extract_job_cached("jd", chain, cache).title == "B"  # 重新抽取
    assert extract_job_cached("jd", chain, cache).title == "B"  # 已被修复，直接命中


def test_prompt_version_is_stable_and_nonempty():
    assert job_prompt_version() == job_prompt_version()
    assert len(job_prompt_version()) > 0
