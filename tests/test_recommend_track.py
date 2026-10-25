import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.cache import JobCache
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.recommend import recommend

RESUME_JSON = json.dumps({"name": "张三", "school": "某大学", "degree": "本科", "skills": ["Python"],
                          "years_of_experience": 0, "projects": ["问答系统"]}, ensure_ascii=False)


class SpyLibrary:
    """只记录 search 被调用时的参数，不返回岗位"""

    def __init__(self):
        self.calls = []

    def search(self, query, k, track=None):
        self.calls.append({"k": k, "track": track})
        return []


def run(tmp_path, **kwargs):
    library = SpyLibrary()
    recommend(
        "简历文字", library, 2,
        resume_chain=build_resume_chain(FakeListChatModel(responses=[RESUME_JSON])),
        job_chain=build_job_chain(FakeListChatModel(responses=["{}"])),
        match_chain=build_match_chain(FakeListChatModel(responses=["{}"])),
        cache=JobCache(tmp_path / "cache"), schools={}, **kwargs,
    )
    return library


def test_the_track_is_passed_on_to_the_library_search(tmp_path):
    assert run(tmp_path, track="数据").calls == [{"k": 2, "track": "数据"}]


def test_without_a_track_the_search_is_not_filtered(tmp_path):
    assert run(tmp_path).calls == [{"k": 2, "track": None}]
