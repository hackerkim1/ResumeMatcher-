from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher import services
from resume_matcher.cache import JobCache
from resume_matcher.library import JobLibrary


def test_build_services_wires_all_the_parts(monkeypatch):
    monkeypatch.setattr(services, "get_llm", lambda: FakeListChatModel(responses=["{}"]))
    s = services.build_services()
    assert hasattr(s.resume_chain, "invoke")
    assert hasattr(s.job_chain, "invoke")
    assert hasattr(s.match_chain, "invoke")
    assert isinstance(s.cache, JobCache)
    assert "985" in s.schools


def test_build_library_syncs_the_jobs_folder(monkeypatch, tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "a.txt").write_text("岗位：测试。必备：Python。", encoding="utf-8")
    monkeypatch.setattr(services, "get_embedding", lambda: DeterministicFakeEmbedding(size=16))
    monkeypatch.setattr(services, "VECTOR_DB_DIR", tmp_path / "db")

    library, stats = services.build_library(jobs)
    assert isinstance(library, JobLibrary)
    assert stats == {"added": 1, "removed": 0, "kept": 0}
    assert library.count() == 1
